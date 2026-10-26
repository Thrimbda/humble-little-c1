#!/usr/bin/env python3
"""Run one supervised Pi round on POSIX; preserve evidence, not task acceptance."""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save_meta(directory, meta):
    tmp = directory / "meta.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(directory / "meta.json")


class Events:
    def __init__(self, output, live, meta):
        self.output, self.live, self.meta = output, live, meta
        self.settled = False
        self.last_stop = None

    def consume(self, line):
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("record is not an object")
            kind = event.get("type")
            if kind == "session":
                self.meta["session_id"] = event.get("id")
            elif kind in ("agent_start", "turn_start", "message_start"):
                self.settled = False
            elif kind == "message_update":
                delta = event.get("assistantMessageEvent", {})
                if delta.get("type") == "text_delta":
                    text = delta["delta"]
                    self.live.write(text)
                    self.live.flush()
                    print(text, end="", flush=True)
            elif kind == "message_end":
                msg = event["message"]
                if msg.get("role") == "assistant":
                    self.settled = False
                    self.last_stop = msg.get("stopReason")
                    self.meta["assistant_messages"].append({
                        key: msg.get(key) for key in
                        ("stopReason", "errorMessage", "provider", "model")
                    })
                    blocks = [b["text"] for b in msg.get("content", []) if b.get("type") == "text"]
                    self.output.write("\n\n".join(blocks) + "\n\n")
                    self.output.flush()
            elif kind == "agent_settled":
                self.settled = event.get("aborted") is False
                self.meta["settled_events"].append(event)
            elif kind == "tool_execution_end" and event.get("isError"):
                self.meta["tool_errors"].append({k: event.get(k) for k in ("toolCallId", "toolName")})
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            self.meta["protocol_errors"].append(str(exc))


def stop_group(proc, grace):
    """Signal only the process group created for this invocation, including children."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        proc.wait()
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        proc.poll()  # Reap leader, so it does not keep the group alive as a zombie.
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait()


def run(args):
    import fcntl  # Deliberately POSIX-only; fail before invoking Pi on other hosts.

    os.umask(0o077)
    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise ValueError("run-dir must be private (chmod 700 after checking ownership)")
    directory = root / args.round
    directory.mkdir(mode=0o700)  # Never overwrite a previous round.
    session = (args.session or root / "session.jsonl").resolve()
    meta = {
        "started_at": now(), "status": "starting", "cwd": str(args.cwd.resolve()),
        "provider": args.provider, "model": args.model, "session": str(session),
        "timeout_seconds": args.timeout_seconds, "memory_limit": None, "host": platform.system(),
        "assistant_messages": [], "settled_events": [], "tool_errors": [],
        "protocol_errors": [], "acceptance": "requires_supervisor_review",
    }
    save_meta(directory, meta)
    proc = None
    proc_cleaned = False
    lock = None
    cancel = []
    previous = {s: signal.signal(s, lambda signum, frame: cancel.append(signum))
                for s in (signal.SIGINT, signal.SIGTERM)}
    started = time.monotonic()
    code = 1
    try:
        prompt = args.prompt.read_bytes()
        prompt.decode("utf-8")
        (directory / "prompt.md").write_bytes(prompt)
        meta["prompt_sha256"] = hashlib.sha256(prompt).hexdigest()
        if not args.cwd.is_dir():
            raise ValueError("cwd is not a directory")
        if not session.parent.is_dir():
            raise ValueError("session parent must already exist")
        lock = open(str(session) + ".lock", "a+", encoding="utf-8")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("session is locked by another runner; do not delete the lock file") from None
        executable = shutil.which(args.pi)
        if not executable:
            raise ValueError("pi executable not found")
        executable = str(Path(executable).resolve())
        help_text = subprocess.run([executable, "--help"], capture_output=True,
                                   text=True, timeout=15, check=True).stdout
        meta["pi_version"] = subprocess.run([executable, "--version"], capture_output=True,
                                           text=True, timeout=15, check=True).stdout.strip()
        flags = ["--no-extensions", "--no-skills", "--no-prompt-templates"]
        required = flags + ["--provider", "--model", "--mode", "--print", "--session",
                            "--no-tools" if args.tools == "none" else "--tools"]
        missing = [flag for flag in required if flag not in help_text]
        if missing:
            raise ValueError("unsupported pi flags: " + ", ".join(missing))
        if "--no-mcp" in help_text:
            flags.append("--no-mcp")
        command = [executable, "--provider", args.provider, "--model", args.model,
                   "--mode", "json", "--print", "--session", str(session)] + flags
        command += ["--no-tools"] if args.tools == "none" else ["--tools", args.tools]
        command += ["--", "@" + str(directory / "prompt.md")]
        meta["command"] = command
        if cancel or (directory / "STOP").exists():
            meta["status"] = "cancelled"
            code = 130
            return code
        with (open(directory / "events.jsonl", "wb", buffering=0) as raw,
              open(directory / "stderr.log", "wb", buffering=0) as err,
              open(directory / "output.md", "w", encoding="utf-8") as output,
              open(directory / "live.txt", "w", encoding="utf-8") as live):
            proc = subprocess.Popen(command, cwd=args.cwd.resolve(), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=err, start_new_session=True)
            meta.update(status="running", pid=proc.pid)
            save_meta(directory, meta)
            parser = Events(output, live, meta)
            buffer = b""
            heartbeat = time.monotonic()
            exited_at = None
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    current = time.monotonic()
                    if cancel or (directory / "STOP").exists():
                        meta["status"], code = "cancelled", 130
                        break
                    if current - started >= args.timeout_seconds:
                        meta["status"], code = "timeout", 124
                        break
                    if current - heartbeat >= 15:
                        print("\n[pi-supervision: running; logs in " + str(directory) + "]",
                              file=sys.stderr, flush=True)
                        heartbeat = current
                    ready = selector.select(timeout=0.2)
                    if ready:
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk:
                            selector.unregister(proc.stdout)
                        else:
                            raw.write(chunk)
                            buffer += chunk
                            while b"\n" in buffer:
                                line, buffer = buffer.split(b"\n", 1)
                                parser.consume(line)
                            if len(buffer) > 64 * 1024 * 1024:
                                meta["protocol_errors"].append("JSONL record exceeds 64 MiB")
                                break
                    rc = proc.poll()
                    if rc is not None:
                        exited_at = exited_at or current
                        if not selector.get_map():
                            break
                        if current - exited_at > 2:
                            meta["protocol_errors"].append("stdout held open after pi exited")
                            break
            # Keep evidence files open while stopping, then drain bytes already in the pipe.
            stop_group(proc, args.grace_seconds)
            proc_cleaned = True
            os.set_blocking(proc.stdout.fileno(), False)
            while True:
                try:
                    chunk = os.read(proc.stdout.fileno(), 65536)
                except BlockingIOError:
                    break
                if not chunk:
                    break
                raw.write(chunk)
                buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                parser.consume(line)
            if buffer:
                meta["protocol_errors"].append("unterminated JSONL record")
            if meta["status"] == "running":
                complete = proc.poll() == 0 and parser.settled and parser.last_stop == "stop"
                complete = complete and not meta["protocol_errors"]
                meta["status"] = "execution_complete" if complete else "incomplete"
                code = 0 if complete else 1
            meta["last_stop_reason"] = parser.last_stop
            meta["settled"] = parser.settled
    except Exception as exc:
        meta.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        print(meta["error"], file=sys.stderr, flush=True)
    finally:
        try:
            if proc is not None:
                if not proc_cleaned:
                    stop_group(proc, args.grace_seconds)
                meta["process_returncode"] = proc.returncode
                proc.stdout.close()
        finally:
            meta.update(finished_at=now(), elapsed_seconds=round(time.monotonic() - started, 3),
                        runner_returncode=code, signals=cancel)
            save_meta(directory, meta)
            if lock is not None:
                lock.close()  # Keep lock inode in place; flock itself is released.
            for signum, handler in previous.items():
                signal.signal(signum, handler)
    print("\n[pi-supervision: " + meta["status"] + "; " + str(directory) + "]", flush=True)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--round", required=True, help="New directory name, e.g. 01 or 03b")
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--session", type=Path, help="Explicit session path; defaults to run-dir/session.jsonl")
    parser.add_argument("--pi", default="pi", help="Pi executable name or absolute path")
    parser.add_argument("--tools", default="read,bash,edit,write", help="Comma-separated tools, or none")
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument("--grace-seconds", type=float, default=2)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("runner requires POSIX process groups; use a verified WSL/native adapter")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.round):
        parser.error("round must be a simple directory name")
    if args.session is not None and not args.session.is_absolute():
        parser.error("--session must be an absolute path")
    if (not math.isfinite(args.timeout_seconds) or not math.isfinite(args.grace_seconds)
            or args.timeout_seconds <= 0 or args.grace_seconds < 0):
        parser.error("timeout must be positive and grace must be nonnegative")
    try:
        return run(args)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
