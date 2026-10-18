"""new_entry.py (domain-lifecycle.md operation 2, step 6; acceptance criterion 2)."""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import helpers
import check_kb
import kbparse
import new_entry
from projects import add_domain, add_entry, build_project
from toolrun import TODAY, run_tool


def errors(proj):
    return [f"{f.path}: {f.message}" for f in check_kb.check(Path(proj)).errors]


def has(items, needle):
    return any(needle in item for item in items)


class EntryCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.proj = build_project(self.tmp / "store")
        add_domain(self.proj, "demo")
        self.entries = self.proj / "domains" / "demo" / "playbook" / "entries"
        self.router = self.proj / "domains" / "demo" / "playbook" / "README.md"

    def new(self, *argv):
        return run_tool(new_entry, self.proj, *argv)

    def refuses(self, *argv):
        before = helpers.snapshot(self.proj)
        code, out, err = self.new(*argv)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(helpers.snapshot(self.proj), before, "a refused run must write nothing")
        self.assertNotIn("Traceback", out + err)
        return out + err


class CreateTests(EntryCase):
    def test_an_entry_and_a_router_stub_are_created(self):
        code, out, err = self.new("demo", "first-thing")
        self.assertEqual(code, 0, out + err)
        entry = (self.entries / "pb-first-thing.md").read_text(encoding="utf-8")
        front, _ = kbparse.parse_front_matter(entry)
        self.assertEqual((front["id"], front["type"], front["status"], front["sources"], front["updated"]),
                         ("pb-first-thing", "playbook-entry", "draft", [], TODAY))
        for heading in check_kb.REQUIRED_HEADINGS:
            self.assertIn(f"## {heading}", entry)
        self.assertIn("| REPLACE_WITH_SITUATION | [pb-first-thing](entries/pb-first-thing.md) |",
                      self.router.read_text(encoding="utf-8"))
        self.assertIn("domains/demo/playbook/entries/pb-first-thing.md", out)

    def test_the_check_fails_on_placeholder_text_until_it_is_filled_in(self):
        self.new("demo", "first-thing")
        found = errors(self.proj)
        self.assertTrue(has(found, "pb-first-thing.md: contains REPLACE_WITH_ text"), found)
        self.assertTrue(has(found, "playbook/README.md: contains REPLACE_WITH_ text"), found)
        for path in (self.entries / "pb-first-thing.md", self.router):
            text = path.read_text(encoding="utf-8")
            text = text.replace("REPLACE_WITH_TITLE", "A first thing")
            text = re.sub(r"REPLACE_WITH_[A-Z_]+", "Filled in.", text)
            path.write_text(text, encoding="utf-8")
        self.assertEqual(errors(self.proj), [])

    def test_a_title_can_be_given(self):
        self.new("demo", "first-thing", "--title", "A first thing")
        entry = (self.entries / "pb-first-thing.md").read_text(encoding="utf-8")
        self.assertEqual(kbparse.parse_front_matter(entry)[0]["title"], "A first thing")
        self.assertIn("# A first thing", entry)

    def test_two_entries_get_two_rows_and_ids(self):
        self.new("demo", "one")
        self.new("demo", "two")
        router = self.router.read_text(encoding="utf-8")
        self.assertIn("(entries/pb-one.md)", router)
        self.assertIn("(entries/pb-two.md)", router)
        self.assertTrue((self.entries / "pb-one.md").is_file() and (self.entries / "pb-two.md").is_file())

    def test_it_runs_as_a_script(self):
        script = helpers.KIT_TOOLS / "new_entry.py"
        done = subprocess.run([sys.executable, "-I", "-B", str(script), "--root", str(self.proj), "demo", "scripted"],
                              capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.entries / "pb-scripted.md").is_file())


class RefusalTests(EntryCase):
    def test_an_unset_charter(self):
        add_domain(self.proj, "drafty", charter="draft")
        self.assertIn("charter", self.refuses("drafty", "thing"))

    def test_a_set_charter_the_checker_would_reject(self):
        charter = self.proj / "domains" / "demo" / "README.md"
        charter.write_text(charter.read_text(encoding="utf-8").replace("## Scope\n\nfilled in", "## Scope\n\nREPLACE_WITH_SCOPE"),
                           encoding="utf-8")
        self.assertIn("REPLACE_WITH_", self.refuses("demo", "thing"))

    def test_an_unknown_or_invalid_domain(self):
        self.refuses("nope", "thing")
        for name in ("..", "A", "a/b", "_skeleton"):
            with self.subTest(name=name):
                self.refuses(name, "thing")

    def test_a_duplicate_id_in_the_same_or_another_domain(self):
        self.new("demo", "thing")
        self.assertIn("already exists", self.refuses("demo", "thing"))
        add_domain(self.proj, "other")
        self.assertIn("already exists", self.refuses("other", "thing"))

    def test_an_invalid_slug(self):
        for slug in ("", "A", "a b", "a/b", "..", "a_b", "x" * 101, "café", "a\n", ".hidden"):
            with self.subTest(slug=slug):
                self.refuses("--", "demo", slug)

    def test_a_title_with_markup_or_invisible_characters(self):
        for title in ("a|b", "a[b", "two\nlines", "tag\U000e0041", "x" * 121, ""):
            with self.subTest(title=title):
                self.refuses("demo", "thing", "--title", title)

    def test_a_router_without_a_table(self):
        self.router.write_text("# Router\n\nNo table here.\n", encoding="utf-8")
        self.refuses("demo", "thing")

    def test_symlinked_or_missing_directories(self):
        moved = self.tmp / "moved"
        os.rename(self.entries, moved)
        os.symlink(moved, self.entries)
        self.refuses("demo", "thing")
        os.unlink(self.entries)
        os.rename(moved, self.entries)
        os.rename(self.router, self.tmp / "router.md")
        self.refuses("demo", "thing")

    def test_a_symlink_or_fifo_where_the_entry_would_go(self):
        os.symlink(self.tmp, self.entries / "pb-thing.md")
        self.refuses("demo", "thing")
        os.unlink(self.entries / "pb-thing.md")
        os.mkfifo(self.entries / "pb-thing.md")
        self.refuses("demo", "thing")

    def test_a_missing_template(self):
        with mock.patch.object(new_entry, "TEMPLATE", self.tmp / "missing.md"):
            self.refuses("demo", "thing")

    def test_a_template_that_is_a_symlink_is_refused(self):
        real = self.tmp / "entry.md"
        real.write_text((helpers.KIT_TOOLS / "templates" / "entry.md").read_text(encoding="utf-8"))
        link = self.tmp / "link.md"
        os.symlink(real, link)
        with mock.patch.object(new_entry, "TEMPLATE", link):
            self.refuses("demo", "thing")


class InterruptionTests(EntryCase):
    def test_a_failure_writing_the_router_row_prints_the_row_and_the_checker_names_the_entry(self):
        real = new_entry.kbfiles.write_atomic
        calls = []

        def fail_on_router(path, data):
            calls.append(path)
            if path.endswith("README.md"):
                raise OSError("disk full")
            return real(path, data)

        with mock.patch.object(new_entry.kbfiles, "write_atomic", side_effect=fail_on_router):
            code, out, err = self.new("demo", "thing", "--title", "A thing")
        self.assertEqual(code, 1)
        self.assertIn("| REPLACE_WITH_SITUATION | [pb-thing](entries/pb-thing.md) |", out + err)
        self.assertTrue((self.entries / "pb-thing.md").is_file())
        self.assertTrue(has(errors(self.proj), "pb-thing.md: entry is not referenced from the domain router"), errors(self.proj))
        # a rerun refuses the duplicate id and prints the row that is still missing
        rerun = self.new("demo", "thing")
        self.assertEqual(rerun[0], 1)
        self.assertIn("already exists", rerun[1] + rerun[2])
        self.assertIn("| REPLACE_WITH_SITUATION | [pb-thing](entries/pb-thing.md) |", rerun[1] + rerun[2])
        # adding the row by hand and filling the placeholders repairs it
        text = self.router.read_text(encoding="utf-8").rstrip("\n") + "\n| Filled in. | [pb-thing](entries/pb-thing.md) |\n"
        self.router.write_text(text, encoding="utf-8")
        entry = self.entries / "pb-thing.md"
        entry.write_text(re.sub(r"REPLACE_WITH_[A-Z_]+", "Filled in.", entry.read_text(encoding="utf-8")), encoding="utf-8")
        self.assertEqual(errors(self.proj), [])

    def test_the_router_is_checked_before_the_entry_is_written(self):
        self.router.write_text("# Router\n\nno table\n", encoding="utf-8")
        self.refuses("demo", "thing")
        self.assertFalse((self.entries / "pb-thing.md").exists())


class CloneTests(EntryCase):
    def test_it_works_in_a_clone_with_no_sources(self):
        add_entry(self.proj, "demo", "pb-existing")
        self.assertEqual(self.new("demo", "another")[0], 0)


if __name__ == "__main__":
    unittest.main()
