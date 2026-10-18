"""install.py --upgrade: applying, idempotence, and recovery (criteria 13, 14, 15, 17, 18)."""
import json
import os
import shutil
import stat
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import helpers
import stores
from stores import content_checksums, make_kit, make_store, manifest, sha, upgrade, write_manifest
from test_upgrade_migrations import chain_kit

install = stores.install
OWNED_DIRS = ("tools", "docs/kb", "domains/_skeleton", "template-module")


def owned_state(store):
    """Bytes of every owned file in a store, keyed by relative path."""
    state = {}
    store = Path(store)
    if (store / "kb.json").is_file():
        state["kb.json"] = (store / "kb.json").read_bytes()
    for rel in OWNED_DIRS:
        for path in sorted((store / rel).rglob("*")):
            if path.is_file() and not path.name.startswith(".kbtmp-"):
                state[path.relative_to(store).as_posix()] = path.read_bytes()
    return state


def newer(kit, rel, text="\n# newer\n"):
    path = kit / "files" / rel
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


class ApplyCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.base = make_kit(self.tmp, "base")
        self.store = make_store(self.tmp, self.base)
        self.kit = make_kit(self.tmp, "newer")

    def run_upgrade(self, store=None, kit=None, *extra):
        return upgrade(store or self.store, *extra, kit=kit or self.kit)

    def ok(self, store=None, kit=None, *extra):
        code, out, err = self.run_upgrade(store, kit, *extra)
        self.assertEqual(code, 0, out + err)
        return out

    def age_chain(self, store):
        old = store / "tools" / "old_tool.py"
        old.write_text("print('old')\n", encoding="utf-8")
        data = manifest(store)
        data["files"]["tools/old_tool.py"] = sha(old)
        write_manifest(store, data)


class TableApplyTests(ApplyCase):
    def test_every_row_of_the_table(self):
        tools = self.store / "tools"
        newer(self.kit, "tools/kbfiles.py")          # recorded, unedited, kit differs -> replace
        (tools / "kbparse.py").unlink()               # missing -> add
        newer(self.kit, "tools/kbscan.py")            # recorded, edited by the owner -> skip
        (tools / "kbscan.py").write_text("# owner's version\n", encoding="utf-8")
        newer(self.kit, "tools/kblife.py")            # edited to equal the kit -> record
        (tools / "kblife.py").write_bytes((self.kit / "files" / "tools" / "kblife.py").read_bytes())
        data = manifest(self.store)
        del data["files"]["tools/new_domain.py"]      # unrecorded, equals the kit -> adopt
        del data["files"]["tools/new_entry.py"]       # unrecorded, differs -> conflict
        (tools / "new_entry.py").write_text("# something else\n", encoding="utf-8")
        (tools / "retired.py").write_text("print('retired')\n", encoding="utf-8")
        data["files"]["tools/retired.py"] = sha(tools / "retired.py")   # recorded, not in kit -> report
        write_manifest(self.store, data)
        before = content_checksums(self.store)

        out = self.ok()

        for line in ("replace tools/kbfiles.py", "add tools/kbparse.py", "skip tools/kbscan.py",
                     "record tools/kblife.py", "adopt tools/new_domain.py", "conflict tools/new_entry.py",
                     "report tools/retired.py"):
            self.assertIn(line, out)
        self.assertEqual((tools / "kbfiles.py").read_bytes(), (self.kit / "files" / "tools" / "kbfiles.py").read_bytes())
        self.assertEqual((tools / "kbparse.py").read_bytes(), (self.kit / "files" / "tools" / "kbparse.py").read_bytes())
        self.assertEqual((tools / "kbscan.py").read_text(encoding="utf-8"), "# owner's version\n")
        self.assertEqual((tools / "new_entry.py").read_text(encoding="utf-8"), "# something else\n")
        self.assertTrue((tools / "retired.py").is_file())
        files = manifest(self.store)["files"]
        self.assertEqual(files["tools/kbfiles.py"], sha(tools / "kbfiles.py"))
        self.assertEqual(files["tools/kbparse.py"], sha(tools / "kbparse.py"))
        self.assertEqual(files["tools/kblife.py"], sha(tools / "kblife.py"))
        self.assertEqual(files["tools/new_domain.py"], sha(tools / "new_domain.py"))
        self.assertNotEqual(files["tools/kbscan.py"], sha(tools / "kbscan.py"))   # the old record is kept
        self.assertNotIn("tools/new_entry.py", files)
        self.assertEqual(files["tools/retired.py"], sha(tools / "retired.py"))
        self.assertEqual(content_checksums(self.store), before)

    def test_content_and_root_files_are_byte_identical(self):
        helpers.write(self.store / "domains" / "mine", "README.md", "mine\n")
        helpers.write(self.store / "catalog", "paper.md", "---\nstem: paper\n---\n")
        helpers.write(self.store / "sources", "paper.pdf", "%PDF-1.7\n")
        helpers.write(self.store / "text", "paper.md", "text\n")
        helpers.write(self.store / "playbook", "extra.md", "extra\n")
        for rel in ("README.md", "AGENTS.md", ".gitignore", "docs/README.md"):
            (self.store / rel).write_text("owner's text " + rel + "\n", encoding="utf-8")
        newer(self.kit, "tools/kbfiles.py")
        before = content_checksums(self.store)
        self.ok()
        self.assertEqual(content_checksums(self.store), before)

    def test_kb_json_may_be_replaced(self):
        meta = json.loads((self.kit / "files" / "kb.json").read_text(encoding="utf-8"))
        meta["note"] = "newer"
        (self.kit / "files" / "kb.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        out = self.ok()
        self.assertIn("replace kb.json", out)
        self.assertEqual(json.loads((self.store / "kb.json").read_text(encoding="utf-8"))["note"], "newer")
        self.assertEqual(manifest(self.store)["files"]["kb.json"], sha(self.store / "kb.json"))

    def test_a_second_run_does_nothing(self):
        newer(self.kit, "tools/kbfiles.py")
        (self.store / "tools" / "kbparse.py").unlink()
        self.ok()
        before = helpers.snapshot(self.store)
        out = self.ok()
        self.assertIn("nothing to do", out)
        self.assertEqual(helpers.snapshot(self.store), before)

    def test_an_unchanged_store_is_not_rewritten(self):
        before = helpers.snapshot(self.store)
        out = self.ok()
        self.assertIn("nothing to do", out)
        self.assertEqual(helpers.snapshot(self.store), before)

    def test_the_manifest_is_refreshed(self):
        newer(self.kit, "tools/kbfiles.py")
        meta = json.loads((self.kit / "kit.json").read_text(encoding="utf-8"))
        meta["kit_version"] = "2"
        (self.kit / "kit.json").write_text(json.dumps(meta), encoding="utf-8")
        commit, dirty = install.starter_state()
        self.ok()
        data = manifest(self.store)
        self.assertEqual(data["kit_version"], "2")
        self.assertEqual((data["starter_commit"], data["starter_dirty"]), (commit, dirty))
        self.assertEqual(data["name"], "store")
        self.assertEqual((data["schema"], data["kb_schema"]), (1, 1))

    def test_the_old_blocks_key_and_ignored_entries_are_dropped_when_the_manifest_is_rewritten(self):
        data = manifest(self.store)
        data["blocks"] = {"AGENTS.md#x": "a" * 64}
        data["files"]["playbook/README.md"] = "b" * 64
        write_manifest(self.store, data)
        newer(self.kit, "tools/kbfiles.py")
        out = self.ok()
        self.assertIn("ignored manifest entry playbook/README.md", out)
        data = manifest(self.store)
        self.assertNotIn("blocks", data)
        self.assertNotIn("playbook/README.md", data["files"])

    def test_the_review_reminder_is_printed_and_nothing_is_committed(self):
        newer(self.kit, "tools/kbfiles.py")
        out = self.ok()
        self.assertIn("git diff", out)
        self.assertIn("git status", out)
        self.assertIn("never commits", out)
        git = subprocess.run(["git", "-C", str(self.store), "rev-parse", "--verify", "HEAD"],
                             capture_output=True, text=True, env={**os.environ, **stores.SAFE_ENV})
        self.assertNotEqual(git.returncode, 0)

    def test_new_files_get_the_kit_mode_and_replaced_files_keep_the_stores(self):
        (self.kit / "files" / "tools" / "brand_new.py").write_text("print('x')\n", encoding="utf-8")
        os.chmod(self.kit / "files" / "tools" / "brand_new.py", 0o755)
        newer(self.kit, "tools/kbfiles.py")
        os.chmod(self.store / "tools" / "kbfiles.py", 0o640)
        self.ok()
        self.assertEqual(stat.S_IMODE(os.stat(self.store / "tools" / "brand_new.py").st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(os.stat(self.store / "tools" / "kbfiles.py").st_mode), 0o640)

    def test_a_new_directory_is_created_for_a_new_file(self):
        shutil.rmtree(self.store / "template-module")
        out = self.ok()
        self.assertIn("add template-module/module.json", out)
        self.assertTrue((self.store / "template-module" / "module.json").is_file())

    def test_names_substituted_for_the_manifest_name(self):
        path = self.kit / "files" / "domains" / "_skeleton" / "log.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nStore: REPLACE_WITH_PROJECT_NAME.\n", encoding="utf-8")
        self.ok()
        self.assertIn("Store: store.", (self.store / "domains" / "_skeleton" / "log.md").read_text(encoding="utf-8"))

    def test_dry_run_changes_nothing_but_apply_does(self):
        newer(self.kit, "tools/kbfiles.py")
        before = helpers.snapshot(self.store)
        self.ok(None, None, "--dry-run")
        self.assertEqual(helpers.snapshot(self.store), before)
        self.ok()
        self.assertNotEqual(helpers.snapshot(self.store), before)


class NoGitInTheStoreTests(ApplyCase):
    def test_git_never_runs_in_the_store(self):
        newer(self.kit, "tools/kbfiles.py")
        sentinel = self.tmp / "ran"
        script = self.tmp / "evil.sh"
        script.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
        script.chmod(0o755)
        (self.store / ".git" / "config").write_text(
            f"[core]\n\tfsmonitor = {script}\n\thooksPath = {self.tmp}\n[alias]\n\tstatus = !{script}\n")
        calls = []
        real_run = subprocess.run

        def spy(cmd, *args, **kwargs):
            calls.append((list(cmd), kwargs.get("cwd")))
            return real_run(cmd, *args, **kwargs)

        with mock.patch.object(install.subprocess, "run", spy):
            self.ok()
        store_real = os.path.realpath(self.store)
        for cmd, cwd in calls:
            self.assertFalse(cwd and os.path.realpath(cwd).startswith(store_real), (cmd, cwd))
        self.assertFalse(sentinel.exists())


class OrderTests(ApplyCase):
    def test_kb_json_is_second_to_last_and_the_manifest_last(self):
        meta = json.loads((self.kit / "files" / "kb.json").read_text(encoding="utf-8"))
        meta["note"] = "newer"
        (self.kit / "files" / "kb.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        newer(self.kit, "tools/kbfiles.py")
        newer(self.kit, "docs/kb/installer.md")
        finals = []
        real = install.rename_into_place

        def record(temp, final):
            finals.append(os.path.relpath(final, os.path.realpath(self.store)))
            real(temp, final)

        with mock.patch.object(install, "rename_into_place", record):
            self.ok()
        self.assertEqual(finals[-2:], ["kb.json", ".kb-manifest"])
        self.assertEqual(sorted(finals[:-2]), ["docs/kb/installer.md", "tools/kbfiles.py"])


class RecoveryTests(ApplyCase):
    """Fail after N steps (renames and deletes), rerun, and compare with an uninterrupted run."""

    def steps_for(self, kit, prepare):
        probe = make_store(self.tmp, self.base, "probe")
        prepare(probe)
        count = []
        real_rename, real_delete = install.rename_into_place, install.delete_file
        with mock.patch.object(install, "rename_into_place", lambda t, f: (count.append(1), real_rename(t, f))), \
                mock.patch.object(install, "delete_file", lambda p: (count.append(1), real_delete(p))):
            self.assertEqual(upgrade(probe, kit=kit)[0], 0)
        shutil.rmtree(probe)
        return len(count)

    def interrupted_then_completed(self, kit, prepare, fail_at):
        store = make_store(self.tmp, self.base, f"interrupted-{fail_at}")
        prepare(store)
        self.content_before = content_checksums(store)
        seen = []
        real_rename, real_delete = install.rename_into_place, install.delete_file

        def tick():
            seen.append(1)
            if len(seen) > fail_at:
                raise OSError(5, "simulated failure")

        with mock.patch.object(install, "rename_into_place", lambda t, f: (tick(), real_rename(t, f))), \
                mock.patch.object(install, "delete_file", lambda p: (tick(), real_delete(p))):
            code, out, err = upgrade(store, kit=kit)
        self.assertEqual(code, 1, out + err)
        self.assertIn("rerun", out + err)
        self.assertEqual([p for p in Path(store).rglob(".kbtmp-*")], [], "no temp file may be left behind")
        code, out, err = upgrade(store, kit=kit)
        self.assertEqual(code, 0, out + err)
        return store

    def assert_same_as_uninterrupted(self, kit, prepare):
        clean = make_store(self.tmp, self.base, "clean")
        prepare(clean)
        self.assertEqual(upgrade(clean, kit=kit)[0], 0)
        total = self.steps_for(kit, prepare)
        self.assertGreater(total, 2)
        for fail_at in range(total):
            with self.subTest(fail_at=fail_at):
                store = self.interrupted_then_completed(kit, prepare, fail_at)
                self.assertEqual(owned_state(store), owned_state(clean))
                self.assertEqual({**manifest(store), "name": ""}, {**manifest(clean), "name": ""})
                self.assertEqual(content_checksums(store), self.content_before)
                shutil.rmtree(store)

    def test_an_ordinary_upgrade_is_completed_by_a_rerun(self):
        newer(self.kit, "tools/kbfiles.py")
        newer(self.kit, "tools/kblife.py")
        newer(self.kit, "docs/kb/installer.md")
        meta = json.loads((self.kit / "files" / "kb.json").read_text(encoding="utf-8"))
        meta["note"] = "newer"
        (self.kit / "files" / "kb.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        self.assert_same_as_uninterrupted(self.kit, lambda store: (store / "tools" / "kbparse.py").unlink())

    def test_a_migration_chain_is_completed_by_a_rerun(self):
        kit = chain_kit(self.tmp, "chainkit")
        self.assert_same_as_uninterrupted(kit, self.age_chain)

    def test_a_chain_upgrade_equals_a_fresh_store(self):
        kit = chain_kit(self.tmp, "chainkit")
        self.age_chain(self.store)
        self.ok(kit=kit)
        fresh = make_store(self.tmp, kit, "fresh")
        self.assertEqual(owned_state(self.store), owned_state(fresh))
        self.assertEqual(manifest(self.store)["files"], manifest(fresh)["files"])
        self.assertEqual(manifest(self.store)["kb_schema"], 3)
        self.assertNotIn("tools/old_tool.py", manifest(self.store)["files"])
        self.assertFalse((self.store / "tools" / "old_tool.py").exists())

    def test_a_hidden_temp_file_from_a_killed_run_is_ignored_and_kept(self):
        newer(self.kit, "tools/kbfiles.py")
        leftovers = [self.store / "tools" / ".kbtmp-999-dead", self.store / "docs" / "kb" / ".kbtmp-1-beef"]
        for path in leftovers:
            path.write_text("half written\n", encoding="utf-8")
        out = self.ok()
        self.assertNotIn(".kbtmp", out)
        for path in leftovers:
            self.assertEqual(path.read_text(encoding="utf-8"), "half written\n")
        self.assertEqual(list(manifest(self.store)["files"]).count(".kbtmp-999-dead"), 0)


class ChangedUnderneathTests(ApplyCase):
    def test_a_file_edited_after_planning_refuses_before_any_rename(self):
        newer(self.kit, "tools/kbfiles.py")
        newer(self.kit, "tools/kblife.py")
        real_plan = install.plan_upgrade

        def plan_then_edit(root, kit):
            result = real_plan(root, kit)
            with open(os.path.join(root, "tools", "kblife.py"), "a", encoding="utf-8") as handle:
                handle.write("# the owner edited this meanwhile\n")
            return result

        before = owned_state(self.store)
        with mock.patch.object(install, "plan_upgrade", plan_then_edit):
            code, out, err = self.run_upgrade()
        self.assertEqual(code, 1, out + err)
        self.assertIn("changed", out + err)
        after = owned_state(self.store)
        after_without_edit = dict(after)
        after_without_edit["tools/kblife.py"] = before["tools/kblife.py"]
        self.assertEqual(after_without_edit, before)
        self.assertEqual(manifest(self.store)["files"]["tools/kbfiles.py"], sha(self.store / "tools" / "kbfiles.py"))
        self.assertEqual([p for p in self.store.rglob(".kbtmp-*")], [])

    def test_a_symlink_swapped_in_after_planning_is_refused(self):
        newer(self.kit, "tools/kbfiles.py")
        victim = self.tmp / "victim.py"
        victim.write_text("keep\n")
        real_plan = install.plan_upgrade

        def plan_then_swap(root, kit):
            result = real_plan(root, kit)
            os.unlink(os.path.join(root, "tools", "kbfiles.py"))
            os.symlink(victim, os.path.join(root, "tools", "kbfiles.py"))
            return result

        with mock.patch.object(install, "plan_upgrade", plan_then_swap):
            code, out, err = self.run_upgrade()
        self.assertEqual(code, 1, out + err)
        self.assertEqual(victim.read_text(), "keep\n")


if __name__ == "__main__":
    unittest.main()


class ReviewFindingTests(ApplyCase):
    def test_an_edited_kb_json_blocks_a_schema_advance(self):
        kit = chain_kit(self.tmp, "chainkit")
        self.age_chain(self.store)
        path = self.store / "kb.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta["owner_key"] = 1
        path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        before = helpers.snapshot(self.store)
        code, out, err = self.run_upgrade(kit=kit)
        self.assertEqual(code, 1, out + err)
        self.assertIn("kb.json", out + err)
        self.assertEqual(helpers.snapshot(self.store), before)
        self.assertEqual(manifest(self.store)["kb_schema"], 1)

    def test_an_empty_dir_is_refused(self):
        code, out, err = stores.run_main("--upgrade", "--dir", "", kit=self.kit)
        self.assertEqual(code, 1, out + err)

    def test_a_failed_run_leaves_no_new_directories(self):
        shutil.rmtree(self.store / "docs" / "kb")
        (self.store / "tools" / "kbscan.py").unlink()
        os.chmod(self.store / "tools", 0o555)
        self.addCleanup(os.chmod, self.store / "tools", 0o755)
        code, out, err = self.run_upgrade()
        self.assertEqual(code, 1, out + err)
        self.assertFalse((self.store / "docs" / "kb").exists())

    def test_a_replace_source_must_be_its_own_path_when_the_kit_has_that_path(self):
        kit = make_kit(self.tmp, "oddkit")
        (kit / "migrations.json").write_text(json.dumps({"steps": [{"from": 1, "to": 2, "ops": [
            {"op": "replace", "path": "tools/kbfiles.py", "source": "tools/kbparse.py"}]}]}), encoding="utf-8")
        code, out, err = self.run_upgrade(kit=kit)
        self.assertEqual(code, 1, out + err)
        self.assertIn("source", out + err)
