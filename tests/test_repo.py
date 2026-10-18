"""Repository audit: the starter ships no content and no personal data (installer criterion 9)."""
import re
import unittest
from pathlib import Path

import helpers

SKIP_DIRS = {".git", ".debug", "__pycache__", "graphify-out"}
SKIP_FILES = {"test_repo.py", "test_kit.py"}  # these define the patterns they search for
PERSONAL = re.compile(r"/Users/|/home/[a-z]|rziegler|@yahoo|@gmail|@outlook")
EMAIL = re.compile(r"[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
ALLOWED_EMAIL = re.compile(r"noreply|example\.(?:org|com)|@b\.c$|@users\.noreply")
# The one place the owner's account name may appear: the copyright line of LICENSE, nowhere else.
LICENSE_HOLDER_LINE = "Copyright (c) 2026 rziegler42"
FRONT_MATTER = ("README.md", "LICENSE", "CONTRIBUTING.md", "docs/README.md", "docs/development.md")
SLOT_COMMENT = re.compile(r"<!-- @module-slot: [a-z-]+ -->")


def tracked_text_files():
    for path in helpers.ROOT.rglob("*"):
        parts = set(path.relative_to(helpers.ROOT).parts)
        if parts & SKIP_DIRS or not path.is_file() or path.name in SKIP_FILES:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def personal_problems(rel, text):
    """Problems found in one file. LICENSE may carry the exact copyright line; no other line anywhere
    may carry a personal path, the account name, or a personal address."""
    problems = []
    for number, line in enumerate(text.split("\n"), start=1):
        if str(rel) == "LICENSE" and line == LICENSE_HOLDER_LINE:
            continue
        if PERSONAL.search(line):
            problems.append(f"{rel}:{number}: personal path or address")
        for email in EMAIL.findall(line):
            if not ALLOWED_EMAIL.search(email):
                problems.append(f"{rel}:{number}: address {email}")
    return problems


class AuditTests(unittest.TestCase):
    def test_starter_has_no_content_directories_or_marker(self):
        for name in ("domains", "catalog", "sources", "text", "playbook"):
            self.assertFalse((helpers.ROOT / name).exists(), name)
        for name in ("kb.json", ".kb-manifest"):
            self.assertFalse((helpers.ROOT / name).exists(), name)

    def test_no_personal_path_or_address(self):
        problems = []
        for path, text in tracked_text_files():
            problems += personal_problems(path.relative_to(helpers.ROOT), text)
        self.assertEqual(problems, [])

    def test_the_account_name_is_allowed_on_the_license_line_only(self):
        self.assertEqual(personal_problems(Path("LICENSE"), LICENSE_HOLDER_LINE + "\n"), [])
        self.assertTrue(personal_problems(Path("README.md"), LICENSE_HOLDER_LINE + "\n"))
        self.assertTrue(personal_problems(Path("docs/LICENSE"), LICENSE_HOLDER_LINE + "\n"))
        self.assertTrue(personal_problems(Path("LICENSE"), LICENSE_HOLDER_LINE + " and more\n"))
        self.assertTrue(personal_problems(Path("LICENSE"), "see github.com/rziegler42\n"))
        self.assertTrue(personal_problems(Path("LICENSE"), "Copyright (c) 2027 rziegler42\n"))
        self.assertTrue(personal_problems(Path("LICENSE"), "/Users/someone/x\n"))

    def test_license_is_not_copied_into_the_kit(self):
        self.assertEqual(list(helpers.KIT.rglob("LICENSE*")), [])


def read(rel):
    return (helpers.ROOT / rel).read_text(encoding="utf-8")


def relative_links(text):
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if not re.match(r"[a-z]+:|#", target):
            yield target.split("#")[0]


class PublicFilesTests(unittest.TestCase):
    def test_license_is_mit_with_the_approved_holder(self):
        text = read("LICENSE")
        self.assertTrue(text.startswith("MIT License\n"))
        self.assertIn("\n" + LICENSE_HOLDER_LINE + "\n", text)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND', text)
        self.assertEqual(list(helpers.KIT.rglob("LICENSE*")), [])

    def test_front_matter_files_have_no_placeholder_or_template_comment(self):
        for rel in FRONT_MATTER:
            text = read(rel)
            with self.subTest(file=rel):
                self.assertNotIn("REPLACE_WITH", text)
                self.assertNotIn("Template note", text)
                self.assertEqual(re.findall(r"<!--.*?-->", SLOT_COMMENT.sub("", text), re.S), [])

    def test_readme_links_to_the_license_and_its_links_resolve(self):
        readme = read("README.md")
        self.assertIn("(LICENSE)", readme)
        for rel in ("README.md", "CONTRIBUTING.md"):
            for target in relative_links(read(rel)):
                with self.subTest(file=rel, link=target):
                    self.assertTrue((helpers.ROOT / target).exists(), target)

    def test_readme_names_only_real_tools_and_installer_options(self):
        readme = read("README.md")
        for name in set(re.findall(r"tools/([a-z_]+\.py)", readme)):
            self.assertTrue((helpers.KIT / "files" / "tools" / name).is_file(), name)
        installer = read("install.py")
        # only command lines that run this repository's installer (program path exactly install.py)
        for line in readme.split("\n"):
            if re.match(r"\s*(?:python3 (?:-I )?)?(?:\./)?install\.py(?:\s|$)", line):
                for option in re.findall(r"(?<!\w)(--[a-z][a-z-]*)", line):
                    self.assertIn(f'"{option}"', installer, line)
        self.assertIn("<template>/install.py --register", readme)
        self.assertIn(installer_registration_hint(), readme)

    def test_contributing_names_the_required_checks(self):
        text = read("CONTRIBUTING.md")
        self.assertIn("python3 -I -B -m unittest discover -s tests", text)
        self.assertIn("git diff --check", text)
        self.assertIn("docs/development.md", text)


def installer_registration_hint():
    match = re.search(r'REGISTER_HINT = "([^"]+)"', read("install.py"))
    return match.group(1).split(" run ")[0] if match else "to register with the project template"


if __name__ == "__main__":
    unittest.main()
