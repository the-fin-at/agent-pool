import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_pool.monitor import DEFAULT_SOURCE, account_view, collect, read_source, snapshot, sources, window_view
from agent_pool.store import Store


def window(used=25, reset=2000, minutes=300):
    return {"key": "codex:primary", "bucket": "codex", "used": used, "reset": reset, "minutes": minutes}


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "state"
        self.store = Store(self.home)
        self.store.add_profile("test-codex", "codex", "codex")
        self.store.update_profile("test-codex", enabled=True)
        self.source = sources(self.store, include_default=False)[0]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_live_metadata_updates_shared_quotas_without_changing_enabled_state(self):
        self.store.update_profile("test-codex", enabled=False)
        data = read_source(self.home, self.source, probe=lambda *a: {
            "connected": True, "email": "one@example.com", "plan": "team", "windows": [window()], "error": None})
        self.assertEqual(data["email"], "one@example.com")
        self.assertEqual(self.store.windows("test-codex")[0]["used"], 25)
        self.assertFalse(self.store.profile("test-codex")["enabled"])

    def test_refresh_failure_preserves_last_observation_with_error(self):
        read_source(self.home, self.source, probe=lambda *a: {
            "connected": True, "email": "one@example.com", "windows": [window()], "error": None})
        def failing(*a):
            raise OSError("Offline")
        result = read_source(self.home, self.source, probe=failing)
        self.assertEqual(result["windows"][0]["used"], 25)
        self.assertEqual(result["error"], "Offline")
        model = account_view(snapshot(self.home, include_default=False)[0], now=1000)
        self.assertEqual(model["status_label"], "Stand prüfen")

    def test_changed_identity_never_inherits_old_quota_if_read_fails(self):
        read_source(self.home, self.source, probe=lambda *a: {
            "connected": True, "email": "one@example.com", "windows": [window()], "error": None})
        read_source(self.home, self.source, probe=lambda *a: {
            "connected": True, "email": "two@example.com", "windows": None, "error": "Cannot fetch"})
        result = snapshot(self.home, include_default=False)[0]
        self.assertEqual(result["email"], "two@example.com")
        self.assertEqual(result["windows"], [])

    def test_logged_out_profile_does_not_display_previous_account_quota(self):
        read_source(self.home, self.source, probe=lambda *a: {
            "connected": True, "email": "one@example.com", "windows": [window()], "error": None})
        read_source(self.home, self.source, probe=lambda *a: {
            "connected": False, "email": None, "windows": None, "error": None})
        self.assertEqual(snapshot(self.home, include_default=False)[0]["windows"], [])

    def test_default_native_account_is_monitor_only_not_a_managed_profile(self):
        default = Path(self.temp.name) / "native-codex"
        default.mkdir()
        with patch.dict("os.environ", {"CODEX_HOME": str(default)}):
            items = sources(self.store)
        main = next(x for x in items if x["name"] == DEFAULT_SOURCE)
        self.assertFalse(main["managed"])
        self.assertFalse(main["enabled"])
        self.assertEqual(len(self.store.profiles()), 1)

    def test_worker_quota_newer_than_desktop_cache_is_displayed(self):
        read_source(self.home, self.source, probe=lambda *a: {
            "connected": True, "email": "one@example.com", "windows": [window()], "error": None})
        self.store.set_windows("test-codex", [window(used=75)])
        self.assertEqual(snapshot(self.home, include_default=False)[0]["windows"][0]["used"], 75)

    def test_claude_uses_saved_windows_and_never_codex_probe(self):
        self.store.add_profile("test-claude", "claude", "claude")
        self.store.update_profile("test-claude", enabled=True)
        self.store.set_windows("test-claude", [{**window(), "bucket": "claude"}])
        source = next(x for x in sources(self.store, include_default=False) if x["provider"] == "claude")
        read_source(self.home, source, probe=lambda *a: self.fail("private Claude read"))
        account = next(x for x in snapshot(self.home, False) if x["provider"] == "claude")
        self.assertTrue(account["connected"])
        self.assertEqual(account["windows"][0]["used"], 25)

    def test_collect_queries_all_profiles_concurrently_and_persists_results(self):
        result = collect(self.home, include_default=False, probe=lambda *a: {
            "connected": True, "email": "one@example.com", "plan": "plus", "windows": [window()], "error": None})
        self.assertEqual(result[0]["email"], "one@example.com")
        self.assertEqual(self.store.cached_monitor("test-codex")["plan"], "plus")

    def test_cache_rejects_secret_fields(self):
        with self.assertRaises(ValueError):
            self.store.cache_monitor("test-codex", {"access_token": "never stored"})

    def test_expired_snapshot_is_never_rendered_as_free_quota(self):
        state = window_view(window(used=99, reset=1000), now=1001)
        self.assertIsNone(state["remaining"])
        self.assertTrue(state["expired"])

    def test_unknown_quota_stays_unknown(self):
        self.assertIsNone(window_view({"used": None}, now=1000)["remaining"])

    def test_model_bucket_and_nonstandard_duration_stay_visible(self):
        result = window_view({**window(minutes=60), "bucket": "codex_other", "model": "opus"}, now=1000)
        self.assertIn("60 Minuten", result["title"])
        self.assertIn("codex_other", result["title"])

    def test_reported_usage_converted_to_remaining_percent(self):
        self.assertEqual(window_view(window(used=31), now=1000)["remaining"], 69)
