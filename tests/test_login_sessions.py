import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from agent_pool import login_sessions as login
from agent_pool.rpc import handle
from agent_pool.store import Store,file_lock


class LoginValidationTests(unittest.TestCase):
    def test_only_official_https_login_hosts_are_openable(self):
        for url in ['https://auth.openai.com/codex/device','https://claude.com/oauth/authorize?state=x']:
            self.assertTrue(login.safe_url(url))
        for url in ['file:///etc/passwd','http://claude.com','https://claude.com.evil.test','https://user@claude.com','https://claude.com:8000','https://claude.com:bad']:
            self.assertFalse(login.safe_url(url))

    def test_observer_extracts_only_public_native_login_instructions(self):
        data=login.observe('codex','\x1b[32mOpen https://auth.openai.com/codex/device\x1b[0m\nABCD-EFGHI\nBearer secret-token')
        self.assertEqual(data['device_code'],'ABCD-EFGHI')
        self.assertNotIn('secret-token',json.dumps(data))
        self.assertEqual(login.observe('claude','Visit https://evil.example/steal\nPaste code here'),{})
        self.assertEqual(login.observe('claude','Visit https://claude.com/oauth/authorize?state=x\nPaste code here')['state'],'awaiting_code')

    def test_invalid_session_ids_cannot_traverse_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in ['../auth','/etc/passwd','x'*32,'a'*33]:
                with self.assertRaises(ValueError):login.paths(tmp,value)

    def test_codes_cannot_be_read_from_server_files_via_rpc(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=handle(tmp,{'version':1,'argv':['auth','input','a'*32,'--code-file','/etc/passwd']})
            self.assertEqual(result['code'],1)

    def test_stale_login_is_expired_without_exposing_url_or_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            ident='a'*32;state,_,_=login.paths(tmp,ident)
            login.write_private(state,{'id':ident,'state':'awaiting_browser','created_at':time.time()-100,'updated_at':time.time()-100,'expires_at':time.time()+20,'url':'https://auth.openai.com/codex/device','device_code':'ABCD-EFGHI'})
            data=login.status(tmp,ident)
            self.assertEqual(data['state'],'expired');self.assertIsNone(data['url']);self.assertIsNone(data['device_code'])

    def test_verification_does_not_accept_an_api_key_as_subscription_login(self):
        with tempfile.TemporaryDirectory() as tmp, patch('agent_pool.login_sessions.executable',return_value='codex'), patch('agent_pool.login_sessions.subprocess.run',return_value=subprocess.CompletedProcess([],0,'Logged in using API key','')):
            with self.assertRaises(ValueError):login.verify({'provider':'codex','binary':'codex'},Path(tmp))


@unittest.skipIf(os.name=='nt','Executable fixture uses POSIX shebang; Windows process APIs unit-tested separately')
class NativeLoginProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.home=self.root/'state'
        self.store=Store(self.home)
        self.binary=self.root/'native-cli'
        self.binary.write_text('#!'+sys.executable+'\n'+Path(__file__).with_name('fake_login.py').read_text())
        self.binary.chmod(0o755);self.sessions=[]

    def tearDown(self):
        for ident in self.sessions:
            try:login.cancel(self.home,ident)
            except (ValueError,OSError):pass
        until=time.monotonic()+2
        while time.monotonic()<until:
            if all(login.status(self.home,x)['state'] not in login.ACTIVE for x in self.sessions):break
            time.sleep(.05)
        self.store.close();self.tmp.cleanup()

    def start(self,provider):
        name='test-'+provider
        self.store.add_profile(name,provider,str(self.binary))
        key=uuid.uuid4().hex;self.sessions.append(key)
        data=login.start(self.home,name,provider,key)
        self.assertEqual(data['id'],key)
        return name,key

    def wait(self,ident,states):
        until=time.monotonic()+10
        while time.monotonic()<until:
            data=login.status(self.home,ident)
            if data['state'] in states:return data
            if data['state'] in {'failed','expired'}:self.fail(str(data))
            time.sleep(.05)
        self.fail('Login did not reach '+repr(states)+': '+str(data))

    def test_device_login_survives_client_process_end_and_refreshes_real_read_model(self):
        name,key=self.start('codex')
        data=self.wait(key,{'awaiting_browser'})
        self.assertEqual(data['device_code'],'ABCD-EFGHI')
        # Browser confirmation is controlled by the provider fixture, not broker credentials.
        (self.store.authdir(name)/'fixture-accepted').write_text('fixture-only')
        done=self.wait(key,{'succeeded'})
        self.assertIsNone(done['device_code']);self.assertIsNone(done['url'])
        self.assertTrue(self.store.profile(name)['enabled'])
        until=time.monotonic()+3
        while not self.store.cached_monitor(name).get('connected') and time.monotonic()<until:time.sleep(.05)
        self.assertEqual(self.store.cached_monitor(name)['email'],'fixture@example.invalid')
        self.assertEqual(login.start(self.home,name,'codex',key)['state'],'succeeded')
        self.assertEqual(len(list(login.folder(self.home).glob('*.json'))),1)

    def test_claude_browser_code_round_trip_and_allowlisted_identity(self):
        name,key=self.start('claude')
        self.wait(key,{'awaiting_code'})
        login.provide_code(self.home,key,'fixture-authorized-code')
        done=self.wait(key,{'succeeded'})
        self.assertEqual(self.store.cached_monitor(name)['email'],'fixture@example.invalid')
        self.assertTrue(self.store.profile(name)['enabled'])
        self.assertFalse(login.paths(self.home,key)[1].exists())
        self.assertNotIn('fixture-authorized-code',login.paths(self.home,key)[0].read_text())
        if os.name!='nt':self.assertEqual(login.paths(self.home,key)[0].stat().st_mode&0o777,0o600)

    def test_cancel_stops_native_process_and_does_not_enable_account(self):
        name,key=self.start('codex');self.wait(key,{'awaiting_browser'})
        pid=int((self.store.authdir(name)/'fixture-native.pid').read_text())
        login.cancel(self.home,key);self.wait(key,{'cancelled'})
        until=time.monotonic()+2
        while time.monotonic()<until:
            try:os.kill(pid,0)
            except ProcessLookupError:break
            time.sleep(.05)
        else:self.fail('Native login process survived cancellation')
        self.assertFalse(self.store.profile(name)['enabled'])

    def test_account_busy_fails_without_interfering_with_existing_worker(self):
        name='test-codex';self.store.add_profile(name,'codex',str(self.binary));key=uuid.uuid4().hex;self.sessions.append(key)
        with file_lock(self.store.authdir(name)/'.native.lock'):
            login.start(self.home,name,'codex',key)
            until=time.monotonic()+4
            while time.monotonic()<until:
                data=login.status(self.home,key)
                if data['state']=='failed':break
                time.sleep(.05)
            self.assertEqual(data['state'],'failed')
        self.assertFalse((self.store.authdir(name)/'fixture-native.pid').exists())

    def test_cancel_before_start_prevents_a_late_native_login(self):
        name='test-codex';self.store.add_profile(name,'codex',str(self.binary))
        key=uuid.uuid4().hex;self.sessions.append(key)
        login.cancel(self.home,key)
        result=login.start(self.home,name,'codex',key)
        self.assertEqual(result['state'],'cancelled')
        self.assertFalse((self.store.authdir(name)/'fixture-native.pid').exists())

    def test_existing_enabled_account_is_not_disabled_by_pending_or_cancelled_login(self):
        name='test-codex';self.store.add_profile(name,'codex',str(self.binary));self.store.update_profile(name,enabled=True)
        key=uuid.uuid4().hex;self.sessions.append(key)
        login.start(self.home,name,'codex',key);self.wait(key,{'awaiting_browser'})
        self.assertTrue(self.store.profile(name)['enabled'])
        self.store.update_profile(name,enabled=False)
        login.cancel(self.home,key);self.wait(key,{'cancelled'})
        self.assertFalse(self.store.profile(name)['enabled'])
