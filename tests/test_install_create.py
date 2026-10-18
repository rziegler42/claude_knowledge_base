import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import helpers
import check_kb

sys.path.insert(0, str(helpers.ROOT))
import install  # noqa: E402

IDENT = ["--git-name", "Test User", "--git-email", "test@users.noreply.github.com"]
SAFE_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


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
        expected = kit_rels() | {"README.md", "AGENTS.md", "docs/README.md", ".gitignore", ".kb-manifest"}
        self.assertEqual(project_files(self.target), expected)

    def test_name_substitution_is_limited(self):
        self.create()
        self.assertTrue((self.target / "README.md").read_text().startswith("# demo-kb\n"))
        for rel in ("docs/kb/installer.md", "tools/check_kb.py", "tools/kbparse.py"):
            self.assertEqual((self.target / rel).read_bytes(), (helpers.KIT / "files" / rel).read_bytes(), rel)
        self.assertIn("REPLACE_WITH_PROJECT_NAME", (self.target / "docs/kb/installer.md").read_text())

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
        owned = ("kb.json", "tools/", "docs/kb/", "domains/_skeleton/")
        self.assertEqual(set(manifest["files"]), {r for r in kit_rels() if r.startswith(owned)})
        for rel, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((self.target / rel).read_bytes()).hexdigest(), digest, rel)
        self.assertEqual(set(manifest["blocks"]), {
            "AGENTS.md#agents-guidance", "README.md#readme-docs",
            "docs/README.md#docs-index", ".gitignore#gitignore"})
        for key, digest in manifest["blocks"].items():
            rel, slot = key.split("#")
            text = (self.target / rel).read_text()
            begin = text.index(f"BEGIN module:knowledge-base slot:{slot}")
            end = text.index(f"END module:knowledge-base slot:{slot}")
            block = text[text.rfind("\n", 0, begin) + 1:text.index("\n", end)]
            self.assertEqual(hashlib.sha256(block.encode()).hexdigest(), digest, key)

    def test_slots_are_applied_with_markers_kept(self):
        self.create()
        for rel, slot in (("AGENTS.md", "agents-guidance"), ("README.md", "readme-docs"),
                          ("docs/README.md", "docs-index")):
            text = (self.target / rel).read_text()
            self.assertIn(f"<!-- BEGIN module:knowledge-base slot:{slot} -->", text)
            self.assertIn(f"<!-- END module:knowledge-base slot:{slot} -->", text)
            self.assertIn(f"<!-- @module-slot: {slot} -->", text)
        ignore = (self.target / ".gitignore").read_text()
        self.assertIn("# BEGIN module:knowledge-base slot:gitignore", ignore)
        self.assertIn("/sources/*", ignore.split("\n"))

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
        result = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True, cwd=self.tmp)
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

    def test_git_component_in_target(self):
        code, out, err = run_install(str(self.tmp / ".GIT" / "x"), *IDENT)
        self.assertEqual(code, 1)

    def test_skip_unsafe_entries_is_rejected_when_creating(self):
        code, out, err = self.create("--skip-unsafe-entries")
        self.assertEqual(code, 1)
        self.assertFalse(self.target.exists())

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
        expected = kit_rels() | {"README.md", "AGENTS.md", "docs/README.md", ".gitignore", ".kb-manifest"}
        for rel in expected:
            self.assertIn(rel, out, rel)

    def test_dry_run_leaves_an_existing_empty_directory_empty(self):
        self.target.mkdir()
        code, out, err = self.create("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(list(self.target.iterdir()), [])


class Criterion7KitValidation(CreateCase):
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

    def set_module(self, kit, **changes):
        path = kit / "module.json"
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

    def test_module_json_rules(self):
        cases = [("name", KeyError), ("kit_version", KeyError), ("description", KeyError),
                 ("order", KeyError), ("requires", KeyError), ("hint", KeyError),
                 ("name", "other"), ("kit_version", 1), ("order", "5"), ("requires", ["x"]),
                 ("hint", "two\nlines"), ("description", 5)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                kit = self.make_kit()
                self.set_module(kit, **{key: value})
                self.refuses_kit(kit)

    def test_module_json_missing_or_not_json(self):
        kit = self.make_kit()
        (kit / "module.json").write_text("{nope")
        self.refuses_kit(kit)
        (kit / "module.json").unlink()
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
            {"from": 2, "to": 3, "ops": [{"op": "remove", "path": "tools/new.py"}]}])
        code, out, err = run_install(str(self.target), *IDENT, kit=kit)
        self.assertEqual(code, 0, out + err)

    def test_symlink_in_kit_is_refused(self):
        kit = self.make_kit()
        os.symlink(kit / "module.json", kit / "files" / "link.md")
        self.refuses_kit(kit)

    def test_symlinked_kit_directory_is_refused(self):
        kit = self.make_kit()
        shutil.move(str(kit / "slots"), str(self.tmp / "elsewhere"))
        os.symlink(self.tmp / "elsewhere", kit / "slots")
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

    def test_unknown_slot_without_a_host_is_refused(self):
        kit = self.make_kit()
        (kit / "slots" / "mystery.md").write_text("x\n")
        self.refuses_kit(kit)

    def test_oversize_kit_file_is_refused(self):
        kit = self.make_kit()
        with open(kit / "files" / "big.bin", "wb") as handle:
            handle.truncate(install.MAX_READ + 1)
        self.refuses_kit(kit)


if __name__ == "__main__":
    unittest.main()
