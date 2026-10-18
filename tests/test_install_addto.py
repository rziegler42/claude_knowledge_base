import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import helpers

sys.path.insert(0, str(helpers.ROOT))
import install  # noqa: E402

SAFE_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
SLOTS = {"AGENTS.md": "agents-guidance", "README.md": "readme-docs",
         "docs/README.md": "docs-index", ".gitignore": "gitignore"}


def run_add(*argv, kit=None):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, SAFE_ENV), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = install.main(["--add-to", *map(str, argv)], kit_dir=kit)
    return code, out.getvalue(), err.getvalue()


def snapshot(root):
    state = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root)
            if os.path.islink(path):
                state[rel] = ("link", os.readlink(path))
            elif os.path.isdir(path):
                state[rel] = ("dir",)
            elif not os.path.isfile(path):
                state[rel] = ("special",)  # a FIFO would block a read
            else:
                with open(path, "rb") as handle:
                    state[rel] = ("file", handle.read())
    return state


def marker(slot, host):
    return install.decorate(host, f"@module-slot: {slot}")


def template_project(root, with_markers=True):
    """A project shaped like one made by the project template."""
    files = {
        "AGENTS.md": "# Project instructions\n\nExisting rules.\n\n{agents}\n\nMore rules.\n",
        "README.md": "# Existing\n\nAbout it.\n\n{readme}\n",
        "docs/README.md": "# Docs\n\n{docs}\n",
        ".gitignore": "node_modules/\n{ignore}\n",
        "src/main.py": "print('hi')\n",
    }
    fills = {"agents": marker("agents-guidance", "AGENTS.md"), "readme": marker("readme-docs", "README.md"),
             "docs": marker("docs-index", "docs/README.md"), "ignore": marker("gitignore", ".gitignore")}
    for rel, text in files.items():
        if not with_markers:
            fills = {k: "" for k in fills}
        helpers.write(root, rel, text.format(**fills))
    return root


class AddCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        self.proj = self.tmp / "existing"
        self.proj.mkdir()

    def refuses(self, *extra, kit=None, code=1):
        before = snapshot(self.proj)
        result, out, err = run_add(self.proj, *extra, kit=kit)
        self.assertEqual(result, code, out + err)
        self.assertEqual(snapshot(self.proj), before, "refused run must write nothing")
        return out + err


class Criterion5Insertion(AddCase):
    def test_fragments_go_at_the_markers(self):
        template_project(self.proj)
        before = {rel: (self.proj / rel).read_text() for rel in SLOTS}
        code, out, err = run_add(self.proj)
        self.assertEqual(code, 0, out + err)
        for host, slot in SLOTS.items():
            text = (self.proj / host).read_text()
            begin = install.decorate(host, f"BEGIN module:knowledge-base slot:{slot}")
            end = install.decorate(host, f"END module:knowledge-base slot:{slot}")
            self.assertIn(begin, text)
            self.assertIn(marker(slot, host), text)
            self.assertEqual(text.index(end) + len(end) + 1, text.index(marker(slot, host)))
            # text outside the block is unchanged
            outside = text[:text.index(begin)] + text[text.index(end) + len(end) + 1:]
            self.assertEqual(outside, before[host], host)
        self.assertTrue((self.proj / "kb.json").is_file())
        self.assertTrue((self.proj / ".kb-manifest").is_file())
        self.assertEqual((self.proj / "src/main.py").read_text(), "print('hi')\n")

    def test_without_markers_blocks_are_appended(self):
        template_project(self.proj, with_markers=False)
        before = {rel: (self.proj / rel).read_bytes() for rel in SLOTS}
        code, out, err = run_add(self.proj)
        self.assertEqual(code, 0, out + err)
        for host, slot in SLOTS.items():
            text = (self.proj / host).read_bytes()
            self.assertTrue(text.startswith(before[host]), host)
            tail = text[len(before[host]):].decode()
            lines = tail.rstrip("\n").split("\n")
            self.assertEqual(lines[0], "" if before[host].endswith(b"\n") else lines[0])
            self.assertIn(install.decorate(host, f"BEGIN module:knowledge-base slot:{slot}"), lines)
            self.assertEqual(lines[-1], marker(slot, host))

    def test_absent_hosts_get_the_base_version(self):
        helpers.write(self.proj, "src/x.py", "x\n")
        code, out, err = run_add(self.proj)
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.proj / "README.md").read_text().startswith("# existing\n"))
        self.assertIn("slot:agents-guidance", (self.proj / "AGENTS.md").read_text())
        self.assertIn("/sources/*", (self.proj / ".gitignore").read_text())
        self.assertIn("slot:docs-index", (self.proj / "docs/README.md").read_text())

    def test_added_project_passes_the_checker(self):
        import check_kb
        template_project(self.proj)
        run_add(self.proj)
        self.assertEqual([str(f) for f in check_kb.check(self.proj).errors], [])

    def test_identical_existing_files_are_left_alone(self):
        helpers.write(self.proj, "kb.json", (helpers.KIT / "files/kb.json").read_text())
        code, out, err = run_add(self.proj)
        self.assertEqual(code, 0, out + err)

    def test_differing_existing_file_aborts_with_nothing_written(self):
        template_project(self.proj)
        for rel in ("kb.json", "tools/kbparse.py", "domains/_skeleton/README.md", "catalog/README.md"):
            with self.subTest(rel=rel):
                helpers.write(self.proj, rel, "mine\n")
                out = self.refuses()
                self.assertIn(rel, out)
                (self.proj / rel).unlink()

    def test_non_empty_content_directories_abort(self):
        template_project(self.proj)
        for rel in ("catalog/a.md", "domains/d/README.md", "playbook/x.md", "sources/a.pdf", "text/a.txt"):
            with self.subTest(rel=rel):
                path = helpers.write(self.proj, rel, "content\n")
                out = self.refuses()
                self.assertIn(rel.split("/")[0], out)
                path.unlink()

    def test_directories_holding_only_kit_files_are_not_content(self):
        # Left over from an earlier run that failed before writing the manifest.
        template_project(self.proj)
        for rel in ("domains/_skeleton/README.md", "catalog/README.md", "sources/README.md"):
            helpers.write(self.proj, rel, (helpers.KIT / "files" / rel).read_text())
        code, out, err = run_add(self.proj)
        self.assertEqual(code, 0, out + err)


class Criterion6BlockParsing(AddCase):
    def host(self, text, name="README.md"):
        template_project(self.proj)
        (self.proj / name).write_bytes(text if isinstance(text, bytes) else text.encode())

    def begin(self, slot="readme-docs", host="README.md"):
        return install.decorate(host, f"BEGIN module:knowledge-base slot:{slot}")

    def end(self, slot="readme-docs", host="README.md"):
        return install.decorate(host, f"END module:knowledge-base slot:{slot}")

    def test_marker_inside_a_fenced_block(self):
        self.host(f"# T\n\n```\n{marker('readme-docs', 'README.md')}\n```\n")
        self.refuses()

    def test_duplicate_markers(self):
        m = marker("readme-docs", "README.md")
        self.host(f"# T\n{m}\n{m}\n")
        self.refuses()

    def test_duplicate_blocks(self):
        pair = f"{self.begin()}\nx\n{self.end()}\n"
        self.host(f"# T\n{pair}{pair}")
        self.refuses()

    def test_begin_without_end(self):
        self.host(f"# T\n{self.begin()}\nx\n")
        self.refuses()

    def test_end_without_begin(self):
        self.host(f"# T\n{self.end()}\n")
        self.refuses()

    def test_nested_and_interleaved_pairs(self):
        self.host(f"# T\n{self.begin()}\n{self.begin('docs-index')}\n{self.end('docs-index')}\n{self.end()}\n")
        self.refuses()
        self.host(f"# T\n{self.begin()}\n{self.begin('docs-index')}\n{self.end()}\n{self.end('docs-index')}\n")
        self.refuses()

    def test_non_utf8_host(self):
        self.host(b"# T\n\xff\xfe\n")
        self.refuses()

    def test_nul_byte_host(self):
        self.host(b"# T\n\x00\n")
        self.refuses()

    def test_marker_not_after_the_end_line(self):
        m = marker("readme-docs", "README.md")
        self.host(f"# T\n{m}\n{self.begin()}\nx\n{self.end()}\n")
        self.refuses()

    def test_modified_existing_block_is_a_conflict(self):
        self.host(f"# T\n{self.begin()}\nedited by the owner\n{self.end()}\n{marker('readme-docs', 'README.md')}\n")
        self.refuses()

    def test_block_with_deleted_marker_is_recognized(self):
        template_project(self.proj)
        code, _, _ = run_add(self.proj)
        self.assertEqual(code, 0)
        (self.proj / ".kb-manifest").unlink()
        text = (self.proj / "README.md").read_text()
        (self.proj / "README.md").write_text(text.replace(marker("readme-docs", "README.md") + "\n", ""))
        code, out, err = run_add(self.proj)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("@module-slot: readme-docs", (self.proj / "README.md").read_text())


class Criterion7Behaviour(AddCase):
    def test_runs_no_git_command_against_the_target(self):
        template_project(self.proj)
        sentinel = self.tmp / "ran"
        script = self.tmp / "fsmonitor.sh"
        script.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
        script.chmod(0o755)
        (self.proj / ".git").mkdir()
        (self.proj / ".git" / "config").write_text(f"[core]\n\tfsmonitor = {script}\n\thooksPath = {self.tmp}\n")
        (self.proj / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        calls = []
        real = install.run_git
        with mock.patch.object(install, "run_git", side_effect=lambda a, cwd, **k: calls.append(cwd) or real(a, cwd, **k)):
            code, out, err = run_add(self.proj)
        self.assertEqual(code, 0, out + err)
        self.assertFalse(sentinel.exists())
        self.assertNotIn(str(self.proj), [str(c) for c in calls])

    def test_second_run_is_refused_as_already_installed(self):
        template_project(self.proj)
        self.assertEqual(run_add(self.proj)[0], 0)
        out = self.refuses(code=install.EXIT_ALREADY_INSTALLED)
        self.assertIn("--upgrade", out)

    def test_run_repeated_after_a_failure_before_the_manifest_completes(self):
        template_project(self.proj)
        fresh = self.tmp / "other" / "existing"  # same project name, so manifests compare equal
        fresh.mkdir(parents=True)
        template_project(fresh)
        real = install.write_file
        count = {"n": 0}

        def flaky(root, rel, data, executable=False):
            count["n"] += 1
            if count["n"] == 6:
                raise OSError("simulated failure")
            return real(root, rel, data, executable)

        with mock.patch.object(install, "write_file", side_effect=flaky):
            code, out, err = run_add(self.proj)
        self.assertEqual(code, 1)
        self.assertFalse((self.proj / ".kb-manifest").exists())
        self.assertIn("nothing was deleted", out + err)
        self.assertEqual(run_add(self.proj)[0], 0)
        self.assertEqual(run_add(fresh)[0], 0)
        self.assertEqual(snapshot(self.proj), snapshot(fresh))

    def test_target_inside_the_starter_is_refused(self):
        code, out, err = run_add(helpers.ROOT / "tests")
        self.assertEqual(code, 1)
        code, out, err = run_add(helpers.ROOT)
        self.assertEqual(code, 1)

    def test_missing_or_symlinked_or_file_target(self):
        self.assertEqual(run_add(self.tmp / "nope")[0], 1)
        link = self.tmp / "link"
        os.symlink(self.proj, link)
        self.assertEqual(run_add(link)[0], 1)
        plain = self.tmp / "plain"
        plain.write_text("x")
        self.assertEqual(run_add(plain)[0], 1)


class Criterion4DryRunAddTo(AddCase):
    def test_dry_run_lists_every_path_and_changes_nothing(self):
        template_project(self.proj)
        before = snapshot(self.proj)
        code, out, err = run_add(self.proj, "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(snapshot(self.proj), before)
        files = helpers.KIT / "files"
        for path in files.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                self.assertIn(path.relative_to(files).as_posix(), out)
        for host, slot in SLOTS.items():
            self.assertIn(host, out)
            self.assertIn(slot, out)
        self.assertIn(".kb-manifest", out)

    def test_dry_run_with_absent_hosts(self):
        helpers.write(self.proj, "src/x.py", "x\n")
        before = snapshot(self.proj)
        code, out, err = run_add(self.proj, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(self.proj), before)
        for host in SLOTS:
            self.assertIn(host, out)


if __name__ == "__main__":
    unittest.main()
