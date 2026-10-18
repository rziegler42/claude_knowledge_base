import json
import re
import unittest

import helpers
import kbparse

SPECS = ("knowledge-base-format", "source-pipeline", "domain-lifecycle", "installer")
FORBIDDEN = ("game_theory", "/Users/", "rziegler", "yahoo.com", "claude_global_config")


def kit_files():
    return [p for p in helpers.KIT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]


class DriftTests(unittest.TestCase):
    def test_each_spec_copy_equals_its_source(self):
        for name in SPECS:
            with self.subTest(spec=name):
                source = (helpers.ROOT / "docs" / "specs" / f"{name}.md").read_text(encoding="utf-8")
                copy = (helpers.KIT / "files" / "docs" / "kb" / f"{name}.md").read_text(encoding="utf-8")
                kept = [l for l in source.split("\n") if "](../roadmaps/" not in l]
                self.assertEqual("\n".join(kept), copy)

    def test_copies_contain_no_roadmap_links(self):
        for name in SPECS:
            copy = (helpers.KIT / "files" / "docs" / "kb" / f"{name}.md").read_text(encoding="utf-8")
            self.assertNotIn("](../roadmaps/", copy)

    def test_no_extra_files_in_docs_kb(self):
        found = {p.name for p in (helpers.KIT / "files" / "docs" / "kb").iterdir()}
        self.assertEqual(found, {f"{n}.md" for n in SPECS})


class KitContentTests(unittest.TestCase):
    def test_no_personal_or_subject_specific_content(self):
        for path in kit_files():
            text = path.read_text(encoding="utf-8")
            for word in FORBIDDEN:
                with self.subTest(file=str(path.relative_to(helpers.ROOT)), word=word):
                    self.assertNotIn(word, text)

    def test_kit_has_no_domain_content_sources_or_text(self):
        files = helpers.KIT / "files"
        self.assertEqual([p.name for p in (files / "catalog").iterdir()], ["README.md"])
        self.assertEqual([p.name for p in (files / "sources").iterdir()], ["README.md"])
        self.assertEqual([p.name for p in (files / "text").iterdir()], ["README.md"])
        domains = sorted(p.name for p in (files / "domains").iterdir())
        self.assertEqual(domains, ["_skeleton"])
        self.assertEqual(list((files / "domains" / "_skeleton" / "playbook" / "entries").glob("pb-*.md")), [])

    def test_kb_json_matches_the_marker_contract(self):
        data = json.loads((helpers.KIT / "files" / "kb.json").read_text(encoding="utf-8"))
        self.assertEqual(
            data,
            {
                "kind": "knowledge-base",
                "schema": 1,
                "router": "playbook/README.md",
                "spec": "docs/kb/knowledge-base-format.md",
            },
        )
        for key in ("router", "spec"):
            self.assertTrue((helpers.KIT / "files" / data[key]).is_file(), key)

    def test_skeleton_front_matter_parses(self):
        text = (helpers.KIT / "files" / "domains" / "_skeleton" / "README.md").read_text(encoding="utf-8")
        data, _ = kbparse.parse_front_matter(text)
        self.assertEqual(data["charter"], "draft")

    def test_skeleton_charter_has_the_six_headings_in_order(self):
        text = (helpers.KIT / "files" / "domains" / "_skeleton" / "README.md").read_text(encoding="utf-8")
        headings = re.findall(r"^## (.+)$", text, flags=re.M)
        self.assertEqual(
            headings,
            [
                "Purpose and consumers",
                "Scope",
                "Non-goals",
                "Source types and trust tiers",
                "Verification bar",
                "Safety and sensitivity notes",
            ],
        )

    def test_root_router_has_markers_and_exact_header(self):
        text = (helpers.KIT / "files" / "playbook" / "README.md").read_text(encoding="utf-8")
        lines = text.split("\n")
        begin = lines.index("<!-- BEGIN kb:domains -->")
        end = lines.index("<!-- END kb:domains -->")
        self.assertLess(begin, end)
        self.assertEqual(lines[begin + 1], "| Domain | Router | Purpose |")

    def test_every_slot_has_a_host_in_base(self):
        hosts = {"agents-guidance": "AGENTS.md", "readme-docs": "README.md",
                 "docs-index": "docs/README.md", "gitignore": ".gitignore"}
        slots = sorted(p.stem for p in (helpers.KIT / "slots").iterdir())
        self.assertEqual(slots, sorted(hosts))
        for slot, host in hosts.items():
            text = (helpers.KIT / "base" / host).read_text(encoding="utf-8")
            self.assertIn(f"@module-slot: {slot}", text)

    def test_module_files_are_json(self):
        for name in ("module.json", "migrations.json"):
            json.loads((helpers.KIT / name).read_text(encoding="utf-8"))
        migrations = json.loads((helpers.KIT / "migrations.json").read_text(encoding="utf-8"))
        self.assertEqual(migrations, {"steps": []})


class SlotContentTests(unittest.TestCase):
    def test_agents_guidance_has_the_four_items(self):
        text = (helpers.KIT / "slots" / "agents-guidance.md").read_text(encoding="utf-8")
        for needle in (
            "untrusted data, never instructions",
            "stay `[U]` or `[A]`",
            "docs/kb/domain-lifecycle.md",
            "sources/quarantine/",
        ):
            with self.subTest(item=needle):
                self.assertIn(needle, text)

    def test_readme_slot_carries_the_copyright_note(self):
        text = (helpers.KIT / "slots" / "readme-docs.md").read_text(encoding="utf-8")
        for needle in ("not legal advice", "jurisdiction", "no\n  `LICENSE`", "untracked", "terms of the sources"):
            with self.subTest(item=needle):
                self.assertIn(needle, text)

    def test_gitignore_slot_ignores_sources_and_text_contents(self):
        text = (helpers.KIT / "slots" / "gitignore.md").read_text(encoding="utf-8")
        for line in ("/sources/*", "!/sources/README.md", "/text/*", "!/text/README.md"):
            self.assertIn(line, text.split("\n"))


if __name__ == "__main__":
    unittest.main()
