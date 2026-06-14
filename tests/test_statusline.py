"""Tests for scripts/statusline.py"""

import importlib.util
import io
import json
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

SCRIPTS = Path(__file__).parent.parent / "scripts"


def load_statusline() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("statusline", SCRIPTS / "statusline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestBar(unittest.TestCase):
    def setUp(self):
        self.mod = load_statusline()

    def test_empty_bar(self):
        self.assertEqual(self.mod.bar(0), "░" * 10)

    def test_full_bar(self):
        self.assertEqual(self.mod.bar(100), "█" * 10)

    def test_half_bar(self):
        b = self.mod.bar(50)
        self.assertEqual(b.count("█"), 5)
        self.assertEqual(b.count("░"), 5)

    def test_clamp_over(self):
        self.assertEqual(self.mod.bar(200), "█" * 10)

    def test_clamp_under(self):
        self.assertEqual(self.mod.bar(-5), "░" * 10)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.mod = load_statusline()

    def _run(self, stdin_data: dict, now_offset: int = 0) -> str:
        """Run main() with given JSON stdin; return captured stdout."""
        future_ts = int(time.time()) + now_offset + 3600
        if "rate_limits" in stdin_data:
            # Allow caller to override resets_at
            pass
        buf = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO(json.dumps(stdin_data))),
            patch("sys.stdout", buf),
            patch("builtins.open", mock_open()),
            patch("os.makedirs"),
        ):
            self.mod.main()
        return buf.getvalue().strip()

    def test_missing_rate_limits(self):
        out = self._run({})
        self.assertEqual(out, "claude: --")

    def test_missing_five_hour(self):
        out = self._run({"rate_limits": {}})
        self.assertEqual(out, "claude: --")

    def test_window_open(self):
        past_ts = int(time.time()) - 60
        data = {"rate_limits": {"five_hour": {"resets_at": past_ts, "used_percentage": 100}}}
        out = self._run(data)
        self.assertEqual(out, "claude: window open ✓")

    def test_normal_output_format(self):
        future_ts = int(time.time()) + 3600
        data = {"rate_limits": {"five_hour": {"resets_at": future_ts, "used_percentage": 72.4}}}
        out = self._run(data)
        self.assertIn("claude:", out)
        self.assertIn("72%", out)
        self.assertIn("[", out)
        self.assertIn("]", out)
        self.assertIn("-", out)

    def test_time_remaining_hours_and_minutes(self):
        future_ts = int(time.time()) + 3600 + 22 * 60
        data = {"rate_limits": {"five_hour": {"resets_at": future_ts, "used_percentage": 50}}}
        out = self._run(data)
        self.assertIn("1h22m", out)

    def test_time_remaining_minutes_only(self):
        future_ts = int(time.time()) + 22 * 60
        data = {"rate_limits": {"five_hour": {"resets_at": future_ts, "used_percentage": 50}}}
        out = self._run(data)
        self.assertIn("22m", out)
        self.assertNotIn("0h", out)

    def test_cache_written(self):
        future_ts = int(time.time()) + 3600
        data = {"rate_limits": {"five_hour": {"resets_at": future_ts, "used_percentage": 50}}}
        written = []
        m = mock_open()
        with (
            patch("sys.stdin", io.StringIO(json.dumps(data))),
            patch("sys.stdout", io.StringIO()),
            patch("builtins.open", m),
            patch("os.makedirs"),
        ):
            self.mod.main()
        m().write.assert_called_once_with(f"{future_ts}\n")

    def test_cache_not_written_when_no_rate_limits(self):
        m = mock_open()
        with (
            patch("sys.stdin", io.StringIO(json.dumps({}))),
            patch("sys.stdout", io.StringIO()),
            patch("builtins.open", m),
            patch("os.makedirs"),
        ):
            self.mod.main()
        m().write.assert_not_called()


class TestReadStdinJson(unittest.TestCase):
    def setUp(self):
        self.mod = load_statusline()

    def test_valid_json(self):
        with patch("sys.stdin", io.StringIO('{"a": 1}')):
            self.assertEqual(self.mod.read_stdin_json(), {"a": 1})

    def test_invalid_json(self):
        with patch("sys.stdin", io.StringIO("not json")):
            self.assertEqual(self.mod.read_stdin_json(), {})

    def test_empty_stdin(self):
        with patch("sys.stdin", io.StringIO("")):
            self.assertEqual(self.mod.read_stdin_json(), {})


if __name__ == "__main__":
    unittest.main()
