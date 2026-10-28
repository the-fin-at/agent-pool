"""Exercise task submission and target switching in a real Tk event loop."""
import tempfile
import time
import unittest
from pathlib import Path
try:
    import tkinter as tk
    from agent_pool.desktop import Dashboard
    from agent_pool.manager import Manager
except ImportError:
    tk=None
from agent_pool.store import Store
from agent_pool.remote import RemoteConfig


@unittest.skipIf(tk is None, 'Python runtime has no Tk')
class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        try:self.root=tk.Tk()
        except tk.TclError as exc:
            self.tmp.cleanup();self.skipTest(str(exc))
        self.root.withdraw()
        self.home=Path(self.tmp.name)/'state'
        self.store=Store(self.home)
        self.store.add_workspace('demo',self.tmp.name)
        self.windows=[]

    def tearDown(self):
        for window in self.windows:
            if not window.closed:window.close()
        try:self.root.destroy()
        except tk.TclError:pass
        self.store.close()
        self.tmp.cleanup()

    def settle(self, manager):
        until=time.monotonic()+3
        while manager.busy and time.monotonic()<until:
            self.root.update();time.sleep(.01)
        self.assertFalse(manager.busy)

    def test_manager_submits_and_rotates_key_after_acknowledged_success(self):
        manager=Manager(self.root,self.home)
        self.windows.append(manager)
        self.settle(manager)
        manager.prompt.insert('1.0','Prüfe den Code')
        oldkey=manager.key.get()
        manager.submit();self.settle(manager)
        jobs=self.store.jobs()
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['prompt'],'Prüfe den Code')
        self.assertEqual(jobs[0]['idempotency_key'],oldkey)
        self.assertNotEqual(manager.key.get(),oldkey)
        self.assertEqual(jobs[0]['status'],'queued')

    def test_old_server_response_cannot_overwrite_new_target(self):
        app=Dashboard(self.root,self.home,initial=[],start_refresh=False)
        self.windows.append(app)
        app.target_epoch=2
        app.events.put(('data',[{'name':'old-server'}],1))
        app._poll()
        self.assertEqual(app.accounts,[])

    def test_missing_remote_configuration_leaves_refresh_controls_usable(self):
        app=Dashboard(self.root,self.home,initial=[],start_refresh=False)
        self.windows.append(app)
        app.remote='missing'
        app.refresh()
        self.assertFalse(app.refreshing)
        self.assertIsNotNone(app.refresh_error)
        self.assertNotEqual(str(app.refresh_button.cget('state')),'disabled')
