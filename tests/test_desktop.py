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

    def test_failed_update_stays_visible_until_a_successful_update(self):
        def settle():
            until = time.monotonic() + 2
            while self.app.refreshing and time.monotonic() < until:
                self.root.update()
                time.sleep(.01)
            self.assertFalse(self.app.refreshing)

        self.app.auto.set(False)
        self.app.refresh()
        settle()
        self.assertIsNotNone(self.app.last_refresh)

        def failed(*args):
            raise OSError("offline")
        self.app.refresh_fn = failed
        self.app.refresh()
        settle()
        failure_text = self.app.status_text.cget("text")
        self.assertIn("offline", failure_text)
        self.app._clock()
        self.assertEqual(self.app.status_text.cget("text"), failure_text)

        self.app.refresh_fn = lambda *args: self.accounts
        self.app.refresh()
        settle()
        self.app._clock()
        self.assertNotIn("offline", self.app.status_text.cget("text"))

    def test_provider_navigation_combines_with_search_and_connection_filter(self):
        claude = {**self.accounts[0], 'name': 'claude', 'provider': 'claude', 'email': 'opus@example.com'}
        self.app.accounts.append(claude)
        self.app.nav_buttons['claude'][0].invoke()
        self.assertEqual(self.app.rendered, ['claude'])
        self.assertEqual(self.app.page_title.cget('text'), 'Claude')
        self.app.search.set('two@example')
        self.assertEqual(self.app.rendered, [])
        self.app.provider_filter.set('codex')
        self.assertEqual(self.app.rendered, ['second'])
        self.app.search.set('')
        self.app.provider_filter.set('all')
        self.assertEqual(set(self.app.rendered), {'first', 'second', 'claude'})

    def test_weekly_only_account_does_not_invent_a_five_hour_balance(self):
        self.app.accounts[0]['windows'] = [{'minutes': 10080, 'bucket': 'codex', 'used': 33, 'reset': time.time()+1000}]
        self.app.render()
        card = self.app.card_views['first']
        self.assertIsNone(card['ring'].remaining)
        self.assertIsNone(card['primary'])
        self.assertEqual(len(card['extra']), 1)
        self.assertEqual(card['extra'][0][1]['remaining'], 67)

    def test_expired_and_unknown_balances_are_not_displayed_as_zero(self):
        self.app.accounts[0]['windows'][0]['reset'] = time.time()-1
        self.app.accounts[1]['windows'][0]['used'] = None
        self.app.render()
        self.assertIsNone(self.app.card_views['first']['ring'].remaining)
        self.assertIsNone(self.app.card_views['second']['ring'].remaining)
        self.app.accounts[0]['windows'][0].update(used=100, reset=time.time()+1000)
        self.app.render()
        self.assertEqual(self.app.card_views['first']['ring'].remaining, 0)

    def test_exhausted_week_does_not_erase_the_five_hour_balance(self):
        self.app.accounts[0]['windows'].append({'minutes': 10080, 'bucket': 'codex', 'used': 100, 'reset': time.time()+1000})
        self.app.render()
        card = self.app.card_views['first']
        self.assertEqual(card['ring'].remaining, 75)
        self.assertEqual(card['extra'][0][1]['remaining'], 0)
        self.assertEqual(card['status'], 'Limit erreicht')

    def test_clock_invalidates_a_ring_at_reset_even_with_auto_refresh_off(self):
        from unittest.mock import patch
        now = time.time()
        self.app.accounts[0]['windows'][0]['reset'] = now+5
        self.app.auto.set(False)
        self.app.render()
        self.assertEqual(self.app.card_views['first']['ring'].remaining, 75)
        with patch('time.time', return_value=now+6):
            self.app._clock()
        self.assertIsNone(self.app.card_views['first']['ring'].remaining)

    def test_narrow_window_keeps_navigation_and_actions_inside_the_viewport(self):
        self.root.deiconify()
        def resize(width):
            self.root.geometry(f'{width}x700')
            until = time.monotonic()+.3
            while time.monotonic() < until:
                self.root.update()
                time.sleep(.01)
        resize(760)
        self.assertTrue(self.app._compact)
        self.assertFalse(self.app.sidebar.winfo_ismapped())
        self.assertTrue(self.app.compact_bar.winfo_ismapped())
        self.assertEqual(self.app.column_count, 1)
        for widget in [self.app.refresh_button, self.app.search_entry, self.app.scope_button]:
            self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), self.root.winfo_rootx()+self.root.winfo_width())
        resize(1000)
        self.assertFalse(self.app._compact)
        self.assertEqual(self.app.column_count, 2)
        resize(1280)
        self.assertEqual(self.app.column_count, 3)

    def test_close_cancels_scheduled_callbacks(self):
        self.app.render()
        self.assertTrue(self.app._after_ids)
        self.app.close()
        self.assertFalse(self.app._after_ids)
        self.app.close()  # Native close and quit can arrive together.

    def test_switching_from_a_running_refresh_to_missing_server_keeps_retry_usable(self):
        release = threading.Event()
        def slow(*args):
            release.wait(timeout=3)
            return self.accounts
        self.app.refresh_fn = slow
        self.app.refresh()
        self.assertEqual(str(self.app.refresh_button.cget('state')), 'disabled')
        try:
            self.app.target.set('missing')
            self.app._select_target()
            self.assertFalse(self.app.refreshing)
            self.assertIsNotNone(self.app.refresh_error)
            self.assertNotEqual(str(self.app.refresh_button.cget('state')), 'disabled')
        finally:
            release.set()

    def test_connected_account_without_email_is_not_labelled_signed_out(self):
        self.accounts[0]['email']=None
        self.app.accounts=[self.accounts[0]];self.app.render();self.root.update()
        def labels(widget):
            values=[]
            try:values.append(widget.cget('text'))
            except tk.TclError:pass
            for child in widget.winfo_children():values.extend(labels(child))
            return values
        self.assertNotIn('Nicht angemeldet',labels(self.root))
        self.assertIn('Verbunden',labels(self.root))
