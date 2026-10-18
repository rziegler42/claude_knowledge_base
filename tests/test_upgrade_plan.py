"""install.py --upgrade --dry-run: reading a store and classifying its owned files (criteria 13 and 15)."""
import json
import os
import unittest
from pathlib import Path

import helpers
import stores
from stores import make_kit, make_store, manifest, sha, upgrade, write_manifest

NEWER = "\n# a newer line from the starter\n"


class PlanCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.kit = make_kit(self.tmp)
        self.store = make_store(self.tmp, self.kit)
        self.tools = self.store / "tools"

    def newer(self, rel, text=NEWER):
        path = self.kit / "files" / rel
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def dry(self, *extra):
        return upgrade(self.store, "--dry-run", *extra, kit=self.kit)

    def refuses(self, *extra):
        before = helpers.snapshot(self.tmp / "store")
        code, out, err = self.dry(*extra)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(helpers.snapshot(self.tmp / "store"), before, "a refused run must write nothing")
        self.assertNotIn("Traceback", out + err)
        return out + err

    def lines(self, out):
        return [line for line in out.split("\n") if line.strip()]


class UsageTests(PlanCase):
    def test_upgrade_needs_dir_and_rejects_creation_arguments(self):
        for argv in (["--upgrade"], ["--upgrade", str(self.tmp / "x"), "--dir", str(self.store)],
                     ["--upgrade", "--dir", str(self.store), "--name", "N"],
                     ["--upgrade", "--dir", str(self.store), "--git-name", "N"],
                     ["--upgrade", "--dir", str(self.store), "--git-email", "a@b.c"],
                     ["--upgrade", "--dir", str(self.store), "--use-global-git-identity"],
                     ["--dir", str(self.store)]):
            with self.subTest(argv=argv):
                code, out, err = stores.run_main(*argv, kit=self.kit)
                self.assertEqual(code, 2, out + err)

    def test_creation_is_unchanged(self):
        code, out, err = stores.run_main(str(self.tmp / "fresh"), *stores.IDENT, "--dry-run", kit=self.kit)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(stores.run_main(kit=self.kit)[0], 2)


class TableTests(PlanCase):
    def test_an_unchanged_store_has_nothing_to_do(self):
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("nothing to do", out)
        self.assertFalse([l for l in self.lines(out) if l.split()[0] in ("add", "replace", "adopt", "skip", "record", "conflict")])

    def test_dry_run_writes_nothing(self):
        self.newer("tools/kbfiles.py")
        (self.tools / "kbparse.py").unlink()
        before = helpers.snapshot(self.store)
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(helpers.snapshot(self.store), before)

    def test_recorded_matching_the_record_but_not_the_kit_is_replaced(self):
        self.newer("tools/kbfiles.py")
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("replace tools/kbfiles.py", out)

    def test_a_missing_file_is_added(self):
        (self.tools / "kbparse.py").unlink()
        code, out, err = self.dry()
        self.assertIn("add tools/kbparse.py", out)

    def test_an_edited_file_is_skipped_and_kept(self):
        self.newer("tools/kbfiles.py")
        path = self.tools / "kbfiles.py"
        path.write_text(path.read_text(encoding="utf-8") + "\n# the owner's change\n", encoding="utf-8")
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("skip tools/kbfiles.py", out)
        self.assertNotIn("replace tools/kbfiles.py", out)

    def test_an_edited_file_that_now_equals_the_kit_is_recorded(self):
        self.newer("tools/kbfiles.py")
        (self.tools / "kbfiles.py").write_bytes((self.kit / "files" / "tools" / "kbfiles.py").read_bytes())
        code, out, err = self.dry()
        self.assertIn("record tools/kbfiles.py", out)

    def test_an_unrecorded_file_equal_to_the_kit_is_adopted_and_a_different_one_is_a_conflict(self):
        data = manifest(self.store)
        del data["files"]["tools/kbfiles.py"]
        del data["files"]["tools/kbparse.py"]
        write_manifest(self.store, data)
        (self.tools / "kbparse.py").write_text("# something else\n", encoding="utf-8")
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("adopt tools/kbfiles.py", out)
        self.assertIn("conflict tools/kbparse.py", out)

    def test_a_recorded_file_no_longer_in_the_kit_is_reported_and_kept(self):
        (self.tools / "old_tool.py").write_text("print('old')\n", encoding="utf-8")
        data = manifest(self.store)
        data["files"]["tools/old_tool.py"] = sha(self.tools / "old_tool.py")
        write_manifest(self.store, data)
        code, out, err = self.dry()
        self.assertIn("report tools/old_tool.py", out)
        self.assertTrue((self.tools / "old_tool.py").is_file())

    def test_names_are_substituted_with_the_manifest_name(self):
        path = self.kit / "files" / "domains" / "_skeleton" / "log.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nThis store is REPLACE_WITH_PROJECT_NAME.\n", encoding="utf-8")
        store = Path(self.tmp) / "My KB"
        code, out, err = stores.run_main(str(store), *stores.IDENT, "--name", "My KB", kit=self.kit)
        self.assertEqual(code, 0, out + err)
        self.assertIn("This store is My KB.", (store / "domains" / "_skeleton" / "log.md").read_text(encoding="utf-8"))
        code, out, err = upgrade(store, "--dry-run", kit=self.kit)
        self.assertEqual(code, 0, out + err)
        self.assertIn("nothing to do", out)

    def test_the_verbatim_directories_are_not_substituted(self):
        path = self.kit / "files" / "docs" / "kb" / "installer.md"
        self.assertIn("REPLACE_WITH_PROJECT_NAME", path.read_text(encoding="utf-8"))
        code, out, err = self.dry()
        self.assertIn("nothing to do", out)

    def test_every_owned_prefix_is_planned(self):
        for rel in ("kb.json", "tools/kbfiles.py", "docs/kb/installer.md", "domains/_skeleton/log.md",
                    "template-module/module.json"):
            (self.store / rel).unlink()
        code, out, err = self.dry()
        for rel in ("kb.json", "tools/kbfiles.py", "docs/kb/installer.md", "domains/_skeleton/log.md",
                    "template-module/module.json"):
            self.assertIn(f"add {rel}", out)

    def test_content_and_root_files_are_never_in_the_plan(self):
        for rel in ("README.md", "AGENTS.md", ".gitignore", "docs/README.md"):
            (self.store / rel).write_text("owner's own text\n", encoding="utf-8")
        helpers.write(self.store / "domains" / "mine", "README.md", "mine\n")
        code, out, err = self.dry()
        for needle in ("README.md", "AGENTS.md", ".gitignore", "domains/mine"):
            self.assertNotIn(needle, out.replace("domains/_skeleton", ""))


class ManifestTests(PlanCase):
    def put(self, text):
        (self.store / ".kb-manifest").write_text(text, encoding="utf-8")

    def test_bad_manifests_are_refused_and_nothing_is_written(self):
        good = manifest(self.store)
        digest = "a" * 64
        cases = {
            "not json": "{nope",
            "a list": "[]",
            "unknown schema": json.dumps({**good, "schema": 2}),
            "no schema": json.dumps({k: v for k, v in good.items() if k != "schema"}),
            "a bad name": json.dumps({**good, "name": "../x"}),
            "an empty name": json.dumps({**good, "name": ""}),
            "a multi-line name": json.dumps({**good, "name": "a\nb"}),
            "a name that is not text": json.dumps({**good, "name": 5}),
            "files is not an object": json.dumps({**good, "files": []}),
            "a checksum of the wrong length": json.dumps({**good, "files": {"tools/kbfiles.py": "abc"}}),
            "an upper-case checksum": json.dumps({**good, "files": {"tools/kbfiles.py": digest.upper()}}),
            "a checksum that is not text": json.dumps({**good, "files": {"tools/kbfiles.py": 5}}),
            "a traversal key": json.dumps({**good, "files": {"../x": digest}}),
            "a .git key": json.dumps({**good, "files": {".GIT/config": digest}}),
            "a key with dots": json.dumps({**good, "files": {"tools/../x": digest}}),
            "a backslash key": json.dumps({**good, "files": {"tools\\x": digest}}),
            "an absolute key": json.dumps({**good, "files": {"/etc/passwd": digest}}),
            "a manifest-name key": json.dumps({**good, "files": {".KB-MANIFEST": digest}}),
            "a nul key": json.dumps({**good, "files": {"tools/a\u0000b": digest}}),
            "duplicate keys": '{"schema": 1, "schema": 1, "name": "x", "kb_schema": 1, "files": {}}',
            "duplicate file keys": '{"schema": 1, "kb_schema": 1, "name": "store", "files": {"tools/a": "%s", "tools/a": "%s"}}' % (digest, digest),
            "a non-integer kb_schema": json.dumps({**good, "kb_schema": "1"}),
            "a boolean kb_schema": json.dumps({**good, "kb_schema": True}),
            "deep nesting": "[" * 100000,
            "too large": json.dumps({**good, "padding": "x" * (1024 * 1024)}),
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                self.put(text)
                self.refuses()

    def test_a_missing_manifest_or_a_symlinked_or_special_one(self):
        os.unlink(self.store / ".kb-manifest")
        self.assertIn("manifest", self.refuses().lower())
        os.symlink(self.tmp / "elsewhere.json", self.store / ".kb-manifest")
        self.refuses()
        os.unlink(self.store / ".kb-manifest")
        os.mkfifo(self.store / ".kb-manifest")
        self.refuses()

    def test_keys_outside_the_owned_prefixes_are_ignored_and_listed(self):
        data = manifest(self.store)
        data["files"]["playbook/README.md"] = "b" * 64
        data["files"]["domains/mine/README.md"] = "b" * 64
        data["files"]["README.md"] = "b" * 64
        write_manifest(self.store, data)
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        for key in ("playbook/README.md", "domains/mine/README.md", "README.md"):
            self.assertIn(f"ignored manifest entry {key}", out)

    def test_unknown_keys_and_the_old_blocks_key_are_tolerated(self):
        data = manifest(self.store)
        data["blocks"] = {"AGENTS.md#agents-guidance": "c" * 64}
        data["something_new"] = {"a": 1}
        write_manifest(self.store, data)
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)

    def test_the_manifest_is_the_only_input_from_the_store_besides_owned_files(self):
        # content directories hold a FIFO and a symlink; they are never opened
        os.mkfifo(self.store / "catalog" / "pipe")
        os.symlink(self.tmp, self.store / "sources" / "link")
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)


class StoreLocationTests(PlanCase):
    def run_dir(self, path):
        return stores.run_main("--upgrade", "--dir", str(path), "--dry-run", kit=self.kit)

    def test_missing_and_non_directory_paths(self):
        for path in (self.tmp / "missing", self.tmp / "file"):
            if path.name == "file":
                path.write_text("x")
            code, out, err = self.run_dir(path)
            self.assertEqual(code, 1, out + err)

    def test_a_symlinked_store_directory(self):
        os.symlink(self.store, self.tmp / "link")
        code, out, err = self.run_dir(self.tmp / "link")
        self.assertEqual(code, 1, out + err)

    def test_the_starter_itself_and_paths_inside_it(self):
        for path in (helpers.ROOT, helpers.ROOT / "tests", helpers.ROOT / "kit", helpers.ROOT / "kit" / "files"):
            with self.subTest(path=str(path.relative_to(helpers.ROOT))):
                code, out, err = self.run_dir(path)
                self.assertEqual(code, 1, out + err)
                self.assertIn("starter", out + err)

    def test_a_path_with_a_git_component(self):
        code, out, err = self.run_dir(self.tmp / ".GIT" / "x")
        self.assertEqual(code, 1, out + err)

    def test_a_directory_that_is_not_a_store(self):
        (self.tmp / "empty").mkdir()
        code, out, err = self.run_dir(self.tmp / "empty")
        self.assertEqual(code, 1, out + err)
        self.assertIn("manifest", (out + err).lower())


class OwnedPathHardeningTests(PlanCase):
    def test_a_symlink_at_an_owned_path(self):
        victim = self.tmp / "victim.py"
        victim.write_text("keep\n")
        (self.tools / "kbfiles.py").unlink()
        os.symlink(victim, self.tools / "kbfiles.py")
        out = self.refuses()
        self.assertIn("tools/kbfiles.py", out)
        self.assertEqual(victim.read_text(), "keep\n")

    def test_a_fifo_at_an_owned_path_does_not_hang(self):
        (self.tools / "kbparse.py").unlink()
        os.mkfifo(self.tools / "kbparse.py")
        self.assertIn("tools/kbparse.py", self.refuses())

    def test_an_oversize_owned_file(self):
        with open(self.tools / "kbfiles.py", "wb") as handle:
            handle.truncate(stores.install.MAX_READ + 1)
        self.assertIn("tools/kbfiles.py", self.refuses())

    def test_a_symlinked_owned_directory(self):
        outside = self.tmp / "outside-tools"
        os.rename(self.tools, outside)
        os.symlink(outside, self.tools)
        out = self.refuses()
        self.assertIn("tools", out)
        self.assertEqual(sorted(p.name for p in outside.iterdir() if p.name.startswith(".kbtmp")), [])

    def test_a_symlinked_skeleton_or_descriptor_directory(self):
        for rel in ("domains/_skeleton", "template-module", "docs/kb"):
            with self.subTest(rel=rel):
                real = self.store / rel
                moved = self.tmp / ("moved-" + rel.replace("/", "-"))
                os.rename(real, moved)
                os.symlink(moved, real)
                try:
                    self.refuses()
                finally:
                    os.unlink(real)
                    os.rename(moved, real)

    def test_a_file_where_an_owned_directory_should_be(self):
        shutil_target = self.store / "template-module"
        import shutil
        shutil.rmtree(shutil_target)
        shutil_target.write_text("not a directory")
        self.refuses()

    def test_a_hostile_git_directory_in_the_store_runs_nothing(self):
        sentinel = self.tmp / "ran"
        script = self.tmp / "evil.sh"
        script.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
        script.chmod(0o755)
        (self.store / ".git").mkdir(exist_ok=True)
        (self.store / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (self.store / ".git" / "config").write_text(
            f"[core]\n\tfsmonitor = {script}\n\thooksPath = {self.tmp}\n[alias]\n\tstatus = !{script}\n")
        env = {"GIT_DIR": str(self.store / ".git"), "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor",
               "GIT_CONFIG_VALUE_0": str(script)}
        code, out, err = stores.run_main("--upgrade", "--dir", str(self.store), "--dry-run", kit=self.kit, env=env)
        self.assertEqual(code, 0, out + err)
        self.assertFalse(sentinel.exists())


class ProjectContentTests(PlanCase):
    def test_content_is_byte_identical_after_a_dry_run(self):
        helpers.write(self.store / "domains" / "mine", "README.md", "mine\n")
        helpers.write(self.store / "catalog", "paper.md", "---\nstem: paper\n---\n")
        helpers.write(self.store / "sources", "paper.pdf", "%PDF-1.7\n")
        before = stores.content_checksums(self.store)
        self.newer("tools/kbfiles.py")
        self.dry()
        self.assertEqual(stores.content_checksums(self.store), before)


if __name__ == "__main__":
    unittest.main()
