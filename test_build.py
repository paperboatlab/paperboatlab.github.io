#!/usr/bin/env python3
"""Unit and integration tests for multi-version git-tracked docs building."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import build

PAPERBOAT_ROOT = Path(__file__).resolve().parent.parent / "paperboat"


def git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return res.stdout.strip()


def init_repo(path: Path, files: dict[str, str], branch: str = "dev") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    for rel, content in files.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", f"init {branch}")


class BuildVersioningTests(unittest.TestCase):
    def test_parse_semver_ordering(self) -> None:
        tags = ["v0.1.0-alpha.2", "v0.1.0", "v0.1.0-alpha.10", "v0.2.0", "v0.1.5", "not-a-tag"]
        valid = sorted((t for t in tags if build.parse_semver(t)), key=build.parse_semver, reverse=True)
        self.assertEqual(valid, ["v0.2.0", "v0.1.5", "v0.1.0", "v0.1.0-alpha.10", "v0.1.0-alpha.2"])

    def test_discover_versions_prefers_release_branch_then_latest_stable_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "app"
            init_repo(repo, {"docs/index.rst": "App\n===\n\nDev.\n"}, branch="dev")
            git(repo, "tag", "v0.1.0-alpha.1")
            git(repo, "tag", "v0.1.0")
            (repo / "docs/index.rst").write_text("App\n===\n\nRelease 0.2.\n")
            git(repo, "commit", "-am", "v0.2.0")
            git(repo, "tag", "v0.2.0")

            vers = build.discover_versions(repo)
            self.assertEqual([v["version"] for v in vers], ["v0.2.0", "v0.1.0", "dev"])
            self.assertEqual(build.default_version(vers)["version"], "v0.2.0")

            git(repo, "checkout", "-q", "-b", "release")
            (repo / "docs/index.rst").write_text("App\n===\n\nRelease branch.\n")
            git(repo, "commit", "-am", "release branch")
            vers_with_rel = build.discover_versions(repo)
            self.assertEqual([v["version"] for v in vers_with_rel], ["release", "v0.2.0", "v0.1.0", "dev"])
            self.assertEqual(build.default_version(vers_with_rel)["version"], "release")

    def test_prerelease_fallback_when_no_stable_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "pre"
            init_repo(repo, {"README.md": "hi"}, branch="dev")
            git(repo, "tag", "v0.1.0-alpha.1")
            git(repo, "tag", "v0.1.0-alpha.2")
            vers = build.discover_versions(repo)
            self.assertEqual([v["version"] for v in vers], ["v0.1.0-alpha.2", "dev"])
            self.assertEqual(build.default_version(vers)["version"], "v0.1.0-alpha.2")

    @unittest.skipUnless((PAPERBOAT_ROOT / "docs/site/build.py").exists(), "requires sibling paperboat checkout")
    def test_end_to_end_multi_version_build_and_cache_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            work = tmp / "work"
            out = tmp / "out"
            prev = tmp / "prev"

            # Create a local app repo with v0.1.0, release branch, and dev branch.
            app_remote = tmp / "remotes/demo-app"
            init_repo(app_remote, {"docs/index.rst": "Demo\n====\n\nVersion 0.1.0.\n"}, branch="dev")
            git(app_remote, "tag", "v0.1.0")
            git(app_remote, "checkout", "-q", "-b", "release")
            (app_remote / "docs/index.rst").write_text("Demo\n====\n\nRelease channel.\n")
            git(app_remote, "commit", "-am", "release channel")
            git(app_remote, "checkout", "-q", "dev")
            (app_remote / "docs/index.rst").write_text("Demo\n====\n\nDev channel.\n")
            git(app_remote, "commit", "-am", "dev channel")

            # Create a minimal paperboat repo using the real docs/site builder and _static assets.
            pb = work / "paperboat"
            init_repo(
                pb,
                {
                    "docs/api/index.rst": "Engine\n======\n\nEngine docs.\n",
                    "toolkits.toml": "",
                    "apps.toml": (
                        '[[apps]]\nname = "demo-app"\nrepo = "' + str(app_remote) + '"\n'
                        'description = "Demo app"\nkind = "squero"\n'
                    ),
                },
                branch="dev",
            )
            # The new platform's registry lists an app with no kind: it is grouped as an app.
            init_repo(
                work / "platform",
                {"apps.toml": '[[apps]]\nname = "demo-platform"\nrepo = "' + str(app_remote) + '"\n'},
                branch="main",
            )
            # Copy real docs/site and docs/_static into the fixture paperboat repo.
            import shutil
            shutil.copytree(PAPERBOAT_ROOT / "docs/site", pb / "docs/site")
            shutil.copytree(PAPERBOAT_ROOT / "docs/_static", pb / "docs/_static")
            git(pb, "add", ".")
            git(pb, "commit", "-q", "-m", "add site builder")
            git(pb, "tag", "v0.1.0")

            # Run build.py via main()
            import sys
            old_argv = sys.argv
            try:
                sys.argv = ["build.py", "--work", str(work), "--out", str(out), "--engine", "unused"]
                rc = build.main()
                self.assertEqual(rc, 0)
            finally:
                sys.argv = old_argv

            # Verify default site, versioned sites, Shibuya switcher, sites.json, and versions.json.
            self.assertTrue((out / "paperboat/index.html").exists())
            self.assertTrue((out / "paperboat/v0.1.0/index.html").exists())
            self.assertTrue((out / "paperboat/dev/index.html").exists())
            self.assertTrue((out / "apps/demo-app/index.html").exists())
            self.assertTrue((out / "apps/demo-app/release/index.html").exists())
            self.assertTrue((out / "apps/demo-app/v0.1.0/index.html").exists())
            self.assertTrue((out / "apps/demo-app/dev/index.html").exists())

            default_html = (out / "apps/demo-app/index.html").read_text()
            self.assertIn("Release channel.", default_html)
            self.assertIn("nav-versions", default_html)
            self.assertIn("v0.1.0", default_html)

            dev_html = (out / "apps/demo-app/dev/index.html").read_text()
            self.assertIn("Dev channel.", dev_html)

            sites_json = json.loads((out / "sites.json").read_text())
            demo_entry = next(s for s in sites_json if s["site"] == "apps/demo-app")
            self.assertEqual(demo_entry["version"], "release")
            self.assertEqual(demo_entry["channel"], "release")
            self.assertEqual(demo_entry["help"], "apps/demo-app/help.json")
            self.assertEqual([v["version"] for v in demo_entry["versions"]], ["release", "v0.1.0", "dev"])

            self.assertTrue((out / "apps/demo-platform/index.html").exists())
            self.assertEqual(next(s for s in sites_json if s["site"] == "apps/demo-platform")["kind"], "app")
            self.assertIn("paperboat app open", (out / "docs/index.html").read_text())
            self.assertIn("An engineering environment", (out / "index.html").read_text())

            versions_json = json.loads((out / "versions.json").read_text())
            self.assertEqual(len(versions_json["sites"]), 3)

            # Verify --reuse-tags copies immutable tag v0.1.0 from --previous.
            shutil.copytree(out, prev)
            marker = prev / "apps/demo-app/v0.1.0/.cached-marker"
            marker.write_text("reused")
            try:
                sys.argv = [
                    "build.py", "--work", str(work), "--out", str(out),
                    "--engine", "unused", "--previous", str(prev), "--reuse-tags",
                ]
                rc = build.main()
                self.assertEqual(rc, 0)
            finally:
                sys.argv = old_argv
            self.assertTrue((out / "apps/demo-app/v0.1.0/.cached-marker").exists())


if __name__ == "__main__":
    unittest.main()
