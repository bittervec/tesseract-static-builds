#!/usr/bin/env python3
"""Tests for the cross-platform vcpkg lock validation."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("checkout_vcpkg", Path(__file__).resolve().parent.parent / "checkout-vcpkg.py")
checkout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkout)
COMMIT = "a" * 40


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vcpkg test ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pin = {"vcpkg_commit": COMMIT, "tesseract_version": "5.5.3"}
        self.port = {"name": "tesseract", "version": "5.5.3"}
        self.old_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.old_cwd)
        self.env = patch.dict(os.environ, {"RUNNER_TEMP": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def write_files(self):
        (self.root / "vcpkg-lock.json").write_text(json.dumps(self.pin), encoding="utf-8")
        port = self.root / "vcpkg" / "ports" / "tesseract" / "vcpkg.json"
        port.parent.mkdir(parents=True, exist_ok=True)
        port.write_text(json.dumps(self.port), encoding="utf-8")

    @patch.object(checkout.subprocess, "check_output", return_value=COMMIT + "\n")
    @patch.object(checkout.subprocess, "run")
    def test_valid_lock(self, run, check_output):
        self.write_files()
        checkout.main()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0][-1], COMMIT)
        self.assertEqual(check_output.call_args.args[0][-2:], ["rev-parse", "HEAD"])

    @patch.object(checkout.subprocess, "run")
    def test_invalid_lock_is_rejected_before_clone(self, run):
        for field, value in (("vcpkg_commit", "main"), ("tesseract_version", " ")):
            with self.subTest(field=field):
                original = self.pin[field]
                self.pin[field] = value
                self.write_files()
                with self.assertRaises(ValueError):
                    checkout.main()
                self.pin[field] = original
        run.assert_not_called()

    @patch.object(checkout.subprocess, "check_output", return_value=COMMIT + "\n")
    @patch.object(checkout.subprocess, "run")
    def test_port_mismatch_is_rejected(self, run, check_output):
        self.port["version"] = "5.0.0"
        self.write_files()
        with self.assertRaises(ValueError):
            checkout.main()

    @patch.object(checkout.subprocess, "check_output", return_value="b" * 40 + "\n")
    @patch.object(checkout.subprocess, "run")
    def test_checkout_mismatch_is_rejected(self, run, check_output):
        self.write_files()
        with self.assertRaises(ValueError):
            checkout.main()


if __name__ == "__main__":
    unittest.main()
