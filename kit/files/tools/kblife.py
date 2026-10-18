"""Readers for the lifecycle artifacts in docs/kb/domain-lifecycle.md.

Pure functions over text: the question table, the log grammar, the charter, reading notes, and
usage tests. They report positioned issues and have no side effects, so the checker, the status
report, and the writing tools all read the artifacts the same way. Lines over MAX_LINE are
refused, not scanned. Standard library only.
"""
import datetime
import os
import re
import sys
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbfiles  # noqa: E402
import kbparse  # noqa: E402

MAX_LINE = 64 * 1024
QUESTION_COLUMNS = ("ID", "Question", "Status", "Entries", "Notes")
QUESTION_STATUSES = ("open", "partial", "answered")
GAP_CATEGORIES = ("usage-test", "open-questions", "conflicts", "reverify", "no-verified", "leads", "stale")
CHARTER_HEADINGS = (
    "Purpose and consumers",
    "Scope",
    "Non-goals",
    "Source types and trust tiers",
    "Verification bar",
    "Safety and sensitivity notes",
)
USAGE_RESULTS = ("pass", "partial", "fail")

Issue = namedtuple("Issue", "line message")
Question = namedtuple("Question", "id question status entries notes line")
Questions = namedtuple("Questions", "rows issues")
LogEntry = namedtuple("LogEntry", "kind date number fields line")
Log = namedtuple("Log", "entries issues status")
CharterResult = namedtuple("CharterResult", "issues state front")
UsageResult = namedtuple("UsageResult", "issues result date")

QUESTION_ID_RE = re.compile(r"^q-[0-9]+\Z")
ENTRY_ID_RE = re.compile(r"pb-[a-z0-9-]+")
SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|\s*$")
HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) (?:wave ([1-9][0-9]{0,5}) (opened|closed|abandoned)|(charter))\Z")
FIELD_RE = re.compile(r"^(Goal|Targets|Limit|Gaps|Added|Left open|Reviewed|Gap result|Reason|Resume from|Change):[ ]?(.*)\Z")
GAP_ITEM_RE = re.compile(r"([a-z-]+)=(\d+|unchanged:[ ]?.*?)(?=, [a-z-]+=|\Z)")
FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
REQUIRED = {
    "opened": ("Goal", "Targets", "Limit"),
    "closed": ("Added", "Left open", "Reviewed"),
    "abandoned": ("Reason", "Resume from"),
    "charter": ("Change", "Reason"),
}


# ---- tables -------------------------------------------------------------------------


def _long_lines(text):
    """Issues for lines too long to check, and the lines with those emptied."""
    issues, lines = [], text.split("\n")
    for number, line in enumerate(lines, start=1):
        if len(line) > MAX_LINE:
            issues.append(Issue(number, "line is too long to check"))
            lines[number - 1] = ""
    return issues, lines


def _cells(line):
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")) or len(stripped) < 2:
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _first_table(lines):
    """(header cells, header line number, [(line number, line)]) for the first table, or None."""
    for index in range(len(lines) - 1):
        if lines[index].startswith("|") and SEPARATOR_RE.match(lines[index + 1]):
            rows = []
            for j in range(index + 2, len(lines)):
                if not lines[j].startswith("|"):
                    break
                rows.append((j + 1, lines[j]))
            return _cells(lines[index]) or [], index + 1, rows
    return None


def table_rows(text):
    """([cell lists], issues) for the data rows of the first table in text; no table means no rows."""
    issues, lines = _long_lines(text)
    table = _first_table(lines)
    if table is None:
        return [], issues
    rows = []
    for _, line in table[2]:
        cells = _cells(line)
        if cells is not None and any(cells):
            rows.append(cells)
    return rows, issues


# ---- questions ----------------------------------------------------------------------


def entry_ids(cell):
    """Entry IDs named in a table cell, in order, however they are written (plain, code, or link)."""
    seen = {}
    for found in ENTRY_ID_RE.findall(cell):
        seen.setdefault(found, None)
    return list(seen)


def parse_questions(text):
    issues, lines = _long_lines(text)
    table = _first_table(lines)
    if table is None:
        return Questions([], issues + [Issue(None, "no questions table found")])
    header, header_line, raw_rows = table
    if tuple(header) != QUESTION_COLUMNS:
        missing = [c for c in QUESTION_COLUMNS if c not in header]
        for column in missing:
            issues.append(Issue(header_line, f"questions table lacks column {column!r}"))
        if not missing:
            issues.append(Issue(header_line, "questions table columns must be ID, Question, Status, Entries, Notes in that order"))
        return Questions([], issues)
    rows, seen = [], {}
    for number, line in raw_rows:
        cells = _cells(line)
        if cells is None or len(cells) != len(QUESTION_COLUMNS):
            issues.append(Issue(number, f"row has {0 if cells is None else len(cells)} cells, expected {len(QUESTION_COLUMNS)}"))
            continue
        qid, question, status, entries_cell, notes = cells
        entries = entry_ids(entries_cell)
        if not QUESTION_ID_RE.match(qid):
            issues.append(Issue(number, f"invalid question id {qid[:30]!r}; use q-<number>"))
        elif qid in seen:
            issues.append(Issue(number, f"duplicate question id {qid!r} (first on line {seen[qid]})"))
        else:
            seen[qid] = number
        if status not in QUESTION_STATUSES:
            issues.append(Issue(number, f"invalid status {status[:20]!r}; use open, partial, or answered"))
        elif status == "open" and entries:
            issues.append(Issue(number, f"open question lists entries ({qid})"))
        elif status in ("answered", "partial") and not entries:
            issues.append(Issue(number, f"{status} question lists no entry ({qid})"))
        elif status == "partial" and not notes:
            issues.append(Issue(number, f"partial question needs a note in Notes ({qid})"))
        rows.append(Question(qid, question, status, entries, notes, number))
    return Questions(rows, issues)


def question_entry_issues(rows, known_ids):
    return [Issue(row.line, f"question {row.id} lists {entry}, which is not an entry")
            for row in rows for entry in row.entries if entry not in known_ids]


# ---- the source index -----------------------------------------------------------------


def index_stems(text):
    """([(stem, line)], issues) from a domain's index/sources.md. A file with no table has no rows."""
    issues, lines = _long_lines(text)
    table = _first_table(lines)
    if table is None:
        return [], issues
    stems = []
    for number, line in table[2]:
        cells = _cells(line)
        if cells is None or len(cells) != 2:
            issues.append(Issue(number, f"row has {0 if cells is None else len(cells)} cells, expected 2"))
            continue
        token = cells[0]
        link = re.match(r"^\[([^\]]+)\]\([^)]*\)\Z", token)
        if link:
            token = link.group(1)
        token = token.strip("`").strip()
        if not kbparse.valid_stem(token):
            issues.append(Issue(number, f"invalid stem {token[:40]!r}"))
            continue
        stems.append((token, number))
    return stems, issues


# ---- the log ------------------------------------------------------------------------


def parse_gaps(value):
    """{category: count} from 'usage-test=2, stale=0', or None when malformed."""
    items = {}
    for part in value.split(", "):
        match = re.match(r"^([a-z-]+)=([0-9]+)\Z", part)
        if not match or match.group(1) in items:
            return None
        items[match.group(1)] = int(match.group(2))
    return items or None


def parse_gap_result(value):
    """{category: count or ('unchanged', reason)} from a Gap result line, or None when malformed."""
    out, pos = {}, 0
    while pos < len(value):
        match = GAP_ITEM_RE.match(value, pos)
        if not match or match.group(1) in out:
            return None
        category, item = match.group(1), match.group(2)
        out[category] = int(item) if item.isdigit() else ("unchanged", item[len("unchanged:"):].strip())
        pos = match.end()
        if pos < len(value):
            if not value.startswith(", ", pos):
                return None
            pos += 2
    return out or None


def parse_log(text):
    issues, lines = _long_lines(text)
    entries, current = [], None
    for number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            match = HEADING_RE.match(line.rstrip())
            date = None
            if match:
                try:
                    date = datetime.date.fromisoformat(match.group(1))
                except ValueError:
                    match = None
            if not match:
                issues.append(Issue(number, "unrecognised log heading; use '## <date> wave <N> opened|closed|abandoned' or '## <date> charter'"))
                current = None
                continue
            kind = match.group(3) or "charter"
            current = LogEntry(kind, date, int(match.group(2)) if match.group(2) else None, {}, number)
            entries.append(current)
        elif current is not None:
            field = FIELD_RE.match(line.rstrip())
            if field and field.group(1) not in current.fields:
                current.fields[field.group(1)] = field.group(2).strip()
    status, last, opened = {}, 0, {}
    for entry in entries:
        label = "charter entry" if entry.kind == "charter" else f"wave {entry.number} {entry.kind}"
        for name in REQUIRED[entry.kind]:
            if name not in entry.fields:
                issues.append(Issue(entry.line, f"{label}: missing {name}: line"))
            elif not entry.fields[name]:
                issues.append(Issue(entry.line, f"{label} has an empty {name}: line"))
        if entry.kind == "opened":
            n = entry.number
            if n in opened:
                issues.append(Issue(entry.line, f"wave {n} opened twice"))
            else:
                if last == 0 and n != 1:
                    issues.append(Issue(entry.line, f"wave numbers must start at 1 (found {n})"))
                elif last and n != last + 1:
                    issues.append(Issue(entry.line, f"wave number {n} should be {last + 1}"))
                opened[n] = entry
                status[n] = "opened"
                last = max(last, n)
            if "Gaps" in entry.fields:
                gaps = parse_gaps(entry.fields["Gaps"])
                if gaps is None:
                    issues.append(Issue(entry.line, "Gaps line is malformed; expected category=count, ..."))
                else:
                    for category in gaps:
                        if category not in GAP_CATEGORIES:
                            issues.append(Issue(entry.line, f"unknown gap category {category[:30]!r}"))
        elif entry.kind in ("closed", "abandoned"):
            n = entry.number
            if n not in opened:
                issues.append(Issue(entry.line, f"wave {n} was never opened"))
            elif status[n] != "opened":
                issues.append(Issue(entry.line, f"wave {n} was already {status[n]}"))
            else:
                status[n] = entry.kind
                if entry.kind == "closed":
                    issues.extend(_gap_result_issues(opened[n], entry))
    return Log(entries, issues, status)


def _gap_result_issues(opened, closed):
    if "Gaps" not in opened.fields:
        return []
    gaps = parse_gaps(opened.fields["Gaps"])
    if gaps is None:
        return []  # reported where the Gaps line is
    n = closed.number
    if "Gap result" not in closed.fields:
        return [Issue(closed.line, f"wave {n} closed needs a Gap result: line because it opened with Gaps:")]
    result = parse_gap_result(closed.fields["Gap result"])
    if result is None:
        return [Issue(closed.line, "Gap result line is malformed; expected category=count or category=unchanged: reason")]
    issues = []
    for category in gaps:
        if category not in result:
            issues.append(Issue(closed.line, f"Gap result lacks the category {category}"))
    for category in result:
        if category not in gaps:
            issues.append(Issue(closed.line, f"Gap result has the category {category}, which Gaps does not"))
    for category, value in result.items():
        if category not in gaps:
            continue
        if isinstance(value, tuple):
            if not value[1]:
                issues.append(Issue(closed.line, f"{category}: unchanged needs a reason"))
        elif value >= gaps[category]:
            issues.append(Issue(closed.line, f"{category}: the count did not fall ({gaps[category]} to {value}); "
                                             f"write {category}=unchanged: <reason>"))
    return issues


def open_waves(log):
    return sorted(n for n, state in log.status.items() if state == "opened")


def abandoned_waves(log):
    return sorted(n for n, state in log.status.items() if state == "abandoned")


def reviewed_entries(log):
    found = set()
    for entry in log.entries:
        if entry.kind == "closed":
            found.update(re.findall(r"(?<![a-z0-9-])pb-[a-z0-9-]+", entry.fields.get("Reviewed", "")))
    return found


# ---- charter, reading notes, usage tests -----------------------------------------------


def _front(text, issues):
    try:
        return kbparse.parse_front_matter(text)
    except kbparse.FrontMatterError as exc:
        issues.append(Issue(exc.line, f"invalid front matter: {exc.message}"))
        return None, None


def _headings(lines):
    """[(level-2 heading text, line number)] outside fenced code blocks."""
    found, fence = [], None
    for number, line in enumerate(lines, start=1):
        marker = FENCE_RE.match(line)
        if marker:
            fence = None if fence == marker.group(1) else (fence or marker.group(1))
            continue
        if fence is None and line.startswith("## "):
            found.append((line[3:].strip(), number))
    return found


def charter_issues(text):
    issues = []
    front, first = _front(text, issues)
    if front is None:
        return CharterResult(issues, None, None)
    for key in ("domain", "title"):
        if not isinstance(front.get(key), str) or not front.get(key):
            issues.append(Issue(None, f"missing {key} in the charter front matter"))
    state = front.get("charter")
    if state not in ("draft", "set"):
        issues.append(Issue(None, "charter must be draft or set"))
    created = front.get("created")
    if not isinstance(created, datetime.date):
        issues.append(Issue(None, "created must be a date (YYYY-MM-DD)"))
    if state == "set":
        lines = text.split("\n")[first - 1:]
        found = _headings(lines)
        names = [name for name, _ in found]
        complete = True
        for heading in CHARTER_HEADINGS:
            count = names.count(heading)
            if count == 0:
                issues.append(Issue(None, f"a set charter lacks the heading '{heading}'"))
                complete = False
            elif count > 1:
                issues.append(Issue(None, f"the heading '{heading}' appears more than once"))
                complete = False
        if complete and [n for n in names if n in CHARTER_HEADINGS] != list(CHARTER_HEADINGS):
            issues.append(Issue(None, "the charter headings must appear in this order: " + "; ".join(CHARTER_HEADINGS)))
        if "REPLACE_WITH_" in text:
            issues.append(Issue(None, "a set charter contains REPLACE_WITH_ text"))
    return CharterResult(issues, state if state in ("draft", "set") else None, front)


def reading_note_issues(text, stem=None):
    issues = []
    front, first = _front(text, issues)
    if front is None:
        return issues
    if not isinstance(front.get("source"), str) or (stem is not None and front.get("source") != stem):
        issues.append(Issue(None, f"source must name the catalog stem{' ' + stem if stem else ''}"))
    if not isinstance(front.get("read"), datetime.date):
        issues.append(Issue(None, "read must be a date (YYYY-MM-DD)"))
    if not isinstance(front.get("by"), str) or not front.get("by").strip():
        issues.append(Issue(None, "by must name who read the source"))
    lines = text.split("\n")[first - 1:]
    start, fence = None, None
    body = []
    for line in lines:
        marker = FENCE_RE.match(line)
        if marker:
            fence = None if fence == marker.group(1) else (fence or marker.group(1))
        if fence is None and not marker and re.match(r"^#{1,2} ", line):
            if start is not None:
                break
            if line.strip() == "## Findings":
                start = True
            continue
        if start:
            body.append(line)
    if not start or not any(line.strip() for line in body):
        issues.append(Issue(None, "the '## Findings' section is missing or empty"))
    if "REPLACE_WITH_" in text:
        issues.append(Issue(None, "contains REPLACE_WITH_ text"))
    return issues


def usage_test_issues(text):
    issues = []
    front, _ = _front(text, issues)
    if front is None:
        return UsageResult(issues, None, None)
    date = front.get("date")
    if not isinstance(date, datetime.date):
        issues.append(Issue(None, "date must be a date (YYYY-MM-DD)"))
        date = None
    if not isinstance(front.get("scenario"), str) or not front.get("scenario").strip():
        issues.append(Issue(None, "scenario must be a non-empty line"))
    result = front.get("result")
    if result not in USAGE_RESULTS:
        issues.append(Issue(None, "result must be pass, partial, or fail"))
        result = None
    return UsageResult(issues, result, date)


# ---- writing front matter --------------------------------------------------------------

PLAIN_RE = re.compile(r"^[A-Za-z0-9._/-]+\Z")


def fm_value(value):
    """A value in the strict front-matter subset: plain when it is safe, else double-quoted."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    text = str(value)
    if not text.isprintable() or "\t" in text:
        raise kbfiles.KbFileError("a front-matter value is not printable single-line text")
    if (PLAIN_RE.match(text) and text not in ("true", "false") and not kbparse.INT_RE.match(text)
            and not kbparse.DATE_RE.match(text)):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def front_matter(fields):
    """A front-matter block for an ordered mapping; the parser must read back what was written."""
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f"  - {fm_value(item)}" for item in value)
        else:
            lines.append(f"{key}: {fm_value(value)}")
    lines.append("---")
    text = "\n".join(lines) + "\n"
    try:
        parsed, _ = kbparse.parse_front_matter(text)
    except kbparse.FrontMatterError:
        raise kbfiles.KbFileError("the front matter to write is not in the strict subset") from None
    for key, value in fields.items():
        if parsed.get(key) != value and not (isinstance(value, list) and not value and parsed.get(key) in (None, [])):
            raise kbfiles.KbFileError(f"front matter key {key} did not round-trip")
    return text


def edit_front_matter(text, updates):
    """Change, add, or (value None) remove top-level scalar keys in a record's front matter, by line,
    then check with the parser that the result says what was asked."""
    lines = text.split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        raise kbfiles.KbFileError("record has no front matter")
    end = lines.index("---", 1)
    head = lines[:end]
    for key, value in updates.items():
        indexes = [i for i, line in enumerate(head) if line.startswith(key + ":")]
        new = None if value is None else f"{key}: {fm_value(value)}"
        if indexes and new is None:
            head = [line for i, line in enumerate(head) if i not in indexes]
        elif indexes:
            head[indexes[0]] = new
            head = [line for i, line in enumerate(head) if i == indexes[0] or i not in indexes]
        elif new is not None:
            head.append(new)
    result = "\n".join(head + lines[end:])
    try:
        parsed, _ = kbparse.parse_front_matter(result)
    except kbparse.FrontMatterError:
        raise kbfiles.KbFileError("the edited front matter is not in the strict subset") from None
    for key, value in updates.items():
        if parsed.get(key) != value:
            raise kbfiles.KbFileError(f"front matter field {key} did not take the new value")
    return result


# ---- titles ---------------------------------------------------------------------------

MAX_TITLE = 120
FORBIDDEN_TITLE = set("|[]\\`")


def validate_title(title):
    """A title that is safe in front matter, a heading, a table cell, and a link."""
    if not title or title != title.strip() or len(title) > MAX_TITLE:
        raise kbfiles.KbFileError(f"the title must be 1 to {MAX_TITLE} characters with no space at either end")
    if not title.isprintable() or FORBIDDEN_TITLE & set(title) or kbparse.bad_chars(title):
        raise kbfiles.KbFileError("the title must be plain printable text without | [ ] \\ ` or invisible characters")
    if "REPLACE_WITH_" in title:
        raise kbfiles.KbFileError("the title must not contain REPLACE_WITH_")
