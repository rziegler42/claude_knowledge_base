"""The tools together: a store goes from empty to a checked domain using only the lifecycle tools."""
import re
import unittest
from pathlib import Path

import helpers  # first: it puts the kit's tools on the import path
import add_source
import check_kb
import new_domain
import new_entry
from pdffixtures import Page, build
from projects import build_project
from toolrun import run_tool


def errors(proj, strict=False):
    return [f"{f.path}: {f.message}" for f in check_kb.check(Path(proj), require_sources=strict).errors]


class FlowTests(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.proj = build_project(self.tmp / "store")

    def fill(self, path):
        text = Path(path).read_text(encoding="utf-8")
        Path(path).write_text(re.sub(r"REPLACE_WITH_[A-Z_]+", "Filled in.", text), encoding="utf-8")

    def test_from_an_empty_store_to_a_checked_domain(self):
        self.assertEqual(run_tool(new_domain, self.proj, "ethics", "--title", "Ethics of Play")[0], 0)
        self.assertEqual(errors(self.proj), [])  # a draft domain with no entries is allowed

        pdf = self.tmp / "paper.pdf"
        pdf.write_bytes(build([Page().text(72, 700, 12, "A paper.")]))
        self.assertEqual(run_tool(add_source, self.proj, "paper-one", str(pdf), "--title", "A paper")[0], 0)

        # a person fills in the charter, adds the questions, and sets it
        domain = self.proj / "domains" / "ethics"
        self.fill(domain / "README.md")
        charter = (domain / "README.md").read_text(encoding="utf-8").replace("charter: draft", "charter: set")
        (domain / "README.md").write_text(charter, encoding="utf-8")
        with open(domain / "questions.md", "a", encoding="utf-8") as handle:
            handle.write("".join(f"| q-{n} | Which option for case {n}? | open | | |\n" for n in (1, 2, 3)))
        with open(domain / "index" / "sources.md", "a", encoding="utf-8") as handle:
            handle.write("| paper-one | The core result. |\n")

        self.assertEqual(run_tool(new_entry, self.proj, "ethics", "fair-play", "--title", "Fair play")[0], 0)
        self.assertTrue(any("REPLACE_WITH_" in e for e in errors(self.proj)))
        entry = domain / "playbook" / "entries" / "pb-fair-play.md"
        text = entry.read_text(encoding="utf-8").replace("sources: []", "sources:\n  - paper-one")
        entry.write_text(re.sub(r"REPLACE_WITH_[A-Z_]+", "Do the thing [A].", text), encoding="utf-8")
        self.fill(domain / "playbook" / "README.md")

        self.assertEqual(errors(self.proj, strict=True), [])
        # the answered question can now name the entry
        questions = (domain / "questions.md").read_text(encoding="utf-8")
        (domain / "questions.md").write_text(questions.replace("| q-1 | Which option for case 1? | open | | |",
                                                               "| q-1 | Which option for case 1? | answered | pb-fair-play | |"),
                                             encoding="utf-8")
        self.assertEqual(errors(self.proj, strict=True), [])

    def test_the_tools_never_write_outside_the_store_or_leave_temporary_files(self):
        before_parent = helpers.snapshot(self.tmp)
        run_tool(new_domain, self.proj, "ethics", "--title", "Ethics")
        pdf = self.tmp / "paper.pdf"
        pdf.write_bytes(build())
        run_tool(add_source, self.proj, "paper-one", str(pdf), "--title", "A paper")
        leftovers = [p for p in Path(self.tmp).rglob("*") if p.name.startswith(".kbtmp-")]
        self.assertEqual(leftovers, [])
        outside = {k for k in helpers.snapshot(self.tmp) if not k.startswith("store") and k not in before_parent}
        self.assertEqual(outside, {"paper.pdf"})


if __name__ == "__main__":
    unittest.main()
