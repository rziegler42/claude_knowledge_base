#!/usr/bin/env python3
"""Report what a domain has and lacks (docs/kb/domain-lifecycle.md, operation 3, step 1).

    python3 tools/kb_status.py [domain] [--json] [--stale-days N] [--root DIR]

Read-only: it writes nothing and never changes an entry's status or tags. Age is the only signal
for a stale entry. A file it cannot read or parse is listed under `problems`, not fatal; a source
whose file is not in this clone is listed as `unsaved`, not as a failure. `--json` prints one
object with `schema: 1` and sorted keys. Standard library only.
"""
import argparse
import datetime
import json
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbfiles  # noqa: E402
import kblife  # noqa: E402
import kbparse  # noqa: E402

SCHEMA = 1
MAX_FILE = 1024 * 1024
MAX_RECORDS = 100000
SAVED_STATES = ("saved", "converted", "read")


def counts(values):
    result = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items(), key=lambda item: str(item[0])))


def scrub(text):
    """Escape control characters, so source-derived text cannot drive the terminal."""
    return "".join(c if c.isprintable() else ascii(c)[1:-1] for c in str(text))


def chain_ok(root, rel, problems, include_last=False):
    """True when every directory from the store root down to rel (or to rel's parent) is a real
    directory, so a symlinked folder inside a domain is never followed."""
    parts = rel.split("/")
    if not include_last:
        parts = parts[:-1]
    current = root
    for index, part in enumerate(parts):
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
        except OSError:
            return False
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            problems.append(f"{'/'.join(parts[:index + 1])}: is a symlink or not a directory; not read")
            return False
    return True


def read(root, rel, problems):
    if not chain_ok(root, rel, problems):
        return None
    try:
        return kbfiles.read_text(os.path.join(root, *rel.split("/")), MAX_FILE)
    except (kbfiles.KbFileError, OSError) as exc:
        problems.append(f"{rel}: {exc}")
        return None


def exists(root, rel):
    try:
        os.lstat(os.path.join(root, *rel.split("/")))
        return True
    except OSError:
        return False


def listing(root, rel, problems):
    if not chain_ok(root, rel, problems, include_last=True):
        return []
    try:
        names = sorted(os.listdir(os.path.join(root, *rel.split("/"))))
    except OSError:
        return []
    if len(names) > MAX_RECORDS:
        problems.append(f"{rel}: too many entries; only the first {MAX_RECORDS} are read")
        names = names[:MAX_RECORDS]
    return names


def load_catalog(root, problems):
    records = {}
    for name in listing(root, "catalog", problems):
        if not name.endswith(".md") or name == "README.md" or name.startswith("."):
            continue
        stem, rel = name[:-3], f"catalog/{name}"
        text = read(root, rel, problems)
        if text is None:
            continue
        try:
            data, _ = kbparse.parse_front_matter(text)
        except kbparse.FrontMatterError as exc:
            problems.append(f"{rel}: invalid front matter ({exc.message})")
            continue
        if data.get("stem") != stem:
            problems.append(f"{rel}: the stem does not match the file name")
            continue
        for key in ("kind", "state", "tier", "scan"):
            if not isinstance(data.get(key), str):
                problems.append(f"{rel}: {key} must be text; reported as invalid")
                data[key] = "invalid"
        records[stem] = data
    return records


def has_file(root, stem, quarantined=False):
    base = os.path.join(root, "sources", "quarantine") if quarantined else os.path.join(root, "sources")
    path = os.path.join(base, f"{stem}.pdf")
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def source_report(root, stems, catalog):
    known = [s for s in stems if s in catalog]
    flagged = [s for s in known if catalog[s].get("scan") == "flagged" and catalog[s].get("released") is None]
    unsaved = [s for s in known if catalog[s].get("state") in SAVED_STATES
               and not has_file(root, s, quarantined=s in flagged) and not has_file(root, s)]
    return {
        "listed": sorted(stems),
        "no_record": sorted(s for s in stems if s not in catalog),
        "by_state": counts(catalog[s].get("state") for s in known),
        "by_tier": counts(catalog[s].get("tier") for s in known),
        "by_scan": counts(catalog[s].get("scan") for s in known),
        "recorded_never_saved": sorted(s for s in known if catalog[s].get("state") == "recorded"
                                       and catalog[s].get("kind") == "document"),
        "quarantined": sorted(flagged),
        "unsaved": sorted(unsaved),
    }


def entry_info(root, name, problems, rel_base):
    rel = f"{rel_base}/{name}"
    text = read(root, rel, problems)
    if text is None:
        return None
    try:
        front, first = kbparse.parse_front_matter(text)
    except kbparse.FrontMatterError as exc:
        problems.append(f"{rel}: invalid front matter ({exc.message})")
        return None
    body = "\n".join(text.split("\n")[first - 1:])
    tags, errors = kbparse.find_tags(body, first)
    letters = counts(t.letter for t in tags)
    sources = front.get("sources")
    updated = front.get("updated")
    conflicts = [{"line": t.line, "stems": list(t.conflict)} for t in tags if t.conflict and len(t.conflict) >= 2]
    malformed = [{"line": line} for line, message in errors if "conflict note must name at least two stems" in message]
    status = front.get("status")
    if not isinstance(status, str):
        problems.append(f"{rel}: status must be text; reported as invalid")
        status = "invalid"
    return {
        "id": name[:-3],
        "status": status,
        "sources": [str(x) for x in sources] if isinstance(sources, list) else [],
        "updated": updated if isinstance(updated, datetime.date) else None,
        "tags": {letter: letters.get(letter, 0) for letter in "VAU"},
        "conflicts": conflicts,
        "malformed": malformed,
    }


def load_entries(root, domain, problems):
    rel_base = f"domains/{domain}/playbook/entries"
    entries = []
    for name in listing(root, rel_base, problems):
        if not name.endswith(".md") or name.startswith("."):
            continue
        info = entry_info(root, name, problems, rel_base)
        if info:
            entries.append(info)
    return entries


def judge_waves(log):
    """How each closed wave that opened with Gaps: fared, by the rules in the lifecycle specification."""
    opened = {e.number: e for e in log.entries if e.kind == "opened"}
    judged = []
    for entry in log.entries:
        if entry.kind != "closed" or entry.number not in opened or "Gaps" not in opened[entry.number].fields:
            continue
        gaps = kblife.parse_gaps(opened[entry.number].fields["Gaps"])
        result = kblife.parse_gap_result(entry.fields.get("Gap result", ""))
        categories, problems = {}, []
        if gaps is None or result is None:
            problems.append("the Gaps or Gap result line is missing or malformed")
        else:
            for category in sorted(set(gaps) | set(result)):
                if category not in result or category not in gaps:
                    problems.append(f"{category} is in only one of Gaps and Gap result")
                    continue
                value = result[category]
                if isinstance(value, tuple):
                    if value[1]:
                        categories[category] = f"unchanged: {value[1]}"
                    else:
                        categories[category] = "unchanged"
                        problems.append(f"{category} is unchanged without a reason")
                elif value < gaps[category]:
                    categories[category] = "fell"
                else:
                    categories[category] = "rose or stayed"
                    problems.append(f"{category} did not fall and is not marked unchanged: <reason>")
        item = {"wave": entry.number, "result": "problem" if problems else "ok", "categories": categories}
        if problems:
            item["problems"] = problems
        judged.append(item)
    return judged


def usage_report(root, rel_base, problems):
    tests = []
    for name in listing(root, rel_base, problems):
        if not name.endswith(".md") or name.startswith("."):
            continue
        text = read(root, f"{rel_base}/{name}", problems)
        if text is None:
            continue
        parsed = kblife.usage_test_issues(text)
        if parsed.issues:
            problems.append(f"{rel_base}/{name}: {parsed.issues[0].message}")
            continue
        scenario = kbparse.parse_front_matter(text)[0].get("scenario")
        tests.append((parsed.date, name, parsed.result, scenario))
    tests.sort()
    unresolved = 0
    for date, name, result, scenario in tests:
        if result != "pass" and not any(s == scenario and r == "pass" and (d, n) > (date, name)
                                        for d, n, r, s in tests):
            unresolved += 1
    latest = None
    if tests:
        date, name, result, scenario = tests[-1]
        latest = {"date": date.isoformat(), "result": result, "scenario": scenario}
    return {"count": len(tests), "latest": latest, "unresolved": unresolved}


def domain_report(root, domain, catalog, stale_days, today, problems):
    rel = f"domains/{domain}"
    charter_text = read(root, f"{rel}/README.md", problems)
    charter = kblife.charter_issues(charter_text).state if charter_text is not None else None
    stems_text = read(root, f"{rel}/index/sources.md", problems) if exists(root, f"{rel}/index/sources.md") else ""
    stems = [s for s, _ in kblife.index_stems(stems_text or "")[0]] if stems_text else []
    entries = load_entries(root, domain, problems)
    live = [e for e in entries if e["status"] != "superseded"]
    cited = {s for e in entries for s in e["sources"]}
    sources = source_report(root, sorted(set(stems)), catalog)
    sources["uncited"] = sorted(s for s in sources["listed"] if s not in cited)

    reverify = []
    for entry in live:
        for stem in entry["sources"]:
            replaced = catalog.get(stem, {}).get("replaced")
            if isinstance(replaced, datetime.date) and entry["updated"] and entry["updated"] < replaced:
                reverify.append(entry["id"])
                break
    stale = [e["id"] for e in live if e["updated"] and (today - e["updated"]).days > stale_days]
    no_verified = [e["id"] for e in live if e["tags"]["V"] == 0]
    open_conflicts = [{"entry": e["id"], "line": c["line"], "stems": c["stems"]} for e in live for c in e["conflicts"]]
    malformed = [{"entry": e["id"], "line": m["line"]} for e in live for m in e["malformed"]]

    questions = {"open": [], "partial": [], "answered": []}
    q_text = read(root, f"{rel}/questions.md", problems) if exists(root, f"{rel}/questions.md") else None
    if q_text is not None:
        for row in kblife.parse_questions(q_text).rows:
            if row.status in questions:
                questions[row.status].append(row.id)
    waves = {"open": [], "abandoned": [], "judged": []}
    log_text = read(root, f"{rel}/log.md", problems) if exists(root, f"{rel}/log.md") else None
    if log_text is not None:
        log = kblife.parse_log(log_text)
        waves = {"open": kblife.open_waves(log), "abandoned": kblife.abandoned_waves(log), "judged": judge_waves(log)}
    leads_text = read(root, f"{rel}/index/leads.md", problems) if exists(root, f"{rel}/index/leads.md") else None
    leads = len(kblife.table_rows(leads_text)[0]) if leads_text else 0
    usage = usage_report(root, f"{rel}/usage-tests", problems)

    by_status = counts(e["status"] for e in entries)
    return {
        "charter": charter,
        "sources": sources,
        "entries": {
            "by_status": by_status,
            "tags": {e["id"]: e["tags"] for e in entries},
            "no_verified": sorted(no_verified),
            "reverify": sorted(reverify),
            "stale": sorted(stale),
            "stale_days": stale_days,
        },
        "conflicts": {"open": open_conflicts, "malformed": malformed},
        "questions": questions,
        "waves": waves,
        "leads": leads,
        "usage_tests": usage,
        "gaps": {
            "usage-test": usage["unresolved"],
            "open-questions": len(questions["open"]) + len(questions["partial"]),
            "conflicts": len(open_conflicts),
            "reverify": len(reverify),
            "no-verified": len(no_verified),
            "leads": leads,
            "stale": len(stale),
        },
    }


def build_report(root, domain=None, stale_days=365, today=None):
    today = today or datetime.date.today()
    problems = []
    catalog = load_catalog(root, problems)
    kbfiles.real_dir(os.path.join(root, "domains"), "domains/")
    if domain is not None:
        if not kbfiles.valid_name(domain) or domain == "_skeleton":
            raise kbfiles.KbFileError("the domain name is not valid")
        kbfiles.real_dir(os.path.join(root, "domains", domain), f"domains/{domain}/")
        names = [domain]
    else:
        names = []
        for name in listing(root, "domains", problems):
            path = os.path.join(root, "domains", name)
            if name.startswith(".") or name == "_skeleton" or os.path.islink(path) or not os.path.isdir(path):
                continue
            names.append(name)
    domains = {name: domain_report(root, name, catalog, stale_days, today, problems) for name in names}
    project = source_report(root, sorted(catalog), catalog)
    return {"schema": SCHEMA, "domains": domains, "project": project, "problems": sorted(set(problems))}


def render_json(report):
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def listed(items):
    shown = [str(i) for i in items]
    return ", ".join(shown) if shown else "none"


def render_text(report):
    lines = []
    project = report["project"]
    lines.append(f"Project: {len(project['listed'])} catalog records; by state: {listed(f'{k} {v}' for k, v in project['by_state'].items())}")
    lines.append(f"  quarantined (awaiting the owner): {listed(project['quarantined'])}")
    lines.append(f"  unsaved (no file in this clone): {listed(project['unsaved'])}")
    for name, d in report["domains"].items():
        s, e, c = d["sources"], d["entries"], d["conflicts"]
        lines.append("")
        lines.append(f"Domain: {name} (charter: {d['charter'] or 'unreadable'})")
        if d["charter"] == "draft":
            lines.append("  the charter is a draft: set it before adding entries")
        lines.append(f"  sources used: {len(s['listed'])}; by state: {listed(f'{k} {v}' for k, v in s['by_state'].items())}; "
                     f"by tier: {listed(f'{k} {v}' for k, v in s['by_tier'].items())}; "
                     f"by scan: {listed(f'{k} {v}' for k, v in s['by_scan'].items())}")
        lines.append(f"  recorded, never saved: {listed(s['recorded_never_saved'])}")
        lines.append(f"  quarantined (awaiting the owner): {listed(s['quarantined'])}")
        lines.append(f"  unsaved (no file in this clone): {listed(s['unsaved'])}")
        lines.append(f"  listed but cited by no entry: {listed(s['uncited'])}")
        if s["no_record"]:
            lines.append(f"  listed with no catalog record: {listed(s['no_record'])}")
        lines.append(f"  entries: {listed(f'{k} {v}' for k, v in e['by_status'].items())}")
        lines.append(f"  entries with no [V] claim: {listed(e['no_verified'])}")
        lines.append(f"  entries citing a replaced source and not updated since: {listed(e['reverify'])}")
        lines.append(f"  stale entries (older than {e['stale_days']} days): {listed(e['stale'])}")
        q = d["questions"]
        lines.append(f"  open questions: {listed(q['open'])}; partial: {listed(q['partial'])}")
        lines.append("  open conflicts: " + listed(f"{x['entry']} line {x['line']} ({', '.join(x['stems'])})" for x in c["open"]))
        if c["malformed"]:
            lines.append("  malformed conflict notes: " + listed(f"{x['entry']} line {x['line']}" for x in c["malformed"]))
        w = d["waves"]
        lines.append(f"  waves still open: {listed(f'wave {n}' for n in w['open'])}; "
                     f"abandoned: {listed(f'wave {n}' for n in w['abandoned'])}")
        for item in w["judged"]:
            if item["result"] != "ok":
                lines.append(f"  wave {item['wave']} gap result problems: " + "; ".join(item["problems"]))
        lines.append(f"  leads: {d['leads']}")
        u = d["usage_tests"]
        latest = f"{u['latest']['date']} {u['latest']['result']} ({u['latest']['scenario']})" if u["latest"] else "none"
        lines.append(f"  usage tests: {u['count']}; latest: {latest}; unresolved failures: {u['unresolved']}")
        lines.append("  gaps: " + ", ".join(f"{k}={v}" for k, v in d["gaps"].items()))
    if report["problems"]:
        lines.append("")
        lines.append("Problems reading files:")
        lines.extend(f"  {p}" for p in report["problems"])
    return "\n".join(scrub(line) for line in lines) + "\n"


def positive(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a whole number") from None
    if not 0 < value < 100000:
        raise argparse.ArgumentTypeError("must be between 1 and 99999")
    return value


def main(argv=None, today=None):
    parser = argparse.ArgumentParser(description="Report what a domain has and lacks. Read-only.")
    parser.add_argument("domain", nargs="?", help="one domain (default: all)")
    parser.add_argument("--json", action="store_true", help="print one JSON object with sorted keys")
    parser.add_argument("--stale-days", type=positive, default=365, help="entries not updated for more than N days are stale")
    parser.add_argument("--root", help="the store root (default: the parent of this tool's directory)")
    args = parser.parse_args(argv)
    try:
        root = kbfiles.find_root(args.root, os.path.dirname(os.path.abspath(__file__)))
        report = build_report(root, args.domain, args.stale_days, today)
    except (kbfiles.KbFileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(render_json(report) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
