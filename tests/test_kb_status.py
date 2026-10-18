"""kb_status.py (domain-lifecycle.md operation 3, step 1; acceptance criteria 5 and 6)."""
import datetime
import json
import os
import subprocess
import sys
import unittest

import helpers
import kb_status
from projects import add_catalog, add_domain, add_entry, add_index_source, build_project, write_log
from toolrun import TODAY, run_tool



def body(approach):
    return (f"# Title\n\n## Use when\n\nWhen.\n\n## Approach\n\n{approach}\n\n## Pitfalls\n\nNone.\n\n"
            "## Evidence and confidence\n\nChecked.\n\n## See also\n\nNothing.\n")


def sha(n):
    return f"{n:x}".rjust(64, "0")


class StatusCase(unittest.TestCase):
    """A domain with known counts for every item in the report."""

    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.proj = build_project(self.tmp / "store")
        self.domain = add_domain(self.proj, "demo", questions=(
            "| q-1 | Open question? | open | | |\n"
            "| q-2 | Partial question? | partial | pb-a | still missing the cost case |\n"
            "| q-3 | Answered question? | answered | pb-a | |\n"))
        catalog = [("s-rec", dict(state="recorded")),
                   ("s-saved", dict(state="saved", sha256=sha(1))),
                   ("s-conv", dict(state="converted", sha256=sha(2), scan="clean")),
                   ("s-read", dict(state="read", sha256=sha(3), scan="review", tier="primary")),
                   ("s-flag", dict(state="saved", sha256=sha(4), scan="flagged", tier="community")),
                   ("s-repl", dict(state="saved", sha256=sha(5), replaced="2026-06-01", tier="secondary")),
                   ("s-unused", dict(state="saved", sha256=sha(6))),
                   ("s-nofile", dict(state="converted", sha256=sha(7), scan="clean"))]
        for stem, fields in catalog:
            add_catalog(self.proj, stem, **fields)
        for stem in ("s-saved", "s-conv", "s-read", "s-repl", "s-unused", "s-rec", "s-flag", "s-nofile"):
            add_index_source(self.proj, "demo", stem)
        # files on disk: everything that should be saved is, except s-nofile (a clone without it)
        for stem in ("s-saved", "s-conv", "s-read", "s-repl", "s-unused"):
            helpers.write(self.proj / "sources", f"{stem}.pdf", "%PDF-1.7\n")
        helpers.write(self.proj / "sources" / "quarantine", "s-flag.pdf", "%PDF-1.7\n")
        add_entry(self.proj, "demo", "pb-a", body=body("Do it [V]. Also this [A]."), sources=["s-saved"], updated="2026-10-01")
        add_entry(self.proj, "demo", "pb-b", body=body("Maybe [U]."), sources=["s-repl", "s-conv"], updated="2025-01-01")
        add_entry(self.proj, "demo", "pb-c", body=body("Contested [U — conflict: s-saved vs s-conv]. Fine [V]."),
                  sources=["s-saved", "s-conv"], updated="2026-10-10")
        add_entry(self.proj, "demo", "pb-d", body=body("Old [U]."), sources=["s-read"], updated="2024-01-01",
                  status="superseded", superseded_by="pb-a", route=False)
        add_entry(self.proj, "demo", "pb-e", body=body("Malformed [U — conflict: s-saved]."), sources=["s-saved"],
                  updated="2026-10-17")
        write_log(self.proj, "demo",
                  "## 2026-01-01 wave 1 opened\n\nGoal: g\nTargets: q-1\nLimit: 5\nGaps: open-questions=3, leads=2\n",
                  "## 2026-01-05 wave 1 closed\n\nAdded: pb-a\nLeft open: q-1\nReviewed: none\n"
                  "Gap result: open-questions=2, leads=unchanged: no new leads\n",
                  "## 2026-02-01 wave 2 opened\n\nGoal: g\nTargets: q-1\nLimit: 5\n",
                  "## 2026-03-01 wave 3 opened\n\nGoal: g\nTargets: q-1\nLimit: 5\n",
                  "## 2026-03-02 wave 3 abandoned\n\nReason: r\nResume from: s\n")
        with open(self.domain / "index" / "leads.md", "a", encoding="utf-8") as handle:
            handle.write("| Lead one | s-saved | Because |\n| Lead two | s-conv | Also |\n")
        helpers.write(self.domain / "usage-tests", "2026-02-01-x-fail.md",
                      '---\ndate: 2026-02-01\nscenario: "X"\nresult: fail\n---\n')
        helpers.write(self.domain / "usage-tests", "2026-03-01-x-pass.md",
                      '---\ndate: 2026-03-01\nscenario: "X"\nresult: pass\n---\n')
        helpers.write(self.domain / "usage-tests", "2026-02-05-y-partial.md",
                      '---\ndate: 2026-02-05\nscenario: "Y"\nresult: partial\n---\n')
        helpers.write(self.domain / "usage-tests", "2026-04-01-z-fail.md",
                      '---\ndate: 2026-04-01\nscenario: "Z"\nresult: fail\n---\n')

    def report(self, domain="demo", stale_days=365):
        return kb_status.build_report(str(self.proj), domain, stale_days=stale_days, today=TODAY)

    def d(self, **kw):
        return self.report(**kw)["domains"]["demo"]


class SourceReportTests(StatusCase):
    def test_sources_used_by_state_tier_and_scan(self):
        s = self.d()["sources"]
        self.assertEqual(s["listed"], ["s-conv", "s-flag", "s-nofile", "s-read", "s-rec", "s-repl", "s-saved", "s-unused"])
        self.assertEqual(s["by_state"], {"converted": 2, "read": 1, "recorded": 1, "saved": 4})
        self.assertEqual(s["by_tier"], {"community": 1, "primary": 6, "secondary": 1})
        self.assertEqual(s["by_scan"], {"clean": 2, "flagged": 1, "none": 4, "review": 1})

    def test_recorded_but_never_saved_and_quarantined(self):
        s = self.d()["sources"]
        self.assertEqual(s["recorded_never_saved"], ["s-rec"])
        self.assertEqual(s["quarantined"], ["s-flag"])

    def test_sources_with_no_file_are_shown_as_unsaved_not_as_a_failure(self):
        self.assertEqual(self.d()["sources"]["unsaved"], ["s-nofile"])

    def test_listed_sources_that_no_entry_cites(self):
        # cited: s-saved (pb-a), s-repl and s-conv (pb-b), s-read (superseded pb-d still counts), s-saved (pb-c, pb-e)
        self.assertEqual(self.d()["sources"]["uncited"], ["s-flag", "s-nofile", "s-rec", "s-unused"])

    def test_a_listed_stem_with_no_catalog_record(self):
        add_index_source(self.proj, "demo", "s-ghost")
        s = self.d()["sources"]
        self.assertIn("s-ghost", s["listed"])
        self.assertEqual(s["no_record"], ["s-ghost"])


class EntryReportTests(StatusCase):
    def test_entries_by_status_and_claim_tag_counts(self):
        e = self.d()["entries"]
        self.assertEqual(e["by_status"], {"draft": 4, "superseded": 1})
        self.assertEqual(e["tags"]["pb-a"], {"V": 1, "A": 1, "U": 0})
        self.assertEqual(e["tags"]["pb-b"], {"V": 0, "A": 0, "U": 1})
        self.assertEqual(e["tags"]["pb-c"], {"V": 1, "A": 0, "U": 1})

    def test_entries_with_no_verified_claim_leave_out_superseded_ones(self):
        self.assertEqual(self.d()["entries"]["no_verified"], ["pb-b", "pb-e"])

    def test_entries_citing_a_replaced_source_that_were_not_updated_since(self):
        self.assertEqual(self.d()["entries"]["reverify"], ["pb-b"])
        add_entry(self.proj, "demo", "pb-f", body=body("Fresh [V]."), sources=["s-repl"], updated="2026-06-01")
        self.assertEqual(self.d()["entries"]["reverify"], ["pb-b"])
        add_entry(self.proj, "demo", "pb-g", body=body("Older [V]."), sources=["s-repl"], updated="2026-05-31")
        self.assertEqual(self.d()["entries"]["reverify"], ["pb-b", "pb-g"])

    def test_stale_entries_follow_the_threshold_and_change_nothing(self):
        before = helpers.snapshot(self.proj)
        self.assertEqual(self.d()["entries"]["stale"], ["pb-b"])
        self.assertEqual(self.d(stale_days=30)["entries"]["stale"], ["pb-b"])
        self.assertEqual(self.d(stale_days=2000)["entries"]["stale"], [])
        # superseded pb-d is 2024 but is never reported as stale
        self.assertNotIn("pb-d", self.d(stale_days=1)["entries"]["stale"])
        self.assertIn("pb-a", self.d(stale_days=10)["entries"]["stale"])
        self.assertEqual(helpers.snapshot(self.proj), before)

    def test_the_threshold_is_exclusive(self):
        age = (TODAY - datetime.date(2025, 1, 1)).days
        self.assertEqual(self.d(stale_days=age)["entries"]["stale"], [])
        self.assertEqual(self.d(stale_days=age - 1)["entries"]["stale"], ["pb-b"])


class ConflictReportTests(StatusCase):
    def test_open_conflicts_with_entry_and_stems(self):
        c = self.d()["conflicts"]
        self.assertEqual([(x["entry"], x["stems"]) for x in c["open"]], [("pb-c", ["s-saved", "s-conv"])])
        self.assertIsInstance(c["open"][0]["line"], int)

    def test_a_note_with_fewer_than_two_stems_is_malformed(self):
        c = self.d()["conflicts"]
        self.assertEqual([x["entry"] for x in c["malformed"]], ["pb-e"])


class QuestionAndLogReportTests(StatusCase):
    def test_open_and_partial_questions(self):
        q = self.d()["questions"]
        self.assertEqual(q["open"], ["q-1"])
        self.assertEqual(q["partial"], ["q-2"])
        self.assertEqual(q["answered"], ["q-3"])

    def test_waves_still_open_or_abandoned(self):
        w = self.d()["waves"]
        self.assertEqual((w["open"], w["abandoned"]), ([2], [3]))

    def test_leads_and_charter(self):
        d = self.d()
        self.assertEqual(d["leads"], 2)
        self.assertEqual(d["charter"], "set")

    def test_a_draft_charter_is_flagged(self):
        text = (self.domain / "README.md").read_text(encoding="utf-8").replace("charter: set", "charter: draft")
        (self.domain / "README.md").write_text(text, encoding="utf-8")
        self.assertEqual(self.d()["charter"], "draft")


class UsageTestReportTests(StatusCase):
    def test_the_latest_usage_test_and_its_result(self):
        u = self.d()["usage_tests"]
        self.assertEqual(u["latest"], {"date": "2026-04-01", "result": "fail", "scenario": "Z"})
        self.assertEqual(u["count"], 4)

    def test_failures_with_no_later_pass_on_the_same_scenario(self):
        self.assertEqual(self.d()["usage_tests"]["unresolved"], 2)  # Y partial and Z fail; X failed then passed

    def test_a_domain_with_no_usage_test(self):
        add_domain(self.proj, "other")
        other = self.report("other")["domains"]["other"]["usage_tests"]
        self.assertEqual((other["latest"], other["count"], other["unresolved"]), (None, 0, 0))


class GapTests(StatusCase):
    def test_every_gap_category_has_its_count(self):
        self.assertEqual(self.d()["gaps"], {"usage-test": 2, "open-questions": 2, "conflicts": 1, "reverify": 1,
                                            "no-verified": 2, "leads": 2, "stale": 1})

    def test_a_gap_result_fixture_is_judged_as_specified(self):
        waves = self.d()["waves"]
        self.assertEqual(waves["judged"], [{"wave": 1, "result": "ok",
                                            "categories": {"open-questions": "fell", "leads": "unchanged: no new leads"}}])
        write_log(self.proj, "demo",
                  "## 2026-04-01 wave 4 opened\n\nGoal: g\nTargets: q-1\nLimit: 5\nGaps: conflicts=1, stale=2\n",
                  "## 2026-04-02 wave 4 closed\n\nAdded: none\nLeft open: q-1\nReviewed: none\n"
                  "Gap result: conflicts=1, stale=unchanged:\n")
        judged = self.d()["waves"]["judged"]
        self.assertEqual([j["wave"] for j in judged], [1, 4])
        self.assertEqual(judged[1]["result"], "problem")
        self.assertIn("conflicts", " ".join(judged[1]["problems"]))


class ReportShapeTests(StatusCase):
    def test_json_output_is_stable_and_sorted(self):
        first = kb_status.render_json(self.report())
        second = kb_status.render_json(self.report())
        self.assertEqual(first, second)
        data = json.loads(first)
        self.assertEqual(data["schema"], 1)
        self.assertEqual(list(data), sorted(data))
        self.assertEqual(first, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def test_the_report_names_no_absolute_path(self):
        self.assertNotIn(str(self.tmp), kb_status.render_json(self.report()))
        self.assertNotIn(str(self.tmp), kb_status.render_text(self.report()))

    def test_the_text_report_covers_each_item(self):
        text = kb_status.render_text(self.report())
        for needle in ("Domain: demo", "charter: set", "s-rec", "s-flag", "quarantined", "unsaved", "pb-b", "pb-c",
                       "q-1", "q-2", "wave 2", "wave 3", "leads: 2", "usage"):
            self.assertIn(needle, text)

    def test_empty_lists_read_as_none_in_the_text_report(self):
        add_domain(self.proj, "other")
        text = kb_status.render_text(self.report("other"))
        for line in ("open conflicts: none", "waves still open: none; abandoned: none", "open questions: q-1, q-2, q-3; partial: none",
                     "entries: none", "stale entries (older than 365 days): none"):
            self.assertIn(line, text)
        self.assertNotRegex(text, r": *\n")
        self.assertNotRegex(text, r": ;")

    def test_the_report_writes_nothing_and_changes_no_entry(self):
        before = helpers.snapshot(self.proj)
        run_tool(kb_status, self.proj)
        run_tool(kb_status, self.proj, "--json")
        run_tool(kb_status, self.proj, "demo", "--stale-days", "5")
        self.assertEqual(helpers.snapshot(self.proj), before)

    def test_all_domains_are_reported_without_an_argument(self):
        add_domain(self.proj, "other")
        domains = self.report(domain=None)["domains"]
        self.assertEqual(sorted(domains), ["demo", "other"])
        self.assertIn("project", self.report(domain=None))

    def test_an_unknown_domain_or_a_bad_option(self):
        self.assertEqual(run_tool(kb_status, self.proj, "nope")[0], 1)
        self.assertEqual(run_tool(kb_status, self.proj, "demo", "--stale-days", "0")[0], 2)
        self.assertEqual(run_tool(kb_status, self.proj, "demo", "--stale-days", "abc")[0], 2)
        self.assertEqual(run_tool(kb_status, self.proj, "..")[0], 1)

    def test_it_runs_as_a_script(self):
        script = helpers.KIT_TOOLS / "kb_status.py"
        done = subprocess.run([sys.executable, "-I", "-B", str(script), "--root", str(self.proj), "--json"],
                              capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)["schema"], 1)


class RobustnessTests(StatusCase):
    def test_unreadable_files_are_reported_not_fatal(self):
        os.unlink(self.domain / "questions.md")
        (self.domain / "log.md").write_text("## not a heading we know\n", encoding="utf-8")
        helpers.write(self.domain / "playbook" / "entries", "pb-broken.md", "no front matter\n")
        report = self.report()
        self.assertTrue(report["problems"])
        self.assertTrue(any("pb-broken" in p for p in report["problems"]))
        self.assertEqual(self.d()["entries"]["by_status"]["draft"], 4)

    def test_symlinks_and_special_files_are_never_followed(self):
        outside = self.tmp / "outside.md"
        outside.write_text("---\nid: pb-out\n---\n")
        os.symlink(outside, self.domain / "playbook" / "entries" / "pb-link.md")
        os.mkfifo(self.domain / "playbook" / "entries" / "pb-pipe.md")
        report = self.report()
        self.assertNotIn("pb-link", json.dumps(report["domains"]["demo"]["entries"]["tags"]))
        self.assertTrue(any("pb-link" in p for p in report["problems"]))

    def test_a_huge_log_or_table_is_read_in_bounded_time(self):
        with open(self.domain / "questions.md", "a", encoding="utf-8") as handle:
            handle.write("".join(f"| q-{n} | Question {n}? | open | | |\n" for n in range(10, 20000)))
        started = __import__("time").monotonic()
        self.report()
        self.assertLess(__import__("time").monotonic() - started, 10)


class HostileTests(StatusCase):
    def test_wrong_typed_values_in_a_record_or_entry_do_not_stop_the_report(self):
        (self.proj / "catalog" / "aa-list.md").write_text(
            "---\nstem: aa-list\nkind: document\ntitle: T\nretrieved: 2026-01-01\nconfirmed: full\ntier: primary\n"
            "state:\n  - x\nscan: none\n---\n", encoding="utf-8")
        (self.proj / "catalog" / "bb-int.md").write_text(
            "---\nstem: bb-int\nkind: document\ntitle: T\nretrieved: 2026-01-01\nconfirmed: full\ntier: 7\n"
            "state: 5\nscan: true\n---\n", encoding="utf-8")
        add_index_source(self.proj, "demo", "aa-list")
        add_index_source(self.proj, "demo", "bb-int")
        helpers.write(self.domain / "playbook" / "entries", "pb-odd.md",
                      "---\nid: pb-odd\ntype: playbook-entry\ntitle: T\nstatus:\n  - a\nsources: [s-saved]\nupdated: 2026-01-01\n---\n"
                      + body("x [V]"))
        report = self.report()
        self.assertIn("aa-list", report["domains"]["demo"]["sources"]["listed"])
        self.assertTrue(any("aa-list" in p and "state" in p for p in report["problems"]), report["problems"])
        self.assertTrue(any("bb-int" in p for p in report["problems"]), report["problems"])
        self.assertTrue(any("pb-odd" in p for p in report["problems"]), report["problems"])
        kb_status.render_text(report)
        kb_status.render_json(report)

    def test_a_symlinked_intermediate_directory_is_not_followed(self):
        outside = self.tmp / "outside"
        (outside / "entries").mkdir(parents=True)
        (outside / "entries" / "pb-leak.md").write_text(
            "---\nid: pb-leak\ntype: playbook-entry\ntitle: T\nstatus: SECRET-OUTSIDE\nsources: []\nupdated: 2026-01-01\n---\n")
        (outside / "sources.md").write_text("| Source | Why |\n|---|---|\n| leaked-stem | x |\n")
        moved = self.tmp / "moved-playbook"
        os.rename(self.domain / "playbook", moved)
        os.symlink(outside, self.domain / "playbook")
        index = self.tmp / "moved-index"
        os.rename(self.domain / "index", index)
        os.makedirs(outside / "index")
        (outside / "index" / "sources.md").write_text("| Source | Why |\n|---|---|\n| leaked-stem | x |\n")
        os.symlink(outside / "index", self.domain / "index")
        report = self.report()
        everything = kb_status.render_json(report) + kb_status.render_text(report)
        self.assertNotIn("SECRET-OUTSIDE", everything)
        self.assertNotIn("leaked-stem", everything)
        self.assertTrue(any("playbook" in p and "symlink" in p for p in report["problems"]), report["problems"])
        self.assertTrue(any("index" in p and "symlink" in p for p in report["problems"]), report["problems"])

    def test_the_text_report_scrubs_source_derived_text(self):
        helpers.write(self.proj / "catalog", "x\x1b[31mRED.md", "not front matter\n")
        with open(self.domain / "questions.md", "a", encoding="utf-8") as handle:
            handle.write("| q-9\x1b[2J\x07 | x | open | | |\n")
        report = self.report()
        text = kb_status.render_text(report)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)
        self.assertIn("RED", text)
        # JSON escapes control characters itself
        self.assertNotIn("\x1b", kb_status.render_json(report))


class CloneTests(StatusCase):
    def test_a_clone_with_no_sources_directory_contents_reports_every_file_as_unsaved(self):
        for path in (self.proj / "sources").glob("*.pdf"):
            path.unlink()
        for path in (self.proj / "sources" / "quarantine").glob("*.pdf"):
            path.unlink()
        s = self.d()["sources"]
        self.assertEqual(s["unsaved"], ["s-conv", "s-flag", "s-nofile", "s-read", "s-repl", "s-saved", "s-unused"])
        self.assertEqual(s["quarantined"], ["s-flag"])  # still flagged in the record, though the file is not here

    def test_the_report_runs_with_no_domain_at_all(self):
        bare = build_project(self.tmp / "bare")
        report = kb_status.build_report(str(bare), None, stale_days=365, today=TODAY)
        self.assertEqual(report["domains"], {})
        self.assertEqual(run_tool(kb_status, bare)[0], 0)


if __name__ == "__main__":
    unittest.main()
