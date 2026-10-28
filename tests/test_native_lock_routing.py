"""Queue liveness through real native locks and controlled provider subprocesses."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agent_pool.providers import run_native
from agent_pool.store import Store, file_lock
from agent_pool.worker import tick

FIXTURE = Path(__file__).with_name("fake_native.py").resolve()


class NativeLockRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agent-fleet-lock-routing-")
        self.root = Path(self.tmp.name)
        self.now = time.time()
        self.store = Store(self.root / "pool")
        for name, provider in [("a", "codex"), ("b", "codex"), ("claude", "claude")]:
            self.store.add_profile(name, provider, "controlled-native")
            self.store.update_profile(name, enabled=True, checked_at=self.now)
        # A wins normal weekly-reset preference; B is the eligible alternative.
        for name, reset in [("a", 300), ("b", 600)]:
            self.store.set_windows(name, [{"key": "week", "bucket": "codex", "minutes": 10080,
                                           "used": 10, "reset": self.now + reset}])

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def submit(self, provider="codex", **kwargs):
        return self.store.submit("Read isolated fixture", self.root, provider, timeout=5, **kwargs)

    def run_tick(self):
        visited = []

        def native(profile, job, authdir):
            visited.append(profile["name"])
            self.assertLessEqual(len(visited), 3, "A busy profile must not spin within one tick")
            return run_native(profile, job, authdir)

        # Only the external CLI invocation is replaced. Locks, runner, process,
        # stream parsing and queue transitions are real.
        def argv(profile, job, final_path):
            return [sys.executable, str(FIXTURE), profile["provider"]]

        with self.store.worker_lock(), patch("agent_pool.providers.command", side_effect=argv):
            progressed = tick(self.store, runner=native, now=self.now)
        return progressed, visited

    def test_pinned_busy_profile_does_not_block_later_independent_provider(self):
        first = self.submit(profile="a")
        second = self.submit("claude")
        with file_lock(self.store.authdir("a") / ".native.lock"):
            progressed, _ = self.run_tick()
        self.assertTrue(progressed)
        self.assertEqual(self.store.job(first["id"])["status"], "waiting")
        self.assertEqual(self.store.job(first["id"])["attempts"], 0)
        self.assertEqual(self.store.job(second["id"])["status"], "succeeded")
        self.assertEqual(self.store.job(second["id"])["chosen_profile"], "claude")
        self.assertEqual(self.store.job(second["id"])["result"], "Worker report: Read isolated fixture")

    def test_unpinned_busy_profile_yields_to_free_same_provider(self):
        job = self.submit()
        with file_lock(self.store.authdir("a") / ".native.lock"):
            progressed, _ = self.run_tick()
        current = self.store.job(job["id"])
        self.assertTrue(progressed)
        self.assertEqual(current["status"], "succeeded")
        self.assertEqual(current["chosen_profile"], "b")
        self.assertEqual(current["attempts"], 1)
        self.assertEqual(current["result"], "Worker report: Read isolated fixture")
        self.assertIsNone(self.store.profile("a")["hold_reason"])

    def test_all_busy_returns_bounded_idle_without_attempts_then_recovers(self):
        job = self.submit()
        with ExitStack() as locks:
            for name in ["a", "b"]:
                locks.enter_context(file_lock(self.store.authdir(name) / ".native.lock"))
            started = time.monotonic()
            for _ in range(3):
                progressed, visited = self.run_tick()
                self.assertFalse(progressed)
                self.assertEqual(visited, ["a", "b"])
                self.assertEqual(self.store.job(job["id"])["attempts"], 0)
            self.assertLess(time.monotonic() - started, 2)
        # Failed lock acquisition is not usage and cannot reorder equal work.
        self.assertEqual(self.store.profile("a")["last_used"], 0)
        self.assertEqual(self.store.profile("b")["last_used"], 0)
        progressed, _ = self.run_tick()
        self.assertTrue(progressed)
        current = self.store.job(job["id"])
        self.assertEqual((current["status"], current["chosen_profile"], current["attempts"]),
                         ("succeeded", "a", 1))
        self.assertEqual(len(self.store.jobs()), 1)

    def test_pin_never_uses_free_other_profile_and_resumes_after_release(self):
        job = self.submit(profile="a")
        with file_lock(self.store.authdir("a") / ".native.lock"):
            progressed, visited = self.run_tick()
            self.assertFalse(progressed)
            self.assertEqual(visited, ["a"])
            self.assertEqual(self.store.job(job["id"])["attempts"], 0)
        progressed, _ = self.run_tick()
        self.assertTrue(progressed)
        current = self.store.job(job["id"])
        self.assertEqual((current["status"], current["chosen_profile"], current["attempts"]),
                         ("succeeded", "a", 1))
        self.assertEqual(self.store.profile("b")["last_used"], 0)
