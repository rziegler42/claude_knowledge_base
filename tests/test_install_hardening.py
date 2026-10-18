import contextlib
import io
import os
import signal
import sys
import unittest
from unittest import mock

import helpers

sys.path.insert(0, str(helpers.ROOT))
import install  # noqa: E402
from test_install_addto import SAFE_ENV, snapshot, template_project  # noqa: E402

IDENT = ["--git-name", "T", "--git-email", "t@users.noreply.github.com"]


def run(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {**SAFE_ENV, **(env or {})}), \
            mock.patch("sys.stdin", io.StringIO("")), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = install.main(argv)
    return code, out.getvalue() + err.getvalue()


class Alarm:
    """Fail a test that hangs (for example on a FIFO read) instead of blocking the suite."""
    def __enter__(self):
        def boom(*_):
            raise AssertionError("the installer hung")
        self.old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(20)

    def __exit__(self, *exc):
        signal.alarm(0)
        signal.signal(signal.SIGALRM, self.old)


class HardenCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.proj = self.tmp / "existing"
        template_project(self.proj)
        self.outside = self.tmp / "outside.txt"
        self.outside.write_text("untouched\n")

    def add(self, *extra):
        with Alarm():
            return run(["--add-to", str(self.proj), *extra])

    def refuses(self, *extra):
        before = snapshot(self.proj)
        code, out = self.add(*extra)
        self.assertEqual(code, 1, out)
        self.assertEqual(snapshot(self.proj), before)
        self.assertEqual(self.outside.read_text(), "untouched\n")
        return out


class FifoTests(HardenCase):
    def test_fifo_as_a_host_file(self):
        (self.proj / "README.md").unlink()
        os.mkfifo(self.proj / "README.md")
        self.refuses()
        self.refuses("--skip-unsafe-entries")  # a needed host file cannot be skipped

    def test_fifo_at_a_kit_destination(self):
        os.mkfifo(self.proj / "kb.json")
        self.refuses()

    def test_fifo_in_a_content_directory(self):
        (self.proj / "catalog").mkdir()
        os.mkfifo(self.proj / "catalog" / "pipe")
        self.refuses()

    def test_fifo_is_skipped_and_listed_with_the_flag(self):
        (self.proj / "catalog").mkdir()
        os.mkfifo(self.proj / "catalog" / "pipe")
        code, out = self.add("--skip-unsafe-entries")
        self.assertEqual(code, 0, out)
        self.assertIn("catalog/pipe", out)
        self.assertTrue((self.proj / "catalog" / "pipe").exists())


class SymlinkTests(HardenCase):
    def test_symlinked_host_is_not_read_or_written_through(self):
        (self.proj / "README.md").unlink()
        os.symlink(self.outside, self.proj / "README.md")
        self.refuses()
        self.refuses("--skip-unsafe-entries")

    def test_symlink_at_a_kit_destination(self):
        os.symlink(self.outside, self.proj / "kb.json")
        self.refuses()

    def test_symlink_in_a_content_directory(self):
        (self.proj / "catalog").mkdir()
        os.symlink(self.outside, self.proj / "catalog" / "link.md")
        self.refuses()

    def test_symlinked_content_directory(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        os.symlink(elsewhere, self.proj / "domains")
        self.refuses()
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_symlinked_parent_of_a_kit_file(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        os.symlink(elsewhere, self.proj / "tools")
        self.refuses()
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_symlinked_parent_of_a_host(self):
        shadow = self.tmp / "shadow"
        shadow.mkdir()
        (shadow / "README.md").write_text("# shadow\n<!-- @module-slot: docs-index -->\n")
        (self.proj / "docs" / "README.md").unlink()
        (self.proj / "docs").rmdir() if not os.listdir(self.proj / "docs") else None
        os.symlink(shadow, self.proj / "docs")
        self.refuses()
        self.refuses("--skip-unsafe-entries")
        self.assertEqual((shadow / "README.md").read_text(), "# shadow\n<!-- @module-slot: docs-index -->\n")

    def test_symlink_is_skipped_never_followed_with_the_flag(self):
        (self.proj / "catalog").mkdir()
        os.symlink(self.outside, self.proj / "catalog" / "link.md")
        code, out = self.add("--skip-unsafe-entries")
        self.assertEqual(code, 0, out)
        self.assertIn("catalog/link.md", out)
        self.assertEqual(self.outside.read_text(), "untouched\n")
        self.assertTrue(os.path.islink(self.proj / "catalog" / "link.md"))

    def test_symlinked_target_directory(self):
        link = self.tmp / "link"
        os.symlink(self.proj, link)
        code, out = run(["--add-to", str(link)])
        self.assertEqual(code, 1, out)


class SizeCapTests(HardenCase):
    def big(self, path):
        with open(path, "wb") as handle:
            handle.truncate(install.MAX_READ + 1)

    def test_over_cap_host(self):
        self.big(self.proj / "README.md")
        self.refuses()
        self.refuses("--skip-unsafe-entries")

    def test_over_cap_file_in_a_content_directory_is_refused_or_skipped(self):
        (self.proj / "sources").mkdir()
        self.big(self.proj / "sources" / "huge.bin")
        self.refuses()
        code, out = self.add("--skip-unsafe-entries")
        self.assertEqual(code, 0, out)
        self.assertIn("sources/huge.bin", out)

    def test_over_cap_file_at_a_kit_destination(self):
        self.big(self.proj / "kb.json")
        self.refuses()


class PathRuleTests(HardenCase):
    def test_git_component_in_the_target_is_refused_case_insensitively(self):
        for name in (".GIT", ".Git", ".git"):
            with self.subTest(name=name):
                target = self.tmp / name / "proj"
                target.mkdir(parents=True, exist_ok=True)  # the filesystem may fold case
                code, out = run(["--add-to", str(target)])
                self.assertEqual(code, 1, out)

    def test_check_rel_rules(self):
        for bad in ("", "/abs", "a/../b", "./a", "a//b", ".GIT/x", "x/.Git/y", "a/.kb-manifest",
                    "a\\b", "a\x00b"):
            with self.subTest(rel=bad), self.assertRaises(install.InstallError):
                install.check_rel(bad)
        install.check_rel("tools/check_kb.py")

    def test_skip_flag_is_rejected_when_creating(self):
        target = self.tmp / "new"
        code, out = run([str(target), *IDENT, "--skip-unsafe-entries"])
        self.assertEqual(code, 1)
        self.assertFalse(target.exists())


class HostileGitTests(HardenCase):
    def test_git_env_drops_everything_but_the_config_selectors(self):
        env = {"GIT_DIR": "/x", "GIT_EXEC_PATH": "/y", "GIT_SSH_COMMAND": "z", "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_GLOBAL": "/g", "GIT_CONFIG_SYSTEM": "/s", "GIT_CONFIG_NOSYSTEM": "1", "PATH": os.environ["PATH"]}
        with mock.patch.dict(os.environ, env, clear=True):
            cleaned = install.git_env()
        self.assertEqual(sorted(k for k in cleaned if k.startswith("GIT_")),
                         ["GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_SYSTEM"])
        self.assertIn("PATH", cleaned)

    def test_hostile_environment_cannot_redirect_or_run_a_program(self):
        sentinel = self.tmp / "ran"
        script = self.tmp / "evil.sh"
        script.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
        script.chmod(0o755)
        decoy = self.tmp / "decoy"
        decoy.mkdir()
        target = self.tmp / "fresh-kb"
        env = {"GIT_DIR": str(decoy), "GIT_WORK_TREE": str(decoy), "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": str(script),
               "GIT_EXEC_PATH": str(decoy), "GIT_SSH_COMMAND": str(script)}
        code, out = run([str(target), *IDENT], env=env)
        self.assertEqual(code, 0, out)
        self.assertTrue((target / ".git" / "HEAD").is_file())
        self.assertEqual(list(decoy.iterdir()), [])
        self.assertFalse(sentinel.exists())

    def test_hostile_project_git_config_is_never_consulted(self):
        sentinel = self.tmp / "ran2"
        script = self.tmp / "evil2.sh"
        script.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
        script.chmod(0o755)
        (self.proj / ".git").mkdir()
        (self.proj / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (self.proj / ".git" / "config").write_text(
            f"[core]\n\tfsmonitor = {script}\n\thooksPath = {self.tmp}\n[alias]\n\tstatus = !{script}\n")
        code, out = self.add()
        self.assertEqual(code, 0, out)
        self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
