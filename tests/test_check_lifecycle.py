"""The lifecycle checks in check_kb.py (domain-lifecycle.md acceptance criterion 4, and 6 for clones)."""
import unittest
from pathlib import Path

import helpers
import check_kb
from projects import (SHA, add_catalog, add_domain, add_entry, add_index_source, add_reading_note,
                      add_usage_test, build_project, good_project, write_log)

CHARTER_REPLACEMENT = "REPLACE_WITH_PURPOSE"


def errors(proj):
    return [f"{f.path}: {f.message}" for f in check_kb.check(Path(proj)).errors]


def warnings(proj):
    return [f"{f.path}: {f.message}" for f in check_kb.check(Path(proj)).warnings]


def has(items, needle):
    return any(needle in item for item in items)


def edit(path, old, new):
    text = Path(path).read_text(encoding="utf-8")
    assert old in text, (old, path)
    Path(path).write_text(text.replace(old, new, 1), encoding="utf-8")


def opened(n=1, gaps=None):
    lines = [f"## 2026-01-0{n} wave {n} opened", "", "Goal: close gaps", "Targets: q-1", "Limit: 5 sources"]
    if gaps:
        lines.append(f"Gaps: {gaps}")
    return "\n".join(lines) + "\n"


def closed(n=1, result=None):
    lines = [f"## 2026-01-1{n} wave {n} closed", "", "Added: pb-one", "Left open: q-2", "Reviewed: none"]
    if result:
        lines.append(f"Gap result: {result}")
    return "\n".join(lines) + "\n"


class LifecycleCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.root = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.proj = good_project(self.root / "p")
        self.demo = self.proj / "domains" / "demo"

    def test_the_good_project_still_passes(self):
        self.assertEqual(errors(self.proj), [])

    def test_a_draft_domain_without_entries_may_have_no_questions(self):
        draft = add_domain(self.proj, "fresh", charter="draft", questions="")
        self.assertEqual(errors(self.proj), [])
        self.assertTrue((draft / "questions.md").is_file())


class CharterChecks(LifecycleCase):
    def test_a_set_charter_missing_a_heading(self):
        edit(self.demo / "README.md", "## Scope", "### Scope")
        self.assertTrue(has(errors(self.proj), "lacks the heading 'Scope'"))

    def test_a_set_charter_containing_placeholder_text(self):
        edit(self.demo / "README.md", "## Scope\n\nfilled in", f"## Scope\n\n{CHARTER_REPLACEMENT}")
        self.assertTrue(has(errors(self.proj), "REPLACE_WITH_"))

    def test_a_draft_charter_may_keep_placeholders_but_not_with_entries(self):
        edit(self.demo / "README.md", "## Scope\n\nfilled in", f"## Scope\n\n{CHARTER_REPLACEMENT}")
        edit(self.demo / "README.md", "charter: set", "charter: draft")
        found = errors(self.proj)
        self.assertTrue(has(found, "a domain with entries cannot have charter: draft"))
        self.assertFalse(has(found, "lacks the heading"))

    def test_charter_front_matter_problems_are_reported_once(self):
        edit(self.demo / "README.md", "charter: set", "charter: final")
        found = [e for e in errors(self.proj) if "domains/demo/README.md" in e]
        self.assertEqual(len(found), 1, found)
        self.assertIn("charter must be draft or set", found[0])

    def test_fewer_than_three_questions_in_a_set_domain(self):
        path = self.demo / "questions.md"
        lines = path.read_text(encoding="utf-8").split("\n")
        path.write_text("\n".join(line for line in lines if not line.startswith("| q-3")), encoding="utf-8")
        self.assertTrue(has(errors(self.proj), "at least three questions"))

    def test_a_missing_questions_file(self):
        (self.demo / "questions.md").unlink()
        self.assertTrue(has(errors(self.proj), "questions.md is missing"))


class QuestionChecks(LifecycleCase):
    def table(self, rows, header="| ID | Question | Status | Entries | Notes |\n|---|---|---|---|---|\n"):
        (self.demo / "questions.md").write_text("# Questions\n\n" + header + rows, encoding="utf-8")

    def test_a_valid_table_with_answered_and_partial_rows_passes(self):
        self.table("| q-1 | A? | answered | pb-one | |\n| q-2 | B? | partial | pb-one | missing the cost case |\n"
                   "| q-3 | C? | open | | |\n")
        self.assertEqual(errors(self.proj), [])

    def test_a_missing_required_column(self):
        self.table("| q-1 | A? | open | |\n| q-2 | B? | open | |\n| q-3 | C? | open | |\n",
                   header="| ID | Question | Status | Entries |\n|---|---|---|---|\n")
        self.assertTrue(has(errors(self.proj), "lacks column 'Notes'"))

    def test_a_duplicate_id(self):
        self.table("| q-1 | A? | open | | |\n| q-1 | B? | open | | |\n| q-3 | C? | open | | |\n")
        self.assertTrue(has(errors(self.proj), "duplicate question id"))

    def test_an_entry_that_does_not_exist(self):
        self.table("| q-1 | A? | answered | pb-gone | |\n| q-2 | B? | open | | |\n| q-3 | C? | open | | |\n")
        self.assertTrue(has(errors(self.proj), "pb-gone, which is not an entry"))

    def test_an_entry_from_another_domain_does_not_count(self):
        other = add_domain(self.proj, "other")
        add_entry(self.proj, "other", "pb-elsewhere")
        self.table("| q-1 | A? | answered | pb-elsewhere | |\n| q-2 | B? | open | | |\n| q-3 | C? | open | | |\n")
        self.assertTrue(has(errors(self.proj), "pb-elsewhere, which is not an entry"))
        self.assertTrue(other.is_dir())

    def test_status_and_entries_must_agree(self):
        self.table("| q-1 | A? | open | pb-one | |\n| q-2 | B? | answered | | |\n| q-3 | C? | partial | pb-one | |\n")
        found = errors(self.proj)
        self.assertTrue(has(found, "open question lists entries"))
        self.assertTrue(has(found, "answered question lists no entry"))
        self.assertTrue(has(found, "partial question needs a note"))


class SourceIndexChecks(LifecycleCase):
    def test_a_stem_with_no_catalog_record(self):
        add_index_source(self.proj, "demo", "src-one")
        self.assertEqual(errors(self.proj), [])
        add_index_source(self.proj, "demo", "src-missing")
        self.assertTrue(has(errors(self.proj), "src-missing"))

    def test_an_invalid_stem_in_the_index(self):
        add_index_source(self.proj, "demo", "Not A Stem")
        self.assertTrue(has(errors(self.proj), "invalid stem"))


class UsageTestChecks(LifecycleCase):
    def test_valid_usage_tests_pass(self):
        for result in ("pass", "partial", "fail"):
            add_usage_test(self.proj, "demo", f"2026-02-0{['pass', 'partial', 'fail'].index(result) + 1}-{result}", result)
        self.assertEqual(errors(self.proj), [])

    def test_an_invalid_result(self):
        add_usage_test(self.proj, "demo", "2026-02-01-bad", "maybe")
        self.assertTrue(has(errors(self.proj), "result must be pass, partial, or fail"))

    def test_front_matter_that_does_not_parse(self):
        helpers.write(self.demo / "usage-tests", "2026-02-01-broken.md", "no front matter\n")
        self.assertTrue(has(errors(self.proj), "invalid front matter"))


class LogChecks(LifecycleCase):
    def log(self, *blocks):
        write_log(self.proj, "demo", *blocks)
        return errors(self.proj)

    def test_a_valid_log_passes(self):
        self.assertEqual(self.log(opened(1), closed(1), opened(2)), [])

    def test_closed_or_abandoned_without_an_opening(self):
        self.assertTrue(has(self.log(closed(1)), "was never opened"))

    def test_closed_and_abandoned_both(self):
        found = self.log(opened(1), closed(1), "## 2026-01-20 wave 1 abandoned\n\nReason: r\nResume from: s\n")
        self.assertTrue(has(found, "already closed"))

    def test_a_number_gap(self):
        self.assertTrue(has(self.log(opened(1), closed(1), opened(3)), "wave number 3 should be 2"))

    def test_a_missing_required_line(self):
        self.assertTrue(has(self.log("## 2026-01-01 wave 1 opened\n\nGoal: g\nTargets: q-1\n"), "missing Limit:"))

    def test_gap_result_rules(self):
        gaps = "open-questions=5, conflicts=2"
        self.assertTrue(has(self.log(opened(1, gaps), closed(1)), "needs a Gap result"))

    def test_categories_must_match_and_counts_must_fall(self):
        gaps = "open-questions=5, conflicts=2"
        found = self.log(opened(1, gaps), closed(1, "open-questions=5"))
        self.assertTrue(has(found, "lacks the category conflicts"))
        self.assertTrue(has(found, "open-questions: the count did not fall"))

    def test_unchanged_with_a_reason_passes(self):
        gaps = "open-questions=5, conflicts=2"
        self.assertEqual(self.log(opened(1, gaps), closed(1, "open-questions=2, conflicts=unchanged: no primary source")), [])

    def test_a_reviewed_entry_still_needs_a_reviewed_line_in_a_closed_wave(self):
        edit(self.demo / "playbook" / "entries" / "pb-one.md", "status: draft", "status: reviewed")
        found = self.log(opened(1), closed(1))
        self.assertTrue(has(found, "needs a Reviewed: line"))


class ConflictChecks(LifecycleCase):
    def test_a_conflict_note_naming_a_stem_with_no_record(self):
        path = self.demo / "playbook" / "entries" / "pb-one.md"
        edit(path, "Do the thing [V].", "Do the thing [U — conflict: src-one vs src-missing].")
        self.assertTrue(has(errors(self.proj), "src-missing"))


class ReadSourceChecks(LifecycleCase):
    def make_read(self):
        add_catalog(self.proj, "src-read", state="read", sha256=SHA, scan="clean")
        add_index_source(self.proj, "demo", "src-read")

    def test_a_read_source_with_a_valid_note_passes(self):
        self.make_read()
        add_reading_note(self.proj, "demo", "src-read")
        self.assertEqual(errors(self.proj), [])

    def test_no_note_in_a_domain_that_lists_it(self):
        self.make_read()
        self.assertTrue(has(errors(self.proj), "no domain that lists it has a valid reading note"))

    def test_a_read_source_no_domain_lists(self):
        add_catalog(self.proj, "src-read", state="read", sha256=SHA, scan="clean")
        add_reading_note(self.proj, "demo", "src-read")
        self.assertTrue(has(errors(self.proj), "no domain that lists it has a valid reading note"))

    def test_an_empty_findings_section(self):
        self.make_read()
        add_reading_note(self.proj, "demo", "src-read", findings="\n")
        found = errors(self.proj)
        self.assertTrue(has(found, "no domain that lists it has a valid reading note"))
        self.assertTrue(has(found, "'## Findings' section is missing or empty"))

    def test_placeholder_text_in_a_note(self):
        self.make_read()
        add_reading_note(self.proj, "demo", "src-read", findings="REPLACE_WITH_FINDINGS\n")
        self.assertTrue(has(errors(self.proj), "REPLACE_WITH_"))

    def test_a_note_in_a_second_domain_counts(self):
        self.make_read()
        add_domain(self.proj, "other")
        add_index_source(self.proj, "other", "src-read")
        add_reading_note(self.proj, "other", "src-read")
        self.assertEqual(errors(self.proj), [])

    def test_a_note_for_another_source_does_not_count(self):
        self.make_read()
        add_reading_note(self.proj, "demo", "src-read")
        edit(self.demo / "topics" / "src-read.md", "source: src-read", "source: src-one")
        self.assertTrue(has(errors(self.proj), "source must name the catalog stem src-read"))


class OrphanSourceChecks(LifecycleCase):
    def test_a_source_file_with_no_catalog_record_is_a_warning(self):
        helpers.write(self.proj / "sources", "orphan-one.pdf", "%PDF-1.7\n")
        self.assertEqual(errors(self.proj), [])
        self.assertTrue(has(warnings(self.proj), "orphan-one.pdf: has no catalog record"), warnings(self.proj))

    def test_a_quarantined_file_with_no_record_is_also_a_warning(self):
        helpers.write(self.proj / "sources" / "quarantine", "orphan-two.pdf", "%PDF-1.7\n")
        self.assertTrue(has(warnings(self.proj), "orphan-two.pdf: has no catalog record"), warnings(self.proj))


class CloneMode(LifecycleCase):
    def test_converted_and_read_sources_with_no_files_stay_valid(self):
        add_catalog(self.proj, "src-conv", state="converted", sha256=SHA, scan="clean")
        add_catalog(self.proj, "src-read", state="read", sha256=SHA, scan="review")
        add_index_source(self.proj, "demo", "src-read")
        add_reading_note(self.proj, "demo", "src-read")
        self.assertEqual(errors(self.proj), [])
        self.assertTrue(has(warnings(self.proj), "src-read") or has(warnings(self.proj), "not present"))

    def test_a_store_with_no_domain_and_the_skeleton_still_pass(self):
        bare = build_project(self.root / "bare")
        self.assertEqual(errors(bare), [])


if __name__ == "__main__":
    unittest.main()
