import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_pool.cli import main, parser
from agent_pool.providers import Outcome, run_native
from agent_pool.remote import RemoteClient, RemoteConfig, task_argv
from agent_pool.rpc import handle
from agent_pool.service import unit
from agent_pool.store import Store, file_lock, WorkerBusy
from agent_pool.worker import tick


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "state"
        self.store = Store(self.home)
        self.store.add_workspace("demo", self.root)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def rpc(self, *argv):
        result = handle(self.home, {"version": 1, "argv": list(argv)})
        return result["code"], json.loads(result["output"])

    def submit(self, prompt="prüfe äöü", key="request-1"):
        return self.rpc("job", "submit", "--workspace", "demo", "--provider", "codex", "--prompt", prompt, "--key", key)

    def test_disconnected_response_resubmission_keeps_one_job_and_rejects_conflict(self):
        self.submit()  # Server committed; pretend the client never received this reply.
        code, job = self.submit()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.store.jobs()), 1)
        self.assertEqual(self.store.job(job["id"])["prompt"], "prüfe äöü")
        self.assertEqual(self.submit("different")[0], 1)

    def test_rpc_never_executes_jobs_or_allows_nested_remote(self):
        for argv in (["work"], ["run"], ["login", "codex-1"], ["rpc"], ["--remote", "x", "doctor"]):
            self.assertEqual(self.rpc(*argv)[0], 1)
        self.assertEqual(len(self.store.jobs()), 0)

    def test_remote_submit_requires_workspace_key_and_no_local_path(self):
        for extra in (["--cwd", str(self.root), "--key", "k"], ["--workspace", "demo"], ["--workspace", "absent", "--key", "k"]):
            self.assertEqual(self.rpc("job", "submit", "--provider", "codex", "--prompt", "x", *extra)[0], 1)
        self.assertEqual(len(self.store.jobs()), 0)

    def test_prompt_is_literal_never_executed_by_a_shell(self):
        target = self.root / "pwned"
        prompt = "$(touch " + str(target) + "); `touch " + str(target) + "`; ' \"\nHallo"
        code, job = self.submit(prompt)
        self.assertEqual(code, 0)
        self.assertEqual(self.store.job(job["id"])["prompt"], prompt)
        self.assertFalse(target.exists())

    def test_invalid_unicode_nul_model_option_and_timeout_rejected(self):
        for value in ("x\x00y", "\ud800"):
            self.assertEqual(self.submit(value)[0], 1)
        for opt, value in [("--model", "--bad"), ("--timeout", "nan"), ("--timeout", "999999"), ("--max-attempts", "101")]:
            self.assertEqual(self.rpc("job", "submit", "--workspace", "demo", "--provider", "codex", "--prompt", "x", "--key", "x", opt, value)[0], 1)

    def test_version_fields_and_excessive_wait_rejected(self):
        for request in ({"version": 2, "argv": ["doctor"]}, {"version": True, "argv": ["doctor"]}, {"version": 1, "argv": ["doctor"], "home": "/tmp"}):
            self.assertEqual(handle(self.home, request)["code"], 1)
        code, job = self.submit()
        for seconds in ("nan", "inf", "61", "-1"):
            self.assertEqual(self.rpc("job", "wait", job["id"], "--seconds", seconds)[0], 1)

    @unittest.skipIf(os.name == "nt", "symlink privilege varies on Windows")
    def test_workspace_symlink_swap_rejected(self):
        original = self.root / "work"
        original.mkdir()
        self.store.add_workspace("work", original)
        original.rmdir()
        original.symlink_to(self.home, target_is_directory=True)
        self.assertEqual(self.rpc("job", "submit", "--workspace", "work", "--provider", "codex", "--prompt", "x", "--key", "k")[0], 1)

    def test_queue_administration_works_while_worker_lease_is_held(self):
        self.store.add_profile("test", "codex", "codex")
        code, job = self.submit()
        with self.store.worker_lock():
            self.assertEqual(self.rpc("profile", "disable", "test")[0], 0)
            self.assertEqual(self.rpc("job", "cancel", job["id"])[0], 0)
            self.assertEqual(self.rpc("job", "retry", job["id"])[0], 0)
        self.assertEqual(self.store.job(job["id"])["status"], "queued")

    def test_cancel_between_selection_and_claim_never_runs(self):
        self.store.add_profile("test", "codex", "codex")
        self.store.update_profile("test", enabled=True, checked_at=9999999999)
        code, job = self.submit()
        from agent_pool.worker import choose
        def cancel_then_choose(*args):
            selected = choose(*args)
            self.rpc("job", "cancel", job["id"])
            return selected
        with patch("agent_pool.worker.choose", side_effect=cancel_then_choose):
            self.assertFalse(tick(self.store, runner=lambda *a: self.fail("cancelled task executed")))
        self.assertEqual(self.store.job(job["id"])["status"], "cancelled")

    def test_disabled_profile_cannot_be_claimed(self):
        self.store.add_profile("test", "codex", "codex")
        code, job = self.submit()
        self.assertFalse(self.store.claim_job(job["id"], "test"))

    def test_native_account_lock_prevents_parallel_provider_processes(self):
        auth = self.root / "auth"
        auth.mkdir()
        with file_lock(auth / ".native.lock"), patch("agent_pool.providers._run_native") as native:
            result = run_native({"provider": "codex"}, {}, auth)
            self.assertEqual(result.kind, "busy")
            native.assert_not_called()

    def test_profile_busy_does_not_consume_an_execution_attempt(self):
        self.store.add_profile("test", "codex", "codex")
        self.store.update_profile("test", enabled=True, checked_at=9999999999)
        code, job = self.submit()
        tick(self.store, runner=lambda *a: Outcome("busy", error="locked"))
        current = self.store.job(job["id"])
        self.assertEqual(current["status"], "waiting")
        self.assertEqual(current["attempts"], 0)

    def test_remote_config_validates_host_and_quotes_remote_executable(self):
        config = RemoteConfig(self.home)
        for host in ("-oProxyCommand=oops", "user@host;touch /tmp/x", "a\nb", "foo bar"):
            with self.assertRaises(ValueError):
                config.add("bad", host)
        config.add("central", "user@server", "/opt/Agent Pool/agent-pool", "/srv/state")
        client = RemoteClient(config.get("central"))
        command = client.command()
        self.assertIn("BatchMode=yes", command)
        self.assertIn("'/opt/Agent Pool/agent-pool'", command[-1])
        self.assertEqual(config.get("central")["home"], "/srv/state")
        if os.name != "nt":
            self.assertEqual(config.path.stat().st_mode & 0o777, 0o600)

    def test_transport_encodes_prompt_only_on_stdin_and_reports_dirty_shell(self):
        client = RemoteClient({"host": "central", "command": "agent-pool", "home": "/srv/agent-pool"})
        with patch("agent_pool.remote.subprocess.run", return_value=subprocess.CompletedProcess([], 0, 'welcome\n{}', '')) as run:
            with self.assertRaisesRegex(ValueError, "quiet SSH shell"):
                client.request(["job", "submit", "--prompt", "secret prompt"])
            argv, = run.call_args.args
            self.assertNotIn("secret prompt", " ".join(argv))
            self.assertIn("secret prompt", run.call_args.kwargs["input"])
            self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")

    def test_transport_timeout_has_unknown_outcome_guidance(self):
        client = RemoteClient({"host": "central", "command": "agent-pool", "home": "/srv/agent-pool"})
        with patch("agent_pool.remote.subprocess.run", side_effect=subprocess.TimeoutExpired("ssh", 1)):
            with self.assertRaisesRegex(ValueError, "identical --key"):
                client.request(["job", "list"])

    def test_prompt_file_read_on_client_and_workspace_preserved(self):
        prompt = self.root / "prompt.txt"
        prompt.write_text("Grüße vom Mac", encoding="utf-8")
        args = parser().parse_args(["job", "submit", "--provider", "claude", "--workspace", "demo", "--prompt-file", str(prompt), "--key", "k"])
        argv = task_argv(args)
        self.assertIn("--prompt=Grüße vom Mac", argv)
        self.assertNotIn(str(prompt), argv)

    def test_service_keeps_process_group_cleanup_and_escapes_paths(self):
        value = unit('/opt/Agent Pool/$x%/agent-pool', '/srv/agent-pool')
        self.assertIn('KillMode=control-group', value)
        self.assertIn('$$x%%', value)
        self.assertIn('UMask=0077', value)
        with self.assertRaises(ValueError):
            unit('relative', self.home)

    def test_actual_rpc_process_utf8_and_request_limit(self):
        def invoke(raw):
            return subprocess.run([sys.executable, '-m', 'agent_pool', '--home', str(self.home), 'rpc'], input=raw, capture_output=True, timeout=10)
        done = invoke(json.dumps({"version": 1, "argv": ["job", "list"]}).encode())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["code"], 0)
        self.assertEqual(json.loads(invoke(b'x'*(2*1024*1024+1)).stdout)["code"], 1)
        self.assertEqual(json.loads(invoke(b'\xff').stdout)["code"], 1)

class ReviewRegressionTests(unittest.TestCase):
    def test_rpc_help_and_nested_json_never_pollute_response_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)/'state'
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = handle(home, {'version':1,'argv':['job','submit','--help']})
            self.assertEqual(out.getvalue(), '')
            self.assertEqual(result['code'],1)
            deep = b'['*2000+b'0'+b']'*2000
            done = subprocess.run([sys.executable,'-m','agent_pool','--home',str(home),'rpc'],input=deep,capture_output=True,timeout=10)
            self.assertEqual(done.returncode,0)
            self.assertEqual(json.loads(done.stdout)['code'],1)

    def test_rpc_never_launches_metadata_or_reconfigures_native_binaries(self):
        with tempfile.TemporaryDirectory() as tmp, patch('agent_pool.monitor.collect') as collect:
            for argv in [['status','--refresh'],['monitor','--refresh'],['quota','refresh'],['profile','add','x','--provider','codex'],['workspace','add','x','--path',tmp],['init']]:
                self.assertEqual(handle(tmp,{'version':1,'argv':argv})['code'],1)
            collect.assert_not_called()

    def test_invalid_executable_and_missing_explicit_server_home_rejected(self):
        from agent_pool.remote import validate
        for config in [{'host':'server','command':None,'home':'/srv/pool'}, {'host':'server','command':'agent-pool','home':None}]:
            with self.assertRaises(ValueError):validate(config)

    def test_busy_native_account_returns_idle_tick_instead_of_spinning(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state')
            store.add_profile('one','codex','codex')
            store.update_profile('one',enabled=True,checked_at=9999999999)
            job=store.submit('read',tmp,'codex')
            self.assertFalse(tick(store,runner=lambda *a:Outcome('busy')))
            self.assertEqual(store.job(job['id'])['attempts'],0)
            store.close()

    def test_heartbeat_reports_liveness_during_work_and_offline_after_stop(self):
        from agent_pool.runtime import heartbeat, worker_state
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(worker_state(tmp)['online'])
            with heartbeat(tmp):
                self.assertTrue(worker_state(tmp)['online'])
                self.assertEqual(worker_state(tmp)['home'],str(Path(tmp).resolve()))
            self.assertFalse(worker_state(tmp)['online'])

    def test_needs_review_retry_requires_explicit_remote_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state')
            job=store.submit('task',tmp,'codex')
            store.update_job(job['id'],status='needs_review')
            request={'version':1,'argv':['job','retry',job['id']]}
            self.assertEqual(handle(store.home,request)['code'],1)
            request['argv'].append('--acknowledge-review')
            self.assertEqual(handle(store.home,request)['code'],0)
            store.close()

@unittest.skipIf(os.name == 'nt', 'SIGTERM cleanup is POSIX; Windows termination differs')
class ShutdownTests(unittest.TestCase):
    def test_sigterm_stops_native_child_and_marks_uncertain_job_for_review(self):
        import time
        from agent_pool.runtime import worker_state
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);home=root/'state';store=Store(home)
            store.add_profile('one','codex','codex')
            store.update_profile('one',enabled=True,checked_at=9999999999)
            job=store.submit('long task',root,'codex')
            fixture=root/'native.py'
            fixture.write_text('import os,time\nfrom pathlib import Path\nPath("native.pid").write_text(str(os.getpid()))\ntime.sleep(60)\n')
            script='''import sys
from unittest.mock import patch
from agent_pool.cli import main
with patch('agent_pool.monitor.collect', return_value=[]), patch('agent_pool.providers.command', return_value=[sys.executable,sys.argv[2]]):
 sys.exit(main(['--home',sys.argv[1],'work','--once']))
'''
            proc=subprocess.Popen([sys.executable,'-c',script,str(home),str(fixture)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                until=time.monotonic()+5
                while not (root/'native.pid').exists() and time.monotonic()<until:time.sleep(.02)
                self.assertTrue((root/'native.pid').exists())
                pid=int((root/'native.pid').read_text())
                proc.terminate()
                stdout,stderr=proc.communicate(timeout=5)
                self.assertEqual(proc.returncode,130,stderr)
                self.assertEqual(store.job(job['id'])['status'],'needs_review')
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)
                self.assertFalse(worker_state(home)['online'])
            finally:
                if proc.poll() is None:proc.kill();proc.communicate()
                store.close()

class LauncherTests(unittest.TestCase):
    def test_mac_remote_uses_packaged_app_without_importing_tk(self):
        from agent_pool.cli import launch_desktop
        with patch('agent_pool.cli.sys.platform','darwin'), patch('agent_pool.cli.Path.is_dir',return_value=True), patch('agent_pool.cli.subprocess.Popen') as popen, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launch_desktop('/tmp/client','central'),0)
        argv=popen.call_args.args[0]
        self.assertEqual(argv[:2],['open','-n'])
        self.assertEqual(argv[-2:],['--remote','central'])
