"""Readers for the lifecycle artifacts (docs/kb/domain-lifecycle.md): questions, log, charter,
reading notes, usage tests. They are pure functions over text, so they need no project on disk."""
import datetime
import time
import unittest

import helpers
import kblife


def messages(issues):
    return [i.message for i in issues]


def has(issues, needle):
    return any(needle in i.message for i in issues)


HEADER = "| ID | Question | Status | Entries | Notes |\n|---|---|---|---|---|\n"


def questions(*rows, header=HEADER):
    return "# Questions\n\nIntro.\n\n" + header + "".join(rows)


class QuestionTests(unittest.TestCase):
    def test_a_valid_table_is_read(self):
        text = questions("| q-1 | Which X when Y? | answered | pb-one, `pb-two` | |\n",
                         "| q-2 | Which Z? | open | | |\n",
                         "| q-10 | Which W? | partial | [pb-three](playbook/entries/pb-three.md) | missing the cost case |\n")
        result = kblife.parse_questions(text)
        self.assertEqual(result.issues, [])
        self.assertEqual([r.id for r in result.rows], ["q-1", "q-2", "q-10"])
        self.assertEqual(result.rows[0].entries, ["pb-one", "pb-two"])
        self.assertEqual(result.rows[1].entries, [])
        self.assertEqual(result.rows[2].entries, ["pb-three"])
        self.assertEqual(result.rows[2].status, "partial")
        self.assertEqual(result.rows[2].notes, "missing the cost case")

    def test_the_skeleton_table_is_valid_and_empty(self):
        result = kblife.parse_questions(questions())
        self.assertEqual((result.rows, result.issues), ([], []))

    def test_a_missing_or_misnamed_column_is_reported(self):
        for header in ("| ID | Question | Status | Entries |\n|---|---|---|---|\n",
                       "| ID | Question | State | Entries | Notes |\n|---|---|---|---|---|\n",
                       "| Question | ID | Status | Entries | Notes |\n|---|---|---|---|---|\n"):
            with self.subTest(header=header[:30]):
                result = kblife.parse_questions(questions(header=header))
                self.assertTrue(has(result.issues, "column"), messages(result.issues))

    def test_no_table_is_reported(self):
        self.assertTrue(has(kblife.parse_questions("# Questions\n\nNothing here.\n").issues, "no questions table"))

    def test_duplicate_and_malformed_ids(self):
        text = questions("| q-1 | A? | open | | |\n", "| q-1 | B? | open | | |\n", "| x-2 | C? | open | | |\n",
                         "| q-03x | D? | open | | |\n")
        issues = kblife.parse_questions(text).issues
        self.assertTrue(has(issues, "duplicate question id"))
        self.assertEqual(sum(1 for i in issues if "invalid question id" in i.message), 2)

    def test_status_rules(self):
        cases = [
            ("| q-1 | A? | open | pb-one | |\n", "open question lists entries"),
            ("| q-1 | A? | answered | | |\n", "answered question lists no entry"),
            ("| q-1 | A? | partial | | gap |\n", "partial question lists no entry"),
            ("| q-1 | A? | partial | pb-one | |\n", "partial question needs a note"),
            ("| q-1 | A? | done | pb-one | |\n", "invalid status"),
            ("| q-1 | A? | open | |\n", "cells"),
        ]
        for row, needle in cases:
            with self.subTest(row=row):
                self.assertTrue(has(kblife.parse_questions(questions(row)).issues, needle), needle)

    def test_issues_carry_the_line_of_the_row(self):
        text = questions("| q-1 | A? | open | | |\n", "| q-1 | B? | open | | |\n")
        issue = [i for i in kblife.parse_questions(text).issues if "duplicate" in i.message][0]
        self.assertEqual(text.split("\n")[issue.line - 1].split("|")[2].strip(), "B?")

    def test_entries_must_exist(self):
        rows = kblife.parse_questions(questions("| q-1 | A? | answered | pb-one, pb-gone | |\n")).rows
        issues = kblife.question_entry_issues(rows, {"pb-one"})
        self.assertEqual(len(issues), 1)
        self.assertIn("pb-gone", issues[0].message)
        self.assertEqual(kblife.question_entry_issues(rows, {"pb-one", "pb-gone"}), [])

    def test_a_huge_table_is_read_in_bounded_time(self):
        rows = "".join(f"| q-{n} | Question {n}? | open | | |\n" for n in range(1, 20001))
        started = time.monotonic()
        result = kblife.parse_questions(questions(rows))
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(len(result.rows) + len(result.issues) >= 1, True)

    def test_a_very_long_line_is_refused_not_scanned(self):
        text = questions("| q-1 | " + "x" * 100000 + " | open | | |\n")
        self.assertTrue(has(kblife.parse_questions(text).issues, "too long"))


def log(*blocks):
    return "# Log\n\nIntro.\n\n" + "\n".join(blocks)


def opened(n=1, date="2026-01-01", gaps=None, goal="Close gaps", targets="q-1", limit="5 sources"):
    lines = [f"## {date} wave {n} opened", "", f"Goal: {goal}", f"Targets: {targets}", f"Limit: {limit}"]
    if gaps:
        lines.append(f"Gaps: {gaps}")
    return "\n".join(lines) + "\n"


def closed(n=1, date="2026-01-02", result=None, added="pb-one", left="q-2", reviewed="none"):
    lines = [f"## {date} wave {n} closed", "", f"Added: {added}", f"Left open: {left}", f"Reviewed: {reviewed}"]
    if result:
        lines.append(f"Gap result: {result}")
    return "\n".join(lines) + "\n"


def abandoned(n=1, date="2026-01-02", reason="ran out of time", resume="step 3"):
    return f"## {date} wave {n} abandoned\n\nReason: {reason}\nResume from: {resume}\n"


def charter_entry(date="2026-01-01", change="Set the charter", reason="First draft"):
    return f"## {date} charter\n\nChange: {change}\nReason: {reason}\n"


class LogTests(unittest.TestCase):
    def issues(self, *blocks):
        return kblife.parse_log(log(*blocks)).issues

    def test_a_valid_log_is_read(self):
        result = kblife.parse_log(log(charter_entry(), opened(1), closed(1), opened(2), abandoned(2)))
        self.assertEqual(result.issues, [])
        self.assertEqual([(e.kind, e.number) for e in result.entries],
                         [("charter", None), ("opened", 1), ("closed", 1), ("opened", 2), ("abandoned", 2)])
        self.assertEqual(result.entries[1].fields["Goal"], "Close gaps")
        self.assertEqual(kblife.open_waves(result), [])

    def test_the_skeleton_log_is_valid_and_empty(self):
        result = kblife.parse_log("# Log\n\nAppend-only record.\n")
        self.assertEqual((result.entries, result.issues), ([], []))

    def test_waves_still_open_or_abandoned_are_listed(self):
        result = kblife.parse_log(log(opened(1), closed(1), opened(2), opened(3), abandoned(3)))
        self.assertEqual(kblife.open_waves(result), [2])
        self.assertEqual(kblife.abandoned_waves(result), [3])

    def test_closed_or_abandoned_without_opening(self):
        self.assertTrue(has(self.issues(closed(1)), "was never opened"))
        self.assertTrue(has(self.issues(abandoned(1)), "was never opened"))

    def test_closed_and_abandoned_both_and_twice(self):
        self.assertTrue(has(self.issues(opened(1), closed(1), abandoned(1)), "already"))
        self.assertTrue(has(self.issues(opened(1), closed(1), closed(1)), "already"))
        self.assertTrue(has(self.issues(opened(1), opened(1)), "opened twice"))

    def test_wave_numbers_start_at_one_and_have_no_gap(self):
        self.assertTrue(has(self.issues(opened(2)), "wave numbers must start at 1"))
        self.assertTrue(has(self.issues(opened(1), closed(1), opened(3)), "wave number 3 should be 2"))

    def test_required_lines(self):
        cases = {
            "opened": ("## 2026-01-01 wave 1 opened\n\nGoal: g\nTargets: q-1\n", "Limit"),
            "closed": (opened(1) + "\n## 2026-01-02 wave 1 closed\n\nAdded: a\nLeft open: b\n", "Reviewed"),
            "abandoned": (opened(1) + "\n## 2026-01-02 wave 1 abandoned\n\nReason: r\n", "Resume from"),
            "charter": ("## 2026-01-01 charter\n\nChange: c\n", "Reason"),
        }
        for kind, (block, field) in cases.items():
            with self.subTest(kind=kind):
                self.assertTrue(has(self.issues(block), f"missing {field}:"), messages(self.issues(block)))

    def test_empty_required_values_are_reported(self):
        self.assertTrue(has(self.issues(opened(1, goal="")), "empty Goal"))
        self.assertTrue(has(self.issues(opened(1), closed(1, added="")), "empty Added"))

    def test_bad_headings(self):
        for heading in ("## 2026-13-01 wave 1 opened", "## 2026-01-01 wave one opened", "## wave 1 opened",
                        "## 2026-01-01 wave 1 reopened", "## Random notes"):
            with self.subTest(heading=heading):
                self.assertTrue(has(self.issues(heading + "\n\nGoal: g\n"), "unrecognised log heading"))

    def test_gaps_need_a_gap_result_with_the_same_categories(self):
        gaps = "open-questions=5, no-verified=2"
        self.assertTrue(has(self.issues(opened(1, gaps=gaps), closed(1)), "needs a Gap result"))
        self.assertTrue(has(self.issues(opened(1, gaps=gaps), closed(1, result="open-questions=3")),
                            "no-verified"))
        self.assertTrue(has(self.issues(opened(1, gaps=gaps),
                                        closed(1, result="open-questions=3, no-verified=1, leads=0")), "leads"))
        self.assertEqual(self.issues(opened(1, gaps=gaps), closed(1, result="open-questions=3, no-verified=1")), [])

    def test_a_count_that_did_not_fall_needs_unchanged_and_a_reason(self):
        gaps = "open-questions=5, conflicts=2"
        self.assertTrue(has(self.issues(opened(1, gaps=gaps), closed(1, result="open-questions=5, conflicts=1")),
                            "open-questions"))
        self.assertTrue(has(self.issues(opened(1, gaps=gaps), closed(1, result="open-questions=6, conflicts=1")),
                            "open-questions"))
        ok = closed(1, result="open-questions=2, conflicts=unchanged: no primary source, only a survey")
        self.assertEqual(self.issues(opened(1, gaps=gaps), ok), [])
        self.assertTrue(has(self.issues(opened(1, gaps=gaps), closed(1, result="open-questions=2, conflicts=unchanged: ")),
                            "reason"))

    def test_unknown_categories_and_bad_counts(self):
        self.assertTrue(has(self.issues(opened(1, gaps="open-questions=x")), "Gaps"))
        self.assertTrue(has(self.issues(opened(1, gaps="mystery=3")), "unknown gap category"))
        self.assertTrue(has(self.issues(opened(1, gaps="open-questions=-1")), "Gaps"))

    def test_an_abandoned_wave_needs_no_gap_result(self):
        self.assertEqual(self.issues(opened(1, gaps="leads=3"), abandoned(1)), [])

    def test_parse_gaps(self):
        self.assertEqual(kblife.parse_gaps("usage-test=2, stale=0"), {"usage-test": 2, "stale": 0})
        self.assertIsNone(kblife.parse_gaps("usage-test=two"))
        result = kblife.parse_gap_result("conflicts=unchanged: a, b and c, open-questions=1")
        self.assertEqual(result, {"conflicts": ("unchanged", "a, b and c"), "open-questions": 1})

    def test_reviewed_names_are_listed_for_closed_waves(self):
        result = kblife.parse_log(log(opened(1), closed(1, reviewed="pb-one (A. Person), pb-two (B. Person)")))
        self.assertEqual(kblife.reviewed_entries(result), {"pb-one", "pb-two"})

    def test_cost_is_linear_in_a_long_log(self):
        blocks = []
        for n in range(1, 801):
            blocks += [opened(n), closed(n)]
        started = time.monotonic()
        result = kblife.parse_log(log(*blocks))
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(result.issues, [])

    def test_a_very_long_line_is_refused(self):
        self.assertTrue(has(self.issues(opened(1, goal="x" * 100000)), "too long"))


CHARTER_BODY = """
# Title

## Purpose and consumers

Who reads this.

## Scope

What is in.

## Non-goals

What is out.

## Source types and trust tiers

Papers are primary.

## Verification bar

Checked against the full saved source.

## Safety and sensitivity notes

None identified.
"""


def charter(state="set", body=CHARTER_BODY, domain="demo"):
    return f'---\ndomain: {domain}\ntitle: "Demo"\ncharter: {state}\ncreated: 2026-01-01\n---\n{body}'


class CharterTests(unittest.TestCase):
    def test_a_complete_set_charter_passes(self):
        result = kblife.charter_issues(charter())
        self.assertEqual(result.issues, [])
        self.assertEqual(result.state, "set")

    def test_a_draft_charter_may_be_incomplete(self):
        result = kblife.charter_issues(charter("draft", "\n# Title\n\nREPLACE_WITH_PURPOSE\n"))
        self.assertEqual(result.issues, [])
        self.assertEqual(result.state, "draft")

    def test_a_missing_misordered_or_repeated_heading(self):
        for heading in ("Purpose and consumers", "Scope", "Non-goals", "Source types and trust tiers",
                        "Verification bar", "Safety and sensitivity notes"):
            with self.subTest(missing=heading):
                body = CHARTER_BODY.replace(f"## {heading}\n", f"### {heading}\n")
                self.assertTrue(has(kblife.charter_issues(charter(body=body)).issues, heading))
        swapped = CHARTER_BODY.replace("## Scope", "## @@").replace("## Non-goals", "## Scope").replace("## @@", "## Non-goals")
        self.assertTrue(has(kblife.charter_issues(charter(body=swapped)).issues, "order"))
        repeated = CHARTER_BODY + "\n## Scope\n\nAgain.\n"
        self.assertTrue(has(kblife.charter_issues(charter(body=repeated)).issues, "more than once"))

    def test_placeholder_text_in_a_set_charter(self):
        body = CHARTER_BODY.replace("Who reads this.", "REPLACE_WITH_PURPOSE")
        self.assertTrue(has(kblife.charter_issues(charter(body=body)).issues, "REPLACE_WITH_"))

    def test_front_matter_and_state(self):
        self.assertTrue(has(kblife.charter_issues("no front matter\n").issues, "front matter"))
        self.assertTrue(has(kblife.charter_issues(charter("final")).issues, "charter must be draft or set"))
        missing = charter().replace('title: "Demo"\n', "")
        self.assertTrue(has(kblife.charter_issues(missing).issues, "title"))
        self.assertTrue(has(kblife.charter_issues(charter().replace("created: 2026-01-01", "created: soon")).issues,
                            "created"))

    def test_a_code_block_heading_does_not_count(self):
        body = CHARTER_BODY.replace("## Scope\n\nWhat is in.", "```\n## Scope\n```\n\nWhat is in.")
        self.assertTrue(has(kblife.charter_issues(charter(body=body)).issues, "Scope"))


def note(source="paper-one", read="2026-01-05", by="A. Person", findings="- p. 3: the result holds.\n"):
    return f'---\nsource: {source}\nread: {read}\nby: "{by}"\n---\n\n# Notes\n\n## Findings\n\n{findings}'


class ReadingNoteTests(unittest.TestCase):
    def test_a_valid_note(self):
        self.assertEqual(kblife.reading_note_issues(note(), "paper-one"), [])

    def test_wrong_source_missing_fields(self):
        self.assertTrue(has(kblife.reading_note_issues(note(source="other"), "paper-one"), "source"))
        self.assertTrue(has(kblife.reading_note_issues(note(read="today"), "paper-one"), "read"))
        self.assertTrue(has(kblife.reading_note_issues(note(by=""), "paper-one"), "by"))
        self.assertTrue(has(kblife.reading_note_issues("no front matter\n", "paper-one"), "front matter"))

    def test_findings_must_exist_and_be_non_empty(self):
        self.assertTrue(has(kblife.reading_note_issues(note(findings=""), "paper-one"), "Findings"))
        self.assertTrue(has(kblife.reading_note_issues(note(findings="\n\n  \n"), "paper-one"), "Findings"))
        nothing = note().split("## Findings")[0] + "## Other\n\ntext\n"
        self.assertTrue(has(kblife.reading_note_issues(nothing, "paper-one"), "Findings"))

    def test_the_template_text_does_not_count(self):
        self.assertTrue(has(kblife.reading_note_issues(note(findings="REPLACE_WITH_FINDINGS\n"), "paper-one"),
                            "REPLACE_WITH_"))

    def test_findings_end_at_the_next_heading(self):
        text = note(findings="\n## Next\n\nmore\n")
        self.assertTrue(has(kblife.reading_note_issues(text, "paper-one"), "Findings"))


def usage(result="pass", date="2026-02-01", scenario="Pick a tool for X"):
    return f'---\ndate: {date}\nscenario: "{scenario}"\nresult: {result}\n---\n\n## Purpose and method\n\nText.\n'


class UsageTestTests(unittest.TestCase):
    def test_valid_results(self):
        for result in ("pass", "partial", "fail"):
            data = kblife.usage_test_issues(usage(result))
            self.assertEqual((data.issues, data.result), ([], result))

    def test_invalid_result_date_and_scenario(self):
        self.assertTrue(has(kblife.usage_test_issues(usage("maybe")).issues, "result"))
        self.assertTrue(has(kblife.usage_test_issues(usage(date="yesterday")).issues, "date"))
        self.assertTrue(has(kblife.usage_test_issues(usage(scenario="")).issues, "scenario"))
        self.assertTrue(has(kblife.usage_test_issues("nothing\n").issues, "front matter"))

    def test_the_date_is_returned(self):
        self.assertEqual(kblife.usage_test_issues(usage()).date, datetime.date(2026, 2, 1))


class IndexSourceTests(unittest.TestCase):
    HEAD = "# Sources used by this domain\n\n| Source | Why it matters here |\n|---|---|\n"

    def test_stems_are_read_however_they_are_written(self):
        text = self.HEAD + "| paper-one | Core result |\n| `paper-two` | Survey |\n| [paper-three](../../catalog/paper-three.md) | Method |\n"
        stems, issues = kblife.index_stems(text)
        self.assertEqual(issues, [])
        self.assertEqual([s for s, _ in stems], ["paper-one", "paper-two", "paper-three"])

    def test_the_skeleton_table_is_empty_and_valid(self):
        self.assertEqual(kblife.index_stems(self.HEAD), ([], []))

    def test_invalid_stems_and_rows(self):
        text = self.HEAD + "| Not A Stem | x |\n| ok-stem |\n"
        stems, issues = kblife.index_stems(text)
        self.assertTrue(has(issues, "invalid stem"))
        self.assertTrue(has(issues, "cells"))

    def test_no_table_is_not_an_error_for_a_domain_with_no_sources_yet(self):
        self.assertEqual(kblife.index_stems("# Sources\n\nNone yet.\n"), ([], []))


class ModuleTests(unittest.TestCase):
    def test_the_module_imports_only_the_standard_library_and_the_sibling_modules(self):
        import re
        text = (helpers.KIT_TOOLS / "kblife.py").read_text(encoding="utf-8")
        modules = set(re.findall(r"^(?:import|from) ([a-z_]+)", text, flags=re.M))
        self.assertTrue(modules <= {"datetime", "re", "collections", "os", "sys", "kbparse", "kbfiles"}, modules)

    def test_the_gap_categories_match_the_specification(self):
        self.assertEqual(kblife.GAP_CATEGORIES, ("usage-test", "open-questions", "conflicts", "reverify",
                                                 "no-verified", "leads", "stale"))
        self.assertEqual(len(kblife.CHARTER_HEADINGS), 6)


if __name__ == "__main__":
    unittest.main()
