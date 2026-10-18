#!/usr/bin/env python3
"""Validate a knowledge-base project against docs/kb/knowledge-base-format.md.

Usage: python3 tools/check_kb.py [--root DIR] [--require-sources]

Reads only; writes nothing. Exit status 1 when any failure is reported, 0 otherwise
(warnings never change the status). Standard library only.
"""
import argparse
import datetime
import hashlib
import json
import os
import posixpath
import re
import stat
import sys
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbparse  # noqa: E402
import kblife  # noqa: E402

MAX_READ = 16 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
SUPPORTED_SCHEMA = 1
MAX_LINE = 64 * 1024
MAX_TEXT = 1024 * 1024
MAX_TAG_FINDINGS = 50

Finding = namedtuple("Finding", "path line message")

ENTRY_ID_RE = re.compile(r"^pb-[a-z0-9-]+\Z")
DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")
SHA_RE = re.compile(r"^[0-9a-f]{64}\Z")
LINK_RE = re.compile(r"\]\(([^)\s]{1,512})\)")
REVIEWED_ID_RE = re.compile(r"(?<![a-z0-9-])pb-[a-z0-9-]+")
BACKTICK_ID_RE = re.compile(r"`(pb-[a-z0-9-]+)`")
ENTRY_LINK_RE = re.compile(r"(?:^|/)entries/pb-[a-z0-9-]+\.md\Z")
ENTRY_PATH_RE = re.compile(r"^domains/[^/]+/playbook/entries/pb-[a-z0-9-]+\.md\Z")
ROOT_HEADER = "| Domain | Router | Purpose |"
REQUIRED_HEADINGS = ("Use when", "Approach", "Pitfalls", "Evidence and confidence", "See also")
STATUSES = ("draft", "reviewed", "superseded")
KINDS = ("document", "site", "repo")
CONFIRMED = ("full", "abstract", "snippet", "memory")
TIERS = ("primary", "secondary", "practitioner", "community", "unknown")
STATES = ("recorded", "saved", "converted", "read")
SCANS = ("none", "clean", "review", "flagged")
FILE_STATES = ("saved", "converted", "read")
PHRASES = [re.compile(p, re.I) for p in (
    r"ignore (all |any )?(previous|prior|above) instructions",
    r"you are (now )?an? (ai|assistant|language model)",
    r"system prompt",
    r"run the following command",
)]


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, path, line, message):
        self.errors.append(Finding(path, line, message))

    def warn(self, path, message):
        self.warnings.append(Finding(path, None, message))


class Checker:
    def __init__(self, root, require_sources):
        self.root = root
        self.require_sources = require_sources
        self.report = Report()
        self.catalog = {}
        self.entries = {}
        self.entry_stems = {}
        self.domains = []
        self.source_files = {}
        self.reviewed = {}
        self.refused = set()
        self.charters = {}
        self.listed = {}

    # ---- filesystem ---------------------------------------------------------------

    def _refuse_dir(self, rel):
        if rel not in self.refused:
            self.refused.add(rel)
            self.report.error(rel, None, "is a symlink or not a directory; refused")

    def _lstat(self, rel):
        """lstat a project-relative path; a symlinked or non-directory ancestor is refused."""
        parts = rel.split("/")
        current = self.root
        st = None
        for index, part in enumerate(parts):
            current = os.path.join(current, part)
            try:
                st = os.lstat(current)
            except (OSError, ValueError):
                return None
            if index < len(parts) - 1 and (stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode)):
                self._refuse_dir("/".join(parts[:index + 1]))
                return None
        return st

    def is_file(self, rel):
        st = self._lstat(rel)
        return bool(st and stat.S_ISREG(st.st_mode))

    def is_dir(self, rel):
        st = self._lstat(rel)
        return bool(st and stat.S_ISDIR(st.st_mode))

    def listdir(self, rel):
        st = self._lstat(rel)
        if st is None:
            return []
        if stat.S_ISLNK(st.st_mode):
            self._refuse_dir(rel)
            return []
        if not stat.S_ISDIR(st.st_mode):
            return []
        try:
            return sorted(os.listdir(os.path.join(self.root, rel)))
        except (OSError, ValueError):
            return []

    def read_bytes(self, rel, limit=MAX_READ):
        st = self._lstat(rel)
        if st is None:
            self.report.error(rel, None, "cannot be read")
            return None
        if stat.S_ISLNK(st.st_mode):
            self.report.error(rel, None, "is a symlink; refused")
            return None
        if not stat.S_ISREG(st.st_mode):
            self.report.error(rel, None, "is not a regular file")
            return None
        if st.st_size > limit:
            self.report.error(rel, None, f"is too large to check (over {limit} bytes)")
            return None
        try:
            fd = os.open(os.path.join(self.root, rel), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as handle:
                return handle.read(limit + 1)
        except (OSError, ValueError) as exc:
            self.report.error(rel, None, f"cannot be read: {getattr(exc, 'strerror', None) or 'invalid path'}")
            return None

    def read(self, rel):
        data = self.read_bytes(rel, MAX_TEXT)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            self.report.error(rel, None, "is not valid UTF-8")
            return None

    def front_matter(self, rel, text):
        try:
            return kbparse.parse_front_matter(text)
        except kbparse.FrontMatterError as exc:
            self.report.error(rel, exc.line, exc.message)
            return None

    # ---- run ----------------------------------------------------------------------

    def run(self):
        schema = self.check_marker()
        self.check_manifest(schema)
        self.check_readme()
        self.scan_sources()
        self.check_catalog()
        self.check_source_files()
        self.collect_domains()
        for domain in self.domains:
            self.check_domain(domain)
        self.check_entries()
        for domain in self.domains:
            self.check_lifecycle(domain)
        self.check_read_sources()
        for domain in self.domains:
            self.check_domain_router(domain)
        self.check_root_router()
        return self.report

    # ---- marker, manifest, README -------------------------------------------------

    def check_marker(self):
        rel = "kb.json"
        if not self.is_file(rel):
            self.report.error(rel, None, "kb.json is missing")
            return None
        data = self.read(rel)
        if data is None:
            return None
        try:
            marker = json.loads(data)
        except (ValueError, RecursionError):
            self.report.error(rel, None, "kb.json is not valid JSON")
            return None
        if not isinstance(marker, dict):
            self.report.error(rel, None, "kb.json must be a JSON object")
            return None
        expected = {"kind": "knowledge-base", "router": "playbook/README.md",
                    "spec": "docs/kb/knowledge-base-format.md"}
        for key, value in expected.items():
            if key not in marker:
                self.report.error(rel, None, f"missing key {key!r}")
            elif marker[key] != value:
                self.report.error(rel, None, f"{key} must be {value!r}")
        schema = marker.get("schema")
        if "schema" not in marker:
            self.report.error(rel, None, "missing key 'schema'")
            return None
        if isinstance(schema, bool) or not isinstance(schema, int) or schema < 0:
            self.report.error(rel, None, "schema must be a non-negative integer")
            return None
        if schema > SUPPORTED_SCHEMA:
            self.report.error(rel, None, f"schema {schema} is newer than this checker supports ({SUPPORTED_SCHEMA})")
        for key in ("router", "spec"):
            if marker.get(key) == expected[key] and not self.is_file(expected[key]):
                self.report.error(rel, None, f"{key} {expected[key]!r} is not a regular file in the project")
        return schema

    def check_manifest(self, schema):
        rel = ".kb-manifest"
        if not self.is_file(rel):
            self.report.error(rel, None, "manifest .kb-manifest is missing")
            return
        data = self.read_bytes(rel, MAX_MANIFEST)
        if data is None:
            return
        try:
            manifest = json.loads(data.decode("utf-8"))
        except (ValueError, RecursionError):
            self.report.error(rel, None, "manifest is not valid JSON")
            return
        if not isinstance(manifest, dict):
            self.report.error(rel, None, "manifest must be a JSON object")
            return
        if schema is not None and manifest.get("kb_schema") != schema:
            self.report.error(rel, None, f"manifest kb_schema {manifest.get('kb_schema')!r} differs from kb.json schema {schema}")

    def check_readme(self):
        text = self.read("README.md") if self.is_file("README.md") else None
        if text is None:
            if not self.is_file("README.md"):
                self.report.error("README.md", None, "README.md is missing; it must carry the copyright and licensing note")
            return
        if "Copyright and licensing" not in text or "not legal advice" not in text:
            self.report.error("README.md", None, "README.md lacks the copyright and licensing note")

    # ---- sources and catalog -------------------------------------------------------

    def scan_sources(self):
        found = {}
        for directory in ("sources", "sources/quarantine"):
            for name in self.listdir(directory):
                rel = f"{directory}/{name}"
                st = self._lstat(rel)
                if name.startswith(".") or name == "README.md" or st is None:
                    continue
                if stat.S_ISLNK(st.st_mode):
                    self.report.error(rel, None, "is a symlink; refused")
                    continue
                if stat.S_ISDIR(st.st_mode):
                    continue
                stem = name.rsplit(".", 1)[0] if "." in name else name
                if not kbparse.valid_stem(stem):
                    self.report.error(rel, None, f"invalid source stem {stem!r}")
                    continue
                found.setdefault(stem, []).append(rel)
        for stem, rels in found.items():
            if len(rels) > 1:
                self.report.error(rels[0], None, f"files {', '.join(rels)} share the stem {stem!r}")
        self.source_files = found

    def check_catalog(self):
        for name in self.listdir("catalog"):
            rel = f"catalog/{name}"
            if name == "README.md" or not name.endswith(".md"):
                continue
            stem = name[:-3]
            if not kbparse.valid_stem(stem):
                self.report.error(rel, None, f"invalid stem {stem!r}")
                self.catalog[stem] = {}
                continue
            text = self.read(rel)
            if text is None:
                self.catalog[stem] = {}
                continue
            self.text_hygiene(rel, text)
            parsed = self.front_matter(rel, text)
            if parsed is None:
                self.catalog[stem] = {}
                continue
            fields = parsed[0]
            self.catalog[stem] = fields
            self.check_record(rel, stem, fields)

    def check_record(self, rel, stem, f):
        err = lambda msg: self.report.error(rel, None, msg)  # noqa: E731
        listed = f.get("stem")
        if str(listed) != stem:
            err(f"stem {listed!r} differs from the filename")
        for key in ("kind", "title", "retrieved", "confirmed", "tier", "state", "scan"):
            if f.get(key) in (None, ""):
                err(f"missing required field {key}")
        for key, allowed in (("kind", KINDS), ("confirmed", CONFIRMED), ("tier", TIERS),
                             ("state", STATES), ("scan", SCANS)):
            if f.get(key) not in (None, "") and f[key] not in allowed:
                err(f"{key}: invalid value {f[key]!r}")
        for key in ("retrieved", "released", "replaced"):
            if f.get(key) not in (None, "") and not isinstance(f[key], datetime.date):
                err(f"{key} must be a date (YYYY-MM-DD)")
        kind, state, scan = f.get("kind"), f.get("state"), f.get("scan")
        released, sha = f.get("released"), f.get("sha256")
        if kind in ("site", "repo") and f.get("url") in (None, ""):
            err("missing required field url")
        if sha not in (None, "") and not (isinstance(sha, str) and SHA_RE.match(sha)):
            err("sha256 must be exactly 64 lowercase hexadecimal digits")
        if state in FILE_STATES and sha in (None, ""):
            err(f"sha256 is required for state {state}")
        if kind in ("site", "repo"):
            if state not in (None, "recorded") or scan not in (None, "none") or sha or released:
                err(f"a {kind} record must stay recorded with scan none and no sha256 or released")
        if state == "recorded" and (scan not in (None, "none") or released):
            err("a recorded source must have scan none and no released date")
        if scan == "flagged":
            if released:
                err("a flagged record cannot carry released")
            if state in ("converted", "read"):
                err("a flagged source cannot be converted or read")
        if released and scan != "review":
            err("a released source must have scan review")
        if state in ("converted", "read") and scan not in ("clean", "review"):
            err(f"state {state} requires scan clean or review")
        retrieved, replaced = f.get("retrieved"), f.get("replaced")
        if isinstance(retrieved, datetime.date) and isinstance(replaced, datetime.date) and replaced < retrieved:
            err("replaced cannot be earlier than retrieved")
        if f.get("authors") is not None and not isinstance(f["authors"], list):
            err("authors must be a list")
        if f.get("confirmed") == "full" and state == "recorded":
            self.report.warn(rel, "confirmed: full but the state is recorded (no saved file)")

    def check_source_files(self):
        for stem, rels in sorted(self.source_files.items()):
            if stem not in self.catalog:
                self.report.warn(rels[0], "has no catalog record")
        for stem, f in sorted(self.catalog.items()):
            state, scan, sha = f.get("state"), f.get("scan"), f.get("sha256")
            if state not in FILE_STATES or f.get("kind") != "document":
                continue
            quarantined = scan == "flagged" and not f.get("released")
            directory = "sources/quarantine" if quarantined else "sources"
            matches = [r for r in self.source_files.get(stem, []) if posixpath.dirname(r) == directory]
            rel = f"catalog/{stem}.md"
            if not matches:
                if self.require_sources:
                    self.report.error(rel, None, f"saved source file is missing (expected {directory}/{stem}.*)")
                else:
                    self.report.warn(rel, f"source file missing (unsaved) in {directory}/")
                continue
            if isinstance(sha, str) and SHA_RE.match(sha):
                actual = self.hash_file(matches[0])
                if actual is not None and actual != sha:
                    self.report.error(rel, None, f"SHA-256 of {matches[0]} differs from the catalog sha256")

    def hash_file(self, rel):
        try:
            fd = os.open(os.path.join(self.root, rel), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            digest = hashlib.sha256()
            with os.fdopen(fd, "rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            self.report.error(rel, None, "cannot be hashed")
            return None

    def text_hygiene(self, rel, text):
        for line, column, code in kbparse.bad_chars(text):
            self.report.error(rel, line, f"disallowed character {code} at column {column}")
        for pattern in PHRASES:
            if pattern.search(text):
                self.report.warn(rel, "contains an instruction-like phrase")
                break

    # ---- domains --------------------------------------------------------------------

    def collect_domains(self):
        for name in self.listdir("domains"):
            rel = f"domains/{name}"
            if name == "_skeleton" or name.startswith("."):
                continue
            st = self._lstat(rel)
            if st is None or stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                self.report.error(rel, None, "domain must be a real directory")
                continue
            if not DOMAIN_RE.match(name):
                self.report.error(rel, None, "invalid domain name")
                continue
            self.domains.append(name)

    def check_domain(self, domain):
        base = f"domains/{domain}"
        charter = f"{base}/README.md"
        if self.is_file(charter) or self._lstat(charter):
            self.charters[domain] = self.read(charter)  # judged with the other lifecycle files
        else:
            self.report.error(charter, None, "charter README.md is missing")
        for name in self.listdir(f"{base}/index"):
            if name.endswith(".md"):
                rel = f"{base}/index/{name}"
                text = self.read(rel)
                if text is not None:
                    self.text_hygiene(rel, text)
        self.reviewed[domain] = self.reviewed_lines(f"{base}/log.md")
        for name in self.listdir(f"{base}/playbook/entries"):
            if name.endswith(".md"):
                rel = f"{base}/playbook/entries/{name}"
                self.entries[rel] = {"domain": domain, "stem": name[:-3]}
                self.entry_stems.setdefault(name[:-3], []).append(rel)

    # ---- lifecycle ---------------------------------------------------------------------

    def report_issues(self, rel, issues):
        for issue in issues:
            self.report.error(rel, issue.line, issue.message)

    def check_lifecycle(self, domain):
        base = f"domains/{domain}"
        charter_rel = f"{base}/README.md"
        entry_ids = {info["stem"] for info in self.entries.values() if info["domain"] == domain}
        state = None
        text = self.charters.get(domain)
        if text is not None:
            result = kblife.charter_issues(text)
            self.report_issues(charter_rel, result.issues)
            state = result.state
            if state == "draft" and entry_ids:
                self.report.error(charter_rel, None, "a domain with entries cannot have charter: draft")
        questions_rel = f"{base}/questions.md"
        if not self._lstat(questions_rel):
            self.report.error(questions_rel, None, "questions.md is missing")
        else:
            text = self.read(questions_rel)
            if text is not None:
                parsed = kblife.parse_questions(text)
                self.report_issues(questions_rel, parsed.issues)
                self.report_issues(questions_rel, kblife.question_entry_issues(parsed.rows, entry_ids))
                if state == "set" and len(parsed.rows) < 3:
                    self.report.error(questions_rel, None, "a set domain needs at least three questions")
        log_rel = f"{base}/log.md"
        if not self._lstat(log_rel):
            self.report.error(log_rel, None, "log.md is missing")
        else:
            text = self.read(log_rel)
            if text is not None:
                self.report_issues(log_rel, kblife.parse_log(text).issues)
        for name in self.listdir(f"{base}/usage-tests"):
            if name.endswith(".md"):
                rel = f"{base}/usage-tests/{name}"
                text = self.read(rel)
                if text is not None:
                    self.report_issues(rel, kblife.usage_test_issues(text).issues)
        index_rel = f"{base}/index/sources.md"
        if self._lstat(index_rel):
            text = self.read(index_rel)
            if text is not None:
                stems, issues = kblife.index_stems(text)
                self.report_issues(index_rel, issues)
                for stem, line in stems:
                    self.listed.setdefault(stem, []).append(domain)
                    if stem not in self.catalog:
                        self.report.error(index_rel, line, f"lists {stem}, which has no catalog record")

    def check_read_sources(self):
        """A source in state read needs a valid reading note in a domain that lists it."""
        for stem in sorted(self.catalog):
            if self.catalog[stem].get("state") != "read":
                continue
            found, problems = False, []
            for domain in self.listed.get(stem, []):
                rel = f"domains/{domain}/topics/{stem}.md"
                if not self._lstat(rel):
                    continue
                text = self.read(rel)
                if text is None:
                    continue
                issues = kblife.reading_note_issues(text, stem)
                if issues:
                    problems.append((rel, issues))
                else:
                    found = True
            if not found:
                self.report.error(f"catalog/{stem}.md", None,
                                  f"{stem} is in state read but no domain that lists it has a valid reading note "
                                  f"(domains/<domain>/topics/{stem}.md)")
                for rel, issues in problems:
                    self.report_issues(rel, issues)

    def reviewed_lines(self, rel):
        if not self.is_file(rel):
            return set()
        text = self.read(rel)
        if text is None:
            return set()
        ids, in_closed = set(), False
        for line in text.split("\n"):
            if line.startswith("## "):
                in_closed = re.match(r"^## \d{4}-\d{2}-\d{2} wave \d+ closed\s*$", line) is not None
            elif in_closed and line.startswith("Reviewed:") and len(line) <= MAX_LINE:
                ids.update(REVIEWED_ID_RE.findall(line))
        return ids

    # ---- entries --------------------------------------------------------------------

    def check_entries(self):
        ids = {}
        for rel in sorted(self.entries):
            info = self.entries[rel]
            text = self.read(rel)
            if text is None:
                continue
            self.check_entry(rel, info, text, ids)

    def check_entry(self, rel, info, text, ids):
        err = lambda line, msg: self.report.error(rel, line, msg)  # noqa: E731
        stem = info["stem"]
        if not ENTRY_ID_RE.match(stem):
            err(None, "entry filename must match pb-[a-z0-9-]+")
        parsed = self.front_matter(rel, text)
        if parsed is None:
            return
        f, body_line = parsed
        info["status"] = f.get("status")
        for key in ("id", "type", "title", "status", "sources", "updated"):
            if key not in f or f[key] in ("",) or (key != "sources" and f[key] is None):
                err(None, f"missing required field {key}")
        entry_id = f.get("id")
        if entry_id is not None:
            entry_id = str(entry_id)
            if entry_id != stem:
                err(None, f"id {entry_id!r} differs from the filename stem {stem!r}")
            if not ENTRY_ID_RE.match(entry_id):
                err(None, "id must match pb-[a-z0-9-]+")
            if entry_id in ids:
                err(None, f"duplicate id {entry_id!r} (also in {ids[entry_id]})")
            else:
                ids[entry_id] = rel
        if f.get("type") not in (None, "playbook-entry"):
            err(None, "type must be playbook-entry")
        if "updated" in f and f["updated"] is not None and not isinstance(f["updated"], datetime.date):
            err(None, "updated must be a date (YYYY-MM-DD)")
        status = f.get("status")
        if status is not None and status not in STATUSES:
            err(None, f"status {status!r} must be draft, reviewed, or superseded")
        sources = f.get("sources") if f.get("sources") is not None else []
        if not isinstance(sources, list):
            err(None, "sources must be a list of catalog stems")
            sources = []
        if not sources and status not in (None, "draft"):
            err(None, "sources may be empty only while status is draft")
        for source in sources:
            if source not in self.catalog:
                err(None, f"source {source!r} has no catalog record")
        superseded_by = f.get("superseded_by")
        if status == "superseded":
            if superseded_by in (None, ""):
                err(None, "a superseded entry needs superseded_by")
            elif str(superseded_by) not in self.entry_stems:
                err(None, f"superseded_by {superseded_by!r} does not resolve to an entry")
        elif superseded_by not in (None, ""):
            err(None, "superseded_by is allowed only when status is superseded")
        body = "\n".join(text.split("\n")[body_line - 1:])
        tags, tag_errors = kbparse.find_tags(body, body_line)
        for line, message in tag_errors[:MAX_TAG_FINDINGS]:
            err(line, message)
        if len(tag_errors) > MAX_TAG_FINDINGS:
            err(None, f"{len(tag_errors) - MAX_TAG_FINDINGS} further tag errors omitted")
        missing = [(t.line, c) for t in tags for c in t.conflict or [] if c not in self.catalog]
        for line, conflict_stem in missing[:MAX_TAG_FINDINGS]:
            err(line, f"conflict note names {conflict_stem!r}, which has no catalog record")
        has_v = any(t.letter == "V" for t in tags)
        if status == "reviewed":
            if not has_v:
                err(None, "a reviewed entry needs at least one [V] claim")
            if tag_errors:
                err(None, "a reviewed entry cannot have tag errors")
            if stem not in self.reviewed.get(info["domain"], set()):
                err(None, "a reviewed entry needs a Reviewed: line in a closed wave of the domain log")
        if has_v:
            for source in sources:
                if self.catalog.get(source, {}).get("state") == "recorded":
                    self.report.warn(rel, f"has a [V] claim but cites {source}, whose state is recorded")
        self.check_headings(rel, body, body_line)
        if "REPLACE_WITH_" in text:
            err(None, "contains REPLACE_WITH_ text")
        refs = self.references(rel, text)
        info["refs"] = refs

    def check_headings(self, rel, body, body_line):
        headings, in_fence = [], False
        for line in body.split("\n"):
            if re.match(r"^ {0,3}(```|~~~)", line):
                in_fence = not in_fence
            elif not in_fence and line.startswith("## "):
                headings.append(line[3:].strip())
        last = -1
        for name in REQUIRED_HEADINGS:
            position = next((i for i, h in enumerate(headings)
                             if h == name or re.fullmatch(re.escape(name) + r" \(.+\)", h)), None)
            if position is None:
                self.report.error(rel, None, f"missing required heading {name!r}")
            elif position < last:
                self.report.error(rel, None, f"heading {name!r} is out of order")
            else:
                last = position

    def references(self, rel, text):
        """Return the set of entry paths referenced by a file; report broken references."""
        found = set()
        too_long = False
        for number, line in enumerate(text.split("\n"), start=1):
            if len(line) > MAX_LINE:
                if not too_long:
                    self.report.error(rel, number, f"line is too long to check (over {MAX_LINE} characters)")
                    too_long = True
                continue
            for target in LINK_RE.findall(line):
                target = target.split("#", 1)[0]
                if "://" in target or not ENTRY_LINK_RE.search(target):
                    continue
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
                if ENTRY_PATH_RE.match(resolved) and resolved in self.entries:
                    found.add(resolved)
                else:
                    self.report.error(rel, number, f"entry link does not resolve: {target}")
            for entry_id in BACKTICK_ID_RE.findall(line):
                if entry_id in self.entry_stems:
                    found.update(self.entry_stems[entry_id])
                else:
                    self.report.error(rel, number, f"reference `{entry_id}` does not resolve")
        return found

    # ---- routers --------------------------------------------------------------------

    def check_domain_router(self, domain):
        rel = f"domains/{domain}/playbook/README.md"
        text = self.read(rel) if self._lstat(rel) else None
        if text is None:
            if not self._lstat(rel):
                self.report.error(rel, None, "domain router is missing")
            return
        if "REPLACE_WITH_" in text:
            self.report.error(rel, None, "contains REPLACE_WITH_ text")
        referenced = self.references(rel, text)
        self.check_table(rel, text, require=True)
        for entry_rel, info in sorted(self.entries.items()):
            if info["domain"] != domain:
                continue
            if info.get("status") == "superseded":
                if entry_rel in referenced:
                    self.report.error(entry_rel, None, "a superseded entry is referenced from the domain router")
            elif entry_rel not in referenced and "status" in info:
                self.report.error(entry_rel, None, "entry is not referenced from the domain router")

    def check_table(self, rel, text, require):
        lines = [l if len(l) <= MAX_LINE else "" for l in text.split("\n")]
        for i, line in enumerate(lines[:-1]):
            if line.startswith("|") and re.match(r"^\|[\s:|-]+\|\s*$", lines[i + 1]):
                width = line.count("|") - 1
                for j in range(i + 2, len(lines)):
                    if not lines[j].startswith("|"):
                        break
                    if lines[j].count("|") - 1 != width:
                        self.report.error(rel, j + 1, f"row has a different number of columns than the header ({width})")
                return
        if require:
            self.report.error(rel, None, "domain router has no table")

    def check_root_router(self):
        rel = "playbook/README.md"
        if not self._lstat(rel):
            self.report.error(rel, None, "root router is missing")
            return
        text = self.read(rel)
        if text is None:
            return
        lines = text.split("\n")
        try:
            begin = lines.index("<!-- BEGIN kb:domains -->")
            end = lines.index("<!-- END kb:domains -->")
        except ValueError:
            self.report.error(rel, None, "the kb:domains markers are missing")
            return
        if begin >= end:
            self.report.error(rel, None, "the kb:domains markers are out of order")
            return
        if lines[begin + 1:begin + 2] != [ROOT_HEADER]:
            self.report.error(rel, begin + 2, f"the table header must be exactly {ROOT_HEADER!r}")
        seen = {}
        for index in range(begin + 3, end):
            line = lines[index]
            if not line.strip():
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]] if line.startswith("|") else []
            if len(cells) != 3:
                self.report.error(rel, index + 1, f"row has {len(cells)} columns, expected 3")
                continue
            domain = cells[0]
            seen[domain] = seen.get(domain, 0) + 1
            link = re.match(r"^\[[^\]]+\]\(([^)]+)\)$", cells[1])
            expected = f"domains/{domain}/playbook/README.md"
            if not link or posixpath.normpath(posixpath.join("playbook", link.group(1))) != expected:
                self.report.error(rel, index + 1, f"the second column must be a link to {expected}")
            if domain not in self.domains:
                self.report.error(rel, index + 1, f"lists unknown domain {domain!r}")
        for domain, count in seen.items():
            if count > 1:
                self.report.error(rel, None, f"domain {domain!r} is listed more than once")
        for domain in self.domains:
            if domain not in seen:
                self.report.error(f"domains/{domain}", None, f"domain {domain!r} is not in the root router")


def check(root, require_sources=False):
    """Check the project at root; return a Report with .errors and .warnings."""
    return Checker(str(root), require_sources).run()


def scrub(text):
    """Escape control characters so a hostile file name cannot drive the terminal."""
    return "".join(c if c.isprintable() else ascii(c)[1:-1] for c in str(text))


def format_finding(kind, finding):
    where = finding.path if not finding.line else f"{finding.path}:{finding.line}"
    return scrub(f"{kind} {where}: {finding.message}")


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Validate a knowledge-base project.")
    parser.add_argument("--root", default=os.path.dirname(here), help="project root (default: parent of tools/)")
    parser.add_argument("--require-sources", action="store_true",
                        help="treat missing saved source files as failures (default: warnings)")
    args = parser.parse_args(argv)
    try:
        report = check(args.root, args.require_sources)
    except Exception as exc:  # a crash must be a reported failure, not a traceback
        print(f"ERROR the checker failed internally ({type(exc).__name__}); the project was not fully checked")
        return 2
    for finding in report.errors:
        print(format_finding("ERROR", finding))
    for finding in report.warnings:
        print(format_finding("WARNING", finding))
    print(f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
