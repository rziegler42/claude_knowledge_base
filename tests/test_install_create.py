import contextlib
import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import helpers
import check_kb

sys.path.insert(0, str(helpers.ROOT))
import install  # noqa: E402

IDENT = ["--git-name", "Test User", "--git-email", "test@users.noreply.github.com"]
SAFE_ENV = helpers.SAFE_ENV
REGISTER = "to register with the project template, run its install.py --register "


def run_install(*argv, kit=None):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, SAFE_ENV), \
            mock.patch("sys.stdin", io.StringIO("")), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = install.main(list(argv), kit_dir=kit)
    return code, out.getvalue(), err.getvalue()


def git(project, *args):
    env = {**os.environ, **SAFE_ENV}
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, env=env)


def project_files(root):
    found = set()
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            found.add(os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/"))
    return found


def kit_rels():
    files = helpers.KIT / "files"
    return {p.relative_to(files).as_posix() for p in files.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}


class CreateCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.target = self.tmp / "demo-kb"

    def create(self, *extra, target=None):
        return run_install(str(target or self.target), *IDENT, *extra)


class Criterion1ExactOutput(CreateCase):
    def test_creates_exactly_the_expected_files(self):
        code, out, err = self.create()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(project_files(self.target), kit_rels() | {".kb-manifest"})

    def test_name_substitution_is_limited(self):
        self.create()
        self.assertTrue((self.target / "README.md").read_text().startswith("# demo-kb\n"))
        for rel in ("docs/kb/installer.md", "tools/check_kb.py", "tools/kbparse.py",
                    "template-module/module.json", "template-module/slots/agents-guidance.md"):
            self.assertEqual((self.target / rel).read_bytes(), (helpers.KIT / "files" / rel).read_bytes(), rel)
        self.assertIn("REPLACE_WITH_PROJECT_NAME", (self.target / "docs/kb/installer.md").read_text())
        self.assertIn("REPLACE_WITH_MODULE_PATH",
                      (self.target / "template-module/slots/agents-guidance.md").read_text())

    def test_name_option(self):
        self.create("--name", "My KB")
        self.assertTrue((self.target / "README.md").read_text().startswith("# My KB\n"))

    def test_git_state(self):
        self.create()
        self.assertEqual(git(self.target, "symbolic-ref", "HEAD").stdout.strip(), "refs/heads/main")
        self.assertEqual(git(self.target, "remote").stdout.strip(), "")
        self.assertNotEqual(git(self.target, "rev-parse", "--verify", "HEAD").returncode, 0)
        self.assertEqual(git(self.target, "config", "--local", "user.name").stdout.strip(), "Test User")
        self.assertEqual(git(self.target, "config", "--local", "user.email").stdout.strip(),
                         "test@users.noreply.github.com")
        exclude = (self.target / ".git" / "info" / "exclude").read_text()
        self.assertIn("/.debug/", exclude.split("\n"))

    def test_no_sample_hooks(self):
        self.create()
        hooks = self.target / ".git" / "hooks"
        self.assertEqual([p.name for p in hooks.glob("*.sample")] if hooks.exists() else [], [])

    def test_manifest_contents_and_checksums(self):
        self.create()
        manifest = json.loads((self.target / ".kb-manifest").read_text())
        self.assertEqual(manifest["schema"], 1)
        self.assertEqual(manifest["kb_schema"], 1)
        self.assertEqual(manifest["name"], "demo-kb")
        self.assertEqual(manifest["kit_version"], "1")
        self.assertIsInstance(manifest["starter_dirty"], bool)
        owned = ("kb.json", "tools/", "docs/kb/", "domains/_skeleton/", "template-module/")
        self.assertEqual(set(manifest["files"]), {r for r in kit_rels() if r.startswith(owned)})
        for rel, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((self.target / rel).read_bytes()).hexdigest(), digest, rel)
        self.assertNotIn("blocks", manifest)
        self.assertEqual(set(manifest), {"schema", "kb_schema", "name", "kit_version",
                                         "starter_commit", "starter_dirty", "files"})

    def test_root_files_have_no_markers_or_managed_blocks(self):
        self.create()
        for rel in ("AGENTS.md", "README.md", "docs/README.md", ".gitignore"):
            text = (self.target / rel).read_text()
            for needle in ("@module-slot", "BEGIN module:", "END module:"):
                self.assertNotIn(needle, text, rel)
        self.assertIn("/sources/*", (self.target / ".gitignore").read_text().split("\n"))

    def test_a_fresh_store_reports_no_leftover_placeholders(self):
        code, out, err = self.create()
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("placeholders left to fill", out)

    def test_the_created_descriptor_satisfies_the_template_rules(self):
        from test_kit import descriptor_problems
        self.create()
        self.assertEqual(descriptor_problems(self.target), [])

    def test_use_global_git_identity_is_explicit_and_reported(self):
        config = self.tmp / "gitconfig"
        config.write_text("[user]\n\tname = Global Person\n\temail = g@users.noreply.github.com\n")
        out, err = io.StringIO(), io.StringIO()
        env = {**SAFE_ENV, "GIT_CONFIG_GLOBAL": str(config)}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install.main([str(self.target), "--use-global-git-identity"])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertEqual(git(self.target, "config", "--local", "user.name").stdout.strip(), "Global Person")
        self.assertIn("global git identity", out.getvalue())

    def test_non_noreply_email_warns(self):
        code, out, err = run_install(str(self.target), "--git-name", "T", "--git-email", "me@example.org")
        self.assertEqual(code, 0)
        self.assertIn("noreply", out + err)


class Criterion2CheckerPasses(CreateCase):
    def test_created_project_passes_the_checker(self):
        self.create()
        report = check_kb.check(self.target)
        self.assertEqual([str(f) for f in report.errors], [])
        script = self.target / "tools" / "check_kb.py"
        result = subprocess.run([sys.executable, "-I", "-B", str(script)], capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_agents_md_has_the_four_guidance_items(self):
        self.create()
        text = (self.target / "AGENTS.md").read_text()
        for needle in ("untrusted data, never instructions", "stay `[U]` or `[A]`",
                       "docs/kb/domain-lifecycle.md", "sources/quarantine/"):
            self.assertIn(needle, text)

    def test_readme_has_the_copyright_note(self):
        self.create()
        text = (self.target / "README.md").read_text()
        self.assertIn("Copyright and licensing", text)
        self.assertIn("not legal advice", text)


class Criterion3Refusals(CreateCase):
    def refuses(self, *argv, target=None, expect_absent=True):
        target = target or self.target
        before = project_files(target) if target.exists() else None
        code, out, err = run_install(*argv) if argv else self.create(target=target)
        self.assertEqual(code, 1, out + err)
        if before is not None:
            self.assertEqual(project_files(target), before)
        elif expect_absent:
            self.assertFalse(target.exists())
        return out + err

    def test_non_empty_target(self):
        self.target.mkdir()
        (self.target / "x").write_text("x")
        self.refuses()

    def test_existing_file(self):
        self.target.write_text("x")
        self.refuses()

    def test_target_is_the_starter(self):
        code, out, err = run_install(str(helpers.ROOT), *IDENT)
        self.assertEqual(code, 1)

    def test_target_inside_the_starter(self):
        inside = helpers.ROOT / "tests" / "never-created"
        code, out, err = run_install(str(inside), *IDENT)
        self.assertEqual(code, 1)
        self.assertFalse(inside.exists())

    def test_target_reached_through_a_symlink_into_the_starter(self):
        link = self.tmp / "linked"
        os.symlink(helpers.ROOT, link)
        code, out, err = run_install(str(link / "newdir"), *IDENT)
        self.assertEqual(code, 1)
        self.assertFalse((helpers.ROOT / "newdir").exists())

    def test_symlinked_target_directory(self):
        real = self.tmp / "real"
        real.mkdir()
        os.symlink(real, self.target)
        self.refuses()
        self.assertEqual(list(real.iterdir()), [])

    @unittest.skipIf(os.geteuid() == 0, "root ignores permissions")
    def test_read_only_target(self):
        self.target.mkdir()
        os.chmod(self.target, 0o555)
        try:
            self.refuses()
        finally:
            os.chmod(self.target, 0o755)

    def test_missing_identity_in_a_non_interactive_run(self):
        code, out, err = run_install(str(self.target))
        self.assertEqual(code, 1)
        self.assertIn("identity", out + err)
        self.assertFalse(self.target.exists())

    def test_bad_names(self):
        for name in ("", " lead", ".dot", "-dash", "a" * 65, "semi;colon", "new\nline", "quo\"te"):
            with self.subTest(name=name):
                code, out, err = run_install(str(self.target), *IDENT, f"--name={name}")
                self.assertEqual(code, 1, out + err)
                self.assertFalse(self.target.exists())

    def test_non_printable_identity(self):
        code, out, err = run_install(str(self.target), "--git-name", "A\nB", "--git-email", "a@b.c")
        self.assertEqual(code, 1)

    def test_empty_target_does_not_install_into_the_current_directory(self):
        empty = self.tmp / "cwd"
        empty.mkdir()
        old = os.getcwd()
        os.chdir(empty)
        try:
            code, out, err = run_install("", *IDENT)
        finally:
            os.chdir(old)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(list(empty.iterdir()), [])

    def test_git_component_in_target(self):
        code, out, err = run_install(str(self.tmp / ".GIT" / "x"), *IDENT)
        self.assertEqual(code, 1)

    def test_empty_existing_directory_is_accepted(self):
        self.target.mkdir()
        code, out, err = self.create()
        self.assertEqual(code, 0, out + err)

    def test_target_under_a_symlinked_ancestor_succeeds(self):
        real = self.tmp / "real"
        real.mkdir()
        link = self.tmp / "ancestor"
        os.symlink(real, link)
        code, out, err = run_install(str(link / "proj"), *IDENT)
        self.assertEqual(code, 0, out + err)
        self.assertTrue((real / "proj" / "kb.json").is_file())


class Criterion4DryRun(CreateCase):
    def test_dry_run_writes_nothing_and_lists_every_path(self):
        code, out, err = self.create("--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.target.exists())
        for rel in kit_rels() | {".kb-manifest"}:
            self.assertIn(rel, out, rel)
        self.assertNotIn(REGISTER, out)

    def test_dry_run_leaves_an_existing_empty_directory_empty(self):
        self.target.mkdir()
        code, out, err = self.create("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(list(self.target.iterdir()), [])


class Criterion9KitValidation(CreateCase):
    kits = 0

    def make_kit(self):
        type(self).kits += 1
        kit = self.tmp / f"kit{self.kits}"
        shutil.copytree(helpers.KIT, kit, ignore=shutil.ignore_patterns("__pycache__"))
        return kit

    def refuses_kit(self, kit):
        code, out, err = run_install(str(self.target), *IDENT, kit=kit)
        self.assertEqual(code, 1, out + err)
        self.assertFalse(self.target.exists())
        return out + err

    def set_kit_json(self, kit, **changes):
        path = kit / "kit.json"
        data = json.loads(path.read_text())
        for key, value in changes.items():
            if value is KeyError:
                del data[key]
            else:
                data[key] = value
        path.write_text(json.dumps(data))

    def test_the_real_kit_is_accepted(self):
        code, out, err = run_install(str(self.target), *IDENT, kit=self.make_kit())
        self.assertEqual(code, 0, out + err)

    def test_kit_json_rules(self):
        cases = [("kit_version", KeyError), ("hint", KeyError), ("kit_version", 1),
                 ("kit_version", ""), ("hint", "two\nlines"), ("hint", 5)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                kit = self.make_kit()
                self.set_kit_json(kit, **{key: value})
                self.refuses_kit(kit)

    def test_unknown_kit_json_keys_are_ignored(self):
        kit = self.make_kit()
        self.set_kit_json(kit, extra="x")
        code, out, err = run_install(str(self.target), *IDENT, kit=kit)
        self.assertEqual(code, 0, out + err)

    def test_kit_json_missing_or_not_json(self):
        kit = self.make_kit()
        (kit / "kit.json").write_text("{nope")
        self.refuses_kit(kit)
        (kit / "kit.json").unlink()
        self.refuses_kit(kit)

    def test_an_old_module_json_kit_is_refused(self):
        kit = self.make_kit()
        (kit / "kit.json").rename(kit / "module.json")
        self.refuses_kit(kit)

    def migrations(self, kit, steps):
        (kit / "migrations.json").write_text(json.dumps({"steps": steps}))

    def test_migrations_rules(self):
        op = {"op": "add", "path": "tools/new.py", "source": "tools/kbparse.py"}
        bad = [
            [{"from": 2, "to": 3, "ops": []}],
            [{"from": 1, "to": 2, "ops": []}, {"from": 3, "to": 4, "ops": []}],
            [{"from": 1, "to": 3, "ops": []}],
            [{"from": 1, "to": 2, "ops": [{"op": "chmod", "path": "tools/x"}]}],
            [{"from": 1, "to": 2, "ops": [{**op, "path": "playbook/README.md"}]}],
            [{"from": 1, "to": 2, "ops": [{**op, "path": "README.md"}]}],
            [{"from": 1, "to": 2, "ops": [{**op, "path": "../x"}]}],
            [{"from": 1, "to": 2, "ops": [{**op, "path": "tools/.git/x"}]}],
            [{"from": 1, "to": 2, "ops": [{**op, "source": "tools/missing.py"}]}],
            [{"from": 1, "to": 2, "ops": [{"op": "remove", "path": "catalog/x.md"}]}],
        ]
        for steps in bad:
            with self.subTest(steps=steps):
                kit = self.make_kit()
                self.migrations(kit, steps)
                self.refuses_kit(kit)

    def test_a_valid_migration_chain_is_accepted(self):
        kit = self.make_kit()
        self.migrations(kit, [
            {"from": 1, "to": 2, "ops": [{"op": "add", "path": "tools/new.py", "source": "tools/kbparse.py"}]},
            {"from": 2, "to": 3, "ops": [{"op": "remove", "path": "template-module/slots/agents-guidance.md"}]}])
        code, out, err = run_install(str(self.target), *IDENT, kit=kit)
        self.assertEqual(code, 0, out + err)

    def test_symlink_in_kit_is_refused(self):
        kit = self.make_kit()
        os.symlink(kit / "kit.json", kit / "files" / "link.md")
        self.refuses_kit(kit)

    def test_symlinked_kit_directory_is_refused(self):
        kit = self.make_kit()
        shutil.move(str(kit / "files"), str(self.tmp / "elsewhere"))
        os.symlink(self.tmp / "elsewhere", kit / "files")
        self.refuses_kit(kit)

    def test_git_component_in_kit_is_refused_case_insensitively(self):
        kit = self.make_kit()
        (kit / "files" / ".GIT").mkdir()
        (kit / "files" / ".GIT" / "config").write_text("x")
        self.refuses_kit(kit)

    def test_manifest_name_in_kit_is_refused(self):
        kit = self.make_kit()
        (kit / "files" / ".KB-MANIFEST").write_text("{}")
        self.refuses_kit(kit)

    def test_oversize_kit_file_is_refused(self):
        kit = self.make_kit()
        with open(kit / "files" / "big.bin", "wb") as handle:
            handle.truncate(install.MAX_READ + 1)
        self.refuses_kit(kit)


class Criterion5RemovedOptions(CreateCase):
    def usage_error(self, *argv):
        err = io.StringIO()
        with mock.patch.dict(os.environ, SAFE_ENV), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as raised:
            install.main(list(argv))
        self.assertEqual(raised.exception.code, 2)
        return err.getvalue()

    def test_add_to_is_an_unknown_option(self):
        existing = self.tmp / "existing"
        existing.mkdir()
        self.assertIn("--add-to", self.usage_error("--add-to", str(existing)))
        self.assertEqual(list(existing.iterdir()), [])

    def test_skip_unsafe_entries_is_an_unknown_option(self):
        self.assertIn("--skip-unsafe-entries", self.usage_error(str(self.target), *IDENT, "--skip-unsafe-entries"))
        self.assertFalse(self.target.exists())

    def test_a_target_is_required(self):
        self.usage_error()

    def test_help_lists_neither_option(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            install.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertNotIn("--add-to", out.getvalue())
        self.assertNotIn("--skip-unsafe-entries", out.getvalue())

    def test_exit_status_three_is_gone(self):
        self.assertFalse(hasattr(install, "EXIT_ALREADY_INSTALLED"))

    def test_installer_source_has_no_marker_or_layering_machinery(self):
        text = (helpers.ROOT / "install.py").read_text(encoding="utf-8")
        for needle in ("@module-slot", "BEGIN module", "run_add_to", "scan_markers", "apply_fragment",
                       "walk_content", "SLOT_HOSTS", "skip_unsafe_entries"):
            self.assertNotIn(needle, text)


class Criterion7RegistrationHint(CreateCase):
    def hint(self, out):
        lines = [l for l in out.split("\n") if l.startswith(REGISTER)]
        self.assertEqual(len(lines), 1, out)
        return lines[0]

    def test_valid_module_name_has_no_suffix(self):
        target = self.tmp / "my_kb"
        code, out, err = run_install(str(target), *IDENT)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.hint(out), REGISTER + shlex.quote(os.path.realpath(target)))
        self.assertIn("see playbook/README.md", out)

    def test_hint_uses_the_real_path_behind_a_symlinked_ancestor(self):
        real = self.tmp / "real"
        real.mkdir()
        os.symlink(real, self.tmp / "ancestor")
        code, out, err = run_install(str(self.tmp / "ancestor" / "kb"), *IDENT)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.hint(out), REGISTER + shlex.quote(str(real.resolve() / "kb")))

    def test_directory_names_the_template_would_refuse_get_a_suggested_name(self):
        cases = {"My KB": "my-kb", "my.kb": "my-kb", "Demo": "demo", "-x": "x", "a  b": "a-b",
                 "###": "kb", "_lead": "lead", "A.B_C": "a-b_c"}
        for dirname, suggestion in cases.items():
            with self.subTest(dirname=dirname):
                target = self.tmp / dirname
                code, out, err = run_install(str(target), *IDENT, "--name", "kb")
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.hint(out),
                                 REGISTER + shlex.quote(os.path.realpath(target)) + f" --name {suggestion}")

    def test_the_suggestion_is_a_valid_template_name(self):
        import re
        for dirname in ("My KB", "###", "a" * 10, "x y z", "Ünï", "--", "9 lives"):
            self.assertRegex(install.suggest_module_name(dirname), r"[a-z0-9][a-z0-9_-]*\Z")
        self.assertIsNone(re.match(r"[a-z0-9][a-z0-9_-]*\Z", "My KB"))

    def test_the_hint_is_absent_after_a_dry_run_and_after_a_refusal(self):
        code, out, err = self.create("--dry-run")
        self.assertEqual(code, 0)
        self.assertNotIn(REGISTER, out + err)
        self.target.mkdir()
        (self.target / "x").write_text("x")
        code, out, err = self.create()
        self.assertEqual(code, 1)
        self.assertNotIn(REGISTER, out + err)

    def test_the_hint_runs_nothing_and_writes_nothing_outside_the_target(self):
        before = helpers.snapshot(self.tmp)
        code, out, err = self.create()
        self.assertEqual(code, 0, out + err)
        after = helpers.snapshot(self.tmp)
        extra = {k for k in after if k not in before and not k.startswith("demo-kb")}
        self.assertEqual(extra, set())

    def test_a_non_printable_real_path_is_refused_before_any_write(self):
        target = self.tmp / "new\nline"
        code, out, err = run_install(str(target), *IDENT, "--name", "kb")
        self.assertEqual(code, 1)
        self.assertFalse(target.exists())
        self.assertNotIn(REGISTER, out + err)

    def test_a_path_with_shell_characters_is_quoted(self):
        target = self.tmp / "it's $HOME;x"
        code, out, err = run_install(str(target), *IDENT, "--name", "kb")
        self.assertEqual(code, 0, out + err)
        line = self.hint(out)
        words = shlex.split(line[len(REGISTER):])
        self.assertEqual(words[0], os.path.realpath(target))
        self.assertEqual(words[1:], ["--name", "it-s-home-x"])


if __name__ == "__main__":
    unittest.main()
