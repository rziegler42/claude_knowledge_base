"""new_domain.py (domain-lifecycle.md operation 1; acceptance criterion 1)."""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import helpers
import check_kb
import kbfiles
import kbparse
import kblife
import new_domain
from projects import build_project
from toolrun import TODAY, run_tool


def errors(proj):
    return [f"{f.path}: {f.message}" for f in check_kb.check(Path(proj)).errors]


def tree(root):
    return {p.relative_to(root).as_posix() for p in Path(root).rglob("*") if p.is_file()}


class DomainCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.proj = build_project(self.tmp / "store")

    def new(self, *argv):
        return run_tool(new_domain, self.proj, *argv)

    def refuses(self, *argv):
        before = helpers.snapshot(self.proj)
        code, out, err = self.new(*argv)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(helpers.snapshot(self.proj), before, "a refused run must write nothing")
        self.assertNotIn("Traceback", out + err)
        return out + err


class CreateTests(DomainCase):
    def test_a_domain_is_created_and_the_store_still_passes_the_check(self):
        code, out, err = self.new("ethics", "--title", "Ethics of Play")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(errors(self.proj), [])
        self.assertIn("domains/ethics", out)

    def test_the_tree_is_the_skeleton_with_the_fields_set(self):
        self.new("ethics", "--title", "Ethics of Play")
        skeleton = tree(self.proj / "domains" / "_skeleton")
        self.assertEqual(tree(self.proj / "domains" / "ethics"), skeleton)
        charter = (self.proj / "domains" / "ethics" / "README.md").read_text(encoding="utf-8")
        front, _ = kbparse.parse_front_matter(charter)
        self.assertEqual((front["domain"], front["title"], front["charter"], front["created"]),
                         ("ethics", "Ethics of Play", "draft", TODAY))
        self.assertIn("# Ethics of Play", charter)
        self.assertNotIn("REPLACE_WITH_DOMAIN", charter)
        self.assertNotIn("REPLACE_WITH_TITLE", charter)
        self.assertIn("REPLACE_WITH_PURPOSE", charter)  # the person fills the charter in
        router = (self.proj / "domains" / "ethics" / "playbook" / "README.md").read_text(encoding="utf-8")
        self.assertIn("# Ethics of Play: playbook", router)
        self.assertNotIn("REPLACE_WITH_", router)

    def test_the_first_log_entry_is_a_charter_entry(self):
        self.new("ethics", "--title", "Ethics")
        log = kblife.parse_log((self.proj / "domains" / "ethics" / "log.md").read_text(encoding="utf-8"))
        self.assertEqual(log.issues, [])
        self.assertEqual([(e.kind, e.date) for e in log.entries], [("charter", TODAY)])
        self.assertTrue(log.entries[0].fields["Change"] and log.entries[0].fields["Reason"])

    def test_the_root_router_gets_one_row_between_the_markers(self):
        self.new("ethics", "--title", "Ethics of Play")
        self.new("tools", "--title", "Tools")
        text = (self.proj / "playbook" / "README.md").read_text(encoding="utf-8")
        begin, end = text.index("<!-- BEGIN kb:domains -->"), text.index("<!-- END kb:domains -->")
        rows = [line for line in text[begin:end].split("\n") if line.startswith("| ") and "---" not in line][1:]
        self.assertEqual(rows, ["| ethics | [Ethics of Play](../domains/ethics/playbook/README.md) | Ethics of Play |",
                                "| tools | [Tools](../domains/tools/playbook/README.md) | Tools |"])
        self.assertEqual(errors(self.proj), [])

    def test_a_draft_domain_with_no_questions_is_allowed_but_not_entries(self):
        self.new("ethics", "--title", "Ethics")
        self.assertEqual(errors(self.proj), [])

    def test_it_prints_each_path_it_wrote_and_the_next_step(self):
        code, out, err = self.new("ethics", "--title", "Ethics")
        for expected in ("domains/ethics/README.md", "domains/ethics/log.md", "playbook/README.md"):
            self.assertIn(expected, out)
        self.assertIn("charter", out)

    def test_it_runs_as_a_script(self):
        script = helpers.KIT_TOOLS / "new_domain.py"
        done = subprocess.run([sys.executable, "-I", "-B", str(script), "--root", str(self.proj), "scripted",
                               "--title", "Scripted"], capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.proj / "domains" / "scripted" / "README.md").is_file())


class RefusalTests(DomainCase):
    def test_a_duplicate_name(self):
        self.new("ethics", "--title", "Ethics")
        self.assertIn("already exists", self.refuses("ethics", "--title", "Again"))

    def test_invalid_names(self):
        for name in ("..", "A", "_skeleton", "a/b", "a b", "-a", "a_b", "x" * 101, "café", ".hidden", "a\n"):
            with self.subTest(name=name):
                self.refuses("--title", "T", "--", name)  # "--" so a leading hyphen reaches the check

    def test_invalid_titles(self):
        for title in ("", " ", "a|b", "a[b", "a]b", "two\nlines", "bell\x07", "x" * 121, "tag\U000e0041", "zero​width",
                      "REPLACE_WITH_TITLE", " leading", "trailing ", "back\\slash", "back`tick"):
            with self.subTest(title=title):
                self.refuses("ethics", "--title", title)

    def test_a_missing_title(self):
        code, out, err = self.new("ethics")
        self.assertEqual(code, 2)

    def test_the_root_router_markers_must_be_present_and_in_order(self):
        path = self.proj / "playbook" / "README.md"
        original = path.read_text(encoding="utf-8")
        for broken in (original.replace("<!-- BEGIN kb:domains -->", ""),
                       original.replace("<!-- END kb:domains -->", ""),
                       original.replace("<!-- BEGIN kb:domains -->", "<!-- X -->").replace("<!-- END kb:domains -->", "<!-- BEGIN kb:domains -->"),
                       original.replace("| Domain | Router | Purpose |", "| Domain | Router |")):
            path.write_text(broken, encoding="utf-8")
            with self.subTest(broken=broken[-80:]):
                self.refuses("ethics", "--title", "Ethics")
        path.write_text(original, encoding="utf-8")
        self.assertEqual(self.new("ethics", "--title", "Ethics")[0], 0)

    def test_a_missing_root_router_or_skeleton(self):
        (self.proj / "playbook" / "README.md").unlink()
        self.refuses("ethics", "--title", "Ethics")

    def test_an_existing_path_of_any_kind(self):
        (self.proj / "domains" / "file-here").write_text("x")
        self.refuses("file-here", "--title", "T")
        os.symlink(self.tmp, self.proj / "domains" / "link-here")
        self.refuses("link-here", "--title", "T")

    def test_a_symlinked_domains_playbook_or_skeleton_directory(self):
        for rel in ("domains", "playbook"):
            with self.subTest(rel=rel):
                real = self.proj / rel
                moved = self.tmp / f"moved-{rel}"
                os.rename(real, moved)
                os.symlink(moved, real)
                try:
                    self.refuses("ethics", "--title", "T")
                finally:
                    os.unlink(real)
                    os.rename(moved, real)

    def test_a_skeleton_with_a_symlink_or_special_file_is_refused(self):
        skeleton = self.proj / "domains" / "_skeleton"
        os.symlink(self.tmp, skeleton / "evil-link")
        self.refuses("ethics", "--title", "T")
        os.unlink(skeleton / "evil-link")
        os.mkfifo(skeleton / "pipe")
        self.refuses("ethics", "--title", "T")

    def test_a_skeleton_file_that_is_not_utf8_is_refused_without_a_traceback(self):
        (self.proj / "domains" / "_skeleton" / "README.md").write_bytes(b"---\xff\xfe\n")
        self.refuses("ethics", "--title", "T")

    def test_a_root_that_is_not_a_store(self):
        os.unlink(self.proj / "kb.json")
        code, out, err = self.new("ethics", "--title", "T")
        self.assertEqual(code, 1)
        self.assertIn("not a knowledge-base store", out + err)


class InterruptionTests(DomainCase):
    def test_a_kill_before_the_rename_leaves_only_a_hidden_directory_the_next_run_ignores(self):
        (self.proj / "domains" / (kbfiles.TEMP_PREFIX + "1234-abcd")).mkdir()
        self.assertEqual(errors(self.proj), [])
        self.assertEqual(self.new("ethics", "--title", "Ethics")[0], 0)
        self.assertEqual(errors(self.proj), [])

    def test_a_failure_while_building_leaves_no_trace(self):
        before = helpers.snapshot(self.proj)
        with mock.patch.object(new_domain, "build_tree", side_effect=OSError("disk full")):
            code, out, err = self.new("ethics", "--title", "Ethics")
        self.assertEqual(code, 1)
        self.assertEqual(helpers.snapshot(self.proj), before)
        self.assertNotIn("Traceback", out + err)

    def test_a_failure_to_write_the_root_row_prints_the_row_and_the_checker_names_it(self):
        real = new_domain.kbfiles.write_atomic

        def fail_on_router(path, data):
            if path.endswith(os.path.join("playbook", "README.md")) and "domains" + os.sep not in path:
                raise OSError("disk full")
            return real(path, data)

        with mock.patch.object(new_domain.kbfiles, "write_atomic", side_effect=fail_on_router):
            code, out, err = self.new("ethics", "--title", "Ethics")
        self.assertEqual(code, 1)
        row = "| ethics | [Ethics](../domains/ethics/playbook/README.md) | Ethics |"
        self.assertIn(row, out + err)
        self.assertTrue((self.proj / "domains" / "ethics" / "README.md").is_file())
        self.assertTrue(any("is not in the root router" in e for e in errors(self.proj)), errors(self.proj))
        # a rerun refuses the existing name and prints the row that is still missing
        rerun = self.new("ethics", "--title", "Another title")
        self.assertEqual(rerun[0], 1)
        self.assertIn("already exists", rerun[1] + rerun[2])
        self.assertIn(row, rerun[1] + rerun[2])  # the domain's own title, not the one just typed
        # adding the one row by hand repairs it
        path = self.proj / "playbook" / "README.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("<!-- END kb:domains -->", row + "\n<!-- END kb:domains -->"), encoding="utf-8")
        self.assertEqual(errors(self.proj), [])


if __name__ == "__main__":
    unittest.main()
