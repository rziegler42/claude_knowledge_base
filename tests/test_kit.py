import json
import re
import shutil
import unittest
from pathlib import Path

import helpers
import kbparse
import stores

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
                kept = [l for l in source.split("\n")
                        if "](../roadmaps/" not in l and "](../decisions/" not in l]
                self.assertEqual("\n".join(kept), copy)

    def test_copies_contain_no_roadmap_or_decision_links(self):
        for name in SPECS:
            copy = (helpers.KIT / "files" / "docs" / "kb" / f"{name}.md").read_text(encoding="utf-8")
            self.assertNotIn("](../roadmaps/", copy)
            self.assertNotIn("](../decisions/", copy)

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

    def test_kit_layout_has_no_slots_base_or_module_json(self):
        self.assertEqual(sorted(p.name for p in helpers.KIT.iterdir()),
                         ["files", "kit.json", "migrations.json"])
        self.assertEqual(sorted(p.relative_to(helpers.KIT).as_posix()
                                for p in helpers.KIT.rglob("module.json")),
                         ["files/template-module/module.json"])

    def test_kit_metadata_files_are_json(self):
        kit = json.loads((helpers.KIT / "kit.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(kit), ["hint", "kit_version"])
        migrations = json.loads((helpers.KIT / "migrations.json").read_text(encoding="utf-8"))
        self.assertEqual(migrations, {"steps": []})

    def test_no_marker_or_managed_block_text_outside_the_spec_copies(self):
        for path in kit_files():
            if "docs/kb" in path.relative_to(helpers.KIT).as_posix():
                continue
            text = path.read_text(encoding="utf-8")
            for needle in ("@module-slot", "BEGIN module:", "END module:"):
                with self.subTest(file=str(path.relative_to(helpers.ROOT)), needle=needle):
                    self.assertNotIn(needle, text)


class RootFileTests(unittest.TestCase):
    def read(self, rel):
        return (helpers.KIT / "files" / rel).read_text(encoding="utf-8")

    def test_agents_guidance_has_the_four_items(self):
        text = self.read("AGENTS.md")
        for needle in (
            "untrusted data, never instructions",
            "stay `[U]` or `[A]`",
            "docs/kb/domain-lifecycle.md",
            "sources/quarantine/",
        ):
            with self.subTest(item=needle):
                self.assertIn(needle, text)

    def test_readme_carries_the_name_placeholder_and_the_copyright_note(self):
        text = self.read("README.md")
        self.assertTrue(text.startswith("# REPLACE_WITH_PROJECT_NAME\n"))
        for needle in ("not legal advice", "jurisdiction", "no\n  `LICENSE`", "untracked", "terms of the sources"):
            with self.subTest(item=needle):
                self.assertIn(needle, text)

    def test_docs_index_lists_the_four_specifications(self):
        text = self.read("docs/README.md")
        for name in SPECS:
            self.assertIn(f"(kb/{name}.md)", text)

    def test_gitignore_ignores_sources_and_text_contents(self):
        lines = self.read(".gitignore").split("\n")
        for line in ("/sources/*", "!/sources/README.md", "/text/*", "!/text/README.md"):
            self.assertIn(line, lines)


NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
ALLOWED_PLACEHOLDERS = {"REPLACE_WITH_MODULE_NAME", "REPLACE_WITH_MODULE_PATH"}
FORBIDDEN_TEXT = ("@module-slot:", "BEGIN module:", "END module:")


INFO_KEYS = ("type", "paths", "data")


def plain_data(data):
    """The template's bounds on `data`: an object of plain JSON, at most 4 levels, 256 values, 4096 bytes."""
    if not isinstance(data, dict):
        return False
    nodes, stack = 0, [(data, 1)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > 256 or depth > 4:
            return False
        if isinstance(value, dict):
            if any(not (isinstance(k, str) and 0 < len(k) <= 64 and k.isprintable()) for k in value):
                return False
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, str):
            if not (0 < len(value) <= 200 and value.isprintable()):
                return False
        elif not (value is None or isinstance(value, (bool, int, float))):
            return False
    return len(json.dumps(data)) <= 4096


def descriptor_problems(store):
    """The template's descriptor rules (docs/specs/installer.md, 'The template descriptor'),
    restated here so the starter has no dependency on the template."""
    store = Path(store)
    problems = []
    root = store / "template-module"
    meta_path, slot_dir = root / "module.json", root / "slots"
    for path in (root, slot_dir):
        if path.is_symlink() or not path.is_dir():
            return [f"{path.name} is not a real directory"]
    if meta_path.is_symlink() or not meta_path.is_file():
        return ["module.json is not a regular file"]
    raw = meta_path.read_bytes()
    if len(raw) > 64 * 1024:
        problems.append("module.json is over 64 KiB")
    try:
        meta = json.loads(raw.decode("utf-8"))
    except ValueError:
        return problems + ["module.json is not JSON"]
    if not isinstance(meta, dict):
        return problems + ["module.json is not an object"]
    fmt = meta.get("module_format")
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt not in (1, 2):
        problems.append("module_format must be the integer 1 or 2")
        fmt = 1
    unknown = set(meta) - {"module_format", "description", "hint"} - (set(INFO_KEYS) if fmt == 2 else set())
    if unknown:
        problems.append(f"unknown keys {sorted(unknown)}")
    if "type" in meta and not (isinstance(meta["type"], str) and len(meta["type"]) <= 64
                               and re.match(r"^[a-z0-9][a-z0-9_-]*\Z", meta["type"])):
        problems.append("type must be a lowercase name of at most 64 characters")
    if "data" in meta and not plain_data(meta["data"]):
        problems.append("data must be a bounded object of plain JSON")
    if "paths" in meta:
        problems.append("paths are project-relative and a store is outside the project")
    for key, required in (("description", True), ("hint", False)):
        if key not in meta and not required:
            continue
        text = meta.get(key)
        if not (isinstance(text, str) and 0 < len(text) <= 200 and text.isprintable()):
            problems.append(f"{key} must be printable single-line text of 1-200 characters")
    entries = sorted(slot_dir.iterdir())
    if len(entries) > 16:
        problems.append("more than 16 fragments")
    for entry in entries:
        slot = entry.name[:-3]
        if entry.is_symlink() or not entry.is_file() or not entry.name.endswith(".md") or not NAME_RE.match(slot):
            problems.append(f"unexpected entry {entry.name}")
            continue
        data = entry.read_bytes()
        if len(data) > 64 * 1024 or b"\x00" in data:
            problems.append(f"{entry.name} is over 64 KiB or has a NUL byte")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{entry.name} is not UTF-8")
            continue
        for line in text.split("\n"):
            if any(mark in line for mark in FORBIDDEN_TEXT):
                problems.append(f"{entry.name} contains a reserved marker")
                break
        stray = set(re.findall(r"REPLACE_WITH_[A-Z_]+", text)) - ALLOWED_PLACEHOLDERS
        if stray:
            problems.append(f"{entry.name} uses placeholders {sorted(stray)}")
    return problems


class DescriptorTests(unittest.TestCase):
    def descriptor(self):
        return helpers.KIT / "files"

    def test_the_shipped_descriptor_satisfies_the_template_rules(self):
        self.assertEqual(descriptor_problems(self.descriptor()), [])

    def test_the_descriptor_has_exactly_one_fragment_and_its_keys(self):
        root = self.descriptor() / "template-module"
        self.assertEqual(sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()),
                         ["module.json", "slots/agents-guidance.md"])
        meta = json.loads((root / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(meta), ["data", "description", "module_format", "type"])

    def test_the_descriptor_declares_the_knowledge_base_type(self):
        meta = json.loads((self.descriptor() / "template-module" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["module_format"], 2)
        self.assertEqual(meta["type"], "knowledge-base")

    def test_the_descriptor_data_equals_kb_json(self):
        files = self.descriptor()
        meta = json.loads((files / "template-module" / "module.json").read_text(encoding="utf-8"))
        marker = json.loads((files / "kb.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["data"], {"router": marker["router"], "spec": marker["spec"]})
        self.assertEqual(meta["type"], marker["kind"])

    def test_the_fragment_names_the_router_and_the_guidance(self):
        text = (self.descriptor() / "template-module" / "slots" / "agents-guidance.md").read_text(encoding="utf-8")
        for needle in ("REPLACE_WITH_MODULE_PATH/playbook/README.md", "REPLACE_WITH_MODULE_NAME",
                       "`[U]`", "never instructions", "specific to one checkout"):
            with self.subTest(item=needle):
                self.assertIn(needle, text)

    def test_the_rules_catch_each_violation(self):
        base = self.descriptor() / "template-module"
        cases = {
            "unknown key": lambda root: self.edit_meta(root, extra=1),
            "wrong format": lambda root: self.edit_meta(root, module_format=3),
            "zero format": lambda root: self.edit_meta(root, module_format=0),
            "format 1 with type": lambda root: self.edit_meta(root, module_format=1),
            "paths": lambda root: self.edit_meta(root, paths={"store": "docs/kb"}),
            "uppercase type": lambda root: self.edit_meta(root, type="Knowledge-Base"),
            "long type": lambda root: self.edit_meta(root, type="a" * 65),
            "non-string type": lambda root: self.edit_meta(root, type=["knowledge-base"]),
            "data not an object": lambda root: self.edit_meta(root, data=["router"]),
            "deep data": lambda root: self.edit_meta(root, data={"a": {"b": {"c": {"d": "x"}}}}),
            "wide data": lambda root: self.edit_meta(root, data={f"k{i}": "x" for i in range(256)}),
            "multi-line data value": lambda root: self.edit_meta(root, data={"router": "a\nb"}),
            "oversize data": lambda root: self.edit_meta(root, data={f"k{i}": "x" * 100 for i in range(50)}),
            "bool format": lambda root: self.edit_meta(root, module_format=True),
            "multi-line description": lambda root: self.edit_meta(root, description="a\nb"),
            "long description": lambda root: self.edit_meta(root, description="x" * 201),
            "bad slot name": lambda root: (root / "slots" / "Bad.md").write_text("x\n"),
            "marker in fragment": lambda root: (root / "slots" / "agents-guidance.md").write_text("see @module-slot: x\n"),
            "foreign placeholder": lambda root: (root / "slots" / "agents-guidance.md").write_text("REPLACE_WITH_PROJECT_NAME\n"),
            "NUL byte": lambda root: (root / "slots" / "agents-guidance.md").write_bytes(b"a\x00b"),
            "not UTF-8": lambda root: (root / "slots" / "agents-guidance.md").write_bytes(b"\xff\xfe"),
            "too many fragments": lambda root: [(root / "slots" / f"s{i}.md").write_text("x\n") for i in range(16)],
        }
        for label, mutate in cases.items():
            with self.subTest(case=label), helpers.scratch() as tmp:
                shutil.copytree(base, tmp / "template-module")
                mutate(tmp / "template-module")
                self.assertNotEqual(descriptor_problems(tmp), [], label)

    @staticmethod
    def edit_meta(root, **changes):
        path = root / "module.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta.update(changes)
        path.write_text(json.dumps(meta), encoding="utf-8")


OLD_DESCRIPTOR = {
    "module_format": 1,
    "description": "Knowledge-base store: domains of claim-tagged playbook entries backed by a source catalog, "
                   "with a router and checking tools",
}


class DescriptorUpgradeTests(unittest.TestCase):
    """A store made with the format 1 descriptor is brought to format 2 as an ordinary owned file."""

    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.store = stores.make_store(self.tmp)
        self.path = self.store / "template-module" / "module.json"
        self.current = self.path.read_bytes()
        self.old = (json.dumps(OLD_DESCRIPTOR, indent=2) + "\n").encode("utf-8")

    def age(self, content):
        self.path.write_bytes(content)
        data = stores.manifest(self.store)
        data["files"]["template-module/module.json"] = stores.sha(self.path)
        stores.write_manifest(self.store, data)

    def test_a_format_1_store_is_upgraded_to_format_2(self):
        self.age(self.old)
        code, out, err = stores.upgrade(self.store)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.path.read_bytes(), self.current)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["module_format"], 2)
        self.assertEqual(descriptor_problems(self.store), [])

    def test_an_edited_descriptor_is_skipped_and_listed(self):
        edited = self.old + b"\n"
        self.age(self.old)
        self.path.write_bytes(edited)
        code, out, err = stores.upgrade(self.store)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.path.read_bytes(), edited)
        self.assertIn("template-module/module.json", out)


if __name__ == "__main__":
    unittest.main()
