"""Exercise the bridge through real pipes and a deterministic fake Pi process."""

import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

RUNNER = Path(__file__).with_name("run_session.py")
FAKE = r'''
import json, os, pathlib, subprocess, sys
if "--help" in sys.argv:
 print("--provider --model --mode --session --no-extensions --no-skills --no-prompt-templates --no-mcp --tools --no-tools"); sys.exit()
if "--version" in sys.argv: print("fake RPC 1.3.0"); sys.exit()
assert sys.argv[sys.argv.index("--mode")+1] == "rpc"
assert not any(a.startswith("@") for a in sys.argv[1:])
memory=""; active=""; queued=[]
def emit(e): print(json.dumps(e,ensure_ascii=False),flush=True)
def reply(c,success=True,disposition=None):
 e=dict(type="response",id=c["id"],command=c["type"],success=success)
 if disposition: e["data"]={"disposition":disposition}
 emit(e)
def message(text,stop="stop"):
 emit({"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":text}],"stopReason":stop,"provider":"test","model":"fake"}})
def done(text,stop="stop",aborted=False):
 message(text,stop); emit({"type":"agent_end"}); emit({"type":"agent_settled","aborted":aborted})
for line in sys.stdin.buffer:
 c=json.loads(line)
 with open("received.jsonl","a") as f: f.write(json.dumps(c)+"\n")
 kind=c["type"]
 if kind=="prompt":
  active=c["message"]
  if active=="reject": reply(c,False); continue
  if active=="handled": reply(c,disposition="handled"); continue
  if active!="ack-last": reply(c,disposition="started")
  emit({"type":"agent_start"})
  emit({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"live\u2028text"}})
  print("round diagnostic",file=sys.stderr,flush=True)
  if active in ("wait","hang","ignore-abort","queue-race","child"):
   if active=="child":
    subprocess.Popen([sys.executable,"-c","import pathlib,time; p=pathlib.Path('child-alive');\nwhile True: p.write_text(str(time.monotonic())); time.sleep(.03)"])
   continue
  if active=="exit": sys.exit(7)
  if active=="truncated": sys.stdout.write('{"type":'); sys.stdout.flush(); sys.exit()
  if active=="invalid": print("bad json",flush=True); continue
  if active=="no-settled": message("not settled"); continue
  if active=="error": done("provider failed","error"); continue
  if active=="recovery": message("retry","error"); emit({"type":"agent_end","willRetry":True}); emit({"type":"agent_start"})
  if active.startswith("remember "): memory=active[len("remember "):]
  done(memory if active=="recall" else "final\u2028text")
  if active=="ack-last": reply(c,disposition="started")
 elif kind in ("steer","follow_up"):
  if active=="queue-race": done("old answer")
  reply(c,disposition="queued"); queued.append(c["message"])
  if active=="wait":
   done(c["message"]); queued=[]
 elif kind=="clear_queue":
  if active=="ignore-abort": continue
  queued=[]; reply(c)
 elif kind=="abort":
  assert not queued,"abort without clear_queue would run stale work"
  done("cancelled","aborted",True); reply(c)
'''


@unittest.skipUnless(os.name == "posix", "POSIX bridge")
class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = self.root / "fake pi"
        self.fake.write_text("#!" + sys.executable + "\n" + FAKE)
        self.fake.chmod(0o700)
        self.logs = self.root / "records"
        self.sequence = 0

    def start(self, extra=()):
        self.err = open(self.root / ("stderr-" + str(time.monotonic())), "wb")
        self.addCleanup(self.err.close)
        self.p = subprocess.Popen([sys.executable,str(RUNNER),"--cwd",str(self.root),
            "--run-dir",str(self.logs),"--pi",str(self.fake),"--provider","test","--model","fake",
            "--timeout-seconds","3","--grace-seconds",".5",*extra],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err)
        self.addCleanup(self.cleanup_process, self.p)
        self.q = queue.Queue()
        q, stream = self.q, self.p.stdout
        def read():
            for line in stream:
                q.put(json.loads(line))
            q.put(None)
        threading.Thread(target=read,daemon=True).start()
        return self.wait("ready")

    @staticmethod
    def cleanup_process(p):
        if p.poll() is None:
            p.terminate()
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        p.stdin.close(); p.stdout.close()

    def wait(self, kind, predicate=lambda e: True, timeout=6):
        deadline = time.monotonic()+timeout
        while True:
            event = self.q.get(timeout=max(.01,deadline-time.monotonic()))
            self.assertIsNotNone(event, "unexpected bridge EOF")
            if event["type"]==kind and predicate(event): return event

    def send(self, kind, **fields):
        self.sequence += 1
        command=dict(id=f"req-{self.sequence}",type=kind,**fields)
        self.p.stdin.write(json.dumps(command,ensure_ascii=False).encode()+b"\n")
        self.p.stdin.flush()
        return command

    def prompt(self, message, name="01"):
        return self.send("prompt",round=name,message=message)

    def live(self):
        self.wait("pi_event", lambda e:e["event"]["type"]=="message_update")

    def finish(self):
        self.send("shutdown")
        self.wait("session_closed")
        self.assertEqual(self.p.wait(timeout=3),0)

    def meta(self, name="01"):
        return json.loads((self.logs/name/"meta.json").read_text())

    def test_same_process_multiple_rounds_streaming_and_literal_file(self):
        ready=self.start()
        prompt=self.root/'prompt $(touch BAD).md'
        prompt.write_text("remember token\u2028literal")
        self.send("prompt",round="01",prompt_file=str(prompt))
        first=self.wait("round_finished")
        self.assertEqual(first["status"],"execution_complete")
        self.prompt("recall","02")
        second=self.wait("round_finished")
        self.assertEqual(first["pid"],second["pid"])
        self.assertEqual(second["pid"],ready["pid"])
        self.assertEqual((self.logs/'02/output.md').read_text().strip(),"token\u2028literal")
        self.assertEqual((self.logs/'01/live.txt').read_text(),"live\u2028text")
        self.assertFalse((self.root/'BAD').exists())
        self.assertEqual(self.logs.stat().st_mode & 0o077,0)
        self.finish()

    def test_steer_and_follow_up_are_streamed_and_recorded(self):
        self.start()
        for n,kind in enumerate(("steer","follow_up"),1):
            name=str(n)
            self.prompt("wait",name); self.live()
            self.assertIsNone(self.p.poll())
            self.send(kind,message="corrected goal")
            self.assertEqual(self.wait("round_finished")["status"],"execution_complete")
            commands=[json.loads(s) for s in (self.logs/name/'inputs.jsonl').read_bytes().split(b'\n') if s]
            self.assertEqual([c['type'] for c in commands],["prompt",kind])
            self.assertIn("corrected goal",(self.logs/name/'output.md').read_text())
        self.finish()

    def test_fast_events_before_prompt_ack_and_recovered_error(self):
        self.start()
        for name in ("ack-last","recovery"):
            self.prompt(name,name)
            self.assertEqual(self.wait("round_finished")["status"],"execution_complete")
        self.assertEqual(self.meta("recovery")["assistant_messages"][0]["stopReason"],"error")
        self.finish()

    def test_rejected_handled_and_final_error_are_not_success(self):
        self.start()
        for mode,status in (("reject","rejected"),("handled","handled"),("error","incomplete")):
            self.prompt(mode,mode)
            self.assertEqual(self.wait("round_finished")["status"],status)
        self.prompt("success","next")
        self.assertEqual(self.wait("round_finished")["status"],"execution_complete")
        self.finish()

    def test_clear_queue_before_abort_and_resume_same_process(self):
        self.start(); self.prompt("hang"); self.live()
        self.send("follow_up",message="must not leak")
        self.wait("pi_event",lambda e:e['event'].get('command')=='follow_up')
        self.send("abort")
        first=self.wait("round_finished")
        self.assertEqual(first["status"],"cancelled")
        commands=[json.loads(s) for s in (self.root/'received.jsonl').read_text().splitlines()]
        self.assertEqual([c['type'] for c in commands][-2:],["clear_queue","abort"])
        self.prompt("success","02")
        self.assertEqual(self.wait("round_finished")["pid"],first["pid"])
        self.finish()

    def test_queue_settlement_race_is_not_false_success(self):
        self.start(); self.prompt("queue-race"); self.live()
        self.send("follow_up",message="late")
        self.assertEqual(self.wait("round_finished")["status"],"incomplete")
        self.assertIn("queue accepted after settlement",str(self.meta()["command_errors"]))
        self.finish()

    def test_eof_and_signal_abort_active_work(self):
        for mode in ("eof","signal"):
            with self.subTest(mode=mode):
                self.logs=self.root/mode
                self.start(); self.prompt("hang"); self.live()
                if mode=="eof": self.p.stdin.close()
                else: self.p.send_signal(signal.SIGINT)
                self.assertEqual(self.wait("round_finished")["status"],"cancelled")
                self.wait("session_closed")
                self.assertEqual(self.p.wait(timeout=3),0)

    def test_missing_settlement_times_out_and_abort_can_recover(self):
        self.start(("--timeout-seconds",".4")); self.prompt("no-settled")
        self.assertEqual(self.wait("round_finished")["status"],"timeout")
        self.finish()

    def test_unresponsive_abort_forces_owned_group_only(self):
        unrelated=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])
        self.addCleanup(lambda:(unrelated.terminate(),unrelated.wait()))
        self.start(("--timeout-seconds",".3")); self.prompt("ignore-abort"); self.live()
        self.wait("session_error")
        self.assertEqual(self.p.wait(timeout=3),1)
        self.assertEqual(self.meta()["status"],"timeout")
        self.assertIsNone(unrelated.poll())

    def test_bad_stream_and_unexpected_exit_fail_with_evidence(self):
        for mode in ("invalid","truncated","exit"):
            with self.subTest(mode=mode):
                self.logs=self.root/mode
                self.start(); self.prompt(mode)
                self.wait("session_error")
                self.assertEqual(self.p.wait(timeout=3),1)
                self.assertEqual(self.meta()["status"],"failed")
                self.assertTrue((self.logs/'01/events.jsonl').stat().st_size)
                if mode=="truncated":
                    self.assertTrue((self.logs/'01/events.jsonl').read_bytes().endswith(b'{"type":'))

    def test_large_prompt_pipe_backpressure(self):
        self.start()
        prompt=self.root/'large.md'
        prompt.write_text("remember " + "x"*200000)
        self.send("prompt",round="01",prompt_file=str(prompt))
        self.assertEqual(self.wait("round_finished")["status"],"execution_complete")
        received=json.loads((self.root/'received.jsonl').read_text().splitlines()[0])
        self.assertEqual(len(received['message']),200009)
        self.finish()

    def test_child_is_cleaned_when_session_closes(self):
        self.start(); self.prompt("child"); self.live()
        heartbeat=self.root/'child-alive'
        deadline=time.monotonic()+3
        while not heartbeat.exists() and time.monotonic()<deadline: time.sleep(.02)
        self.assertTrue(heartbeat.exists())
        self.finish()
        value=heartbeat.read_bytes(); time.sleep(.1)
        self.assertEqual(heartbeat.read_bytes(),value)

    def test_control_errors_and_round_collision_leave_session_usable(self):
        self.start()
        for command in ({"id":"bad","type":"bogus"},{"id":"x","type":"prompt","round":"../escape","message":"x"}):
            self.p.stdin.write(json.dumps(command).encode()+b'\n'); self.p.stdin.flush()
            self.wait("command_error")
        self.prompt("success")
        self.wait("round_finished")
        before=(self.logs/'01/meta.json').read_bytes()
        self.prompt("success")
        self.wait("command_error")
        self.assertEqual((self.logs/'01/meta.json').read_bytes(),before)
        self.prompt("success","02"); self.wait("round_finished"); self.finish()

    def test_session_lock_refuses_second_writer(self):
        self.start()
        alias=self.root/'session-alias.jsonl'
        alias.symlink_to(self.logs/'session.jsonl')
        for extra in ([],["--session",str(alias)]):
            result=subprocess.run([sys.executable,str(RUNNER),"--cwd",str(self.root),"--run-dir",str(self.logs),
                "--provider","test","--model","fake","--pi",str(self.fake),*extra],input=b'',capture_output=True,timeout=3)
            self.assertEqual(result.returncode,1)
            self.assertIn(b'BlockingIOError',result.stdout)
        self.prompt("success"); self.wait("round_finished"); self.finish()


if __name__ == "__main__":
    unittest.main()
