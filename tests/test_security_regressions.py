"""Regression tests for the findings of the adversarial security review (plan Increment F)."""
import contextlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import helpers
import check_kb
import kbparse
from projects import add_catalog, add_domain, add_entry, good_project

sys.path.insert(0, str(helpers.ROOT))
import install  # noqa: E402
from test_install_addto import SAFE_ENV, snapshot, template_project, marker  # noqa: E402

IDENT = ["--git-name", "T", "--git-email", "t@users.noreply.github.com"]


def run(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {**SAFE_ENV, **(env or {})}), mock.patch("sys.stdin", io.StringIO("")), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = install.main(argv)
    return code, out.getvalue() + err.getvalue()


def timed(func, *args):
    start = time.monotonic()
    result = func(*args)
    return result, time.monotonic() - start


class Scratch(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)


class M1GitConfigRunsNoProgram(Scratch):
    def test_starter_state_runs_no_clean_filter(self):
        starter = self.tmp / "starter"
        starter.mkdir()
        sentinel = self.tmp / "filter-ran"
        script = self.tmp / "filter.sh"
        script.write_text(f"#!/bin/sh\ntouch {sentinel}\ncat\n")
        script.chmod(0o755)
        attrs = self.tmp / "attrs"
        attrs.write_text("* filter=x\n")
        hostile = self.tmp / "gitconfig"
        hostile.write_text(f"[core]\n\tattributesFile = {attrs}\n[filter \"x\"]\n\tclean = {script}\n")
        quiet = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

        def git(*args):
            subprocess.run(["git", "-C", str(starter), "-c", "user.name=x", "-c", "user.email=x@users.noreply.github.com", *args],
                           check=True, capture_output=True, env=quiet)

        git("init", "-q")
        (starter / "a.txt").write_text("one\n")
        git("add", "a.txt")
        git("commit", "-q", "-m", "init")
        (starter / "a.txt").write_text("one\n")  # new mtime: git must re-hash the file
        with mock.patch.object(install, "STARTER", starter), \
                mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(hostile), "GIT_CONFIG_NOSYSTEM": "1"}):
            install.starter_state()
        self.assertFalse(sentinel.exists(), "a configured clean filter ran during the starter-state query")


class M2ContainmentByIdentity(Scratch):
    def case_variant(self):
        variant = Path(str(helpers.ROOT.parent / helpers.ROOT.name.swapcase()))
        if str(variant) == str(helpers.ROOT) or not variant.exists():
            self.skipTest("case-sensitive filesystem")
        return variant

    def test_case_variant_of_the_starter_is_refused_when_creating(self):
        variant = self.case_variant()
        code, out = run([str(variant / "newkb"), *IDENT, "--dry-run"])
        self.assertEqual(code, 1, out)

    def test_case_variant_of_the_starter_is_refused_for_add_to(self):
        variant = self.case_variant()
        code, out = run(["--add-to", str(variant / "tests"), "--dry-run"])
        self.assertEqual(code, 1, out)

    def test_a_target_containing_the_starter_is_refused(self):
        code, out = run(["--add-to", str(helpers.ROOT.parent), "--dry-run"])
        self.assertEqual(code, 1, out)
        self.assertIn("starter", out)


class M3QuadraticInputs(Scratch):
    LIMIT = 3.0

    def test_link_pattern_line_is_capped(self):
        proj = good_project(self.tmp / "p")
        entry = proj / "domains/demo/playbook/entries/pb-one.md"
        entry.write_text(entry.read_text() + "\n" + "](" * 40000 + "\n", encoding="utf-8")
        report, seconds = timed(check_kb.check, proj)
        self.assertLess(seconds, self.LIMIT)
        self.assertTrue([f for f in report.errors if "too long" in f.message])

    def test_conflict_note_is_linear(self):
        text = "[U — conflict: a" + " " * 40000 + "x]\n"
        (tags, errors), seconds = timed(kbparse.find_tags, text)
        self.assertLess(seconds, self.LIMIT)

    def test_unclosed_candidates_are_linear(self):
        for text in ("[V — " * 12000, "[V" * 30000):
            (_, errors), seconds = timed(kbparse.find_tags, text)
            self.assertLess(seconds, self.LIMIT)

    def test_a_huge_paragraph_is_refused_not_scanned(self):
        (tags, errors), seconds = timed(kbparse.find_tags, "[V — " * 200000)
        self.assertLess(seconds, self.LIMIT)
        self.assertTrue([e for e in errors if "too long" in e[1]])

    def test_error_floods_are_capped(self):
        proj = good_project(self.tmp / "p")
        entry = proj / "domains/demo/playbook/entries/pb-one.md"
        entry.write_text(entry.read_text() + "\n" + "[Q] " * 5000 + "\n", encoding="utf-8")
        report = check_kb.check(proj)
        self.assertLess(len(report.errors), 200)


class M4NoTracebacks(Scratch):
    def setUp(self):
        super().setUp()
        self.proj = good_project(self.tmp / "p")

    def test_nul_in_marker_paths(self):
        data = json.loads((self.proj / "kb.json").read_text())
        data["router"] = "a\x00b"
        (self.proj / "kb.json").write_text(json.dumps(data))
        report = check_kb.check(self.proj)
        self.assertTrue(report.errors)

    def test_deeply_nested_json(self):
        (self.proj / "kb.json").write_text("[" * 2000000)
        self.assertTrue(check_kb.check(self.proj).errors)
        (self.proj / "kb.json").write_text((helpers.KIT / "files/kb.json").read_text())
        (self.proj / ".kb-manifest").write_text("[" * 900000)
        self.assertTrue(check_kb.check(self.proj).errors)

    def test_huge_integer_in_front_matter(self):
        path = self.proj / "catalog" / "src-one.md"
        path.write_text(path.read_text().replace("retrieved: 2026-01-01", "retrieved: " + "9" * 5000))
        report = check_kb.check(self.proj)
        self.assertTrue([f for f in report.errors if "retrieved" in f.message])

    def test_int_parsing_is_bounded(self):
        data, _ = kbparse.parse_front_matter("---\nv: " + "9" * 5000 + "\n---\n")
        self.assertIsInstance(data["v"], str)

    def test_main_never_prints_a_traceback(self):
        (self.proj / "kb.json").write_text("[" * 2000000)
        script = helpers.KIT_TOOLS / "check_kb.py"
        result = subprocess.run([sys.executable, "-I", "-B", str(script), "--root", str(self.proj)],
                                capture_output=True, text=True)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.returncode, 1)


class M5SymlinkedDirectories(Scratch):
    def test_symlinked_catalog_is_refused_and_not_listed(self):
        proj = good_project(self.tmp / "p")
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "leakname.md").write_text("---\nstem leak\n---\n")
        for child in (proj / "catalog").iterdir():
            child.unlink()
        (proj / "catalog").rmdir()
        os.symlink(outside, proj / "catalog")
        report = check_kb.check(proj)
        text = " ".join(f"{f.path} {f.message}" for f in report.errors + report.warnings)
        self.assertIn("symlink", text)
        self.assertNotIn("leakname", text)

    def test_symlinked_entries_directory(self):
        proj = good_project(self.tmp / "p")
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "pb-leak.md").write_text("---\nbad line\n---\n")
        entries = proj / "domains/demo/playbook/entries"
        for child in entries.iterdir():
            child.unlink()
        entries.rmdir()
        os.symlink(outside, entries)
        report = check_kb.check(proj)
        text = " ".join(f"{f.path} {f.message}" for f in report.errors)
        self.assertNotIn("pb-leak", text)
        self.assertIn("symlink", text)

    def test_marker_paths_are_not_probed_outside_the_project(self):
        proj = good_project(self.tmp / "p")
        probe = self.tmp / "probe.md"
        probe.write_text("x")
        data = json.loads((proj / "kb.json").read_text())
        data["spec"] = str(probe)
        (proj / "kb.json").write_text(json.dumps(data))
        with mock.patch.object(os, "lstat", wraps=os.lstat) as spy:
            check_kb.check(proj)
        self.assertNotIn(str(probe), [str(c.args[0]) for c in spy.call_args_list])


class L1FullMatch(Scratch):
    def test_trailing_newline_is_not_a_stem_or_name(self):
        self.assertFalse(kbparse.valid_stem("a\n"))
        self.assertFalse(check_kb.DOMAIN_RE.match("a\n"))
        self.assertFalse(check_kb.ENTRY_ID_RE.match("pb-a\n"))
        self.assertFalse(check_kb.SHA_RE.match("a" * 64 + "\n"))
        code, out = run([str(self.tmp / "p"), *IDENT, "--name=foo\n"])
        self.assertEqual(code, 1, out)
        self.assertFalse((self.tmp / "p").exists())


class L2Escaping(Scratch):
    def test_install_messages_escape_control_characters(self):
        proj = self.tmp / "proj"
        template_project(proj)
        hostile = proj / "domains" / "\x1b[31mred"
        hostile.mkdir(parents=True)
        (hostile / "f.md").write_text("x")
        code, out = run(["--add-to", str(proj)])
        self.assertEqual(code, 1)
        self.assertNotIn("\x1b", out)

    def test_checker_output_escapes_control_characters(self):
        finding = check_kb.Finding("domains/\x1b[31mred/README.md", 3, "bad\x07 thing")
        line = check_kb.format_finding("ERROR", finding)
        self.assertNotIn("\x1b", line)
        self.assertNotIn("\x07", line)


class L3IdentityFlags(Scratch):
    def test_identity_flags_are_rejected_with_add_to(self):
        proj = self.tmp / "proj"
        template_project(proj)
        for extra in (["--git-email", "a@b.c"], ["--git-name", "n"], ["--use-global-git-identity"]):
            with self.subTest(extra=extra):
                before = snapshot(proj)
                code, out = run(["--add-to", str(proj), *extra])
                self.assertEqual(code, 1, out)
                self.assertEqual(snapshot(proj), before)


class L4DeepTrees(Scratch):
    def test_deep_content_tree_is_refused_cleanly(self):
        proj = self.tmp / "proj"
        template_project(proj)
        path = proj / "text"
        for _ in range(100):
            path = path / "d"
        path.mkdir(parents=True)
        before = snapshot(proj)
        code, out = run(["--add-to", str(proj)])
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(snapshot(proj), before)


class L5BlockParserFidelity(Scratch):
    def add(self, name, text):
        proj = self.tmp / name
        template_project(proj)
        (proj / "README.md").write_bytes(text.encode() if isinstance(text, str) else text)
        before = snapshot(proj)
        code, out = run(["--add-to", str(proj)])
        return proj, before, code, out

    def test_tilde_fence_inside_a_backtick_fence_does_not_close_it(self):
        m = marker("readme-docs", "README.md")
        proj, before, code, out = self.add("a", f"# T\n\n```\n~~~\n{m}\n```\n")
        self.assertEqual(code, 1, out)
        self.assertEqual(snapshot(proj), before)

    def test_unclosed_fence_is_refused(self):
        proj, before, code, out = self.add("b", "# T\n\n```\ncode\n")
        self.assertEqual(code, 1, out)
        self.assertEqual(snapshot(proj), before)

    def test_indented_code_marker_is_not_a_marker(self):
        m = marker("readme-docs", "README.md")
        proj, before, code, out = self.add("c", f"# T\n\n    {m}\n")
        self.assertEqual(code, 0, out)
        text = (proj / "README.md").read_text()
        self.assertTrue(text.startswith(f"# T\n\n    {m}\n"))  # the indented line was left alone
        self.assertIn("BEGIN module:knowledge-base slot:readme-docs", text.split(f"    {m}\n", 1)[1])

    def test_crlf_host_keeps_crlf(self):
        m = marker("readme-docs", "README.md")
        proj, before, code, out = self.add("d", f"# T\r\n\r\n{m}\r\n")
        self.assertEqual(code, 0, out)
        data = (proj / "README.md").read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        self.assertIn(b"BEGIN module:knowledge-base slot:readme-docs -->\r\n", data)


class L6MigrationTypes(Scratch):
    def test_float_chain_numbers_are_refused(self):
        kit = self.tmp / "kit"
        import shutil
        shutil.copytree(helpers.KIT, kit, ignore=shutil.ignore_patterns("__pycache__"))
        (kit / "migrations.json").write_text(json.dumps({"steps": [{"from": 1.0, "to": 2, "ops": []}]}))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, SAFE_ENV), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install.main([str(self.tmp / "t"), *IDENT], kit_dir=kit)
        self.assertEqual(code, 1)
        self.assertFalse((self.tmp / "t").exists())


if __name__ == "__main__":
    unittest.main()


class SecondReviewRegressions(Scratch):
    def test_nested_tag_notes_are_not_stored(self):
        text = "[V — " * 12000 + "]"
        (tags, errors), seconds = timed(kbparse.find_tags, text)
        self.assertLess(seconds, 3.0)
        self.assertLess(sum(len(t.note or "") for t in tags), 100000)
        self.assertTrue([e for e in errors if "too long" in e[1]])

    def test_oversize_text_files_are_not_scanned(self):
        proj = good_project(self.tmp / "p")
        entry = proj / "domains/demo/playbook/entries/pb-one.md"
        entry.write_text(entry.read_text() + "\n" + ("filler line\n" * 100000), encoding="utf-8")
        report, seconds = timed(check_kb.check, proj)
        self.assertLess(seconds, 3.0)
        self.assertTrue([f for f in report.errors if "too large" in f.message])

    def test_bad_chars_is_fast_on_large_input(self):
        _, seconds = timed(kbparse.bad_chars, ("a" * 99 + "\n") * 50000)
        self.assertLess(seconds, 1.0)

    def test_git_component_reached_through_a_symlink_is_refused(self):
        victim = self.tmp / "victim" / ".git"
        victim.mkdir(parents=True)
        link = self.tmp / "lnk"
        os.symlink(victim, link)
        code, out = run([str(link / "proj"), *IDENT])
        self.assertEqual(code, 1, out)
        self.assertEqual(list(victim.iterdir()), [])

    def test_overlong_path_component_is_refused_cleanly(self):
        code, out = run(["--add-to", str(self.tmp / ("x" * 300))])
        self.assertEqual(code, 1, out)

    def test_existing_host_keeps_its_mode(self):
        proj = self.tmp / "proj"
        template_project(proj)
        for rel in ("AGENTS.md", ".gitignore"):
            os.chmod(proj / rel, 0o600)
        code, out = run(["--add-to", str(proj)])
        self.assertEqual(code, 0, out)
        for rel in ("AGENTS.md", ".gitignore"):
            self.assertEqual(oct(os.stat(proj / rel).st_mode & 0o777), "0o600", rel)

    def test_reviewed_lookup_is_by_token(self):
        proj = good_project(self.tmp / "p")
        entry = proj / "domains/demo/playbook/entries/pb-one.md"
        entry.write_text(entry.read_text().replace("status: draft", "status: reviewed"))
        log = proj / "domains/demo/log.md"
        log.write_text(log.read_text() + "\n## 2026-01-02 wave 1 closed\n\nReviewed: xpb-one, pb-one-extra\n")
        self.assertTrue([f for f in check_kb.check(proj).errors if "Reviewed:" in f.message])
        log.write_text(log.read_text() + "Reviewed: pb-one (A. Person)\n")
        self.assertEqual([f for f in check_kb.check(proj).errors if "Reviewed:" in f.message], [])
