import contextlib
import io
import os
import shutil
import signal
import sys
import unittest
from unittest import mock

import helpers

sys.path.insert(0, str(helpers.ROOT))
import install  # noqa: E402

SAFE_ENV = helpers.SAFE_ENV
IDENT = ["--git-name", "T", "--git-email", "t@users.noreply.github.com"]


def run(argv, env=None, kit=None):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {**SAFE_ENV, **(env or {})}), \
            mock.patch("sys.stdin", io.StringIO("")), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = install.main(argv, kit_dir=kit)
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
        self.target = self.tmp / "fresh-kb"
        self.outside = self.tmp / "outside.txt"
        self.outside.write_text("untouched\n")
        self.kits = 0

    def make_kit(self):
        self.kits += 1
        kit = self.tmp / f"kit{self.kits}"
        shutil.copytree(helpers.KIT, kit, ignore=shutil.ignore_patterns("__pycache__"))
        return kit

    def create(self, *extra, kit=None, env=None):
        with Alarm():
            return run([str(self.target), *IDENT, *extra], env=env, kit=kit)

    def refuses_kit(self, kit):
        code, out = self.create(kit=kit)
        self.assertEqual(code, 1, out)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.outside.read_text(), "untouched\n")
        return out


class KitReadTests(HardenCase):
    def test_fifo_in_the_kit_does_not_hang_and_is_refused(self):
        kit = self.make_kit()
        os.mkfifo(kit / "files" / "pipe")
        self.refuses_kit(kit)

    def test_fifo_as_kit_json_does_not_hang(self):
        kit = self.make_kit()
        (kit / "kit.json").unlink()
        os.mkfifo(kit / "kit.json")
        self.refuses_kit(kit)

    def test_symlinked_kit_json_is_refused(self):
        kit = self.make_kit()
        (kit / "kit.json").unlink()
        os.symlink(self.outside, kit / "kit.json")
        self.refuses_kit(kit)

    def test_symlinked_migrations_json_is_refused(self):
        kit = self.make_kit()
        (kit / "migrations.json").unlink()
        os.symlink(self.outside, kit / "migrations.json")
        self.refuses_kit(kit)

    def test_symlinked_descriptor_directory_is_refused(self):
        kit = self.make_kit()
        shutil.move(str(kit / "files" / "template-module"), str(self.tmp / "elsewhere"))
        os.symlink(self.tmp / "elsewhere", kit / "files" / "template-module")
        self.refuses_kit(kit)

    def test_over_cap_kit_json_is_refused(self):
        kit = self.make_kit()
        with open(kit / "kit.json", "wb") as handle:
            handle.truncate(install.MAX_JSON + 1)
        self.refuses_kit(kit)


class PathRuleTests(HardenCase):
    def test_git_component_in_the_target_is_refused_case_insensitively(self):
        for name in (".GIT", ".Git", ".git"):
            with self.subTest(name=name):
                code, out = run([str(self.tmp / name / "proj"), *IDENT])
                self.assertEqual(code, 1, out)

    def test_check_rel_rules(self):
        for bad in ("", "/abs", "a/../b", "./a", "a//b", ".GIT/x", "x/.Git/y", "a/.kb-manifest",
                    "a\\b", "a\x00b"):
            with self.subTest(rel=bad), self.assertRaises(install.InstallError):
                install.check_rel(bad)
        install.check_rel("tools/check_kb.py")

    def test_template_module_is_starter_owned_and_verbatim(self):
        self.assertTrue(install.owned("template-module/module.json"))
        self.assertTrue(install.verbatim("template-module/slots/agents-guidance.md"))
        self.assertFalse(install.verbatim("README.md"))


class HostileGitTests(HardenCase):
    def test_git_env_drops_everything_but_the_config_selectors(self):
        env = {"GIT_DIR": "/x", "GIT_EXEC_PATH": "/y", "GIT_SSH_COMMAND": "z", "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_GLOBAL": "/g", "GIT_CONFIG_SYSTEM": "/s", "GIT_CONFIG_NOSYSTEM": "1", "PATH": os.environ["PATH"]}
        with mock.patch.dict(os.environ, env, clear=True):
            cleaned = install.git_env()
        self.assertEqual(sorted(k for k in cleaned if k.startswith("GIT_")),
                         ["GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_SYSTEM"])
        self.assertIn("PATH", cleaned)

    def script(self, name):
        sentinel = self.tmp / f"ran-{name}"
        script = self.tmp / f"{name}.sh"
        script.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
        script.chmod(0o755)
        return script, sentinel

    def test_hostile_environment_cannot_redirect_or_run_a_program(self):
        script, sentinel = self.script("env")
        decoy = self.tmp / "decoy"
        decoy.mkdir()
        env = {"GIT_DIR": str(decoy), "GIT_WORK_TREE": str(decoy), "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": str(script),
               "GIT_EXEC_PATH": str(decoy), "GIT_SSH_COMMAND": str(script)}
        code, out = self.create(env=env)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.target / ".git" / "HEAD").is_file())
        self.assertEqual(list(decoy.iterdir()), [])
        self.assertFalse(sentinel.exists())

    def test_global_git_configuration_naming_hooks_or_helpers_runs_nothing(self):
        script, sentinel = self.script("config")
        hooks = self.tmp / "hooks"
        hooks.mkdir()
        for hook in ("pre-commit", "post-checkout", "post-init", "reference-transaction"):
            shutil.copy(script, hooks / hook)
        templates = self.tmp / "templates"
        (templates / "hooks").mkdir(parents=True)
        shutil.copy(script, templates / "hooks" / "post-checkout")
        config = self.tmp / "gitconfig"
        config.write_text(
            f"[core]\n\tfsmonitor = {script}\n\thooksPath = {hooks}\n\tpager = {script}\n"
            f"\tsshCommand = {script}\n\tattributesFile = {self.tmp}/attrs\n"
            f"[init]\n\ttemplateDir = {templates}\n[alias]\n\tinit = !{script}\n"
            f"[filter \"x\"]\n\tclean = {script}\n")
        code, out = self.create(env={"GIT_CONFIG_GLOBAL": str(config)})
        self.assertEqual(code, 0, out)
        self.assertFalse(sentinel.exists())
        hooks_dir = self.target / ".git" / "hooks"
        self.assertEqual([p.name for p in hooks_dir.iterdir()] if hooks_dir.exists() else [], [])


if __name__ == "__main__":
    unittest.main()
