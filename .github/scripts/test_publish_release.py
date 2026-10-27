#!/usr/bin/env python3
"""Exercise the release script with a fake GitHub API; no network or credentials."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("publish-release.sh")
ASSETS = [
    "tesseract-arm64-linux.tar.gz",
    "tesseract-x64-linux.tar.gz",
    "tesseract-x64-windows-static.zip",
    "tesseract-arm64-osx.tar.gz",
]
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
p = os.environ["STATE"]
with open(p) as f:
    s = json.load(f)
a = sys.argv[1:]
s["calls"].append(a)
def save():
    with open(p, "w") as f:
        json.dump(s, f)
def fail(message):
    save()
    print(message, file=sys.stderr)
    sys.exit(1)
if "--paginate" in a:
    s["lists"] += 1
    if s["lists"] == s.get("fail_list"):
        fail("API list failed")
    if s["lists"] == s.get("race_list"):
        s["releases"].append({"id": 456, "tag_name": os.environ["TAG"], "draft": True})
    # Model --slurp output with one result per page, including unrelated tags.
    result = [[r] for r in s["releases"]] or [[]]
    if s.get("malformed_list"):
        result = {"message": "unexpected"}
    print(json.dumps(result))
elif "POST" in a and a[-1] == "generate_release_notes=true":
    s["releases"].append({"id": 123, "tag_name": os.environ["TAG"], "draft": True})
    if s.get("race"):
        s["releases"].append({"id": 456, "tag_name": os.environ["TAG"], "draft": True})
    print(json.dumps(s["releases"][-2 if s.get("race") else -1]))
elif "POST" in a and any("uploads.github.com" in x for x in a):
    s["uploads"] += 1
    if s["uploads"] == s.get("fail_upload"):
        fail("upload failed")
    print("{}")
elif "PATCH" in a:
    if s.get("fail_patch"):
        fail("publish failed")
    s["releases"][-1]["draft"] = False
    print("{}")
else:
    fail("unexpected call: " + repr(a))
save()
'''
FAKE_GIT = "#!/bin/sh\nexit ${GIT_RESULT:-0}\n"


class PublishReleaseTests(unittest.TestCase):
    def run_release(self, *, releases=None, config=None, missing=None, git_result=0):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "bin").mkdir()
            (root / "release-assets").mkdir()
            for name in ASSETS:
                if name != missing:
                    (root / "release-assets" / name).write_bytes(b"asset")
            for name, content in (("gh", FAKE_GH), ("git", FAKE_GIT)):
                path = root / "bin" / name
                path.write_text(content)
                path.chmod(0o755)
            state = root / "state.json"
            state.write_text(json.dumps({
                "releases": releases or [], "calls": [], "lists": 0, "uploads": 0,
                **(config or {}),
            }))
            env = {**os.environ, "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
                   "STATE": str(state), "TAG": "v1.0", "GITHUB_REPOSITORY": "owner/repo",
                   "GIT_RESULT": str(git_result)}
            proc = subprocess.run(["bash", str(SCRIPT)], cwd=root, env=env,
                                  text=True, capture_output=True)
            return proc, json.loads(state.read_text())

    def test_publishes_only_after_four_id_scoped_uploads(self):
        proc, state = self.run_release(releases=[{"id": 1, "tag_name": "other", "draft": False}])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(state["uploads"], 4)
        self.assertFalse(state["releases"][-1]["draft"])
        calls = state["calls"]
        uploads = [a for a in calls if any("uploads.github.com" in x for x in a)]
        self.assertTrue(all("/releases/123/assets" in " ".join(a) for a in uploads))
        self.assertTrue(all("Content-Length: 5" in a and "--input" in a for a in uploads))
        self.assertIn("repos/owner/repo/releases/123", calls[-1])
        self.assertIn("PATCH", calls[-1])

    def test_existing_draft_or_published_release_never_modified(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                existing = {"id": 5, "tag_name": "v1.0", "draft": draft}
                proc, state = self.run_release(releases=[
                    {"id": 6, "tag_name": "other", "draft": False}, existing])
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(state["releases"][-1], existing)
                self.assertTrue(all("--paginate" in c for c in state["calls"]))

    def test_list_errors_and_malformed_results_stop_before_create(self):
        for config in ({"fail_list": 1}, {"malformed_list": True}):
            with self.subTest(config=config):
                proc, state = self.run_release(config=config)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(state["releases"], [])
                self.assertEqual(state["uploads"], 0)

    def test_malformed_release_entry_stops_before_create(self):
        proc, state = self.run_release(releases=[{"id": 5, "draft": True}])
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(len(state["releases"]), 1)
        self.assertEqual(state["uploads"], 0)

    def test_competing_draft_after_create_stops_before_upload(self):
        proc, state = self.run_release(config={"race": True})
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(state["uploads"], 0)
        self.assertEqual([r["id"] for r in state["releases"]], [123, 456])
        self.assertTrue(all(r["draft"] for r in state["releases"]))

    def test_competing_draft_after_upload_stops_before_publish(self):
        proc, state = self.run_release(config={"race_list": 3})
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(state["uploads"], 4)
        self.assertEqual([r["id"] for r in state["releases"]], [123, 456])
        self.assertTrue(all(r["draft"] for r in state["releases"]))
        self.assertFalse(any("PATCH" in call for call in state["calls"]))

    def test_failure_after_creation_leaves_draft_unpublished(self):
        for config in ({"fail_list": 2}, {"fail_upload": 2}, {"fail_list": 3}, {"fail_patch": True}):
            with self.subTest(config=config):
                proc, state = self.run_release(config=config)
                self.assertNotEqual(proc.returncode, 0)
                self.assertTrue(state["releases"][0]["draft"])
                if not config.get("fail_patch"):
                    self.assertFalse(any("PATCH" in call for call in state["calls"]))
                self.assertFalse(any("DELETE" in call for call in state["calls"]))

    def test_missing_asset_or_tag_never_creates_draft(self):
        for kwargs in ({"missing": ASSETS[0]}, {"git_result": 2}):
            with self.subTest(kwargs=kwargs):
                proc, state = self.run_release(**kwargs)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(state["releases"], [])


if __name__ == "__main__":
    unittest.main()
