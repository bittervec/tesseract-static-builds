#!/usr/bin/env python3
"""Check out the locked vcpkg commit and validate its Tesseract port."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main():
    with Path("vcpkg-lock.json").open(encoding="utf-8") as file:
        pin = json.load(file)
    commit = pin.get("vcpkg_commit")
    version = pin.get("tesseract_version")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid vcpkg commit in vcpkg-lock.json")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Invalid Tesseract version in vcpkg-lock.json")

    root = Path(os.environ["RUNNER_TEMP"]) / "vcpkg"
    subprocess.run(["git", "clone", "--no-checkout", "https://github.com/microsoft/vcpkg.git", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "checkout", "--detach", commit], check=True)
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual != commit:
        raise ValueError("vcpkg checkout does not match the recorded commit")
    with (root / "ports" / "tesseract" / "vcpkg.json").open(encoding="utf-8") as file:
        port = json.load(file)
    if port.get("name") != "tesseract" or port.get("version") != version:
        raise ValueError(f"Tesseract port version {port.get('version')!r} does not match {version!r}")
    print(f"Using vcpkg {actual} with Tesseract {version}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
