"""Repository audit: the starter ships no content and no personal data (installer criterion 9)."""
import re
import unittest

import helpers

SKIP_DIRS = {".git", ".debug", "__pycache__", "graphify-out"}
SKIP_FILES = {"test_repo.py", "test_kit.py"}  # these define the patterns they search for
PERSONAL = re.compile(r"/Users/|/home/[a-z]|rziegler|@yahoo|@gmail|@outlook")
EMAIL = re.compile(r"[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
ALLOWED_EMAIL = re.compile(r"noreply|example\.(?:org|com)|@b\.c$|@users\.noreply")


def tracked_text_files():
    for path in helpers.ROOT.rglob("*"):
        parts = set(path.relative_to(helpers.ROOT).parts)
        if parts & SKIP_DIRS or not path.is_file() or path.name in SKIP_FILES:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


class AuditTests(unittest.TestCase):
    def test_starter_has_no_content_directories_or_marker(self):
        for name in ("domains", "catalog", "sources", "text", "playbook"):
            self.assertFalse((helpers.ROOT / name).exists(), name)
        for name in ("kb.json", ".kb-manifest"):
            self.assertFalse((helpers.ROOT / name).exists(), name)

    def test_no_personal_path_or_address(self):
        problems = []
        for path, text in tracked_text_files():
            rel = path.relative_to(helpers.ROOT)
            for number, line in enumerate(text.split("\n"), start=1):
                if PERSONAL.search(line):
                    problems.append(f"{rel}:{number}: personal path or address")
                for email in EMAIL.findall(line):
                    if not ALLOWED_EMAIL.search(email):
                        problems.append(f"{rel}:{number}: address {email}")
        self.assertEqual(problems, [])

    def test_license_is_not_copied_into_the_kit(self):
        self.assertEqual(list(helpers.KIT.rglob("LICENSE*")), [])


if __name__ == "__main__":
    unittest.main()
