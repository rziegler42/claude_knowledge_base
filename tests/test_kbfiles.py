"""The file helpers every tool shares: real directories, hashing, bounded reads, atomic writes."""
import hashlib
import os
import stat
import unittest

import helpers
import kbfiles


class ScratchCase(unittest.TestCase):
    def setUp(self):
        cm = helpers.scratch()
        self.tmp = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)


class RealDirTests(ScratchCase):
    def test_a_real_directory_passes(self):
        (self.tmp / "d").mkdir()
        kbfiles.real_dir(str(self.tmp / "d"), "d/")

    def test_missing_symlinked_and_file_paths_are_refused(self):
        (self.tmp / "real").mkdir()
        os.symlink(self.tmp / "real", self.tmp / "link")
        (self.tmp / "file").write_text("x")
        for name in ("missing", "link", "file"):
            with self.subTest(name=name), self.assertRaises(kbfiles.KbFileError):
                kbfiles.real_dir(str(self.tmp / name), name)


class ReadTests(ScratchCase):
    def test_read_head_returns_at_most_the_cap(self):
        (self.tmp / "f").write_bytes(b"0123456789")
        self.assertEqual(kbfiles.read_head(str(self.tmp / "f"), 4), b"0123")
        self.assertEqual(kbfiles.read_head(str(self.tmp / "f"), 100), b"0123456789")

    def test_symlinks_and_special_files_are_refused_and_do_not_hang(self):
        (self.tmp / "real").write_text("x")
        os.symlink(self.tmp / "real", self.tmp / "link")
        os.mkfifo(self.tmp / "pipe")
        (self.tmp / "dir").mkdir()
        for name in ("link", "pipe", "dir"):
            with self.subTest(name=name), self.assertRaises(kbfiles.KbFileError):
                kbfiles.read_head(str(self.tmp / name), 10)

    def test_sha256_file_matches_hashlib(self):
        data = os.urandom(3 * (1 << 20) + 17)
        (self.tmp / "f").write_bytes(data)
        self.assertEqual(kbfiles.sha256_file(str(self.tmp / "f")), hashlib.sha256(data).hexdigest())

    def test_sha256_file_refuses_a_symlink_a_fifo_and_a_directory(self):
        (self.tmp / "real").write_text("x")
        os.symlink(self.tmp / "real", self.tmp / "link")
        os.mkfifo(self.tmp / "pipe")
        (self.tmp / "dir").mkdir()
        for name in ("link", "pipe", "dir"):
            with self.subTest(name=name), self.assertRaises(kbfiles.KbFileError):
                kbfiles.sha256_file(str(self.tmp / name))

    def test_read_text_refuses_what_is_not_text_and_what_is_too_big(self):
        (self.tmp / "ok").write_text("héllo\n", encoding="utf-8")
        self.assertEqual(kbfiles.read_text(str(self.tmp / "ok"), 100), "héllo\n")
        (self.tmp / "nul").write_bytes(b"a\x00b")
        (self.tmp / "bad").write_bytes(b"\xff\xfe")
        (self.tmp / "big").write_bytes(b"x" * 101)
        for name in ("nul", "bad", "big"):
            with self.subTest(name=name), self.assertRaises(kbfiles.KbFileError):
                kbfiles.read_text(str(self.tmp / name), 100)


class WriteTests(ScratchCase):
    def test_a_new_file_is_written_with_ordinary_permissions(self):
        kbfiles.write_atomic(str(self.tmp / "new"), b"data\n")
        self.assertEqual((self.tmp / "new").read_bytes(), b"data\n")
        self.assertEqual(stat.S_IMODE((self.tmp / "new").stat().st_mode), 0o644)

    def test_a_replaced_file_keeps_its_permissions(self):
        path = self.tmp / "f"
        path.write_text("old")
        os.chmod(path, 0o600)
        kbfiles.write_atomic(str(path), b"new")
        self.assertEqual(path.read_bytes(), b"new")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_no_temporary_file_is_left_after_a_write_or_a_failure(self):
        kbfiles.write_atomic(str(self.tmp / "f"), b"x")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["f"])
        (self.tmp / "dir").mkdir()
        with self.assertRaises(kbfiles.KbFileError):
            kbfiles.write_atomic(str(self.tmp / "dir"), b"x")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["dir", "f"])

    def test_a_symlink_or_special_file_is_never_replaced_or_followed(self):
        victim = self.tmp / "victim"
        victim.write_text("keep")
        os.symlink(victim, self.tmp / "link")
        os.mkfifo(self.tmp / "pipe")
        for name in ("link", "pipe"):
            with self.subTest(name=name), self.assertRaises(kbfiles.KbFileError):
                kbfiles.write_atomic(str(self.tmp / name), b"x")
        self.assertEqual(victim.read_text(), "keep")

    def test_a_failed_write_leaves_the_original(self):
        path = self.tmp / "f"
        path.write_text("original")
        real_replace = os.replace
        os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
        try:
            with self.assertRaises(OSError):
                kbfiles.write_atomic(str(path), b"new")
        finally:
            os.replace = real_replace
        self.assertEqual(path.read_text(), "original")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["f"])

    def test_the_temporary_name_is_hidden_so_the_checker_ignores_it(self):
        self.assertTrue(kbfiles.TEMP_PREFIX.startswith("."))


class RootTests(ScratchCase):
    def test_the_root_is_the_argument_or_the_parent_of_the_tools_directory(self):
        (self.tmp / "kb.json").write_text("{}")
        (self.tmp / "tools").mkdir()
        self.assertEqual(kbfiles.find_root(str(self.tmp), "/elsewhere"), str(self.tmp))
        self.assertEqual(kbfiles.find_root(None, str(self.tmp / "tools")), str(self.tmp))

    def test_a_directory_without_a_marker_or_with_a_symlinked_one_is_refused(self):
        with self.assertRaises(kbfiles.KbFileError):
            kbfiles.find_root(str(self.tmp), "/x")
        (self.tmp / "real.json").write_text("{}")
        os.symlink(self.tmp / "real.json", self.tmp / "kb.json")
        with self.assertRaises(kbfiles.KbFileError):
            kbfiles.find_root(str(self.tmp), "/x")
        os.symlink(self.tmp, self.tmp.parent / (self.tmp.name + "-link"))
        try:
            with self.assertRaises(kbfiles.KbFileError):
                kbfiles.find_root(str(self.tmp.parent / (self.tmp.name + "-link")), "/x")
        finally:
            os.unlink(self.tmp.parent / (self.tmp.name + "-link"))


class PathTests(ScratchCase):
    def test_safe_name_rules(self):
        for good in ("ethics", "a-b", "x1", "9lives"):
            self.assertTrue(kbfiles.valid_name(good), good)
        for bad in ("", "-a", "a_b", "A", "a.b", "a/b", "..", "a" * 101, "a b", "a\n", "café"):
            self.assertFalse(kbfiles.valid_name(bad), repr(bad))

    def test_inside_refuses_paths_that_leave_the_root(self):
        root = str(self.tmp)
        self.assertEqual(kbfiles.inside(root, "a/b.md"), os.path.join(root, "a", "b.md"))
        for bad in ("../x", "/etc/passwd", "a/../../x", "", "a//b", ".git/config", "a/.GIT/x"):
            with self.subTest(bad=bad), self.assertRaises(kbfiles.KbFileError):
                kbfiles.inside(root, bad)


if __name__ == "__main__":
    unittest.main()
