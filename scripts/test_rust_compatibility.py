"""Cross-language contract tests. Python is the legacy oracle, not a runtime dependency."""
import concurrent.futures
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent_pool.store import Store, WorkerBusy, file_lock
from agent_pool.rpc import handle
from agent_pool.monitor import snapshot

BINARY = Path(os.environ.get('FLEET_RUST_BIN', ROOT / ('target/debug/agent-fleet'+('.exe' if os.name=='nt' else ''))))


@unittest.skipUnless(BINARY.is_file(), 'Build the native Rust CLI before running compatibility tests')
class RustCompatibility(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fleet-rust-contract-')
        self.root = Path(self.tmp.name)
        self.sessions = []
        self.home = self.root / 'pool'
        self.workspace = self.root / 'work'
        self.workspace.mkdir()
        self.db = Store(self.home)
        self.db.add_workspace('project', self.workspace)
        self.db.add_profile('legacy', 'codex', str(BINARY.parent/'examples'/('controlled_provider'+('.exe' if os.name=='nt' else ''))))
        self.db.cache_monitor('legacy', {'connected': True, 'email': 'legacy@example.invalid', 'plan': 'team', 'windows': [], 'observed_at': time.time()})

    def tearDown(self):
        for ident in self.sessions:
            subprocess.run([str(BINARY), '--home', str(self.home), 'auth', 'cancel', ident], capture_output=True, timeout=10)
        self.db.close()
        self.tmp.cleanup()

    def call(self, *args, code=0, timeout=20, input=None):
        done = subprocess.run([str(BINARY), '--home', str(self.home), *args], text=True,
                              input=input, capture_output=True, timeout=timeout)
        self.assertEqual(done.returncode, code, done.stderr + done.stdout)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def test_existing_profiles_jobs_results_and_state_survive_both_runtimes(self):
        old = self.db.submit('Existing instruction', self.workspace, 'codex', key='old-key')
        self.db.update_job(old['id'], status='succeeded', result='Existing report 🧭', chosen_profile='legacy')
        before_profiles = self.db.profiles()
        before_jobs = self.db.jobs()
        self.assertEqual(self.call('profile', 'list'), before_profiles)
        got = self.call('job', 'get', old['id'])
        self.assertEqual(got['result'], 'Existing report 🧭')
        new = self.call('job', 'submit', '--provider', 'codex', '--workspace', 'project', '--prompt', 'Native instruction', '--key', 'new-key')
        self.assertEqual(self.db.job(new['id'])['prompt'], 'Native instruction')
        self.assertEqual(self.db.profiles(), before_profiles)
        self.assertEqual(self.db.job(old['id']), before_jobs[0])
        rust_accounts = self.call('status')['accounts']
        self.assertEqual(rust_accounts, snapshot(self.home, include_default=False))

    def test_controlled_load_has_one_native_execution_per_job(self):
        from collections import Counter
        name = self.native_fixture()
        submitted = [self.db.submit('Controlled load '+str(i), self.workspace, 'codex', profile=name, key='load-'+str(i)) for i in range(100)]
        started = time.monotonic()
        self.call('work', '--drain', timeout=120)
        elapsed = time.monotonic()-started
        jobs = self.db.jobs()
        self.assertEqual(len(jobs), 100)
        self.assertEqual({j['id'] for j in jobs}, {j['id'] for j in submitted})
        for job in jobs:
            self.assertEqual(job['status'], 'succeeded', job)
            self.assertEqual(job['attempts'], 1)
            self.assertEqual(job['result'], 'read-only: '+job['prompt'])
        trace = [json.loads(line) for line in (self.db.authdir(name)/'fixture-executions.jsonl').read_text().splitlines()]
        self.assertEqual(Counter(row['prompt'] for row in trace), Counter(j['prompt'] for j in jobs))
        self.assertEqual(len(trace), 100)
        print('Native controlled workload: 100 unique jobs/executions in '+format(elapsed,'.3f')+' seconds', flush=True)

    def test_concurrent_cross_language_retries_create_one_job_and_validate_content(self):
        argv = ['job', 'submit', '--provider', 'codex', '--workspace', 'project', '--prompt', 'Literal 🧭 $(touch NEVER)', '--key', 'stable-key']
        def submit(i):
            if i % 2:
                reply = handle(self.home, {'version': 1, 'argv': argv})
                self.assertEqual(reply['code'], 0, reply)
                return json.loads(reply['output'])['id']
            return self.call(*argv)['id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(submit, range(16)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.db.jobs()), 1)
        self.assertFalse((self.workspace / 'NEVER').exists())
        self.call(*[v if v != 'Literal 🧭 $(touch NEVER)' else 'different' for v in argv], code=1)
        self.assertEqual(self.db.jobs()[0]['id'], ids[0])

    def test_needs_review_is_not_replayed_or_implicitly_retried(self):
        job = self.db.submit('Inspect first', self.workspace, 'codex', key='review')
        self.db.update_job(job['id'], status='needs_review', result='Partial result')
        self.call('job', 'get', job['id'], code=1)
        reply = self.call('rpc', input=json.dumps({'version': 1, 'argv': ['job', 'retry', job['id']]}))
        self.assertEqual(reply['code'], 1)
        self.assertEqual(self.db.job(job['id'])['status'], 'needs_review')
        reply = self.call('rpc', input=json.dumps({'version': 1, 'argv': ['job', 'retry', job['id'], '--acknowledge-review']}))
        self.assertEqual(reply['code'], 0)
        self.assertEqual(self.db.job(job['id'])['status'], 'queued')

    def test_rpc_limits_allowlist_and_exit_codes_are_compatible(self):
        forbidden = [None, {'version': True, 'argv': ['status']}, {'version': 1, 'argv': ['status', '--refresh']},
                     {'version': 1, 'argv': ['work']}, {'version': 1, 'argv': ['job', 'submit', '--cwd', str(self.workspace), '--prompt', 'x', '--provider', 'codex', '--key', 'x']},
                     {'version': 1, 'argv': ['profile', 'add', 'native', '--provider', 'codex']},
                     {'version': 1, 'argv': ['auth', 'input', 'a'*32, '--code-file', '/etc/passwd']},
                     {'version': 1, 'argv': ['status', '--remote', 'other']},
                     {'version': 1, 'argv': ['job', 'wait', 'missing', '--seconds', 'inf']}]
        for request in forbidden:
            result = self.call('rpc', input=json.dumps(request))
            self.assertEqual(result['code'], 1, request)
        job = self.db.submit('waiting', self.workspace, 'codex')
        self.call('job', 'get', job['id'], code=2)
        self.call('job', 'wait', job['id'], '--seconds', '0', code=2)
        self.call('job', 'cancel', job['id'])
        self.call('job', 'get', job['id'], code=1)

    def test_existing_attached_directory_and_remote_config_are_not_copied_or_replaced(self):
        native = self.root / 'native-account'
        native.mkdir()
        (native / 'sentinel').write_text('existing account directory; not a credential')
        self.db.add_profile('attached', 'codex', 'codex', auth_home=native)
        self.call('profile', 'enable', 'attached')
        self.assertEqual(self.db.authdir('attached'), native.resolve())
        self.assertEqual((native / 'sentinel').read_text(), 'existing account directory; not a credential')
        self.call('profile', 'add', 'duplicate', '--provider', 'codex', '--auth-home', str(native), code=1)
        self.call('remote', 'add', 'fixture', '--host', 'fixture-alias', '--command', '/home/fixture/bin/agent-fleet', '--server-home', '/home/fixture/.local/share/agent-pool')
        from agent_pool.remote import RemoteConfig
        config = RemoteConfig(self.home).get('fixture')
        self.assertEqual(config['host'], 'fixture-alias')
        self.assertEqual(self.call('remote', 'list')['fixture'], config)

    def test_python_worker_lease_blocks_rust_worker_without_changing_jobs(self):
        job = self.db.submit('Do not execute', self.workspace, 'codex')
        with self.db.worker_lock():
            self.call('work', '--once', code=1)
        self.assertEqual(self.db.job(job['id'])['status'], 'queued')

    def test_all_observed_limits_and_unknown_resets_are_preserved(self):
        self.db.update_profile('legacy', enabled=True, checked_at=time.time())
        windows = [{'key': 'codex:primary', 'bucket': 'codex', 'minutes': 300, 'used': 100, 'reset': time.time()-1, 'model': None},
                   {'key': 'codex:secondary', 'bucket': 'codex', 'minutes': 10080, 'used': 100, 'reset': time.time()+2000, 'model': None}]
        self.db.set_windows('legacy', windows, replace=True)
        self.assertFalse(self.call('quota', 'show', 'legacy')[0]['availability']['ready'])
        self.db.set_windows('legacy', [{**windows[1], 'reset': None}], replace=True)
        state = self.call('quota', 'show', 'legacy')[0]['availability']
        self.assertFalse(state['ready'])
        self.assertIsNone(state['ready_at'])

    def native_fixture(self, provider='codex', name=None):
        import shutil
        path = self.root / 'controlled-native'
        compiled = BINARY.parent / 'examples' / ('controlled_provider'+('.exe' if os.name=='nt' else ''))
        self.assertTrue(compiled.is_file(), 'Build actual native examples before acceptance: cargo build -p fleet-cli --examples')
        shutil.copy2(compiled, path.with_suffix('.exe') if os.name=='nt' else path)
        path = path.with_suffix('.exe') if os.name=='nt' else path
        name = name or 'native-'+provider
        self.db.add_profile(name, provider, str(path))
        self.db.update_profile(name, enabled=True, checked_at=time.time())
        (self.db.authdir(name)/'fixture-accepted').write_text('fixture-only')
        return name

    def test_native_worker_completes_readonly_and_edit_tasks_without_api_keys(self):
        name = self.native_fixture()
        ids = []
        for edits in [False, True]:
            job = self.db.submit('Native 🧭 $(touch NEVER)', self.workspace, 'codex', profile=name, allow_edits=edits)
            ids.append(job['id'])
            env = os.environ.copy()
            env.update(OPENAI_API_KEY='fixture-key-not-real', ANTHROPIC_API_KEY='fixture-key-not-real', OPENAI_BASE_URL='https://invalid.example')
            r = subprocess.run([str(BINARY), '--home', str(self.home), 'work', '--once'], env=env, text=True, capture_output=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr+r.stdout)
            result = self.db.job(job['id'])
            self.assertEqual(result['status'], 'succeeded', result)
            self.assertEqual(result['attempts'], 1)
            self.assertEqual(result['result'], ('workspace-write' if edits else 'read-only')+': Native 🧭 $(touch NEVER)')
        self.assertEqual(len(set(ids)), 2)
        self.assertFalse((self.workspace / 'NEVER').exists())

    @unittest.skipIf(os.name == 'nt', 'Unix process-group assertion')
    def test_timeout_marks_uncertain_job_and_kills_descendant_process(self):
        name = self.native_fixture()
        job = self.db.submit('__timeout__', self.workspace, 'codex', profile=name, timeout=.4)
        self.call('work', '--once')
        current = self.db.job(job['id'])
        self.assertEqual(current['status'], 'needs_review', current)
        child = int((self.db.authdir(name)/'fixture-child.pid').read_text())
        until = time.monotonic()+3
        running = True
        while time.monotonic() < until:
            p = subprocess.run(['ps','-p',str(child),'-o','stat='],text=True,capture_output=True)
            running = bool(p.stdout.strip()) and not p.stdout.strip().startswith('Z')
            if not running: break
            time.sleep(.05)
        self.assertFalse(running, 'Native descendant survived timeout')

    def wait_login(self, ident, states):
        until = time.monotonic()+12
        last = None
        while time.monotonic() < until:
            last = self.call('auth', 'get', ident)
            if last['state'] in states:
                return last
            if last['state'] in {'failed', 'expired'}:
                self.fail(str(last))
            time.sleep(.05)
        self.fail('Native login did not reach expected state: '+str(last))

    def test_native_codex_login_outlives_start_process_and_keeps_same_key(self):
        import uuid
        name = self.native_fixture()
        (self.db.authdir(name)/'fixture-accepted').unlink()
        key = uuid.uuid4().hex
        self.sessions.append(key)
        first = self.call('auth', 'start', name, '--provider', 'codex', '--key', key)
        self.assertEqual(first['id'], key)
        awaiting = self.wait_login(key, {'awaiting_browser'})
        self.assertEqual(awaiting['device_code'], 'ABCD-EFGHI')
        self.assertTrue(awaiting['url'].startswith('https://auth.openai.com/'))
        again = self.call('auth', 'start', name, '--provider', 'codex', '--key', key)
        self.assertEqual(again['id'], key)
        (self.db.authdir(name)/'fixture-accepted').write_text('fixture-only')
        done = self.wait_login(key, {'succeeded'})
        self.assertIsNone(done.get('url'))
        self.assertIsNone(done.get('device_code'))
        self.assertTrue(self.db.profile(name)['enabled'])

    def test_native_claude_login_consumes_code_without_persisting_it(self):
        import uuid
        name = self.native_fixture('claude')
        (self.db.authdir(name)/'fixture-accepted').unlink()
        key = uuid.uuid4().hex
        self.sessions.append(key)
        self.call('auth', 'start', name, '--provider', 'claude', '--key', key)
        self.wait_login(key, {'awaiting_code'})
        self.call('auth', 'input', key, '--code=fixture-authorized-code')
        self.wait_login(key, {'succeeded'})
        for path in self.home.rglob('*'):
            if path.is_file() and path.suffix in {'.json', '.input', '.log'}:
                self.assertNotIn(b'fixture-authorized-code', path.read_bytes(), str(path))
        self.assertTrue(self.db.profile(name)['enabled'])

    def test_native_login_cancel_is_real_and_keeps_new_profile_disabled(self):
        import uuid
        name = self.native_fixture()
        self.db.update_profile(name, enabled=False)
        (self.db.authdir(name)/'fixture-accepted').unlink()
        key = uuid.uuid4().hex
        self.sessions.append(key)
        self.call('auth', 'start', name, '--provider', 'codex', '--key', key)
        self.wait_login(key, {'awaiting_browser'})
        self.call('auth', 'cancel', key)
        self.wait_login(key, {'cancelled'})
        self.assertFalse(self.db.profile(name)['enabled'])

    def test_cancelled_reauthentication_preserves_existing_profile_activation(self):
        import uuid
        name = self.native_fixture()
        (self.db.authdir(name)/'fixture-accepted').unlink()
        key = uuid.uuid4().hex
        self.sessions.append(key)
        self.call('auth', 'start', name, '--provider', 'codex', '--key', key)
        self.wait_login(key, {'awaiting_browser'})
        self.call('auth', 'cancel', key)
        self.wait_login(key, {'cancelled'})
        self.assertTrue(self.db.profile(name)['enabled'])

    def routing_windows(self, name, five=10, week=10, reset=600, model=None):
        reset_at, week_at = time.time()+reset, time.time()+3600
        self.db.set_windows(name, [
            {'key': 'codex:primary', 'bucket': 'codex', 'minutes': 300, 'used': five, 'reset': reset_at, 'model': None},
            {'key': 'codex:secondary', 'bucket': 'codex', 'minutes': 10080, 'used': week, 'reset': week_at, 'model': model},
        ], replace=True)
        # A real worker refreshes metadata at startup. The controlled provider must
        # report the same observation; otherwise a fresh free observation wins.
        metadata = {'rateLimits': {
            'primary': {'usedPercent':five, 'windowDurationMins':300, 'resetsAt':reset_at},
            'secondary': {'usedPercent':week, 'windowDurationMins':10080, 'resetsAt':week_at},
        }}
        (self.db.authdir(name)/'fixture-ratelimits.json').write_text(json.dumps(metadata))

    def test_routing_skips_full_five_hour_and_week_accounts(self):
        self.db.update_profile('legacy', enabled=False)
        a = self.native_fixture(name='a')
        b = self.native_fixture(name='b')
        for five, week in [(100, 10), (0, 100)]:
            self.routing_windows(a, five=five, week=week)
            self.routing_windows(b)
            job = self.db.submit('Auto account', self.workspace, 'codex')
            self.call('work', '--once')
            current = self.db.job(job['id'])
            self.assertEqual(current['status'], 'succeeded', current)
            self.assertEqual(current['chosen_profile'], b)
            self.assertEqual(current['attempts'], 1)

    def test_busy_native_account_does_not_hide_free_same_provider_account(self):
        a = self.native_fixture(name='a')
        b = self.native_fixture(name='b')
        self.routing_windows(a)
        self.routing_windows(b)
        before = self.db.profile(a)['last_used']
        job = self.db.submit('Skip locked account', self.workspace, 'codex', key='locked-auto')
        with file_lock(self.db.authdir(a)/'.native.lock'):
            self.call('work', '--once')
        current = self.db.job(job['id'])
        self.assertEqual(current['status'], 'succeeded', current)
        self.assertEqual(current['chosen_profile'], b)
        self.assertEqual(current['attempts'], 1)
        self.assertEqual(current['idempotency_key'], 'locked-auto')
        self.assertEqual(self.db.profile(a)['last_used'], before)
        self.assertEqual(len(self.db.jobs()), 1)

    def test_busy_pinned_account_does_not_starve_later_other_provider_job(self):
        a = self.native_fixture(name='a')
        c = self.native_fixture('claude')
        self.routing_windows(a)
        pinned = self.db.submit('Pinned to locked account', self.workspace, 'codex', profile=a)
        later = self.db.submit('Independent Claude job', self.workspace, 'claude', profile=c)
        with file_lock(self.db.authdir(a)/'.native.lock'):
            self.call('work', '--once')
        self.assertEqual(self.db.job(pinned['id'])['status'], 'waiting')
        self.assertEqual(self.db.job(pinned['id'])['attempts'], 0)
        self.assertEqual(self.db.job(later['id'])['status'], 'succeeded')
        self.call('work', '--once')
        self.assertEqual(self.db.job(pinned['id'])['status'], 'succeeded')
        self.assertEqual(self.db.job(pinned['id'])['attempts'], 1)

    @unittest.skipIf(os.name == 'nt', 'Unix SIGTERM and process-group assertion')
    def test_sigterm_quarantines_inflight_job_and_reaps_native_descendants(self):
        name = self.native_fixture()
        job = self.db.submit('__timeout__', self.workspace, 'codex', profile=name, timeout=30)
        child_file = self.db.authdir(name)/'fixture-child.pid'
        worker = subprocess.Popen([str(BINARY), '--home', str(self.home), 'work', '--once'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            until = time.monotonic()+10
            while not child_file.is_file() and time.monotonic() < until:
                self.assertIsNone(worker.poll(), 'Worker exited before native execution')
                time.sleep(.05)
            self.assertTrue(child_file.is_file())
            worker.terminate()
            out, err = worker.communicate(timeout=8)
            self.assertEqual(worker.returncode, 130, err+out)
            self.assertEqual(self.db.job(job['id'])['status'], 'needs_review')
            for pid_file in ['fixture-parent.pid', 'fixture-child.pid']:
                pid = int((self.db.authdir(name)/pid_file).read_text())
                state = subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
                self.assertTrue(not state or state.startswith('Z'), 'Native process survived SIGTERM')
            self.call('work', '--once')
            self.assertEqual(self.db.job(job['id'])['attempts'], 1)
            self.assertEqual(self.db.job(job['id'])['status'], 'needs_review')
        finally:
            if worker.poll() is None:
                worker.terminate()
                worker.communicate(timeout=8)

    def test_readonly_quota_fails_over_same_job_but_edit_quota_is_not_replayed(self):
        self.db.update_profile('legacy', enabled=False)
        a = self.native_fixture(name='a')
        b = self.native_fixture(name='b')
        marker = self.db.authdir(a)/'fixture-quota-reject'
        marker.write_text('fixture-only')
        self.routing_windows(a)
        self.routing_windows(b)
        job = self.db.submit('Runtime quota readonly', self.workspace, 'codex', key='same-readonly')
        self.call('work', '--once')
        current = self.db.job(job['id'])
        self.assertEqual(current['status'], 'waiting', current)
        self.assertEqual(current['attempts'], 1)
        self.call('work', '--once')
        current = self.db.job(job['id'])
        self.assertEqual(current['status'], 'succeeded', current)
        self.assertEqual(current['chosen_profile'], b)
        self.assertEqual(current['attempts'], 2)
        self.assertEqual(current['idempotency_key'], 'same-readonly')
        self.assertEqual(len(self.db.jobs()), 1)
        # Re-enable A's observed capacity for a distinct explicitly editing task.
        self.db.update_profile(a, hold_until=None, hold_reason=None)
        self.routing_windows(a)
        self.db.update_profile(b, enabled=False)
        edit = self.db.submit('Runtime quota edit', self.workspace, 'codex', key='uncertain-edit', allow_edits=True)
        self.call('work', '--once')
        uncertain = self.db.job(edit['id'])
        self.assertEqual(uncertain['status'], 'needs_review', uncertain)
        self.assertEqual(uncertain['attempts'], 1)
        self.assertEqual((self.workspace/'fixture-edit-effect').read_text(), 'partial controlled edit')
        self.db.update_profile(b, enabled=True)
        # A fresh native worker process opens the same database after the editing failure.
        self.call('work', '--once')
        self.assertEqual(self.db.job(edit['id'])['status'], 'needs_review')
        self.assertEqual(self.db.job(edit['id'])['attempts'], 1)
        self.assertEqual(len(self.db.jobs()), 2)

    def test_pinned_profile_and_unknown_quota_hold_do_not_use_free_account(self):
        self.db.update_profile('legacy', enabled=False)
        a = self.native_fixture(name='a')
        self.native_fixture(name='b')
        self.routing_windows(a, five=100)
        job = self.db.submit('Pinned account', self.workspace, 'codex', profile=a)
        self.call('work', '--once')
        current = self.db.job(job['id'])
        self.assertEqual(current['status'], 'waiting')
        self.assertEqual(current['attempts'], 0)
        self.db.update_profile(a, hold_reason='quota_reset_unknown')
        self.db.set_windows(a, [], replace=True)
        (self.db.authdir(a)/'fixture-metadata-error').write_text('fixture-only')
        self.call('work', '--once')
        self.assertEqual(self.db.job(job['id'])['attempts'], 0)

    def test_blocked_codex_does_not_block_claude_and_model_limits_remain_scoped(self):
        self.db.update_profile('legacy', enabled=False)
        codex = self.native_fixture()
        claude = self.native_fixture('claude')
        self.routing_windows(codex, five=100)
        self.db.set_windows(claude, [
            {'key': 'five_hour', 'bucket': 'claude', 'minutes': 300, 'used': 10, 'reset': time.time()+600, 'model': None},
            {'key': 'seven_day_opus', 'bucket': 'claude', 'minutes': 10080, 'used': 100, 'reset': time.time()+3600, 'model': 'opus'},
        ], replace=True)
        blocked = self.db.submit('Must stay Codex', self.workspace, 'codex')
        sonnet = self.db.submit('Run Sonnet', self.workspace, 'claude', model='sonnet')
        opus = self.db.submit('Hold Opus', self.workspace, 'claude', model='opus')
        self.call('work', '--once')
        self.assertEqual(self.db.job(sonnet['id'])['status'], 'succeeded')
        # The native Sonnet response has no Opus observation; existing Opus limits survive.
        self.call('work', '--once')
        self.assertEqual(self.db.job(blocked['id'])['attempts'], 0)
        self.assertEqual(self.db.job(blocked['id'])['provider'], 'codex')
        self.assertEqual(self.db.job(opus['id'])['attempts'], 0)

    def test_claude_native_events_keep_model_quota_observations(self):
        name = self.native_fixture('claude')
        job = self.db.submit('native Claude', self.workspace, 'claude', profile=name)
        self.call('work', '--once')
        self.assertEqual(self.db.job(job['id'])['status'], 'succeeded')
        windows = self.db.windows(name)
        self.assertTrue(any(w.get('minutes') == 300 and w.get('used') == 20 for w in windows), windows)
        self.assertTrue(any(w.get('minutes') == 10080 and w.get('used') == 42 for w in windows), windows)


if __name__ == '__main__':
    if not BINARY.is_file():
        raise SystemExit('Missing native CLI: cargo build -p fleet-cli --examples && cargo build -p fleet-cli')
    unittest.main(verbosity=2)
