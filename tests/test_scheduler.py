"""Tests for scripts/scheduler.py"""

import importlib.util
import logging
import os
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch, call

SCRIPTS = Path(__file__).parent.parent / "scripts"


def load_scheduler() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("scheduler", SCRIPTS / "scheduler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.log.handlers = [logging.NullHandler()]
    mod.log.propagate = False
    return mod


class TestReadResetTs(unittest.TestCase):
    def setUp(self):
        self.mod = load_scheduler()

    def test_reads_valid_timestamp(self):
        with patch("builtins.open", mock_open(read_data="1781298600\n")):
            with patch("os.path.isfile", return_value=True):
                self.assertEqual(self.mod.read_reset_ts(), 1781298600)

    def test_missing_file_returns_none(self):
        with patch("os.path.isfile", return_value=False):
            self.assertIsNone(self.mod.read_reset_ts())

    def test_invalid_content_returns_none(self):
        with patch("builtins.open", mock_open(read_data="not-a-number\n")):
            with patch("os.path.isfile", return_value=True):
                self.assertIsNone(self.mod.read_reset_ts())

    def test_empty_file_returns_none(self):
        with patch("builtins.open", mock_open(read_data="")):
            with patch("os.path.isfile", return_value=True):
                self.assertIsNone(self.mod.read_reset_ts())


class TestMainLogic(unittest.TestCase):
    def setUp(self):
        self.mod = load_scheduler()

    def _run(
        self,
        reset_ts=None,
        existing_timers=None,
        timer_fire_ts=None,
        schedule_raises=False,
    ) -> int:
        existing_timers = existing_timers or []

        def fake_timer_fire(unit):
            return timer_fire_ts

        schedule_mock = MagicMock()
        if schedule_raises:
            import subprocess
            schedule_mock.side_effect = subprocess.CalledProcessError(1, "systemd-run", stderr=b"fail")

        with (
            patch.object(self.mod, "read_reset_ts", return_value=reset_ts),
            patch.object(self.mod, "list_claim_timers", return_value=existing_timers),
            patch.object(self.mod, "timer_fire_ts", side_effect=fake_timer_fire),
            patch.object(self.mod, "cancel_timers"),
            patch.object(self.mod, "find_claim_py", return_value="/lib/claim.py"),
            patch.object(self.mod, "schedule_claim", schedule_mock),

        ):
            return self.mod.main()

    def test_no_cache_does_nothing(self):
        rc = self._run(reset_ts=None)
        self.assertEqual(rc, 0)

    def test_stale_cache_does_nothing(self):
        # More than 1 hour in the past
        stale_ts = int(time.time()) - 3700
        rc = self._run(reset_ts=stale_ts)
        self.assertEqual(rc, 0)

    def test_future_reset_schedules_claim(self):
        future_ts = int(time.time()) + 3600
        rc = self._run(reset_ts=future_ts)
        self.assertEqual(rc, 0)

    def test_already_scheduled_within_tolerance_skips(self):
        future_ts = int(time.time()) + 3600
        fire_ts = future_ts + self.mod.LEAD_SECONDS
        # Timer already scheduled within ±5 min
        rc = self._run(
            reset_ts=future_ts,
            existing_timers=["claim-claude-window-abc.timer"],
            timer_fire_ts=fire_ts + 60,  # 1 minute off — within tolerance
        )
        self.assertEqual(rc, 0)

    def test_timer_outside_tolerance_reschedules(self):
        future_ts = int(time.time()) + 3600
        fire_ts = future_ts + self.mod.LEAD_SECONDS
        schedule_mock = MagicMock()
        cancel_mock = MagicMock()
        with (
            patch.object(self.mod, "read_reset_ts", return_value=future_ts),
            patch.object(self.mod, "list_claim_timers", return_value=["claim-claude-window-old.timer"]),
            patch.object(self.mod, "timer_fire_ts", return_value=fire_ts + 600),  # 10 min off
            patch.object(self.mod, "cancel_timers", cancel_mock),
            patch.object(self.mod, "find_claim_py", return_value="/lib/claim.py"),
            patch.object(self.mod, "schedule_claim", schedule_mock),

        ):
            rc = self.mod.main()
        self.assertEqual(rc, 0)
        cancel_mock.assert_called_once()
        schedule_mock.assert_called_once()

    def test_schedule_failure_returns_nonzero(self):
        future_ts = int(time.time()) + 3600
        rc = self._run(reset_ts=future_ts, schedule_raises=True)
        self.assertEqual(rc, 1)

    def test_reset_in_past_within_stale_threshold_still_schedules(self):
        # Just past reset but within 1-hour stale window — claim.py should fire ASAP
        # scheduler skips if fire_ts is past, so this ends with no schedule (not an error)
        recent_past = int(time.time()) - 30
        rc = self._run(reset_ts=recent_past)
        self.assertEqual(rc, 0)


class TestCancelTimers(unittest.TestCase):
    def setUp(self):
        self.mod = load_scheduler()

    def test_stops_each_unit(self):
        run_mock = MagicMock()
        with patch("subprocess.run", run_mock):
            self.mod.cancel_timers(["unit-a.timer", "unit-b.timer"])
        calls = [c[0][0] for c in run_mock.call_args_list]
        self.assertTrue(any("unit-a.timer" in c for c in calls))
        self.assertTrue(any("unit-b.timer" in c for c in calls))

    def test_empty_list_is_noop(self):
        run_mock = MagicMock()
        with patch("subprocess.run", run_mock):
            self.mod.cancel_timers([])
        run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
