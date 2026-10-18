"""install.py --upgrade: the schema check and the migration operations (criterion 16)."""
import json
import os
import unittest

import helpers
from stores import make_kit, make_store, manifest, sha, upgrade, write_manifest

NEWER = "\n# newer\n"


def chain_kit(tmp, name="chain"):
    """A kit at schema 3 whose chain is: 1->2 add tools/new_tool.py, replace tools/kbfiles.py;
    2->3 remove tools/old_tool.py, replace docs/kb/installer.md."""
    kit = make_kit(tmp, name)
    files = kit / "files"
    meta = json.loads((files / "kb.json").read_text(encoding="utf-8"))
    meta["schema"] = 3
    (files / "kb.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (files / "tools" / "new_tool.py").write_text("print('new')\n", encoding="utf-8")
    for rel in ("tools/kbfiles.py", "docs/kb/installer.md"):
        path = files / rel
        path.write_text(path.read_text(encoding="utf-8") + NEWER, encoding="utf-8")
    (kit / "migrations.json").write_text(json.dumps({"steps": [
        {"from": 1, "to": 2, "ops": [
            {"op": "add", "path": "tools/new_tool.py", "source": "tools/new_tool.py"},
            {"op": "replace", "path": "tools/kbfiles.py", "source": "tools/kbfiles.py"}]},
        {"from": 2, "to": 3, "ops": [
            {"op": "remove", "path": "tools/old_tool.py"},
            {"op": "replace", "path": "docs/kb/installer.md", "source": "docs/kb/installer.md"}]},
    ]}, indent=2) + "\n", encoding="utf-8")
    return kit


class MigrationCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.base = make_kit(self.tmp, "base")
        self.store = make_store(self.tmp, self.base)
        self.kit = chain_kit(self.tmp)
        self.old = self.store / "tools" / "old_tool.py"
        self.old.write_text("print('old')\n", encoding="utf-8")
        data = manifest(self.store)
        data["files"]["tools/old_tool.py"] = sha(self.old)
        write_manifest(self.store, data)

    def dry(self, kit=None):
        return upgrade(self.store, "--dry-run", kit=kit or self.kit)

    def refuses(self, kit=None):
        before = helpers.snapshot(self.store)
        code, out, err = self.dry(kit)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(helpers.snapshot(self.store), before, "a refused run must write nothing")
        self.assertNotIn("Traceback", out + err)
        return out + err

    def set_schemas(self, manifest_schema=None, kb_schema=None):
        if manifest_schema is not None:
            data = manifest(self.store)
            data["kb_schema"] = manifest_schema
            write_manifest(self.store, data)
        if kb_schema is not None:
            path = self.store / "kb.json"
            meta = json.loads(path.read_text(encoding="utf-8"))
            meta["schema"] = kb_schema
            path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
            data = manifest(self.store)
            data["files"]["kb.json"] = sha(path)
            write_manifest(self.store, data)


class SchemaCheckTests(MigrationCase):
    def test_a_lower_store_with_no_chain_refuses_and_points_at_the_docs(self):
        for steps in ([], [{"from": 1, "to": 2, "ops": []}]):
            with self.subTest(steps=len(steps)):
                (self.kit / "migrations.json").write_text(json.dumps({"steps": steps}), encoding="utf-8")
                out = self.refuses()
                self.assertIn("docs/kb", out)
                self.assertIn("1", out)
                self.assertIn("3", out)

    def test_a_higher_store_refuses(self):
        self.set_schemas(manifest_schema=2, kb_schema=2)
        out = self.refuses(kit=self.base)
        self.assertIn("newer", out)

    def test_a_manifest_and_kb_json_that_disagree_refuse(self):
        self.set_schemas(kb_schema=2)  # kb.json says 2, manifest says 1, kit says 3
        self.assertIn("kb.json", self.refuses())

    def test_a_malformed_store_kb_json_refuses(self):
        for text in ("{nope", "[]", '{"schema": "1"}', '{"schema": true}', '{"kind": "knowledge-base"}'):
            with self.subTest(text=text):
                (self.store / "kb.json").write_text(text, encoding="utf-8")
                self.assertIn("kb.json", self.refuses())

    def test_the_interrupted_state_is_accepted(self):
        # kb.json was renamed to the kit's schema but the manifest still says 1
        self.set_schemas(kb_schema=3)
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("migrate", out)

    def test_an_equal_schema_runs_no_migration_steps(self):
        code, out, err = self.dry(kit=self.base)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("migrate", out)

    def test_a_missing_store_kb_json_is_planned_as_an_add(self):
        os.unlink(self.store / "kb.json")
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("add kb.json", out)


class ChainTests(MigrationCase):
    def test_the_whole_chain_is_planned_in_order(self):
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        order = [out.index(f"migrate {op} {rel}") for op, rel in (
            ("add", "tools/new_tool.py"), ("replace", "tools/kbfiles.py"),
            ("remove", "tools/old_tool.py"), ("replace", "docs/kb/installer.md"))]
        self.assertEqual(order, sorted(order))
        self.assertIn("1 -> 3", out)

    def test_only_the_steps_after_the_stores_schema_run(self):
        self.set_schemas(manifest_schema=2, kb_schema=2)
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("migrate add tools/new_tool.py", out)
        self.assertIn("migrate remove tools/old_tool.py", out)
        self.assertIn("2 -> 3", out)

    def test_nothing_else_is_removed(self):
        code, out, err = self.dry()
        self.assertEqual([l for l in out.split("\n") if "remove" in l and not l.startswith("migrate")], [])
        self.assertEqual(len([l for l in out.split("\n") if l.startswith("migrate remove")]), 1)

    def test_a_path_the_ordinary_table_also_replaces_is_planned_once_per_stage(self):
        # kbfiles.py: the migration replaces it with the kit file, which then already equals the kit
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("\nreplace tools/kbfiles.py", out)


class AddTests(MigrationCase):
    def test_present_and_different_is_a_conflict(self):
        (self.store / "tools" / "new_tool.py").write_text("print('mine')\n", encoding="utf-8")
        out = self.refuses()
        self.assertIn("tools/new_tool.py", out)

    def test_present_and_equal_is_complete(self):
        (self.store / "tools" / "new_tool.py").write_text("print('new')\n", encoding="utf-8")
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("migrate add tools/new_tool.py (already done)", out)

    def test_absent_is_written(self):
        code, out, err = self.dry()
        self.assertIn("migrate add tools/new_tool.py (written from the starter)", out)


class ReplaceTests(MigrationCase):
    def test_an_edited_file_is_a_conflict(self):
        path = self.store / "tools" / "kbfiles.py"
        path.write_text(path.read_text(encoding="utf-8") + "\n# mine\n", encoding="utf-8")
        out = self.refuses()
        self.assertIn("tools/kbfiles.py", out)

    def test_a_file_already_equal_to_the_source_is_complete(self):
        path = self.store / "tools" / "kbfiles.py"
        path.write_bytes((self.kit / "files" / "tools" / "kbfiles.py").read_bytes())
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("migrate replace tools/kbfiles.py (already done)", out)

    def test_a_missing_file_is_a_conflict(self):
        os.unlink(self.store / "docs" / "kb" / "installer.md")
        self.assertIn("docs/kb/installer.md", self.refuses())

    def test_an_unrecorded_different_file_is_a_conflict(self):
        data = manifest(self.store)
        del data["files"]["tools/kbfiles.py"]
        write_manifest(self.store, data)
        path = self.store / "tools" / "kbfiles.py"
        path.write_text(path.read_text(encoding="utf-8") + "\n# mine\n", encoding="utf-8")
        self.assertIn("tools/kbfiles.py", self.refuses())


class RemoveTests(MigrationCase):
    def test_a_matching_regular_file_is_removed(self):
        code, out, err = self.dry()
        self.assertIn("migrate remove tools/old_tool.py (deleted)", out)
        self.assertTrue(self.old.exists())  # a dry run deletes nothing

    def test_an_edited_file_is_a_conflict(self):
        self.old.write_text("print('mine')\n", encoding="utf-8")
        self.assertIn("tools/old_tool.py", self.refuses())

    def test_an_absent_file_is_complete(self):
        os.unlink(self.old)
        data = manifest(self.store)
        del data["files"]["tools/old_tool.py"]
        write_manifest(self.store, data)
        code, out, err = self.dry()
        self.assertEqual(code, 0, out + err)
        self.assertIn("migrate remove tools/old_tool.py (already absent)", out)

    def test_an_unrecorded_file_is_a_conflict(self):
        data = manifest(self.store)
        del data["files"]["tools/old_tool.py"]
        write_manifest(self.store, data)
        self.assertIn("tools/old_tool.py", self.refuses())

    def test_a_symlink_or_fifo_is_refused_not_followed(self):
        victim = self.tmp / "victim.py"
        victim.write_text("print('old')\n", encoding="utf-8")
        os.unlink(self.old)
        os.symlink(victim, self.old)
        self.assertIn("tools/old_tool.py", self.refuses())
        self.assertEqual(victim.read_text(encoding="utf-8"), "print('old')\n")
        os.unlink(self.old)
        os.mkfifo(self.old)
        self.assertIn("tools/old_tool.py", self.refuses())

    def test_a_directory_at_the_path_is_refused(self):
        os.unlink(self.old)
        self.old.mkdir()
        self.assertIn("tools/old_tool.py", self.refuses())

    def test_every_conflict_is_listed_at_once(self):
        self.old.write_text("print('mine')\n", encoding="utf-8")
        (self.store / "tools" / "new_tool.py").write_text("print('mine')\n", encoding="utf-8")
        out = self.refuses()
        self.assertIn("tools/old_tool.py", out)
        self.assertIn("tools/new_tool.py", out)


if __name__ == "__main__":
    unittest.main()
