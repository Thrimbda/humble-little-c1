#!/usr/bin/env python3
"""Persistent Pi RPC bridge: JSONL controls on stdin, live JSONL events on stdout."""

import argparse
from contextlib import ExitStack
import fcntl
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
import uuid

from run_round import Events, now, save_meta, stop_group

MAX_RECORD = 4 * 1024 * 1024


def emit(kind, **fields):
    print(json.dumps(dict(type=kind, **fields), ensure_ascii=False), flush=True)


class Bridge:
    def __init__(self, args, stack):
        self.args, self.stack = args, stack
        self.root = args.run_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_mode & 0o077:
            raise ValueError("run-dir must be private")
        self.session = (args.session or self.root / "session.jsonl").resolve()
        lock = stack.enter_context(open(str(self.session) + ".lock", "a+"))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.directory = self.root / ("rpc-" + uuid.uuid4().hex[:12])
        self.directory.mkdir(mode=0o700)
        self.meta = dict(status="starting", started_at=now(), session=str(self.session),
                         cwd=str(args.cwd.resolve()), provider=args.provider, model=args.model,
                         rounds=[], memory_limit=None, timeout_seconds=args.timeout_seconds,
                         idle_timeout_seconds=args.idle_timeout_seconds, grace_seconds=args.grace_seconds)
        save_meta(self.directory, self.meta)
        self.files = {name: stack.enter_context(open(self.directory / name, "wb", buffering=0))
                      for name in ("controls.jsonl", "inputs.jsonl", "events.jsonl", "stderr.log")}
        self.proc = None
        self.group_cleaned = False
        self.active = None
        self.pending = {}
        self.ids = set()
        self.buffer = {"pi": b"", "control": b""}
        self.outgoing = b""
        self.closing = False
        self.close_deadline = None
        self.cancel_signal = None
        self.last_activity = time.monotonic()
        self.selector = stack.enter_context(selectors.SelectSelector())

    def launch(self):
        executable = shutil.which(self.args.pi)
        if not executable:
            raise ValueError("pi executable not found")
        executable = str(Path(executable).resolve())
        def probe(flag):
            return subprocess.run([executable, flag], stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=15, check=True).stdout
        help_text = probe("--help")
        self.meta["pi_version"] = probe("--version").strip()
        flags = ["--no-extensions", "--no-skills", "--no-prompt-templates"]
        required = flags + ["--provider", "--model", "--session", "--mode",
                            "--no-tools" if self.args.tools == "none" else "--tools"]
        if any(flag not in help_text for flag in required):
            raise ValueError("installed pi lacks required flags; inspect --help")
        if "--no-mcp" in help_text:
            flags.append("--no-mcp")
        command = [executable, "--mode", "rpc", "--provider", self.args.provider,
                   "--model", self.args.model, "--session", str(self.session)] + flags
        command += ["--no-tools"] if self.args.tools == "none" else ["--tools", self.args.tools]
        self.proc = subprocess.Popen(command, cwd=self.args.cwd.resolve(), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     start_new_session=True)
        self.meta.update(status="running", command=command, pid=self.proc.pid)
        save_meta(self.directory, self.meta)
        for stream, label in ((self.proc.stdout, "pi"), (self.proc.stderr, "stderr"),
                              (sys.stdin.buffer, "control")):
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, label)
        os.set_blocking(self.proc.stdin.fileno(), False)
        emit("ready", pid=self.proc.pid, session=str(self.session), records=str(self.directory))

    def send(self, command):
        raw = json.dumps(command, ensure_ascii=False).encode() + b"\n"
        if len(self.outgoing) + len(raw) > MAX_RECORD:
            raise ValueError("pending stdin data exceeds limit")
        self.files["inputs.jsonl"].write(raw)
        if self.active:
            self.active["files"]["inputs.jsonl"].write(raw)
        self.pending[command["id"]] = command["type"]
        self.outgoing += raw
        try:
            self.selector.get_key(self.proc.stdin)
        except KeyError:
            self.selector.register(self.proc.stdin, selectors.EVENT_WRITE, "write")

    def begin_round(self, command, message):
        name = command.get("round", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise ValueError("round must be a simple new directory name")
        directory = self.root / name
        directory.mkdir(mode=0o700)
        resources = ExitStack()
        self.stack.callback(resources.close)
        files = {n: resources.enter_context(open(directory / n, "wb", buffering=0))
                 for n in ("events.jsonl", "inputs.jsonl", "stderr.log")}
        output = resources.enter_context(open(directory / "output.md", "w", encoding="utf-8"))
        live = resources.enter_context(open(directory / "live.txt", "w", encoding="utf-8"))
        (directory / "prompt.md").write_text(message, encoding="utf-8")
        meta = dict(status="running", started_at=now(), round=name, pid=self.proc.pid,
                    session=str(self.session), provider=self.args.provider, model=self.args.model,
                    cwd=str(self.args.cwd.resolve()), assistant_messages=[], settled_events=[],
                    protocol_errors=[], tool_errors=[], command_errors=[],
                    acceptance="requires_supervisor_review")
        self.active = dict(directory=directory, resources=resources, files=files, meta=meta,
                           parser=Events(output, live, meta, display=False), settled=False,
                           accepted=False, handled=False, stop=None, abort_ack=False,
                           started=time.monotonic(), abort_deadline=None)
        save_meta(directory, meta)

    def control(self, command):
        ident = command.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", ident):
            raise ValueError("id must be 1-80 letters, digits, underscores or hyphens")
        if ident in self.ids:
            raise ValueError("duplicate control id")
        self.ids.add(ident)
        kind = command.get("type")
        if kind == "shutdown":
            self.closing = True
            if self.active:
                self.abort("cancelled")
            emit("command_sent", id=ident, command=kind)
            return
        if self.closing:
            raise ValueError("session is shutting down")
        if kind == "abort":
            if not self.active:
                raise ValueError("no active round")
            self.abort("cancelled")
            emit("command_sent", id=ident, command=kind)
            return
        if kind not in ("prompt", "steer", "follow_up"):
            raise ValueError("supported controls: prompt, steer, follow_up, abort, shutdown")
        if kind == "prompt" and self.active:
            raise ValueError("wait for round_finished before starting another round")
        if kind != "prompt" and (not self.active or not self.active["accepted"] or
                                  self.active["stop"] or self.active["settled"]):
            raise ValueError("steer/follow_up requires an accepted, still-running round")
        if ("message" in command) == ("prompt_file" in command):
            raise ValueError("provide exactly one of message or prompt_file")
        if "prompt_file" in command:
            path = Path(command["prompt_file"])
            if not path.is_absolute() or not path.is_file() or path.stat().st_size > MAX_RECORD // 2:
                raise ValueError("prompt_file must be an absolute regular file, at most 2 MiB")
            message = path.read_text(encoding="utf-8")
        else:
            message = command["message"]
        if not isinstance(message, str) or not message.strip() or len(message.encode()) > MAX_RECORD // 2:
            raise ValueError("message must be nonempty text, at most 2 MiB")
        outgoing = dict(id=ident, type=kind, message=message)
        if len(json.dumps(outgoing, ensure_ascii=False).encode()) + 1 + len(self.outgoing) > MAX_RECORD:
            raise ValueError("pending stdin data exceeds limit")
        if kind == "prompt":
            self.begin_round(command, message)
        self.send(outgoing)
        emit("command_sent", id=ident, command=kind, round=self.active["meta"]["round"])

    def abort(self, reason):
        if self.active["stop"]:
            return
        self.active["stop"] = reason
        self.active["abort_deadline"] = time.monotonic() + self.args.grace_seconds
        # Pi abort alone may continue queued follow-ups. Await clearing first.
        self.send(dict(id="internal:clear:" + uuid.uuid4().hex, type="clear_queue"))

    def pi_event(self, event):
        emit("pi_event", event=event)
        a = self.active
        if not a:
            if event.get("type") == "agent_start":
                raise RuntimeError("unexpected work while no round is active")
            return
        kind = event.get("type")
        if kind in ("agent_start", "turn_start", "message_start", "message_end"):
            a["settled"] = False
        if kind == "agent_settled":
            a["settled"] = True
        if kind == "response":
            expected = self.pending.pop(event.get("id"), None)
            if not expected or event.get("command") != expected:
                raise RuntimeError("uncorrelated or mismatched RPC response")
            if event.get("success") is not True:
                a["meta"]["command_errors"].append(event)
                if expected in ("clear_queue", "abort"):
                    raise RuntimeError("Pi rejected cancellation")
                if expected == "prompt" and not a["stop"]:
                    self.finish("rejected")
                    return
            elif expected == "prompt":
                disposition = event.get("data", {}).get("disposition")
                if disposition == "handled":
                    a["handled"] = True
                elif disposition == "started":
                    a["accepted"] = True
                else:
                    raise RuntimeError("idle prompt was not started or handled")
            elif expected == "clear_queue":
                self.send(dict(id="internal:abort:" + uuid.uuid4().hex, type="abort"))
            elif expected == "abort":
                a["abort_ack"] = True
            elif expected in ("steer", "follow_up"):
                disposition = event.get("data", {}).get("disposition")
                if disposition not in ("queued", "handled"):
                    raise RuntimeError("unknown queued command disposition")
                if disposition == "queued" and a["settled"]:
                    a["meta"]["command_errors"].append({"error": "queue accepted after settlement"})
                    self.abort("incomplete")
        if a["meta"]["protocol_errors"]:
            raise RuntimeError("malformed Pi event")
        if self.pending:
            return
        if a["stop"] and a["abort_ack"]:
            # abort response itself guarantees Pi is idle, even if no run started.
            self.finish(a["stop"])
        elif a["handled"]:
            self.finish("handled")
        elif a["accepted"] and a["settled"]:
            parser = a["parser"]
            good = parser.settled and parser.last_stop == "stop" and not a["meta"]["command_errors"]
            self.finish("execution_complete" if good else "incomplete")

    def finish(self, status, error=None):
        a = self.active
        if not a:
            return
        a["meta"].update(status=status, finished_at=now(), last_stop_reason=a["parser"].last_stop,
                         settled=a["parser"].settled)
        if error:
            a["meta"]["error"] = error
        save_meta(a["directory"], a["meta"])
        self.meta["rounds"].append(dict(round=a["meta"]["round"], status=status))
        save_meta(self.directory, self.meta)
        a["resources"].close()
        self.active = None
        self.last_activity = time.monotonic()
        emit("round_finished", round=a["meta"]["round"], status=status,
             records=str(a["directory"]), pid=self.proc.pid)

    def read(self, stream, label):
        chunk = os.read(stream.fileno(), 65536)
        if not chunk:
            self.selector.unregister(stream)
            if label in self.buffer and self.buffer[label]:
                raise RuntimeError("unterminated " + label + " JSONL record")
            if label == "control":
                self.closing = True
                if self.active:
                    self.abort("cancelled")
            elif label == "pi" and not self.closing:
                raise RuntimeError("unexpected Pi stdout EOF")
            return
        if label == "stderr":
            self.files["stderr.log"].write(chunk)
            if self.active:
                self.active["files"]["stderr.log"].write(chunk)
            emit("pi_stderr", text=chunk.decode("utf-8", errors="replace"))
            return
        self.files["events.jsonl" if label == "pi" else "controls.jsonl"].write(chunk)
        self.buffer[label] += chunk
        while b"\n" in self.buffer[label]:
            line, self.buffer[label] = self.buffer[label].split(b"\n", 1)
            if len(line) > MAX_RECORD:
                raise RuntimeError(label + " record exceeds limit")
            if label == "pi" and self.active:
                self.active["files"]["events.jsonl"].write(line + b"\n")
            event = None
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("record must be an object")
                if label == "control":
                    self.control(event)
                else:
                    if self.active:
                        self.active["parser"].consume(line)
                    self.pi_event(event)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                if label != "control":
                    raise
                emit("command_error", id=event.get("id") if isinstance(event, dict) else None,
                     error=str(exc))
        if len(self.buffer[label]) > MAX_RECORD:
            raise RuntimeError(label + " record exceeds limit")

    def loop(self):
        self.launch()
        while True:
            current = time.monotonic()
            if self.cancel_signal:
                self.closing = True
                if self.active:
                    self.abort("cancelled")
            if self.active:
                a = self.active
                if current - a["started"] >= self.args.timeout_seconds:
                    self.abort("timeout")
                if a["abort_deadline"] and current >= a["abort_deadline"]:
                    raise TimeoutError("Pi did not acknowledge cancellation in time")
            elif current - self.last_activity >= self.args.idle_timeout_seconds:
                self.closing = True
            if self.closing and not self.active and self.close_deadline is None:
                self.proc.stdin.close()
                self.close_deadline = current + self.args.grace_seconds
            if self.close_deadline is not None and current >= self.close_deadline:
                raise TimeoutError("Pi did not exit after stdin EOF")
            # This waits for ready pipe descriptors, not periodic log-file reads.
            for key, _ in self.selector.select(timeout=0.2):
                if key.data == "write":
                    try:
                        count = os.write(self.proc.stdin.fileno(), self.outgoing)
                    except BlockingIOError:
                        continue
                    self.outgoing = self.outgoing[count:]
                    if not self.outgoing:
                        self.selector.unregister(self.proc.stdin)
                else:
                    self.read(key.fileobj, key.data)
            rc = self.proc.poll()
            pipes = any(k.data in ("pi", "stderr") for k in self.selector.get_map().values())
            if rc is not None:
                if not self.closing or self.active or rc != 0:
                    raise RuntimeError("unexpected Pi exit: " + str(rc))
                if not self.group_cleaned:
                    # Children may keep inherited pipes open after Pi exits normally.
                    stop_group(self.proc, min(self.args.grace_seconds, 2))
                    self.group_cleaned = True
                    self.close_deadline = time.monotonic() + self.args.grace_seconds
                if not pipes:
                    break
        self.meta["status"] = "closed"
        return 0

    def close(self, error=None):
        if error:
            self.meta.update(status="failed", error=str(error))
        if self.active and self.buffer["pi"]:
            self.active["files"]["events.jsonl"].write(self.buffer["pi"])
            self.buffer["pi"] = b""
        if self.proc:
            if not self.group_cleaned:
                stop_group(self.proc, min(self.args.grace_seconds, 2))
                self.group_cleaned = True
            # Drain remaining pipe bytes after termination so partial output survives.
            for stream, label in ((self.proc.stdout, "pi"), (self.proc.stderr, "stderr")):
                try:
                    while True:
                        chunk = os.read(stream.fileno(), 65536)
                        if not chunk:
                            break
                        name = "events.jsonl" if label == "pi" else "stderr.log"
                        self.files[name].write(chunk)
                        if self.active:
                            self.active["files"][name].write(chunk)
                except BlockingIOError:
                    pass
                stream.close()
            if not self.proc.stdin.closed:
                self.proc.stdin.close()
            self.meta["process_returncode"] = self.proc.returncode
        if self.active:
            self.finish(self.active["stop"] or "failed", str(error or "session closed"))
        self.meta["finished_at"] = now()
        save_meta(self.directory, self.meta)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("cwd", "run-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--session", type=Path)
    p.add_argument("--provider", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--pi", default="pi")
    p.add_argument("--tools", default="read,bash,edit,write")
    p.add_argument("--timeout-seconds", type=float, default=1800)
    p.add_argument("--idle-timeout-seconds", type=float, default=1800)
    p.add_argument("--grace-seconds", type=float, default=10)
    args = p.parse_args()
    if os.name != "posix" or not args.cwd.is_dir():
        p.error("requires POSIX and an existing cwd")
    if args.session and not args.session.is_absolute():
        p.error("session must be absolute")
    if any(not math.isfinite(n) or n <= 0 for n in
           (args.timeout_seconds, args.idle_timeout_seconds, args.grace_seconds)):
        p.error("timeouts must be finite and positive")
    os.umask(0o077)
    bridge = None
    previous = {}
    with ExitStack() as stack:
        try:
            bridge = Bridge(args, stack)
            def cancel(signum, frame):
                bridge.cancel_signal = signum
            previous = {s: signal.signal(s, cancel) for s in (signal.SIGINT, signal.SIGTERM)}
            code = bridge.loop()
            bridge.close()
            emit("session_closed", records=str(bridge.directory))
            return code
        except Exception as exc:
            if bridge:
                bridge.close(exc)
            emit("session_error", error=f"{type(exc).__name__}: {exc}")
            return 1
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


if __name__ == "__main__":
    sys.exit(main())
