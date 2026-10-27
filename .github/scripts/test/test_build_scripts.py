#!/usr/bin/env python3
"""Exercise the Unix build scripts using a temporary fake vcpkg tree."""

import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent.parent / "bash"


class BuildScriptsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="build scripts ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vcpkg = self.root / "vcpkg"
        self.vcpkg.mkdir()
        self.env = {**os.environ, "RUNNER_TEMP": str(self.root),
                    "VCPKG_ROOT": str(self.vcpkg), "TRIPLET": "x64-linux"}

    def run_script(self, name):
        return subprocess.run(["bash", str(SCRIPTS / name)], cwd=self.root,
                              env=self.env, capture_output=True, text=True)

    def fake_executable(self, name):
        executable = self.vcpkg / name
        executable.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n', encoding="utf-8")
        executable.chmod(0o755)

    def test_bootstrap_and_install_arguments(self):
        self.fake_executable("bootstrap-vcpkg.sh")
        self.fake_executable("vcpkg")
        bootstrap = self.run_script("bootstrap-vcpkg.sh")
        self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
        self.assertEqual(bootstrap.stdout.splitlines(), ["-disableMetrics"])
        install = self.run_script("install-tesseract.sh")
        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertEqual(install.stdout.splitlines(), ["install", "tesseract", "--triplet=x64-linux", "--disable-metrics"])

    def test_package_contains_binary_and_runtime_library(self):
        binary_dir = self.vcpkg / "installed" / "x64-linux" / "bin"
        binary_dir.mkdir(parents=True)
        (binary_dir / "tesseract").write_bytes(b"executable")
        (binary_dir / "libtest.so").write_bytes(b"library")
        result = self.run_script("package-tesseract.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.root / "dist" / "tesseract-x64-linux.tar.gz") as archive:
            self.assertEqual(archive.extractfile("./tesseract").read(), b"executable")
            self.assertEqual(archive.extractfile("./libtest.so").read(), b"library")

    def test_package_fails_when_binary_missing(self):
        (self.vcpkg / "installed" / "x64-linux").mkdir(parents=True)
        result = self.run_script("package-tesseract.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not find the Tesseract executable", result.stderr)
        self.assertFalse((self.root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
