import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_pool.cli import main
from agent_pool.providers import Outcome, command, environment, parse_run, run_native
from agent_pool.quota import availability, claude_window, codex_windows, timestamp
from agent_pool.store import Store
from agent_pool.worker import choose, tick


class QuotaTests(unittest.TestCase):
    def window(self, used=100, reset=200, minutes=300, **extra):
        return {"key": "test", "used": used, "reset": reset, "minutes": minutes, **extra}

    def test_waits_for_latest_of_all_exhausted_windows(self):
        state = availability([self.window(reset=200), self.window(reset=800, minutes=10080)], 100)
        self.assertFalse(state["ready"])
        self.assertEqual(state["ready_at"], 800)

    def test_expired_window_does_not_mean_still_exhausted(self):
        self.assertTrue(availability([self.window(reset=99)], 100)["ready"])

    def test_missing_reset_stays_unknown(self):
        state = availability([self.window(reset=None)], 100)
        self.assertFalse(state["ready"])
        self.assertIsNone(state["ready_at"])

    def test_bucket_does_not_exhaust_other_model_bucket(self):
        self.assertTrue(availability([self.window(bucket="codex_other")], 100, bucket="codex")["ready"])

    def test_model_specific_claude_limits(self):
        w = self.window(model="opus")
        self.assertTrue(availability([w], 100, model="sonnet")["ready"])
        self.assertFalse(availability([w], 100, model="opus")["ready"])
        self.assertFalse(availability([w], 100)["ready"])

    def test_duration_is_not_inferred_from_primary_slot(self):
        parsed = codex_windows({"rateLimits": {"primary": {"usedPercent": 42, "windowDurationMins": 15, "resetsAt": 123}}})
        self.assertEqual(parsed[0]["minutes"], 15)

    def test_prefer_multi_bucket_payload_over_legacy_duplicate(self):
        parsed = codex_windows({"rateLimits": {"primary": {"usedPercent": 100}}, "rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 10, "windowDurationMins": 300, "resetsAt": 999}}}})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["used"], 10)

    def test_claude_native_event_fraction_and_model(self):
        w = claude_window({"rate_limit_info": {"rateLimitType": "seven_day_opus", "status": "allowed_warning", "utilization": .92, "resetsAt": 123}})
        self.assertEqual(w["used"], 92)
        self.assertEqual(w["model"], "opus")

    def test_rejected_event_without_utilization_is_exhausted(self):
        self.assertEqual(claude_window({"rate_limit_info": {"status": "rejected"}})["used"], 100)

    def test_manual_reset_requires_timezone(self):
        with self.assertRaises(ValueError):
            timestamp("2026-10-29T08:00:00")
        self.assertEqual(timestamp("1970-01-01T01:00:01+01:00"), 1)


class UnifiedClaudeLimitsTests(unittest.TestCase):
    def test_live_event_exposes_both_windows_through_native_outcome(self):
        event=json.loads((Path(__file__).parent/'fixtures/claude-unified-limits.json').read_text())
        payload=json.dumps(event)+'\n'+json.dumps({'type':'result','subtype':'success','is_error':False,'result':'OK'})
        outcome=parse_run('claude',payload,'',0)
        self.assertEqual(outcome.kind,'success')
        self.assertEqual([(w['key'],w['minutes'],w['used'],w['reset']) for w in outcome.windows],
                         [('five_hour',300,0,1793221200),('seven_day',10080,2,1793757600)])

    def outcome(self,info):
        return parse_run('claude',json.dumps({'type':'rate_limit_event','rate_limit_info':info}), '', 1)

    def test_rejected_limiting_window_does_not_exhaust_other_windows(self):
        out=self.outcome({'status':'rejected','rateLimitType':'five_hour','unifiedWindows':{
            'five_hour':{'status':'rejected','resetsAt':1000},
            'seven_day':{'status':'allowed','utilization':.02,'resetsAt':2000},
            'seven_day_opus':{'status':'allowed','utilization':.25,'resetsAt':2000},
            'overage':{'status':'rejected'}}})
        self.assertEqual([(w['key'],w['used'],w['model']) for w in out.windows],
                         [('five_hour',100,None),('seven_day',2,None),('seven_day_opus',25,'opus')])

    def test_legacy_event_without_unified_windows_remains_supported(self):
        out=self.outcome({'status':'allowed','rateLimitType':'five_hour','utilization':.5,'resetsAt':1000})
        self.assertEqual([(w['key'],w['used'],w['reset']) for w in out.windows],[('five_hour',50,1000)])

    def test_partial_unified_payload_retains_distinct_legacy_window(self):
        out=self.outcome({'status':'allowed','rateLimitType':'five_hour','utilization':.5,'resetsAt':1000,
                          'unifiedWindows':{'seven_day':{'utilization':.02,'resetsAt':2000}}})
        self.assertEqual([(w['key'],w['used']) for w in out.windows],[('seven_day',2),('five_hour',50)])


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "state"
        self.cwd = Path(self.temp.name) / "repo"
        self.cwd.mkdir()
        self.store = Store(self.home)
        self.store.add_profile("one", "codex", "codex")
        self.store.update_profile("one", enabled=True, checked_at=time.time())

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def submit(self, **kw):
        return self.store.submit("Inspect this project", str(self.cwd), "codex", **kw)

    def test_submit_is_persisted_across_connections(self):
        job = self.submit()
        other = Store(self.home)
        self.assertEqual(other.job(job["id"])["prompt"], "Inspect this project")
        other.close()

    def test_duplicate_key_returns_same_job(self):
        a = self.submit(key="unique")
        self.assertEqual(self.submit(key="unique")["id"], a["id"])
        with self.assertRaises(ValueError):
            self.store.submit("Different prompt", self.cwd, "codex", key="unique")

    def test_simultaneous_submitters_share_one_idempotent_task(self):
        def submitter(_):
            with_store = Store(self.home)
            try:
                return with_store.submit("same", self.cwd, "codex", key="concurrent")["id"]
            finally:
                with_store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(submitter, range(12)))
        self.assertEqual(len(set(ids)), 1)

    def test_routes_to_weekly_allowance_expiring_soonest(self):
        now = time.time()
        self.store.add_profile("two", "codex", "codex")
        self.store.update_profile("two", enabled=True)
        for name, reset in [("one", now+200), ("two", now+100)]:
            self.store.set_windows(name, [{"key": "weekly", "bucket": "codex", "minutes": 10080, "used": 20, "reset": reset}])
        selected, _ = choose(self.store, self.submit(), now)
        self.assertEqual(selected["name"], "two")

    def test_pinned_job_does_not_use_another_profile(self):
        self.store.add_profile("two", "codex", "codex")
        self.store.update_profile("two", enabled=True)
        self.store.update_profile("one", enabled=False)
        selected, reason = choose(self.store, self.submit(profile="one"), time.time())
        self.assertIsNone(selected)
        self.assertIn("one:disabled", reason)

    def test_provider_never_crosses(self):
        self.store.add_profile("claude-test", "claude", "claude")
        self.store.update_profile("claude-test", enabled=True)
        self.store.update_profile("one", enabled=False)
        self.assertIsNone(choose(self.store, self.submit(), time.time())[0])

    def test_success_returns_report_to_requester(self):
        job = self.submit()
        with self.store.worker_lock():
            tick(self.store, runner=lambda *args: Outcome("success", "Found three modules"))
        stored = self.store.job(job["id"])
        self.assertEqual(stored["status"], "succeeded")
        self.assertEqual(stored["result"], "Found three modules")
        self.assertEqual(stored["attempts"], 1)

    def test_exhausted_job_waits_without_consuming_attempt(self):
        now = time.time()
        job = self.submit()
        self.store.set_windows("one", [{"key": "limit", "bucket": "codex", "minutes": 300, "used": 100, "reset": now+100}])
        with self.store.worker_lock():
            self.assertFalse(tick(self.store, runner=lambda *args: self.fail("must not run"), now=now))
        self.assertEqual(self.store.job(job["id"])["attempts"], 0)
        self.assertEqual(self.store.job(job["id"])["status"], "waiting")
        with self.store.worker_lock():
            tick(self.store, runner=lambda *args: Outcome("success", "After reset"), probe=lambda *args: [], now=now+101)
        self.assertEqual(self.store.job(job["id"])["status"], "succeeded")

    def test_unknown_quota_error_holds_account_instead_of_repeated_retries(self):
        job = self.submit()
        def unavailable(*a):
            raise ValueError("No metadata")
        with self.store.worker_lock():
            tick(self.store, runner=lambda *a: Outcome("quota", error="usage_limit_reached"), probe=unavailable)
            tick(self.store, runner=lambda *a: self.fail("must not retry"), probe=unavailable)
        self.assertEqual(self.store.profile("one")["hold_reason"], "quota_reset_unknown")
        self.assertEqual(self.store.job(job["id"])["attempts"], 1)

    def test_quota_during_edit_requires_review(self):
        job = self.submit(allow_edits=True)
        with self.store.worker_lock():
            tick(self.store, runner=lambda *a: Outcome("quota", error="usage limit"), probe=lambda *a: [])
        self.assertEqual(self.store.job(job["id"])["status"], "needs_review")

    def test_crash_recovery_does_not_reexecute_running_task(self):
        job = self.submit()
        self.store.update_job(job["id"], status="running", attempts=1)
        self.assertEqual(self.store.recover(), 1)
        with self.store.worker_lock():
            self.assertFalse(tick(self.store, runner=lambda *a: self.fail("duplicate run")))
        self.assertEqual(self.store.job(job["id"])["status"], "needs_review")

    def test_timeout_needs_review_even_for_read_task(self):
        job = self.submit()
        with self.store.worker_lock():
            tick(self.store, runner=lambda *a: Outcome("uncertain", error="timeout"))
        self.assertEqual(self.store.job(job["id"])["status"], "needs_review")

    def test_second_worker_cannot_enter(self):
        with self.store.worker_lock():
            # Test OS locking with a distinct process, including on Windows.
            code = 'from pathlib import Path; from agent_pool.store import Store; import sys; s=Store(Path(sys.argv[1]));\nwith s.worker_lock(): pass'
            result = subprocess.run([sys.executable, "-c", code, str(self.home)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another worker", result.stderr)

    def test_unsafe_profile_path_rejected(self):
        for name in ("../escape", "a/b", "con", "aux"):
            with self.assertRaises(ValueError):
                self.store.add_profile(name, "codex", "codex")

    def test_unknown_quota_is_not_fabricated(self):
        self.assertEqual(self.store.windows("one"), [])
        self.assertTrue(choose(self.store, self.submit(), time.time())[0])


class ProviderTests(unittest.TestCase):
    def test_environment_isolated_and_ambient_api_credentials_removed(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret", "CODEX_HOME": "/wrong", "ANTHROPIC_BASE_URL": "https://wrong", "CLAUDE_CONFIG_DIR": "/wrong"}):
            env = environment("codex", Path("/isolated"))
        self.assertEqual(env["CODEX_HOME"], "/isolated")
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("ANTHROPIC_BASE_URL", env)
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)

    def test_model_prose_does_not_trigger_rate_limit_retry(self):
        raw = json.dumps({"type": "result", "subtype": "success", "result": "The bug is a rate limit", "is_error": False})
        self.assertEqual(parse_run("claude", raw, "", 0).kind, "success")

    def test_codex_requires_completion_even_with_exit_zero(self):
        self.assertEqual(parse_run("codex", "", "", 0, "Partial answer").kind, "failed")

    def test_claude_result_error_not_success_when_exit_zero(self):
        raw = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True, "errors": ["rate_limit"]})
        self.assertEqual(parse_run("claude", raw, "", 0).kind, "quota")

    def test_provider_tokens_redacted(self):
        raw = json.dumps({"type": "error", "message": "Bearer abc.secret"})
        self.assertNotIn("abc.secret", parse_run("codex", raw, "", 1).error)

    def test_native_command_uses_argv_and_stdin_marker(self):
        with patch("agent_pool.providers.executable", return_value="native"):
            cmd = command({"provider": "codex", "binary": "codex"}, {"allow_edits": False, "model": None}, Path("out"))
        self.assertEqual(cmd[-1], "-")
        self.assertIn("read-only", cmd)
        self.assertNotIn("danger-full-access", cmd)
