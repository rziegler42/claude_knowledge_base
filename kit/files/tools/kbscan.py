"""Scan rules for saved sources that need no PDF library.

Implements the text-level rules in docs/kb/source-pipeline.md: the phrase list, invisible and
tag characters, the hidden-text thresholds, link schemes, and the levels. A worker that opens
the PDF feeds this module facts; this module turns them into a level and labelled findings.
Findings carry labels only. The matched text is kept apart and shown only when asked.
Standard library only.
"""
import html
import re
import unicodedata
from collections import namedtuple
from pathlib import Path

SCANNER_VERSION = 1

LEVELS = {"clean": 0, "medium": 1, "high": 2}
SCAN_NAMES = {"clean": "clean", "medium": "review", "high": "flagged"}

MAX_PHRASES = 200
MAX_PATTERN = 500
MAX_FINDINGS = 50
MAX_INVISIBLE = 5
HIDDEN_CHARS = 200
SNIPPET_LENGTH = 80
UNTRACED_MIN = 24  # untraced characters needed to call a phrase hidden, at most
ALLOWED_SCHEMES = frozenset({"http", "https", "mailto", "doi"})

LABEL_RE = re.compile(r"^[a-z][a-z0-9-]*\Z")
TAG_RE = re.compile("[\U000e0000-\U000e007f]")
INVISIBLE_RE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]")
SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
IMAGE_LINK_RE = re.compile(
    r"!\[(?:[^\]\\]|\\.)*\]\(\s*<?\s*(?:https?:|data:|//)|<img\b[^>]{0,500}?\bsrc\s*=\s*[\"']?\s*(?:https?:|data:|//)",
    re.IGNORECASE,
)
REFERENCE_RE = re.compile(r"^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*<?[ \t]*(?:https?:|data:|//)", re.IGNORECASE | re.MULTILINE)

Finding = namedtuple("Finding", "level where label snippet")


class PhraseListError(ValueError):
    pass


def default_phrase_path():
    return Path(__file__).resolve().parent / "scan_phrases.txt"


def load_phrases(path):
    """Return [(label, compiled regex)] from a phrase list, or raise PhraseListError."""
    try:
        raw = Path(path).read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PhraseListError(f"cannot read the phrase list {path}: {type(exc).__name__}") from None
    phrases = []
    for number, line in enumerate(text.split("\n"), start=1):
        line = line.rstrip("\r")
        if not line.strip() or line.startswith("#"):
            continue
        label, _, pattern = line.partition(" ")
        if not LABEL_RE.match(label) or not pattern:
            raise PhraseListError(f"phrase list line {number}: expected 'label expression'")
        if len(pattern) > MAX_PATTERN:
            raise PhraseListError(f"phrase list line {number}: expression is longer than {MAX_PATTERN} characters")
        try:
            phrases.append((label, re.compile(pattern, re.IGNORECASE)))
        except re.error:
            raise PhraseListError(f"phrase list line {number}: the expression does not compile") from None
        if len(phrases) > MAX_PHRASES:
            raise PhraseListError(f"phrase list has more than {MAX_PHRASES} patterns")
    return phrases


def scan_name(level):
    return SCAN_NAMES[level]


def link_scheme(uri):
    """The scheme a viewer would read from a link target, lowercase, or None.

    Whitespace and control characters are dropped first, because a viewer ignores them inside
    the scheme ("java\\nscript:")."""
    cleaned = "".join(ch for ch in str(uri) if ord(ch) > 0x20 and ch != "\x7f")
    match = SCHEME_RE.match(cleaned)
    return match.group(1).lower() if match else None


def scheme_allowed(uri):
    return link_scheme(uri) in ALLOWED_SCHEMES


def has_remote_image_link(markdown):
    """True when Markdown embeds an image from the network or a data URL, inline or by reference,
    however the scheme is spelled (character references are decoded first)."""
    text = html.unescape(markdown)
    if IMAGE_LINK_RE.search(text):
        return True
    return "![" in text and bool(REFERENCE_RE.search(text))


def _snippet(text):
    shown = "".join(ch if ch.isprintable() else "?" for ch in text[:SNIPPET_LENGTH])
    return shown


class Result:
    def __init__(self, level, findings, suppressed):
        self.level = level
        self.scan = SCAN_NAMES[level]
        self.findings = findings
        self.suppressed = suppressed

    def lines(self, snippets=False):
        out = []
        for f in self.findings:
            line = f"{f.level}: {f.where}: {f.label}"
            if snippets and f.snippet:
                line += f" ({f.snippet})"
            out.append(line)
        return out


class Collector:
    """Gathers facts about one source and returns its level and findings."""

    def __init__(self, phrases, snippets=False):
        self.phrases = phrases
        self.snippets = snippets
        self.findings = []
        self.keys = set()
        self.suppressed = 0
        self.invisible = 0
        self.total_chars = 0
        self.hidden_chars = 0

    def add(self, level, where, label, snippet=None):
        if level not in ("medium", "high"):
            raise ValueError(f"unknown level {level!r}")
        key = (level, where, label)
        if key in self.keys:
            return
        self.keys.add(key)
        if len(self.findings) >= MAX_FINDINGS:
            self.suppressed += 1
            return
        self.findings.append(Finding(level, where, label, _snippet(snippet) if snippet and self.snippets else None))

    def _phrases(self, level, where, text, label=None):
        # one space between words, so a phrase wrapped over lines or drawn in pieces still matches
        normalised = " ".join(unicodedata.normalize("NFKC", text).split())
        for name, regex in self.phrases:
            match = regex.search(normalised)
            if match:
                self.add(level, where, label or name, match.group(0))

    def _characters(self, where, text):
        if TAG_RE.search(text):
            self.add("high", where, "unicode-tag-characters")
        body = text[1:] if text.startswith("﻿") else text
        self.invisible += len(INVISIBLE_RE.findall(body))

    def add_text(self, where, text):
        """Text a reader can see, or an annotation or metadata field."""
        self.total_chars += len(text)
        self._characters(where, text)
        self._phrases("medium", where, text)

    def add_hidden(self, where, text):
        """Text the page hides from a reader. The page text normally includes it too, so only the
        hidden count and the phrase check are done here. A phrase in hidden text is high."""
        self._characters(where, text)
        self.hidden_chars += len("".join(text.split()))
        self._phrases("high", where, text, label="hidden-text-instruction")

    def check_phrases(self, where, text, hidden=False):
        """Check text only against the phrase list: text as the page draws it, which the page text
        already counted. A phrase in hidden text is high, in visible text medium."""
        if hidden:
            self._phrases("high", where, text, label="hidden-text-instruction")
        else:
            self._phrases("medium", where, text)

    def check_untraced(self, where, text, excess):
        """`excess` is how many characters of the page text the renderer did not report as drawn (text
        filled with a pattern, for example). A phrase in the page text that is no longer than that (or
        UNTRACED_MIN characters, if shorter) may be made of such characters, so it is treated as hidden.
        The match is not located, so visible words placed around the hidden ones cannot break it up."""
        normalised = " ".join(unicodedata.normalize("NFKC", text).split())
        for name, regex in self.phrases:
            match = regex.search(normalised)
            if match and excess >= min(len("".join(match.group(0).split())), UNTRACED_MIN):
                self.add("high", where, "hidden-text-instruction", match.group(0))

    def result(self):
        if self.invisible > MAX_INVISIBLE:
            self.add("medium", "source", "invisible-characters")
        if self.hidden_chars > 0 and (self.hidden_chars > HIDDEN_CHARS or self.hidden_chars * 20 > self.total_chars):
            self.add("medium", "hidden text", "hidden-text")
        level = "clean"
        for f in self.findings:
            if LEVELS[f.level] > LEVELS[level]:
                level = f.level
        order = sorted(self.findings, key=lambda f: -LEVELS[f.level])
        return Result(level, order, self.suppressed)
