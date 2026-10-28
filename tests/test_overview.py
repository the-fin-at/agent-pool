"""Overview interaction contract: context switch, connections and integrated login, no task modals."""
import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
try:
    import tkinter as tk
    from agent_pool.desktop import Dashboard
except ImportError:
    tk=None
from agent_pool.remote import RemoteConfig


@unittest.skipIf(tk is None,'Tk is not available')
class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.tmp.cleanup();self.skipTest(str(exc))
        self.root.withdraw()
        now=time.time()
        self.accounts=[{'name':'local-one','email':'local@example.invalid','provider':'codex','managed':True,'connected':True,'enabled':True,'plan':'team','observed_at':now,'windows':[]}]
        self.app=Dashboard(self.root,self.home,initial=self.accounts,refresh_fn=lambda home:self.accounts,start_refresh=False)
        self.app.auto.set(False)
        self.root.update()

    def tearDown(self):
        with patch('agent_pool.login_sessions.launch_cancel'):
            self.app.close()
        self.tmp.cleanup()

    def settle(self,predicate,seconds=3):
        until=time.monotonic()+seconds
        while not predicate() and time.monotonic()<until:self.root.update();time.sleep(.01)
        self.assertTrue(predicate())

    def texts(self,widget):
        result=[]
        try:result.append(widget.cget('text'))
        except tk.TclError:pass
        for child in widget.winfo_children():result.extend(self.texts(child))
        return result

    def test_context_menu_matches_local_remote_pattern_and_uses_no_toplevel(self):
        self.app.scope_button.invoke();self.root.update()
        self.assertIsNotNone(self.app.scope_menu)
        self.assertEqual(set(self.app.scope_options),{'local','remote'})
        self.assertTrue(self.app.scope_options['local'].instate(['selected']))
        self.assertFalse(any(isinstance(w,tk.Toplevel) for w in self.root.winfo_children()))
        self.app.close_scope_menu();self.assertIsNone(self.app.scope_menu)

    def test_remote_scope_does_not_mix_in_local_accounts(self):
        self.app.scope_button.invoke();self.app.scope_options['remote'].invoke()
        self.root.update()
        self.assertEqual(self.app.scope,'remote')
        self.assertEqual(self.app.page,'connections')
        self.assertEqual(self.app.accounts,[])
        self.assertEqual(self.app.rendered,[])
        self.assertEqual(self.app.page_title.cget('text'),'Verbindungen')
        self.assertNotIn('Auf diesem Rechner',self.app.worker_text.cget('text'))
        self.app.select_scope('local')
        self.settle(lambda:not self.app.refreshing)
        self.assertEqual(self.app.rendered,['local-one'])

    def test_overview_exposes_no_task_composer_or_technical_target_picker(self):
        text=self.texts(self.root)
        self.assertNotIn('Aufträge',text)
        self.assertNotIn('Ausführen auf',text)
        self.assertFalse(hasattr(self.app,'target_pickers'))
        self.assertFalse(hasattr(self.app,'open_manager'))

    def test_add_connection_is_one_integrated_form_without_simpledialogs(self):
        self.app.add_server();self.root.update()
        self.assertEqual(self.app.page,'connect')
        self.assertEqual(set(self.app.connection_form),{'name','host','command','home'})
        self.assertFalse(self.app.connection_advanced.get())
        self.assertFalse(any(isinstance(w,tk.Toplevel) for w in self.root.winfo_children()))
        self.app.save_connection()
        self.assertIsNotNone(self.app.form_error)
        self.assertFalse(self.app.form_busy)

    def test_discovery_saves_only_a_verified_connection_and_selects_it(self):
        self.app.add_server()
        self.app.connection_form['name'].set('central');self.app.connection_form['host'].set('pool-host')
        remote={'host':'pool-host','command':'/usr/bin/agent-fleet','home':'/srv/pool'}
        data={'accounts':[],'worker':{'online':True},'pending_jobs':0,'features':['native-login-sessions']}
        with patch('agent_pool.overview_panels.discover',return_value=remote),patch('agent_pool.overview_panels.RemoteClient.data',return_value=data),patch('agent_pool.remote.RemoteClient.data',return_value=data):
            self.app.save_connection()
            self.settle(lambda:not self.app.form_busy)
            self.settle(lambda:not self.app.refreshing)
        self.assertEqual(RemoteConfig(self.home).get('central'),remote)
        self.assertEqual(self.app.remote,'central')
        self.assertEqual(self.app.page,'accounts')

    def test_failed_connection_stays_in_form_and_does_not_save_config(self):
        self.app.add_server();self.app.connection_form['name'].set('central');self.app.connection_form['host'].set('host')
        with patch('agent_pool.overview_panels.discover',side_effect=ValueError('SSH offline')):
            self.app.save_connection();self.settle(lambda:not self.app.form_busy)
        self.assertEqual(self.app.page,'connect');self.assertIn('offline',self.app.form_error)
        self.assertEqual(RemoteConfig(self.home).all(),{})

    def test_account_details_are_inline_and_not_a_messagebox(self):
        from agent_pool.monitor import account_view
        self.app.details(account_view(self.accounts[0]));self.root.update()
        self.assertEqual(self.app.page,'details')
        self.assertFalse(any(isinstance(w,tk.Toplevel) for w in self.root.winfo_children()))
        self.app.go_back();self.assertEqual(self.app.page,'accounts')

    def test_login_poll_does_not_recreate_code_entry_or_steal_focus(self):
        self.app.show_login()
        self.app.login_state={'id':self.app.login_key,'profile':'claude-one','provider':'claude','state':'awaiting_code','message':'Code eingeben','url':'https://claude.com/oauth/authorize?state=fixture','device_code':None,'updated_at':1}
        self.app.render();entry=self.app.login_code_entry
        self.app.login_form['code'].set('half-entered')
        self.app.handle_panel_event({'kind':'login','token':self.app.login_key,'data':{**self.app.login_state,'updated_at':2}})
        self.assertEqual(self.app.login_code_entry,entry)
        self.assertEqual(self.app.login_form['code'].get(),'half-entered')

    def test_stale_login_reply_cannot_override_another_login(self):
        self.app.show_login();old=self.app.login_key
        self.app.show_login();self.assertNotEqual(self.app.login_key,old)
        self.app.handle_panel_event({'kind':'login','token':old,'data':{'state':'succeeded'}})
        self.assertIsNone(self.app.login_state)

    def test_only_one_login_poll_timer_and_one_inflight_read_exist(self):
        self.app.show_login()
        self.app.login_state={'id':self.app.login_key,'profile':'one','provider':'codex','state':'awaiting_browser','message':'Anmelden','url':None,'device_code':None,'updated_at':1}
        self.app.schedule_login_poll();first=self.app.login_poll_id
        self.app.schedule_login_poll();second=self.app.login_poll_id
        self.assertNotEqual(first,second)
        self.assertNotIn(first,self.root.tk.call('after','info'))
        self.assertIn(second,self.root.tk.call('after','info'))
        self.app.cancel_login_timer()
        with patch.object(self.app,'run_panel_action') as action:
            self.app.poll_login(self.app.login_key)
            self.app.poll_login(self.app.login_key)
        self.assertEqual(action.call_count,1)

    def test_leaving_login_cancels_the_server_session_and_invalidates_replies(self):
        self.app.show_login();key=self.app.login_key
        self.app.login_state={'id':key,'profile':'one','provider':'codex','state':'awaiting_browser'}
        with patch.object(self.app,'run_panel_action') as action:
            self.app.go_back()
        self.assertEqual(action.call_args.args[:2],('abandon_login',key))
        self.assertIsNone(self.app.login_key)
        self.assertEqual(self.app.page,'accounts')

    @unittest.skipIf(__import__('os').name=='nt','Executable native fixture uses a POSIX shebang')
    def test_real_ui_to_native_device_login_to_connected_account(self):
        import sys
        from agent_pool.store import Store
        from agent_pool.monitor import collect
        binary=self.home/'native-cli'
        binary.write_text('#!'+sys.executable+'\n'+Path(__file__).with_name('fake_login.py').read_text())
        binary.chmod(0o755)
        store=Store(self.home)
        store.add_profile('ui-account','codex',str(binary))
        self.app.local_refresh_fn=lambda home:collect(home,include_default=False)
        self.app.refresh_fn=self.app.local_refresh_fn
        self.app.show_login({'name':'ui-account','provider':'codex'})
        self.app.login_start_button.invoke()
        self.settle(lambda:self.app.login_state is not None and self.app.login_state['state']=='awaiting_browser',seconds=10)
        self.assertEqual(self.app.login_state['device_code'],'ABCD-EFGHI')
        with patch('agent_pool.overview_panels.webbrowser.open') as browser:
            self.app.open_login_url()
        browser.assert_called_once_with('https://auth.openai.com/codex/device')
        (store.authdir('ui-account')/'fixture-accepted').write_text('fixture-only')
        self.settle(lambda:self.app.login_state['state']=='succeeded',seconds=10)
        self.app.finish_login()
        self.settle(lambda:not self.app.refreshing)
        self.assertIn('ui-account',self.app.rendered)
        self.assertTrue(self.app.accounts[0]['connected'])
        self.assertEqual(self.app.accounts[0]['email'],'fixture@example.invalid')
        store.close()

    def test_integrated_forms_reset_account_column_groups_and_fill_the_viewport(self):
        self.root.deiconify();self.root.geometry('1280x900')
        self.app.show_connection_form()
        until=time.monotonic()+.3
        while time.monotonic()<until:self.root.update();time.sleep(.01)
        for index in range(3):
            self.assertIn(self.app.cards.grid_columnconfigure(index)['uniform'],('',None))
        self.assertGreater(self.app.connection_name_entry.winfo_width(),600)
        self.app.show_login()
        until=time.monotonic()+.3
        while time.monotonic()<until:self.root.update();time.sleep(.01)
        self.assertGreater(self.app.login_name_entry.winfo_width(),600)
