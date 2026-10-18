import datetime
import unittest

import helpers  # noqa: F401  (puts the kit tools on sys.path)
import kbparse


def fm(*lines):
    return "\n".join(["---", *lines, "---", "body"]) + "\n"


class FrontMatterTests(unittest.TestCase):
    def parse(self, *lines):
        return kbparse.parse_front_matter(fm(*lines))

    def test_scalars_and_types(self):
        data, body_line = self.parse(
            "id: pb-example",
            "count: 3",
            "flag: true",
            "off: false",
            "updated: 2026-01-01",
            "empty:",
            'title: "Quoted: with colon"',
            "url: https://example.org/paper",
        )
        self.assertEqual(data["id"], "pb-example")
        self.assertEqual(data["count"], 3)
        self.assertIs(data["flag"], True)
        self.assertIs(data["off"], False)
        self.assertEqual(data["updated"], datetime.date(2026, 1, 1))
        self.assertIsNone(data["empty"])
        self.assertEqual(data["title"], "Quoted: with colon")
        self.assertEqual(data["url"], "https://example.org/paper")
        self.assertEqual(body_line, 11)

    def test_quoted_escapes(self):
        data, _ = self.parse(r'title: "a \"b\" c \\ d"')
        self.assertEqual(data["title"], 'a "b" c \\ d')

    def test_unknown_escape_is_error(self):
        with self.assertRaises(kbparse.FrontMatterError) as ctx:
            self.parse(r'title: "a \n b"')
        self.assertEqual(ctx.exception.line, 2)

    def test_lists(self):
        data, _ = self.parse(
            "sources:",
            "  - one",
            "  - two",
            "tags: [a, b]",
            "none: []",
        )
        self.assertEqual(data["sources"], ["one", "two"])
        self.assertEqual(data["tags"], ["a", "b"])
        self.assertEqual(data["none"], [])

    def test_comments(self):
        data, _ = self.parse(
            "# full-line comment",
            "status: draft   # trailing",
            'title: "keep # inside"',
        )
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["title"], "keep # inside")

    def test_title_with_colon_unquoted_is_error(self):
        with self.assertRaises(kbparse.FrontMatterError) as ctx:
            self.parse("title: Card games: hidden state")
        self.assertEqual(ctx.exception.line, 2)

    def test_duplicate_key_is_error(self):
        with self.assertRaises(kbparse.FrontMatterError) as ctx:
            self.parse("id: a", "id: b")
        self.assertEqual(ctx.exception.line, 3)

    def test_tab_is_error(self):
        with self.assertRaises(kbparse.FrontMatterError):
            self.parse("id:\ta")

    def test_bad_key_is_error(self):
        for key in ("Id", "1id", "my-key"):
            with self.subTest(key=key), self.assertRaises(kbparse.FrontMatterError):
                self.parse(f"{key}: x")

    def test_forbidden_plain_starts(self):
        for value in ("[unclosed", "- item", "&anchor", "*alias", "!tag"):
            with self.subTest(value=value), self.assertRaises(kbparse.FrontMatterError):
                self.parse(f"v: {value}")

    def test_nested_mapping_and_continuation_are_errors(self):
        with self.assertRaises(kbparse.FrontMatterError):
            self.parse("outer:", "  inner: 1")
        with self.assertRaises(kbparse.FrontMatterError):
            self.parse("v: first", "  continued")

    def test_flow_list_items_are_plain(self):
        with self.assertRaises(kbparse.FrontMatterError):
            self.parse('tags: ["a, b"]')

    def test_missing_open_or_close(self):
        with self.assertRaises(kbparse.FrontMatterError) as ctx:
            kbparse.parse_front_matter("id: x\n---\n")
        self.assertEqual(ctx.exception.line, 1)
        with self.assertRaises(kbparse.FrontMatterError):
            kbparse.parse_front_matter("---\nid: x\nbody\n")

    def test_date_must_be_real(self):
        data, _ = self.parse("when: 2026-13-45")
        self.assertEqual(data["when"], "2026-13-45")  # not a date; stays text
        self.assertFalse(isinstance(data["when"], datetime.date))


class TagTests(unittest.TestCase):
    def tags(self, text):
        return kbparse.find_tags(text)

    def test_valid_tags(self):
        tags, errors = self.tags("A claim [V]. Another [A — abstract only]. Third [U].\n")
        self.assertEqual(errors, [])
        self.assertEqual([t.letter for t in tags], ["V", "A", "U"])
        self.assertEqual(tags[1].note, "abstract only")
        self.assertIsNone(tags[0].note)

    def test_backticked_tag_is_counted(self):
        tags, errors = self.tags("Set off like `[V — Table 3]` in prose.\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(tags), 1)

    def test_fenced_code_is_ignored(self):
        text = "```\n[q] [V - bad]\n```\n~~~\n[z]\n~~~\n"
        tags, errors = self.tags(text)
        self.assertEqual((tags, errors), ([], []))

    def test_task_boxes_links_and_numbers_ignored(self):
        text = "- [ ] open\n- [x] done\n[a](http://x) and [b]: label\n[1] ref\n"
        tags, errors = self.tags(text)
        self.assertEqual((tags, errors), ([], []))

    def test_bad_letter_is_error(self):
        _, errors = self.tags("text [v] and [Q] here\n")
        self.assertEqual(len(errors), 2)

    def test_hyphen_or_en_dash_is_error(self):
        _, errors = self.tags("a [V - note] b [A – note]\n")
        self.assertEqual(len(errors), 2)

    def test_unclosed_candidate_is_error(self):
        _, errors = self.tags("a [V — note that never closes\n\nnext paragraph ]\n")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], 1)

    def test_note_may_wrap_within_a_paragraph(self):
        tags, errors = self.tags("Elo is pool-relative `[A — KataGo\n  training site]`.\n")
        self.assertEqual(errors, [])
        self.assertEqual(tags[0].note, "KataGo training site")
        self.assertEqual(tags[0].line, 1)

    def test_wrap_across_blank_line_or_heading_is_error(self):
        _, errors = self.tags("a [A — first\n\nsecond]\n")
        self.assertEqual(len(errors), 1)
        _, errors = self.tags("a [A — first\n## Heading]\n")
        self.assertEqual(len(errors), 1)

    def test_line_numbers(self):
        tags, _ = self.tags("one\ntwo [U]\n\nthree [V]\n")
        self.assertEqual([t.line for t in tags], [2, 4])

    def test_line_offset(self):
        tags, _ = kbparse.find_tags("x [V]\n", first_line=10)
        self.assertEqual(tags[0].line, 10)


class ConflictTests(unittest.TestCase):
    def test_conflict_on_u_with_two_stems(self):
        tags, errors = kbparse.find_tags("Contested [U — conflict: aaa-1 vs bbb-2].\n")
        self.assertEqual(errors, [])
        self.assertEqual(tags[0].conflict, ["aaa-1", "bbb-2"])

    def test_three_stems_with_commas(self):
        tags, errors = kbparse.find_tags("x [U — conflict: a1, b2 vs c3]\n")
        self.assertEqual(errors, [])
        self.assertEqual(tags[0].conflict, ["a1", "b2", "c3"])

    def test_conflict_on_other_letter_is_error(self):
        _, errors = kbparse.find_tags("x [V — conflict: a1 vs b2]\n")
        self.assertEqual(len(errors), 1)

    def test_conflict_with_one_stem_is_error(self):
        _, errors = kbparse.find_tags("x [U — conflict: a1]\n")
        self.assertEqual(len(errors), 1)

    def test_conflict_with_bad_stem_is_error(self):
        _, errors = kbparse.find_tags("x [U — conflict: A_1 vs b2]\n")
        self.assertEqual(len(errors), 1)

    def test_ordinary_note_has_no_conflict(self):
        tags, _ = kbparse.find_tags("x [U — from memory]\n")
        self.assertIsNone(tags[0].conflict)


class StemTests(unittest.TestCase):
    def test_valid(self):
        for stem in ("2020-author-short-title", "a", "0", "a-b-c"):
            self.assertTrue(kbparse.valid_stem(stem), stem)

    def test_invalid(self):
        for stem in ("", "-a", "A", "a.b", "a_b", "readme", "quarantine", "a" * 101, "a b"):
            self.assertFalse(kbparse.valid_stem(stem), stem)

    def test_length_limit_boundary(self):
        self.assertTrue(kbparse.valid_stem("a" * 100))


class BadCharTests(unittest.TestCase):
    def test_allowed_whitespace(self):
        self.assertEqual(kbparse.bad_chars("line one\n\tindented\n"), [])

    def test_rejected_characters(self):
        text = "a\rb\x00c\x7fd​e‮f⁠g﻿h\U000e0041"
        found = kbparse.bad_chars(text)
        self.assertEqual(len(found), 8)

    def test_reports_line_and_column(self):
        self.assertEqual(kbparse.bad_chars("ok\nab​c\n"), [(2, 3, "U+200B")])


if __name__ == "__main__":
    unittest.main()
