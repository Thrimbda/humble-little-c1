"""Deterministic process/stream contract tests; no model credentials required."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

RUNNER = Path(__file__).with_name("run_round.py")
FAKE = r'''
import json, os, pathlib, signal, subprocess, sys, time
if "--help" in sys.argv:
    print("--provider --model --mode --print --session --no-extensions --no-skills --no-prompt-templates --no-mcp --tools --no-tools")
    sys.exit(0)
if "--version" in sys.argv:
    print("fake 1.3.0")
    sys.exit(0)
def emit(event):
    print(json.dumps(event, ensure_ascii=False), flush=True)
def message(text, reason="stop"):
    emit({"type":"message_end", "message":{"role":"assistant", "content":[{"type":"text", "text":text}], "stopReason":reason, "provider":"test", "model":"fake"}})
mode = pathlib.Path(sys.argv[-1][1:]).read_text()
session = pathlib.Path(sys.argv[sys.argv.index("--session") + 1])
count = int(session.read_text()) + 1 if session.exists() else 1
session.write_text(str(count))
emit({"type":"session", "id":"fixture-session"})
emit({"type":"agent_start"})
print("fixture diagnostic", file=sys.stderr, flush=True)
emit({"type":"message_update", "assistantMessageEvent":{"type":"text_delta", "delta":"partial\u2028text"}})
if mode in ("hang", "child", "hold-pipe"):
    if mode in ("child", "hold-pipe"):
        child = subprocess.Popen([sys.executable, "-c", "import pathlib,time; p=pathlib.Path('child-alive');\nwhile True: p.write_text(str(time.monotonic())); time.sleep(.05)"])
        pathlib.Path("child.pid").write_text(str(child.pid))
    if mode != "hold-pipe":
        time.sleep(30)
if mode == "invalid":
    print("not JSON", flush=True)
elif mode == "truncated":
    sys.stdout.write('{"type":')
elif mode == "error":
    message("provider failed", "error")
elif mode == "tool-only":
    message("using tool", "toolUse")
elif mode != "empty":
    if mode == "recovery":
        message("transient failure", "error")
        emit({"type":"agent_end", "willRetry":True})
        emit({"type":"agent_start"})
    if mode == "multi":
        message("checking inputs", "toolUse")
        emit({"type":"tool_execution_end", "toolCallId":"t1", "toolName":"bash", "isError":True})
    message("final\u2028text " + str(count))
emit({"type":"agent_end"})
if mode != "no-settled":
    emit({"type":"agent_settled", "aborted":mode == "aborted"})
if mode == "nonzero":
    sys.exit(7)
'''


@unittest.skipUnless(os.name == "posix", "POSIX runner")
class RoundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = self.root / "logs"
        self.fake = self.root / "fake pi"
        self.fake.write_text("#!" + sys.executable + "\n" + FAKE)
        self.fake.chmod(0o700)

    def command(self, mode="success", round_name="01", extra=()):
        prompt = self.root / (round_name + " prompt $(touch SHOULD_NOT_EXIST).md")
        prompt.write_text(mode)
        return [sys.executable, str(RUNNER), "--cwd", str(self.root), "--run-dir", str(self.logs),
                "--round", round_name, "--prompt", str(prompt), "--provider", "test",
                "--model", "fake", "--pi", str(self.fake), "--timeout-seconds", "5",
                "--grace-seconds", ".1", *extra]

    def invoke(self, mode="success", round_name="01", extra=()):
        return subprocess.run(self.command(mode, round_name, extra), capture_output=True, timeout=10)

    def meta(self, round_name="01"):
        return json.loads((self.logs / round_name / "meta.json").read_text())

    def wait_file(self, path, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists() and path.stat().st_size:
                return
            time.sleep(.03)
        self.fail("missing live file: " + str(path))

    def start(self, mode="hang", extra=()):
        # Output to disk to avoid hiding a runner pipe deadlock in test code.
        stream = open(self.root / "runner.log", "wb")
        self.addCleanup(stream.close)
        proc = subprocess.Popen(self.command(mode, extra=extra), stdout=stream, stderr=stream)
        self.addCleanup(lambda: proc.kill() if proc.poll() is None else None)
        self.wait_file(self.logs / "01" / "live.txt")
        return proc

    def test_literal_prompt_unicode_and_authoritative_output(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        directory = self.logs / "01"
        self.assertEqual((directory / "output.md").read_text(), "final\u2028text 1\n\n")
        self.assertEqual((directory / "live.txt").read_text(), "partial\u2028text")
        self.assertIn(b"partial", result.stdout)
        self.assertEqual((directory / "stderr.log").read_text(), "fixture diagnostic\n")
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())
        self.assertEqual(directory.stat().st_mode & 0o077, 0)
        self.assertEqual(self.meta()["status"], "execution_complete")

    def test_multi_turn_records_all_text_and_tool_errors(self):
        self.assertEqual(self.invoke("multi").returncode, 0)
        text = (self.logs / "01" / "output.md").read_text()
        self.assertEqual(text, "checking inputs\n\nfinal\u2028text 1\n\n")
        self.assertEqual(len(self.meta()["tool_errors"]), 1)

    def test_intermediate_error_can_recover(self):
        self.assertEqual(self.invoke("recovery").returncode, 0)
        self.assertEqual(self.meta()["assistant_messages"][0]["stopReason"], "error")
        self.assertEqual(self.meta()["last_stop_reason"], "stop")

    def test_false_success_states_fail(self):
        for mode in ("error", "tool-only", "empty", "invalid", "truncated", "no-settled", "aborted", "nonzero"):
            with self.subTest(mode=mode):
                self.assertEqual(self.invoke(mode, mode).returncode, 1)
                self.assertEqual(self.meta(mode)["status"], "incomplete")

    def test_fixed_session_and_round_collision(self):
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(self.invoke(round_name="02").returncode, 0)
        self.assertIn("text 2", (self.logs / "02" / "output.md").read_text())
        before = (self.logs / "01" / "meta.json").read_bytes()
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertEqual((self.logs / "01" / "meta.json").read_bytes(), before)

    def test_session_lock_and_stop_keeps_partial_text(self):
        proc = self.start()
        self.assertIsNone(proc.poll())
        second = self.invoke(round_name="02")
        self.assertEqual(second.returncode, 1)
        self.assertIn("locked", self.meta("02")["error"])
        (self.logs / "01" / "STOP").touch()
        self.assertEqual(proc.wait(timeout=5), 130)
        self.assertEqual(self.meta()["status"], "cancelled")
        self.assertEqual((self.logs / "01" / "live.txt").read_text(), "partial\u2028text")
        self.assertEqual(self.invoke(round_name="03").returncode, 0)

    def test_timeout_kills_own_child_not_unrelated_process(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (unrelated.terminate(), unrelated.wait()))
        proc = self.start("child", ("--timeout-seconds", "1"))
        self.wait_file(self.root / "child-alive")
        self.assertEqual(proc.wait(timeout=5), 124)
        self.assertEqual(self.meta()["status"], "timeout")
        heartbeat = (self.root / "child-alive").read_bytes()
        time.sleep(.2)
        self.assertEqual((self.root / "child-alive").read_bytes(), heartbeat)
        self.assertIsNone(unrelated.poll())

    def test_signal_is_recorded(self):
        proc = self.start()
        proc.send_signal(signal.SIGINT)
        self.assertEqual(proc.wait(timeout=5), 130)
        self.assertEqual(self.meta()["status"], "cancelled")

    def test_pipe_held_by_descendant_is_incomplete_and_cleaned(self):
        proc = self.start("hold-pipe")
        self.assertEqual(proc.wait(timeout=6), 1)
        self.assertIn("stdout held open", " ".join(self.meta()["protocol_errors"]))
        heartbeat = (self.root / "child-alive").read_bytes()
        time.sleep(.2)
        self.assertEqual((self.root / "child-alive").read_bytes(), heartbeat)

    def test_spawn_failure_preserves_prompt_and_metadata(self):
        result = self.invoke(extra=("--pi", str(self.root / "missing")))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.meta()["status"], "failed")
        self.assertIn("finished_at", self.meta())
        self.assertEqual((self.logs / "01" / "prompt.md").read_text(), "success")

    def test_invalid_limits_and_ambiguous_session_rejected_before_launch(self):
        for extra in (("--timeout-seconds", "nan"), ("--grace-seconds", "inf"),
                      ("--session", "relative.jsonl")):
            with self.subTest(extra=extra):
                self.assertEqual(self.invoke(extra=extra).returncode, 2)
                self.assertFalse(self.logs.exists())


if __name__ == "__main__":
    unittest.main()
