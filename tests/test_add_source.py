"""add_source.py (domain-lifecycle.md operation 2, step 3; acceptance criterion 3)."""
import datetime
import hashlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import helpers
import add_source
import check_kb
import kbparse
from pdffixtures import Page, build
from projects import add_catalog, build_project
from toolrun import TODAY, run_tool


def errors(proj, strict=False):
    return [f"{f.path}: {f.message}" for f in check_kb.check(Path(proj), require_sources=strict).errors]


def has(items, needle):
    return any(needle in item for item in items)


def pdf(text="Body."):
    return build([Page().text(72, 700, 12, text)])


class SourceCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.proj = build_project(self.tmp / "store")
        self.file = self.tmp / "incoming.pdf"
        self.file.write_bytes(pdf())

    def add(self, *argv):
        return run_tool(add_source, self.proj, *argv)

    def record(self, stem="paper-one"):
        text = (self.proj / "catalog" / f"{stem}.md").read_text(encoding="utf-8")
        return kbparse.parse_front_matter(text)[0]

    def refuses(self, *argv):
        before = helpers.snapshot(self.proj)
        code, out, err = self.add(*argv)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(helpers.snapshot(self.proj), before, "a refused run must write nothing")
        self.assertNotIn("Traceback", out + err)
        return out + err

    def save(self, stem="paper-one", file=None, *extra):
        return self.add(stem, str(file or self.file), "--title", "A source", *extra)


class NewRecordTests(SourceCase):
    def test_a_pdf_is_copied_hashed_and_recorded(self):
        code, out, err = self.save()
        self.assertEqual(code, 0, out + err)
        saved = self.proj / "sources" / "paper-one.pdf"
        self.assertEqual(saved.read_bytes(), self.file.read_bytes())
        record = self.record()
        self.assertEqual(record["sha256"], hashlib.sha256(self.file.read_bytes()).hexdigest())
        self.assertEqual((record["stem"], record["kind"], record["title"], record["state"], record["scan"]),
                         ("paper-one", "document", "A source", "saved", "none"))
        self.assertEqual((record["confirmed"], record["tier"], record["retrieved"]), ("full", "unknown", TODAY))
        self.assertNotIn("released", record)
        self.assertNotIn("replaced", record)
        self.assertEqual(errors(self.proj, strict=True), [])

    def test_the_options_are_recorded(self):
        code, out, err = self.add("paper-two", str(self.file), "--title", "A source", "--author", "Author One",
                                  "--author", "Smith, J.", "--url", "https://example.org/p", "--tier", "primary",
                                  "--confirmed", "abstract", "--retrieved", "2026-01-02", "--note", "Received by email.")
        self.assertEqual(code, 0, out + err)
        record = self.record("paper-two")
        self.assertEqual(record["authors"], ["Author One", "Smith, J."])
        self.assertEqual((record["url"], record["tier"], record["confirmed"], record["retrieved"]),
                         ("https://example.org/p", "primary", "abstract", datetime.date(2026, 1, 2)))
        self.assertIn("Received by email.", (self.proj / "catalog" / "paper-two.md").read_text(encoding="utf-8"))
        self.assertEqual(errors(self.proj), [])

    def test_it_prints_each_path_and_the_hash(self):
        code, out, err = self.save()
        self.assertIn("sources/paper-one.pdf", out)
        self.assertIn("catalog/paper-one.md", out)
        self.assertIn(hashlib.sha256(self.file.read_bytes()).hexdigest(), out)

    def test_the_source_file_is_not_modified_or_moved(self):
        before = self.file.read_bytes()
        self.save()
        self.assertEqual(self.file.read_bytes(), before)

    def test_no_temporary_file_is_left(self):
        self.save()
        self.assertEqual(sorted(p.name for p in (self.proj / "sources").iterdir() if p.name != "README.md"),
                         ["paper-one.pdf"])

    def test_it_runs_as_a_script(self):
        script = helpers.KIT_TOOLS / "add_source.py"
        done = subprocess.run([sys.executable, "-I", "-B", str(script), "--root", str(self.proj), "scripted",
                               str(self.file), "--title", "Scripted"], capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.proj / "catalog" / "scripted.md").is_file())


class RefusalTests(SourceCase):
    def test_invalid_stems(self):
        for stem in ("..", "Paper", "a_b", "a b", "readme", "quarantine", "x" * 101, "a.b", "a/b"):
            with self.subTest(stem=stem):
                self.refuses(stem, str(self.file), "--title", "T")

    def test_a_missing_symlinked_special_or_directory_file(self):
        os.symlink(self.file, self.tmp / "link.pdf")
        os.mkfifo(self.tmp / "pipe.pdf")
        (self.tmp / "dir.pdf").mkdir()
        for name in ("missing.pdf", "link.pdf", "pipe.pdf", "dir.pdf"):
            with self.subTest(name=name):
                self.refuses("paper-one", str(self.tmp / name), "--title", "T")

    def test_a_file_that_is_not_a_pdf(self):
        fake = self.tmp / "fake.pdf"
        fake.write_bytes(b"not really a pdf")
        self.assertIn("PDF", self.refuses("paper-one", str(fake), "--title", "T"))

    def test_another_extension_points_at_record_only(self):
        other = self.tmp / "notes.txt"
        other.write_text("hello")
        self.assertIn("--record-only", self.refuses("paper-one", str(other), "--title", "T"))
        weird = self.tmp / "paper.pdf.exe"
        weird.write_bytes(self.file.read_bytes())
        self.refuses("paper-one", str(weird), "--title", "T")

    def test_a_file_over_the_size_cap(self):
        with mock.patch.object(add_source, "MAX_SOURCE", 100):
            self.refuses("paper-one", str(self.file), "--title", "T")

    def test_a_quarantined_stem(self):
        folder = self.proj / "sources" / "quarantine"
        folder.mkdir()
        (folder / "paper-one.pdf").write_bytes(self.file.read_bytes())
        self.assertIn("quarantine", self.refuses("paper-one", str(self.file), "--title", "T"))
        self.assertIn("quarantine", self.refuses("paper-one", str(self.file), "--title", "T", "--replace"))

    def test_an_existing_record_without_replace(self):
        self.save()
        self.assertIn("--replace", self.refuses("paper-one", str(self.file), "--title", "T"))

    def test_an_existing_source_file_with_different_content_and_no_record(self):
        (self.proj / "sources" / "paper-one.pdf").write_bytes(pdf("Different."))
        self.assertIn("different content", self.refuses("paper-one", str(self.file), "--title", "T"))

    def test_bad_titles_authors_urls_dates_and_values(self):
        cases = [("--title", ""), ("--title", "two\nlines"), ("--title", "bell\x07"), ("--title", "x" * 501),
                 ("--author", "tag\U000e0041"), ("--author", "two\nlines"), ("--url", "javascript:alert(1)"),
                 ("--url", "https://a b"), ("--url", "ftp://example.org"), ("--url", "https://e.org/‮"),
                 ("--retrieved", "yesterday"), ("--retrieved", "2026-13-40"), ("--tier", "top"), ("--confirmed", "sure"),
                 ("--kind", "blog"), ("--note", "two\nlines"), ("--note", "x" * 501)]
        for flag, value in cases:
            with self.subTest(flag=flag, value=value[:20]):
                argv = ["paper-one", str(self.file), "--title", "T"]
                if flag == "--title":
                    argv = ["paper-one", str(self.file), "--title", value]
                else:
                    argv += [flag, value]
                code, out, err = self.add(*argv)
                self.assertIn(code, (1, 2))
                self.assertFalse((self.proj / "catalog" / "paper-one.md").exists())
                self.assertFalse((self.proj / "sources" / "paper-one.pdf").exists())

    def test_a_missing_title_is_a_usage_error(self):
        self.assertEqual(self.add("paper-one", str(self.file))[0], 2)

    def test_symlinked_catalog_or_sources_directories(self):
        for name in ("catalog", "sources"):
            with self.subTest(name=name):
                real = self.proj / name
                moved = self.tmp / f"moved-{name}"
                os.rename(real, moved)
                os.symlink(moved, real)
                try:
                    self.refuses("paper-one", str(self.file), "--title", "T")
                finally:
                    os.unlink(real)
                    os.rename(moved, real)

    def test_a_record_path_that_is_a_symlink_or_fifo(self):
        os.symlink(self.tmp, self.proj / "catalog" / "paper-one.md")
        self.refuses("paper-one", str(self.file), "--title", "T")
        os.unlink(self.proj / "catalog" / "paper-one.md")
        os.mkfifo(self.proj / "catalog" / "paper-one.md")
        self.refuses("paper-one", str(self.file), "--title", "T", "--replace")


class RecordOnlyTests(SourceCase):
    def test_a_link_only_document_needs_a_note_and_stays_recorded(self):
        self.refuses("paper-one", "--title", "T", "--record-only")
        code, out, err = self.add("paper-one", "--title", "A paper", "--record-only", "--confirmed", "snippet",
                                  "--note", "Behind a paywall; not saved.", "--url", "https://example.org/p")
        self.assertEqual(code, 0, out + err)
        record = self.record()
        self.assertEqual((record["state"], record["scan"], record["confirmed"]), ("recorded", "none", "snippet"))
        self.assertNotIn("sha256", record)
        self.assertIn("Behind a paywall", (self.proj / "catalog" / "paper-one.md").read_text(encoding="utf-8"))
        self.assertFalse((self.proj / "sources" / "paper-one.pdf").exists())
        self.assertEqual(errors(self.proj), [])

    def test_a_site_or_repository_is_reference_only(self):
        for kind in ("site", "repo"):
            with self.subTest(kind=kind):
                self.refuses(f"{kind}-one", "--title", "T", "--kind", kind)  # a URL is required
                code, out, err = self.add(f"{kind}-one", "--title", "A site", "--kind", kind, "--url",
                                          "https://example.org/x", "--confirmed", "snippet")
                self.assertEqual(code, 0, out + err)
                self.assertEqual(self.record(f"{kind}-one")["state"], "recorded")
        self.assertEqual(errors(self.proj), [])

    def test_a_site_cannot_be_given_a_file(self):
        self.refuses("site-one", str(self.file), "--title", "T", "--kind", "site", "--url", "https://example.org")

    def test_record_only_and_a_file_or_replace_do_not_mix(self):
        self.refuses("paper-one", str(self.file), "--title", "T", "--record-only", "--note", "n")
        self.save()
        self.refuses("paper-one", "--title", "T", "--record-only", "--replace", "--note", "n")


class ReplaceTests(SourceCase):
    def converted(self):
        self.save()
        text = (self.proj / "catalog" / "paper-one.md").read_text(encoding="utf-8")
        text = text.replace("state: saved", "state: converted").replace("scan: none", "scan: review")
        text = text.replace("\n---\n", "\nreleased: 2026-01-03\n---\n", 1)
        (self.proj / "catalog" / "paper-one.md").write_text(text, encoding="utf-8")

    def test_a_replace_updates_the_record_and_the_file(self):
        self.converted()
        old = self.record()["sha256"]
        new = self.tmp / "new.pdf"
        new.write_bytes(pdf("A newer version."))
        code, out, err = self.add("paper-one", str(new), "--replace")
        self.assertEqual(code, 0, out + err)
        record = self.record()
        self.assertEqual(record["sha256"], hashlib.sha256(new.read_bytes()).hexdigest())
        self.assertNotEqual(record["sha256"], old)
        self.assertEqual((record["state"], record["scan"], record["replaced"]), ("saved", "none", TODAY))
        self.assertNotIn("released", record)
        self.assertEqual((self.proj / "sources" / "paper-one.pdf").read_bytes(), new.read_bytes())
        self.assertEqual(errors(self.proj, strict=True), [])

    def test_the_title_and_other_fields_are_kept(self):
        self.save()
        new = self.tmp / "new.pdf"
        new.write_bytes(pdf("A newer version."))
        before = self.record()
        self.add("paper-one", str(new), "--replace")
        after = self.record()
        for key in ("stem", "kind", "title", "retrieved", "confirmed", "tier"):
            self.assertEqual(after[key], before[key], key)

    def test_a_replace_without_a_record_or_for_a_site(self):
        self.refuses("paper-one", str(self.file), "--replace")
        self.add("site-one", "--title", "S", "--kind", "site", "--url", "https://example.org", "--confirmed", "snippet")
        self.refuses("site-one", str(self.file), "--replace")

    def test_replacing_with_the_same_bytes_changes_nothing(self):
        self.save()
        before = helpers.snapshot(self.proj)
        code, out, err = self.add("paper-one", str(self.file), "--replace")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(helpers.snapshot(self.proj), before)
        self.assertIn("nothing to do", out)

    def test_a_replace_in_a_clone_with_no_source_file(self):
        self.save()
        os.unlink(self.proj / "sources" / "paper-one.pdf")
        new = self.tmp / "new.pdf"
        new.write_bytes(pdf("A newer version."))
        self.assertEqual(self.add("paper-one", str(new), "--replace")[0], 0)
        self.assertTrue((self.proj / "sources" / "paper-one.pdf").is_file())

    def test_the_old_file_is_replaced_not_left_beside_the_new_one(self):
        self.save()
        new = self.tmp / "new.pdf"
        new.write_bytes(pdf("A newer version."))
        self.add("paper-one", str(new), "--replace")
        self.assertEqual(sorted(p.name for p in (self.proj / "sources").iterdir() if p.name != "README.md"),
                         ["paper-one.pdf"])


class RaceAndTamperTests(SourceCase):
    def swap_after_hashing(self, target, new_bytes):
        real = add_source.kbfiles.sha256_file

        def hashing(path):
            digest = real(path)
            if path == str(target):
                Path(target).write_bytes(new_bytes)  # the source changes right after it was hashed
            return digest

        return mock.patch.object(add_source.kbfiles, "sha256_file", side_effect=hashing)

    def test_a_source_that_changes_after_it_is_hashed_is_refused_and_nothing_is_replaced(self):
        self.save()
        before = helpers.snapshot(self.proj)
        new = self.tmp / "new.pdf"
        new.write_bytes(pdf("A newer version."))
        with self.swap_after_hashing(new, pdf("Swapped in after the hash.")):
            code, out, err = self.add("paper-one", str(new), "--replace")
        self.assertEqual(code, 1, out + err)
        self.assertIn("changed while it was copied", out + err)
        self.assertEqual(helpers.snapshot(self.proj), before)  # the saved file, the record, and no temporary file

    def test_a_same_hash_repair_never_leaves_a_file_that_differs_from_the_record(self):
        self.save()
        saved = self.proj / "sources" / "paper-one.pdf"
        saved.write_bytes(b"%PDF-1.4 TAMPERED")
        before = helpers.snapshot(self.proj)
        with self.swap_after_hashing(self.file, pdf("Swapped in after the hash.")):
            code, out, err = self.add("paper-one", str(self.file), "--replace")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(saved.read_bytes(), b"%PDF-1.4 TAMPERED")  # untouched, not half-repaired
        after = helpers.snapshot(self.proj)
        self.assertEqual({k: v for k, v in after.items() if not k.startswith("incoming")},
                         {k: v for k, v in before.items() if not k.startswith("incoming")})

    def test_the_header_is_checked_on_the_bytes_that_were_copied(self):
        new = self.tmp / "new.pdf"
        new.write_bytes(pdf("A newer version."))
        self.save()
        real = add_source.check_file

        def swap_then_check(path):
            size = real(path)
            Path(path).write_bytes(b"not a pdf at all, swapped after the check")
            return size

        with mock.patch.object(add_source, "check_file", side_effect=swap_then_check):
            code, out, err = self.add("paper-one", str(new), "--replace")
        self.assertEqual(code, 1, out + err)
        self.assertIn("PDF", out + err)
        self.assertEqual(sorted(p.name for p in (self.proj / "sources").iterdir() if p.name != "README.md"),
                         ["paper-one.pdf"])
        self.assertTrue((self.proj / "sources" / "paper-one.pdf").read_bytes().startswith(b"%PDF-"))

    def test_a_replace_with_an_unchanged_hash_repairs_a_tampered_saved_file(self):
        self.save()
        saved = self.proj / "sources" / "paper-one.pdf"
        saved.write_bytes(b"%PDF-1.4 TAMPERED")
        code, out, err = self.add("paper-one", str(self.file), "--replace")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(saved.read_bytes(), self.file.read_bytes())
        self.assertIn("repaired", out)
        self.assertEqual(errors(self.proj, strict=True), [])


class InterruptionTests(SourceCase):
    def fail_on_record(self):
        real = add_source.kbfiles.write_atomic

        def failing(path, data):
            if os.sep + "catalog" + os.sep in path:
                raise OSError("disk full")
            return real(path, data)

        return mock.patch.object(add_source.kbfiles, "write_atomic", side_effect=failing)

    def test_a_failure_after_the_copy_is_completed_by_running_it_again(self):
        with self.fail_on_record():
            code, out, err = self.save()
        self.assertEqual(code, 1)
        self.assertTrue((self.proj / "sources" / "paper-one.pdf").is_file())
        self.assertFalse((self.proj / "catalog" / "paper-one.md").exists())
        self.assertIn("run the same command again", out + err)
        code, out, err = self.save()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(errors(self.proj, strict=True), [])

    def test_a_failure_during_a_replace_is_completed_by_running_it_again(self):
        self.save()
        new = self.tmp / "new.pdf"
        new.write_bytes(pdf("A newer version."))
        with self.fail_on_record():
            self.assertEqual(self.add("paper-one", str(new), "--replace")[0], 1)
        self.assertTrue(has(errors(self.proj, strict=True), "sha256"), errors(self.proj, strict=True))
        self.assertEqual(self.add("paper-one", str(new), "--replace")[0], 0)
        self.assertEqual(errors(self.proj, strict=True), [])

    def test_a_failure_during_the_copy_leaves_no_partial_file(self):
        with mock.patch.object(add_source.os, "replace", side_effect=OSError("disk full")):
            code, out, err = self.save()
        self.assertEqual(code, 1)
        self.assertEqual(sorted(p.name for p in (self.proj / "sources").iterdir() if p.name != "README.md"), [])
        self.assertFalse((self.proj / "catalog" / "paper-one.md").exists())

    def test_a_hidden_temporary_file_from_a_killed_run_is_ignored_by_the_check(self):
        (self.proj / "sources" / ".kbtmp-1-abcd").write_bytes(b"partial")
        self.assertEqual(errors(self.proj), [])
        self.assertEqual(self.save()[0], 0)


class CloneTests(SourceCase):
    def test_other_records_with_no_files_do_not_matter(self):
        add_catalog(self.proj, "src-conv", state="converted", sha256="a" * 64, scan="clean")
        self.assertEqual(self.save()[0], 0)
        self.assertEqual(errors(self.proj), [])


if __name__ == "__main__":
    unittest.main()
