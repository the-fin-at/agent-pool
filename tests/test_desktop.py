"""Native window behavior, skipped only when Tk/display is not available."""
import tempfile
import subprocess
import sys
import json
import threading
import time
import unittest
from pathlib import Path

try:
    import tkinter as tk
    from agent_pool.desktop import Dashboard
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "Python runtime has no Tk")
class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.temp.cleanup()
            self.skipTest(str(exc))
        self.root.withdraw()
        now = time.time()
        def account(name, email, connected=True):
            return {"name": name, "email": email, "provider": "codex", "managed": True,
                    "connected": connected, "enabled": connected, "plan": "team", "error": None,
                    "observed_at": now, "windows": [{"minutes": 300, "bucket": "codex", "used": 25, "reset": now + 500}] if connected else []}
        self.accounts = [account("first", "one@example.com"), account("second", "two@example.com"),
                         account("empty", None, False)]
        self.app = Dashboard(self.root, Path(self.temp.name), initial=self.accounts,
                             refresh_fn=lambda *a: self.accounts, start_refresh=False)
        self.root.update()

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.close()
        self.temp.cleanup()

    def test_search_and_connection_filter_show_matching_accounts(self):
        self.assertEqual(set(self.app.rendered), {"first", "second"})
        self.app.search.set("two@example")
        self.assertEqual(self.app.rendered, ["second"])
        self.app.search.set("")
        self.app.show_all.set(True)
        self.app.render()
        self.assertEqual(set(self.app.rendered), {"first", "second", "empty"})

    def test_search_remains_responsive_while_provider_read_is_blocked(self):
        release = threading.Event()
        entered = threading.Event()
        def slow(*args):
            entered.set()
            release.wait(timeout=3)
            return self.accounts
        self.app.refresh_fn = slow
        self.app.refresh()
        self.assertTrue(entered.wait(timeout=1))
        self.app.search.set("one@example")
        self.root.update()
        self.assertEqual(self.app.rendered, ["first"])
        self.assertTrue(self.app.refreshing)
        release.set()
        until = time.monotonic() + 2
        while self.app.refreshing and time.monotonic() < until:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app.refreshing)
        self.assertIsNotNone(self.app.last_refresh)

    def test_refresh_failure_reenables_controls_and_keeps_accounts(self):
        def failed(*args):
            raise OSError("offline")
        self.app.refresh_fn = failed
        self.app.refresh()
        until = time.monotonic() + 2
        while self.app.refreshing and time.monotonic() < until:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app.refreshing)
        self.assertEqual(len(self.app.accounts), 3)
        self.assertIn("offline", self.app.status_text.cget("text"))

    def test_mapped_window_reaches_requested_geometry(self):
        # A fresh process and mainloop reproduce first-window mapping, unlike update().
        script = """import json,sys,tkinter as tk
from pathlib import Path
from agent_pool.desktop import Dashboard
root=tk.Tk()
app=Dashboard(root,Path(sys.argv[1]),initial=json.loads(sys.stdin.read()),start_refresh=False)
def inspect():
 print(json.dumps({'width':root.winfo_width(),'height':root.winfo_height()}),flush=True)
 app.close()
root.after(400,inspect)
root.mainloop()
"""
        result = subprocess.run([sys.executable, "-c", script, self.temp.name],
                                input=json.dumps(self.accounts), text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        size = json.loads(result.stdout)
        self.assertGreaterEqual(size["width"], 760)
        self.assertGreaterEqual(size["height"], 560)
