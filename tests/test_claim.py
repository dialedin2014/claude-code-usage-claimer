"""Tests for scripts/claim.py"""

import importlib.util
import json
import logging
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

SCRIPTS = Path(__file__).parent.parent / "scripts"


def load_claim() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("claim", SCRIPTS / "claim.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Replace any file/stream handlers with a NullHandler so tests stay silent
    # and don't open the real log file.
    mod.log.handlers = [logging.NullHandler()]
    mod.log.propagate = False
    return mod


def make_completed_process(stdout: str, returncode: int = 0):
    cp = MagicMock()
    cp.stdout = stdout
    cp.returncode = returncode
    return cp


class TestFindClaude(unittest.TestCase):
    def setUp(self):
        self.mod = load_claim()

    def test_env_override(self):
        with (
            patch.dict(os.environ, {"CLAUDE_BIN": "/usr/bin/claude"}),
            patch("os.path.isfile", return_value=True),
            patch("os.access", return_value=True),
        ):
            self.assertEqual(self.mod.find_claude(), "/usr/bin/claude")

    def test_which_fallback(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which", return_value="/usr/local/bin/claude"),
        ):
            self.assertEqual(self.mod.find_claude(), "/usr/local/bin/claude")

    def test_not_found_raises(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which", return_value=None),
            patch("os.path.isfile", return_value=False),
        ):
            with self.assertRaises(RuntimeError):
                self.mod.find_claude()


class TestWriteProvisionalReset(unittest.TestCase):
    def setUp(self):
        self.mod = load_claim()

    def test_writes_future_timestamp(self):
        import time
        m = mock_open()
        with (
            patch("builtins.open", m),
            patch("os.makedirs"),
        ):
            ts = self.mod.write_provisional_reset()
        now = int(time.time())
        self.assertGreater(ts, now + 5 * 3600)
        m().write.assert_called_once()
        written = m().write.call_args[0][0]
        self.assertEqual(written.strip(), str(ts))


class TestMain(unittest.TestCase):
    def setUp(self):
        self.mod = load_claim()

    def _run_with_claude_output(self, stdout: str, returncode: int = 0) -> int:
        cp = make_completed_process(stdout, returncode)
        with (
            patch.object(self.mod, "find_claude", return_value="/usr/bin/claude"),
            patch("subprocess.run", return_value=cp),
            patch.object(self.mod, "write_provisional_reset", return_value=9999999999),
        ):
            return self.mod.main()

    def test_success_pass(self):
        envelope = json.dumps({"is_error": False, "result": "Hey there!"})
        rc = self._run_with_claude_output(envelope, returncode=0)
        self.assertEqual(rc, 0)

    def test_is_error_true_fails(self):
        envelope = json.dumps({"is_error": True, "result": "", "subtype": "error_during_execution"})
        rc = self._run_with_claude_output(envelope, returncode=0)
        self.assertEqual(rc, 1)

    def test_nonzero_returncode_fails(self):
        envelope = json.dumps({"is_error": False, "result": "Hi"})
        rc = self._run_with_claude_output(envelope, returncode=1)
        self.assertEqual(rc, 1)

    def test_empty_result_fails(self):
        envelope = json.dumps({"is_error": False, "result": ""})
        rc = self._run_with_claude_output(envelope, returncode=0)
        self.assertEqual(rc, 1)

    def test_invalid_json_fails(self):
        rc = self._run_with_claude_output("not json", returncode=0)
        self.assertEqual(rc, 1)

    def test_rate_limit_in_output_detected(self):
        envelope = json.dumps({"is_error": True, "result": "5-hour limit reached", "subtype": "usage_limit"})
        cp = make_completed_process(envelope, returncode=1)
        logged_errors = []
        with (
            patch.object(self.mod, "find_claude", return_value="/usr/bin/claude"),
            patch("subprocess.run", return_value=cp),
            patch.object(self.mod.log, "error", side_effect=lambda msg, *a: logged_errors.append(msg)),
        ):
            rc = self.mod.main()
        self.assertEqual(rc, 1)
        self.assertTrue(any("usage-limit" in e for e in logged_errors))

    def test_claude_not_found_fails(self):
        with (
            patch.object(self.mod, "find_claude", side_effect=RuntimeError("not found")),
        ):
            rc = self.mod.main()
        self.assertEqual(rc, 1)

    def test_timeout_fails(self):
        import subprocess
        with (
            patch.object(self.mod, "find_claude", return_value="/usr/bin/claude"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120)),
        ):
            rc = self.mod.main()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
