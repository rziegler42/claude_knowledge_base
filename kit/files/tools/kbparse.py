"""Strict front-matter subset, claim-tag grammar, stems, and character checks.

Implements the rules in docs/kb/knowledge-base-format.md. Standard library only.
"""
import bisect
import datetime
import re
from collections import namedtuple

KEY_RE = re.compile(r"^[a-z][a-z0-9_]*\Z")
STEM_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")
RESERVED_STEMS = frozenset({"readme", "quarantine"})
MAX_STEM = 100
INT_RE = re.compile(r"^(0|-?[1-9][0-9]{0,17})\Z")  # no leading zeros and bounded, so "007" stays text
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
EM_DASH = "—"
MAX_LINE = 64 * 1024
MAX_PARAGRAPH = 64 * 1024
MAX_TAG_ERRORS = 50
MAX_NOTE = 1024

Tag = namedtuple("Tag", "letter note line conflict")


class FrontMatterError(ValueError):
    def __init__(self, message, line):
        super().__init__(f"line {line}: {message}")
        self.message = message
        self.line = line


def valid_stem(stem):
    return bool(
        STEM_RE.match(stem) and len(stem) <= MAX_STEM and stem not in RESERVED_STEMS
    )


# ---- front matter -------------------------------------------------------------


def _strip_comment(rest):
    """Cut a trailing comment: a '#' preceded by whitespace outside a quoted string."""
    in_quote = False
    i = 0
    while i < len(rest):
        ch = rest[i]
        if in_quote:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_quote = False
        elif ch == '"':
            in_quote = True
        elif ch == "#" and (i == 0 or rest[i - 1] in " "):
            return rest[:i]
        i += 1
    return rest


def _quoted(value, line):
    out = []
    i = 1
    while i < len(value):
        ch = value[i]
        if ch == "\\":
            nxt = value[i + 1] if i + 1 < len(value) else ""
            if nxt not in ('"', "\\"):
                raise FrontMatterError("unsupported escape in quoted string", line)
            out.append(nxt)
            i += 2
            continue
        if ch == '"':
            if i != len(value) - 1:
                raise FrontMatterError("text after closing quote", line)
            return "".join(out)
        out.append(ch)
        i += 1
    raise FrontMatterError("unterminated quoted string", line)


def _plain_text(value, line):
    if value[0] in "#[\"'&*!|>@%`" or value.startswith("- ") or value == "-":
        raise FrontMatterError("plain value starts with a reserved character", line)
    if ": " in value or value.endswith(":"):
        raise FrontMatterError("plain value contains a colon; quote it", line)
    return value


def _plain(value, line):
    text = _plain_text(value, line)
    if text in ("true", "false"):
        return text == "true"
    if INT_RE.match(text):
        return int(text)
    if DATE_RE.match(text):
        try:
            return datetime.date.fromisoformat(text)
        except ValueError:
            return text
    return text


def _flow_list(value, line):
    if not value.endswith("]"):
        raise FrontMatterError("unterminated flow list", line)
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_plain_text(item.strip(), line) for item in inner.split(",") if item.strip()]


def _scalar(value, line):
    value = value.strip()
    if not value:
        return None
    if value.startswith('"'):
        return _quoted(value, line)
    if value.startswith("["):
        return _flow_list(value, line)
    return _plain(value, line)


def parse_front_matter(text):
    """Return (mapping, first_body_line) or raise FrontMatterError."""
    lines = text.split("\n")
    if lines[0] != "---":
        raise FrontMatterError("front matter must start on line 1 with ---", 1)
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise FrontMatterError("front matter is not closed with ---", 1) from None
    data = {}
    open_list = None
    for number, raw in enumerate(lines[1:end], start=2):
        if len(raw) > MAX_LINE:
            raise FrontMatterError("line is too long to check", number)
        if "\t" in raw:
            raise FrontMatterError("tab characters are not allowed", number)
        if not raw.strip() or raw.startswith("#"):
            continue
        if raw[0] == " ":
            item = re.match(r"^  - (.*)$", raw)
            if item is None or open_list is None:
                raise FrontMatterError("nested or continued values are not allowed", number)
            value = _strip_comment(item.group(1)).strip()
            if value.startswith('"'):
                data[open_list].append(_quoted(value, number))
            elif value:
                data[open_list].append(_plain_text(value, number))
            else:
                raise FrontMatterError("empty list item", number)
            continue
        open_list = None
        key, sep, rest = raw.partition(":")
        if not sep or not KEY_RE.match(key):
            raise FrontMatterError(f"invalid key {key!r}", number)
        if rest and not rest.startswith(" "):
            raise FrontMatterError("a space must follow the colon", number)
        if key in data:
            raise FrontMatterError(f"duplicate key {key!r}", number)
        value = _strip_comment(rest)
        data[key] = _scalar(value, number)
        if data[key] is None:
            open_list = key
            data[key] = _PendingList()  # a list if indented items follow, else empty
    for key, value in list(data.items()):
        if isinstance(value, _PendingList):
            data[key] = list(value) if value else None
    return data, end + 2


class _PendingList(list):
    """An empty value that turns into a list if indented items follow."""


# ---- claim tags ---------------------------------------------------------------

_FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
_ITEM_RE = re.compile(r"^\s*(?:[-*+]|[0-9]+[.)])\s")
_CANDIDATE_RE = re.compile(r"\[([A-Za-z])")


def _paragraphs(text, first_line):
    """Yield (first_line_number, text) for each paragraph outside fenced code."""
    block = []
    start = first_line
    in_fence = False

    def flush():
        nonlocal block
        if block:
            yield start, "\n".join(block)
        block = []

    for offset, line in enumerate(text.split("\n")):
        number = first_line + offset
        if _FENCE_RE.match(line):
            yield from flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            yield from flush()
            continue
        if line.startswith("#"):
            yield from flush()
            yield number, line
            continue
        if _ITEM_RE.match(line):
            yield from flush()
        if not block:
            start = number
        block.append(line)
    yield from flush()


def _conflict(note):
    if not note.startswith("conflict:"):
        return None
    parts = re.split(r",|\bvs\b", note[len("conflict:"):])
    return [p.strip() for p in parts if p.strip()]


_DASH_RE = re.compile(r"\s*[-\u2013]")


def find_tags(text, first_line=1):
    """Return (tags, errors); errors are (line, message). Linear in the paragraph length."""
    tags, errors = [], []
    for start, para in _paragraphs(text, first_line):
        if len(errors) >= MAX_TAG_ERRORS:
            errors.append((start, "further tag errors omitted"))
            break
        if len(para) > MAX_PARAGRAPH:
            errors.append((start, f"paragraph is too long to check (over {MAX_PARAGRAPH} characters)"))
            continue
        newlines = [i for i, ch in enumerate(para) if ch == "\n"]
        closes = [i for i, ch in enumerate(para) if ch == "]"]
        for match in _CANDIDATE_RE.finditer(para):
            if len(errors) >= MAX_TAG_ERRORS:
                break
            letter = match.group(1)
            row = bisect.bisect_left(newlines, match.start())
            line = start + row
            line_start = newlines[row - 1] + 1 if row else 0
            after = match.end()
            note = None
            if para.startswith("]", after):
                close = after
            elif para.startswith(" " + EM_DASH + " ", after):
                index = bisect.bisect_left(closes, after)
                if index == len(closes):
                    errors.append((line, "tag is not closed within its paragraph"))
                    continue
                close = closes[index]
                if close - (after + 3) > MAX_NOTE:
                    errors.append((line, f"tag note is too long (over {MAX_NOTE} characters) or unclosed"))
                    continue
                note = " ".join(part.strip() for part in para[after + 3:close].split("\n")).strip()
            elif letter in "VAUvau" and _DASH_RE.match(para, after):
                errors.append((line, "a tag note needs an em dash (\u2014), not a hyphen or en dash"))
                continue
            else:
                continue
            if para[close + 1:close + 2] in ("(", ":"):
                continue  # link text or a label
            prefix = para[line_start:match.start()]
            if note is None and letter in "xX" and _ITEM_RE.match(prefix + " "):
                continue  # task box
            if letter not in "VAU":
                errors.append((line, f"invalid tag letter {letter!r}; use V, A, or U"))
                continue
            conflict = _conflict(note) if note is not None else None
            if conflict is not None:
                if letter != "U":
                    errors.append((line, "a conflict note is valid only on a [U] tag"))
                elif len(conflict) < 2:
                    errors.append((line, "a conflict note must name at least two stems"))
                elif not all(valid_stem(s) for s in conflict):
                    errors.append((line, "a conflict note names an invalid stem"))
            tags.append(Tag(letter, note, line, conflict))
    return tags, errors


# ---- characters ---------------------------------------------------------------

_BAD_RANGES = (
    (0x00, 0x08), (0x0B, 0x1F), (0x7F, 0x9F),
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0x2066, 0x2069),
    (0xFEFF, 0xFEFF), (0xE0000, 0xE007F),
)


_BAD_RE = re.compile("[" + "".join(
    f"\\U{lo:08x}-\\U{hi:08x}" for lo, hi in _BAD_RANGES) + "]")


def bad_chars(text):
    """Return (line, column, 'U+XXXX') for each rejected character (1-based)."""
    found = []
    for number, line in enumerate(text.split("\n"), start=1):
        for match in _BAD_RE.finditer(line):
            found.append((number, match.start() + 1, f"U+{ord(match.group()):04X}"))
    return found
