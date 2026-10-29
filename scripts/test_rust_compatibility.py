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
        self.env = os.environ.copy()
        self.env['HOME'] = str(self.root / 'user')
        self.env['USERPROFILE'] = self.env['HOME']
        self.env['CODEX_HOME'] = str(self.root / 'native-codex')
        self.env.pop('CLAUDE_CONFIG_DIR', None)
        self.workspace = self.root / 'work'
        self.workspace.mkdir()
        self.db = Store(self.home)
        self.db.add_workspace('project', self.workspace)
        self.db.add_profile('legacy', 'codex', str(BINARY.parent/'examples'/('controlled_provider'+('.exe' if os.name=='nt' else ''))))
        self.db.cache_monitor('legacy', {'connected': True, 'email': 'legacy@example.invalid', 'plan': 'team', 'windows': [], 'observed_at': 1700000000.25})

    def tearDown(self):
        for ident in self.sessions:
            subprocess.run([str(BINARY), '--home', str(self.home), 'auth', 'cancel', ident], capture_output=True, timeout=10)
        self.db.close()
        self.tmp.cleanup()

    def call(self, *args, code=0, timeout=20, input=None):
        done = subprocess.run([str(BINARY), '--home', str(self.home), *args], text=True,
                              input=input, capture_output=True, timeout=timeout, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr + done.stdout)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def default_claude_fixture(self):
        import shutil
        native = Path(self.env['HOME']) / '.claude'
        native.mkdir(parents=True)
        (native / 'fixture-accepted').write_text('controlled login')
        (native / 'fixture-default-only').write_text('requires unset CLAUDE_CONFIG_DIR')
        binaries = self.root / 'bin'
        binaries.mkdir()
        fixture = BINARY.parent / 'examples' / ('controlled_provider'+('.exe' if os.name == 'nt' else ''))
        shutil.copy2(fixture, binaries / ('claude.exe' if os.name == 'nt' else 'claude'))
        self.env['PATH'] = str(binaries) + os.pathsep + self.env.get('PATH', '')
        return native

    def test_default_claude_cli_login_is_discovered_once_and_used_without_config_override(self):
        native = self.default_claude_fixture()
        first = self.call('overview', '--refresh')['accounts']
        defaults = [a for a in first if a.get('auth_mode') == 'native_default']
        self.assertEqual(len(defaults), 1, first)
        account = defaults[0]
        self.assertTrue(account['connected'])
        self.assertTrue(account['enabled'])
        self.call('overview', '--refresh')
        profiles = self.call('profile', 'list')
        self.assertEqual(len([p for p in profiles if p.get('auth_mode') == 'native_default']), 1)
        job = self.call('job', 'submit', '--provider', 'claude', '--workspace', 'project', '--prompt', 'default context', '--key', 'native-default')
        self.call('work', '--drain')
        done = self.call('job', 'get', job['id'])
        self.assertEqual(done['chosen_profile'], account['name'])
        self.assertEqual(done['result'], 'Claude: default context')
        trace = json.loads((native / 'fixture-executions.jsonl').read_text().splitlines()[0])
        self.assertFalse(trace['config_override'])
        self.assertFalse((self.home / 'profiles' / account['name']).exists())
        refreshed=next(a for a in self.call('monitor','--refresh') if a['name']==account['name'])
        self.assertEqual(next(w['used'] for w in refreshed['windows'] if w['key']=='five_hour'),20)

    def test_default_is_automatic_canonical_account_but_managed_pin_keeps_its_directory(self):
        native = self.default_claude_fixture()
        alias = self.native_fixture('claude', 'a-managed')
        accounts = self.call('overview', '--refresh')['accounts']
        default = next(a['name'] for a in accounts if a.get('auth_mode') == 'native_default')
        jobs = [self.db.submit('automatic', self.workspace, 'claude'),
                self.db.submit('pinned', self.workspace, 'claude', profile=alias)]
        self.call('work', '--drain')
        self.assertEqual(self.call('job', 'get', jobs[0]['id'])['chosen_profile'], default)
        self.assertEqual(self.call('job', 'get', jobs[1]['id'])['chosen_profile'], alias)
        self.assertTrue(next(p for p in self.call('profile', 'list') if p['name'] == alias)['enabled'])
        self.assertFalse(json.loads((native/'fixture-executions.jsonl').read_text().splitlines()[0])['config_override'])
        managed_trace = json.loads((self.db.authdir(alias)/'fixture-executions.jsonl').read_text().splitlines()[0])
        self.assertTrue(managed_trace['config_override'])

    def test_default_auth_is_external_and_cannot_start_a_fleet_login(self):
        import uuid
        native = self.default_claude_fixture()
        accounts = self.call('overview', '--refresh')['accounts']
        name = next(a['name'] for a in accounts if a.get('auth_mode') == 'native_default')
        key = uuid.uuid4().hex
        self.sessions.append(key)
        rejected = self.call('auth', 'start', name, '--provider', 'claude', '--key', key, code=1)
        self.assertIn('Claude-CLI', rejected['error'])
        self.assertTrue((native/'fixture-accepted').exists())
        self.assertFalse((native/'fixture-parent.pid').exists())

    def test_same_account_aliases_share_quota_holds_and_busy_locks_without_blocking_other_accounts(self):
        self.default_claude_fixture()
        alias = self.native_fixture('claude', 'a-managed')
        other = self.native_fixture('claude', 'other-account')
        (self.db.authdir(other)/'fixture-email').write_text('separate@example.invalid')
        accounts = self.call('overview', '--refresh')['accounts']
        default = next(a['name'] for a in accounts if a.get('auth_mode') == 'native_default')
        self.db.set_windows(alias, [{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}], replace=True)
        blocked = self.db.submit('same-account exhausted', self.workspace, 'claude', profile=default)
        pinned = self.db.submit('same-account pinned', self.workspace, 'claude', profile=alias)
        separate = self.db.submit('different account', self.workspace, 'claude', profile=other)
        self.call('work', '--drain')
        self.assertEqual(self.call('job', 'get', separate['id'])['chosen_profile'], other)
        for job in [blocked,pinned]:
            current=self.call('job','get',job['id'],code=2)
            self.assertEqual(current['status'],'waiting')
            self.assertEqual(current['attempts'],0)
        self.db.set_windows(alias, [], replace=True)
        self.db.set_windows(default, [], replace=True)
        self.db.update_profile(alias,hold_reason='quota_reset_unknown',hold_until=None)
        self.call('work','--once')
        self.assertEqual(self.call('job','get',blocked['id'],code=2)['attempts'],0)
        self.db.update_profile(alias,hold_reason=None,hold_until=None)
        self.db.update_profile(default,hold_reason=None,hold_until=None)
        with file_lock(self.db.authdir(alias)/'.native.lock'):
            self.call('work','--once')
            self.assertEqual(self.call('job','get',blocked['id'],code=2)['attempts'],0)
            account=next(a for a in self.call('monitor') if a['name']==alias)
            self.assertTrue(account['connected'], 'Busy metadata must not fabricate logout')
        self.call('work','--drain')
        self.assertEqual(self.call('job','get',blocked['id'])['chosen_profile'],default)
        self.assertEqual(self.call('job','get',pinned['id'])['chosen_profile'],alias)

    def test_default_external_logout_relogin_identity_change_and_manual_disable(self):
        native=self.default_claude_fixture()
        account=next(a for a in self.call('overview','--refresh')['accounts'] if a.get('auth_mode')=='native_default')
        name=account['name']
        self.db.set_windows(name,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}],replace=True)
        self.db.update_profile(name,hold_reason='quota_reset_unknown',hold_until=None)
        (native/'fixture-accepted').unlink()
        logged_out=next(a for a in self.call('monitor','--refresh') if a['name']==name)
        self.assertFalse(logged_out['connected'])
        self.assertTrue(logged_out['enabled'])
        self.assertEqual(logged_out['windows'],[])
        job=self.db.submit('recover after external login',self.workspace,'claude')
        self.call('work','--once')
        self.assertEqual(self.call('job','get',job['id'],code=2)['attempts'],0)
        (native/'fixture-email').write_text('changed@example.invalid')
        (native/'fixture-accepted').write_text('controlled relogin')
        returned=next(a for a in self.call('monitor','--refresh') if a['name']==name)
        self.assertTrue(returned['connected'])
        self.assertEqual(returned['email'],'changed@example.invalid')
        self.assertIsNone(returned['hold_reason'])
        self.call('profile','disable',name)
        self.call('overview','--refresh')
        self.call('work','--once')
        self.assertEqual(self.call('job','get',job['id'],code=2)['attempts'],0)
        self.call('profile','enable',name)
        self.call('work','--drain')
        self.assertEqual(self.call('job','get',job['id'])['chosen_profile'],name)

    def test_additional_claude_login_remains_isolated_with_default_present(self):
        import uuid
        native=self.default_claude_fixture()
        self.call('overview','--refresh')
        name=self.native_fixture('claude','additional')
        (self.db.authdir(name)/'fixture-accepted').unlink()
        self.db.update_profile(name,enabled=False)
        key=uuid.uuid4().hex
        self.sessions.append(key)
        self.call('auth','start',name,'--provider','claude','--key',key)
        self.wait_login(key,{'awaiting_code'})
        self.call('auth','input',key,'--code=fixture-authorized-code')
        self.wait_login(key,{'succeeded'})
        self.assertTrue((native/'fixture-accepted').exists())
        self.assertFalse((native/'fixture-parent.pid').exists())
        self.assertTrue(self.db.profile(name)['enabled'])
        self.assertTrue(self.db.authdir(name).is_relative_to(self.home.resolve()/'profiles'))

    def test_unknown_identity_cannot_duplicate_default_capacity_but_verified_other_account_runs(self):
        self.default_claude_fixture()
        unknown=self.native_fixture('claude','unknown')
        (self.db.authdir(unknown)/'fixture-metadata-error').write_text('controlled unavailable identity')
        other=self.native_fixture('claude','other')
        (self.db.authdir(other)/'fixture-email').write_text('separate@example.invalid')
        accounts=self.call('overview','--refresh')['accounts']
        default=next(a['name'] for a in accounts if a.get('auth_mode')=='native_default')
        blocked=self.db.submit('ambiguous identity',self.workspace,'claude',profile=default)
        separate=self.db.submit('verified independent',self.workspace,'claude',profile=other)
        self.call('work','--drain')
        self.assertEqual(self.call('job','get',separate['id'])['chosen_profile'],other)
        current=self.call('job','get',blocked['id'],code=2)
        self.assertEqual(current['attempts'],0)
        (self.db.authdir(unknown)/'fixture-metadata-error').unlink()
        self.call('work','--drain')
        self.assertEqual(self.call('job','get',blocked['id'])['chosen_profile'],default)

    def test_malformed_native_status_is_unknown_and_preserves_confirmed_identity_and_quota(self):
        native=self.default_claude_fixture()
        default=next(a['name'] for a in self.call('overview','--refresh')['accounts'] if a.get('auth_mode')=='native_default')
        self.db.set_windows(default,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}],replace=True)
        self.call('monitor','--refresh')
        for invalid in [{}, {'loggedIn':'true','authMethod':'claude.ai'}, {'loggedIn':True}, {'loggedIn':True,'authMethod':'none'}]:
            (native/'fixture-status.json').write_text(json.dumps({'configDirectory':str(native.resolve()),**invalid}))
            account=next(a for a in self.call('monitor','--refresh') if a['name']==default)
            self.assertTrue(account['connected'], 'Malformed metadata is not confirmed logout')
            self.assertEqual(account['email'],'rust-fixture@example.invalid')
            self.assertIsNotNone(account['error'])
            self.assertEqual(self.call('quota','show',default)[0]['windows'][0]['used'],100)
        self.db.set_windows(default,[],replace=True)
        job=self.db.submit('unknown auth cannot run',self.workspace,'claude',profile=default)
        self.call('work','--once')
        self.assertEqual(self.call('job','get',job['id'],code=2)['attempts'],0)

    def test_same_claude_identity_with_changed_email_case_keeps_its_quota_hold(self):
        native=self.default_claude_fixture()
        default=next(a['name'] for a in self.call('overview','--refresh')['accounts'] if a.get('auth_mode')=='native_default')
        self.db.set_windows(default,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}],replace=True)
        self.db.update_profile(default,hold_reason='quota_reset_unknown',hold_until=None)
        (native/'fixture-email').write_text('RUST-FIXTURE@EXAMPLE.INVALID')
        account=next(a for a in self.call('monitor','--refresh') if a['name']==default)
        self.assertEqual(self.call('quota','show',default)[0]['windows'][0]['used'],100)
        self.assertEqual(account['hold_reason'],'quota_reset_unknown')

    def test_codex_only_queue_does_not_probe_registered_claude_accounts(self):
        native=self.default_claude_fixture()
        self.call('overview','--refresh')
        codex=self.native_fixture('codex')
        (native/'fixture-status-calls').write_text('')
        job=self.db.submit('independent Codex work',self.workspace,'codex',profile=codex)
        self.call('work','--once')
        self.assertEqual(self.call('job','get',job['id'])['chosen_profile'],codex)
        self.assertEqual((native/'fixture-status-calls').read_text(),'')

    def test_default_account_switch_preserves_old_alias_quota_and_new_account_is_free(self):
        native=self.default_claude_fixture()
        alias=self.native_fixture('claude','managed-a')
        default=next(a['name'] for a in self.call('overview','--refresh')['accounts'] if a.get('auth_mode')=='native_default')
        self.db.set_windows(default,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None},
                                     {'key':'seven_day','bucket':'claude','minutes':10080,'used':10,'reset':time.time()+3600,'model':None}],replace=True)
        self.db.set_windows(alias,[{'key':'seven_day','bucket':'claude','minutes':10080,'used':90,'reset':time.time()+7200,'model':None}],replace=True)
        observed_before=max(p['observed_at'] or 0 for p in self.call('profile','list'))
        old=self.db.submit('old account remains exhausted',self.workspace,'claude',profile=alias)
        self.call('work','--once')
        self.assertEqual(self.call('job','get',old['id'],code=2)['attempts'],0)
        (native/'fixture-email').write_text('new-account@example.invalid')
        new=self.db.submit('new account may run',self.workspace,'claude')
        self.call('work','--drain')
        self.assertEqual(self.call('job','get',old['id'],code=2)['attempts'],0)
        self.assertEqual(self.call('quota','show',alias)[0]['windows'][0]['used'],100)
        self.assertEqual(next(w['used'] for w in self.call('quota','show',alias)[0]['windows'] if w['key']=='seven_day'),90)
        self.assertLessEqual(next(p['observed_at'] for p in self.call('profile','list') if p['name']==alias),observed_before+1e-6)
        self.assertEqual(self.call('job','get',new['id'])['chosen_profile'],default)

    def test_default_logout_retains_unknown_quota_hold_on_its_remaining_managed_alias(self):
        native=self.default_claude_fixture()
        alias=self.native_fixture('claude','managed-a')
        default=next(a['name'] for a in self.call('overview','--refresh')['accounts'] if a.get('auth_mode')=='native_default')
        self.db.update_profile(default,hold_reason='quota_reset_unknown',hold_until=None)
        (native/'fixture-accepted').unlink()
        self.call('monitor','--refresh')
        old=self.db.submit('unknown old-account limit',self.workspace,'claude',profile=alias)
        self.call('work','--once')
        self.assertEqual(self.call('job','get',old['id'],code=2)['attempts'],0)
        profile=next(p for p in self.call('profile','list') if p['name']==alias)
        self.assertEqual(profile['hold_reason'],'quota_reset_unknown')
        self.assertTrue(profile['enabled'])

    def test_managed_login_account_switch_does_not_inherit_previous_account_limits(self):
        import uuid
        self.default_claude_fixture()
        alias=self.native_fixture('claude','managed-a')
        default=next(a['name'] for a in self.call('overview','--refresh')['accounts'] if a.get('auth_mode')=='native_default')
        self.db.set_windows(default,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}],replace=True)
        self.db.update_profile(default,hold_reason='quota_reset_unknown',hold_until=None)
        (self.db.authdir(alias)/'fixture-email').write_text('new-account@example.invalid')
        key=uuid.uuid4().hex;self.sessions.append(key)
        self.call('auth','start',alias,'--provider','claude','--key',key)
        self.wait_login(key,{'awaiting_code'})
        self.call('auth','input',key,'--code=fixture-authorized-code')
        self.wait_login(key,{'succeeded'})
        self.assertEqual(self.call('quota','show',alias)[0]['windows'],[])
        self.assertIsNone(self.call('quota','show',alias)[0]['hold_reason'])
        self.assertEqual(self.call('quota','show',default)[0]['windows'][0]['used'],100)
        self.assertEqual(self.call('quota','show',default)[0]['hold_reason'],'quota_reset_unknown')
        job=self.db.submit('new managed identity is free',self.workspace,'claude',profile=alias)
        self.call('work','--drain')
        self.assertEqual(self.call('job','get',job['id'])['chosen_profile'],alias)

    def test_same_managed_identity_reauthentication_preserves_its_quota_hold(self):
        import uuid
        self.default_claude_fixture()
        alias=self.native_fixture('claude','managed-a')
        self.call('overview','--refresh')
        self.db.set_windows(alias,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}],replace=True)
        self.db.update_profile(alias,hold_reason='quota_reset_unknown',hold_until=None)
        key=uuid.uuid4().hex;self.sessions.append(key)
        self.call('auth','start',alias,'--provider','claude','--key',key)
        self.wait_login(key,{'awaiting_code'})
        self.call('auth','input',key,'--code=fixture-authorized-code')
        self.wait_login(key,{'succeeded'})
        self.assertEqual(self.call('quota','show',alias)[0]['windows'][0]['used'],100)
        self.assertEqual(self.call('quota','show',alias)[0]['hold_reason'],'quota_reset_unknown')

    def test_interactive_claude_login_uses_the_same_identity_transition(self):
        self.default_claude_fixture()
        alias=self.native_fixture('claude','managed-a')
        default=next(a['name'] for a in self.call('overview','--refresh')['accounts'] if a.get('auth_mode')=='native_default')
        self.db.set_windows(alias,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}],replace=True)
        self.db.update_profile(alias,hold_reason='quota_reset_unknown',hold_until=None)
        def login():
            done=subprocess.run([str(BINARY),'--home',str(self.home),'login',alias],env=self.env,input='fixture-authorized-code\n',capture_output=True,text=True,timeout=15)
            self.assertEqual(done.returncode,0,done.stderr+done.stdout)
        login()
        self.assertEqual(self.call('quota','show',alias)[0]['windows'][0]['used'],100)
        self.assertEqual(self.call('quota','show',alias)[0]['hold_reason'],'quota_reset_unknown')
        (self.db.authdir(alias)/'fixture-email').write_text('new-account@example.invalid')
        login()
        self.assertEqual(self.call('quota','show',alias)[0]['windows'],[])
        self.assertIsNone(self.call('quota','show',alias)[0]['hold_reason'])
        self.assertEqual(self.call('quota','show',default)[0]['windows'][0]['used'],100)
        self.assertEqual(self.call('quota','show',default)[0]['hold_reason'],'quota_reset_unknown')

    def test_session_login_rejects_missing_null_blank_and_nonstring_identity_without_losing_limits(self):
        import uuid
        self.default_claude_fixture()
        alias=self.native_fixture('claude','managed-a')
        self.call('overview','--refresh')
        self.db.set_windows(alias,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}],replace=True)
        self.db.update_profile(alias,hold_reason='quota_reset_unknown',hold_until=None)
        for invalid in [{},{'email':None},{'email':'  '},{'email':42}]:
            (self.db.authdir(alias)/'fixture-status.json').write_text(json.dumps({'loggedIn':True,'authMethod':'claude.ai','configDirectory':str(self.db.authdir(alias)),**invalid}))
            key=uuid.uuid4().hex;self.sessions.append(key)
            self.call('auth','start',alias,'--provider','claude','--key',key)
            self.wait_login(key,{'awaiting_code'})
            self.call('auth','input',key,'--code=fixture-authorized-code')
            failed=self.wait_login(key,{'failed','succeeded'})
            self.assertEqual(failed['state'],'failed')
            self.assertIn('Accountidentität',failed['message'])
            profile=self.call('quota','show',alias)[0]
            self.assertEqual(profile['windows'][0]['used'],100)
            self.assertEqual(profile['hold_reason'],'quota_reset_unknown')
            account=next(a for a in self.call('monitor') if a['name']==alias)
            self.assertEqual(account['email'],'rust-fixture@example.invalid')

    def test_interactive_login_rejects_ambiguous_identity_without_losing_limits(self):
        self.default_claude_fixture()
        alias=self.native_fixture('claude','managed-a')
        self.call('overview','--refresh')
        self.db.set_windows(alias,[{'key':'five_hour','bucket':'claude','minutes':300,'used':100,'reset':time.time()+600,'model':None}],replace=True)
        self.db.update_profile(alias,hold_reason='quota_reset_unknown',hold_until=None)
        for invalid in [{},{'email':None},{'email':'  '},{'email':42}]:
            (self.db.authdir(alias)/'fixture-status.json').write_text(json.dumps({'loggedIn':True,'authMethod':'claude.ai','configDirectory':str(self.db.authdir(alias)),**invalid}))
            done=subprocess.run([str(BINARY),'--home',str(self.home),'login',alias],env=self.env,input='fixture-authorized-code\n',capture_output=True,text=True,timeout=15)
            self.assertEqual(done.returncode,1,done.stderr+done.stdout)
            self.assertIn('Accountidentität',done.stdout)
            profile=self.call('quota','show',alias)[0]
            self.assertEqual(profile['windows'][0]['used'],100)
            self.assertEqual(profile['hold_reason'],'quota_reset_unknown')
            self.assertEqual(next(a for a in self.call('monitor') if a['name']==alias)['email'],'rust-fixture@example.invalid')

    def test_existing_profiles_jobs_results_and_state_survive_both_runtimes(self):
        old = self.db.submit('Existing instruction', self.workspace, 'codex', key='old-key')
        self.db.update_job(old['id'], status='succeeded', result='Existing report 🧭', chosen_profile='legacy')
        before_profiles = self.db.profiles()
        before_jobs = self.db.jobs()
        self.assertEqual(self.call('profile', 'list'), [{**p,'auth_mode':'directory'} for p in before_profiles])
        got = self.call('job', 'get', old['id'])
        self.assertEqual(got['result'], 'Existing report 🧭')
        new = self.call('job', 'submit', '--provider', 'codex', '--workspace', 'project', '--prompt', 'Native instruction', '--key', 'new-key')
        self.assertEqual(self.db.job(new['id'])['prompt'], 'Native instruction')
        self.assertEqual(self.db.profiles(), [{**p,'auth_mode':'directory'} for p in before_profiles])
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

    def test_native_claude_rejected_code_can_be_corrected_in_same_session(self):
        import uuid
        name = self.native_fixture('claude')
        self.db.update_profile(name, enabled=False)
        (self.db.authdir(name)/'fixture-accepted').unlink()
        key = uuid.uuid4().hex
        self.sessions.append(key)
        self.call('auth', 'start', name, '--provider', 'claude', '--key', key)
        self.wait_login(key, {'awaiting_code'})
        provider_pid = (self.db.authdir(name)/'fixture-parent.pid').read_text()
        self.call('auth', 'input', key, '--code=fixture-rejected-code')
        until = time.monotonic()+3
        retry = None
        while time.monotonic() < until:
            retry = self.call('auth', 'get', key)
            if retry['state'] == 'awaiting_code' and 'nicht akzeptiert' in retry['message']:
                break
            time.sleep(.05)
        self.assertEqual(retry['state'], 'awaiting_code', retry)
        self.assertIn('nicht akzeptiert', retry['message'])
        self.assertIn('vollständigen Code', retry['message'])
        self.assertEqual(retry['id'], key)
        self.assertEqual(retry['profile'], name)
        self.assertEqual((self.db.authdir(name)/'fixture-parent.pid').read_text(), provider_pid)
        profile = next(p for p in self.call('profile', 'list') if p['name'] == name)
        self.assertFalse(profile['enabled'])
        account = next(a for a in self.call('status')['accounts'] if a['name'] == name)
        self.assertFalse(account['connected'])
        self.call('auth', 'input', key, '--code=fixture-authorized-code')
        self.wait_login(key, {'succeeded'})
        self.assertTrue(next(p for p in self.call('profile', 'list') if p['name'] == name)['enabled'])
        self.assertTrue(next(a for a in self.call('status')['accounts'] if a['name'] == name)['connected'])
        for path in self.home.rglob('*'):
            if path.is_file() and path.suffix in {'.json', '.input', '.log'}:
                for secret in (b'fixture-rejected-code', b'fixture-authorized-code'):
                    self.assertNotIn(secret, path.read_bytes(), str(path))

    def test_native_claude_rejected_code_remains_cancellable(self):
        import uuid
        name = self.native_fixture('claude')
        self.db.update_profile(name, enabled=False)
        (self.db.authdir(name)/'fixture-accepted').unlink()
        key = uuid.uuid4().hex
        self.sessions.append(key)
        self.call('auth', 'start', name, '--provider', 'claude', '--key', key)
        self.wait_login(key, {'awaiting_code'})
        self.call('auth', 'input', key, '--code=fixture-rejected-code')
        until = time.monotonic()+3
        while time.monotonic() < until:
            state = self.call('auth', 'get', key)
            if state['state'] == 'awaiting_code' and 'nicht akzeptiert' in state['message']:
                break
            time.sleep(.05)
        self.assertEqual(state['state'], 'awaiting_code', state)
        self.call('auth', 'cancel', key)
        self.wait_login(key, {'cancelled'})
        self.assertFalse(next(p for p in self.call('profile', 'list') if p['name'] == name)['enabled'])

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

    def test_unusable_native_lock_reports_error_without_busy_retry_loop(self):
        name = self.native_fixture()
        auth = self.db.authdir(name)
        (auth/'.native.lock').mkdir()
        job = self.db.submit('Never run with broken lock', self.workspace, 'codex', profile=name)
        self.call('work', '--once')
        current = self.db.job(job['id'])
        self.assertEqual(current['status'], 'needs_review', current)
        self.assertTrue(current['error'])
        self.assertFalse((auth/'fixture-executions.jsonl').exists())
        self.call('work', '--once')
        self.assertEqual(self.db.job(job['id'])['attempts'], 1)

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
