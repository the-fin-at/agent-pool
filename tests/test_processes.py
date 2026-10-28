"""Real OS process boundaries; provider inference replaced by an explicit fixture."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_pool.providers import read_codex_quota, run_native
from agent_pool.store import Store

FIXTURE = Path(__file__).with_name("fake_native.py").resolve()


class ProcessTests(unittest.TestCase):
    def test_two_agents_exchange_a_report_through_the_cli(self):
        with tempfile.TemporaryDirectory(prefix="agent-pool-e2e-") as tmp:
            home = str(Path(tmp) / "state")
            def cli(*args):
                run = subprocess.run([sys.executable, "-m", "agent_pool", "--home", home, *args], capture_output=True, text=True, check=True)
                return json.loads(run.stdout)
            cli("init")
            cli("profile", "enable", "codex-1")
            submitted = cli("job", "submit", "--provider", "codex", "--cwd", tmp,
                            "--prompt", "Examine the module", "--key", "parent-request-1")
            # Worker is a separate process and launches a third process as its native CLI.
            script = '''
import sys
from pathlib import Path
from unittest.mock import patch
from agent_pool.store import Store
from agent_pool.worker import tick
s = Store(Path(sys.argv[1]))
with s.worker_lock(), patch('agent_pool.providers.command', return_value=[sys.executable, sys.argv[2], 'codex']):
    tick(s, probe=lambda *a: [])
s.close()
'''
            worker = subprocess.run([sys.executable, "-c", script, home, str(FIXTURE)], capture_output=True, text=True)
            self.assertEqual(worker.returncode, 0, worker.stderr)
            retrieved = cli("job", "get", submitted["id"])
            self.assertEqual(retrieved["status"], "succeeded")
            self.assertEqual(retrieved["result"], "Worker report: Examine the module")
            self.assertEqual(cli("job", "submit", "--provider", "codex", "--cwd", tmp,
                                 "--prompt", "Examine the module", "--key", "parent-request-1")["id"], submitted["id"])

    def test_claude_native_stream_reports_usage_and_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("agent_pool.providers.command", return_value=[sys.executable, str(FIXTURE), "claude"]):
                result = run_native({"provider": "claude"}, {"cwd": tmp, "prompt": "read", "timeout": 5}, Path(tmp))
            self.assertEqual(result.kind, "success")
            self.assertEqual(result.result, "Worker report: read")
            self.assertEqual(result.windows[0]["used"], 20)

    def test_actual_timeout_terminates_child_and_returns_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("agent_pool.providers.command", return_value=[sys.executable, str(FIXTURE), "timeout"]):
                result = run_native({"provider": "codex"}, {"cwd": tmp, "prompt": "read", "timeout": .1}, Path(tmp))
            self.assertEqual(result.kind, "uncertain")

    def test_quota_jsonrpc_handshake_uses_no_model_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / "rpc.py"
            server.write_text('''import json, sys
for line in sys.stdin:
 m=json.loads(line)
 if m['method']=='initialize':
  print(json.dumps({'id':m['id'],'result':{}}),flush=True)
 elif m['method']=='initialized':
  continue
 elif m['method']=='account/rateLimits/read':
  print(json.dumps({'id':m['id'],'result':{'rateLimits':{'primary':{'usedPercent':30,'windowDurationMins':300,'resetsAt':9999999999}}}}),flush=True)
 else:
  sys.exit(42)
''', encoding="utf-8")
            real_popen = subprocess.Popen
            def popen(argv, **kw):
                return real_popen([sys.executable, str(server)], **kw)
            with patch("agent_pool.providers.executable", return_value="codex"), patch("agent_pool.providers.subprocess.Popen", side_effect=popen):
                windows = read_codex_quota({"binary": "codex"}, Path(tmp), timeout=5)
            self.assertEqual(windows[0]["used"], 30)

class AdministrativeTests(unittest.TestCase):
    def test_completed_job_cannot_be_cancelled(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from agent_pool.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "state")
            job = store.submit("task", tmp, "codex")
            store.update_job(job["id"], status="succeeded", result="kept")
            with redirect_stdout(StringIO()):
                code = main(["--home", str(store.home), "job", "cancel", job["id"]])
            self.assertEqual(code, 1)
            self.assertEqual(store.job(job["id"])["status"], "succeeded")
            store.close()

    def test_nonfinite_timeout_rejected_before_enqueue(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "state")
            with self.assertRaises(ValueError):
                store.submit("task", tmp, "codex", timeout=float("nan"))
            store.close()

    def test_run_attaches_to_an_existing_worker(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from agent_pool.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "state")
            captured = StringIO()
            with store.worker_lock(), redirect_stdout(captured):
                code = main(["--home", str(store.home), "run", "--provider", "codex", "--cwd", tmp,
                             "--prompt", "wait for the other worker", "--wait-seconds", "0"])
            self.assertEqual(code, 2)
            job = json.loads(captured.getvalue())
            self.assertEqual(job["status"], "queued")
            self.assertEqual(store.job(job["id"])["prompt"], "wait for the other worker")
            store.close()
