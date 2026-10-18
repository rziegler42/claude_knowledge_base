#!/usr/bin/env python3
"""Scaffold a playbook entry (docs/kb/domain-lifecycle.md, operation 2, step 6).

    python3 tools/new_entry.py <domain> <slug> [--title "Title"] [--root DIR]

Creates domains/<domain>/playbook/entries/pb-<slug>.md from tools/templates/entry.md and adds a
stub row to the domain router. Both hold REPLACE_WITH_ text that the check rejects until a person
fills it in. The domain's charter must be set. The router is checked before anything is written; the
entry is written first and the router row second, so an interruption leaves an entry the check names
and the tool prints the one row to add. Standard library only.
"""
import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbfiles  # noqa: E402
import kblife  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "entry.md")
MAX_FILE = 1024 * 1024
ROW_PLACEHOLDER = "REPLACE_WITH_SITUATION"


def entry_row(entry_id):
    return f"| {ROW_PLACEHOLDER} | [{entry_id}](entries/{entry_id}.md) |"


def with_router_row(text, entry_id):
    """The domain router with a stub row added after its table, or a refusal."""
    lines = text.split("\n")
    for index in range(len(lines) - 1):
        if lines[index].startswith("|") and re.match(r"^\|[\s:|-]+\|\s*$", lines[index + 1]):
            last = index + 1
            while last + 1 < len(lines) and lines[last + 1].startswith("|"):
                last += 1
            lines.insert(last + 1, entry_row(entry_id))
            return "\n".join(lines)
    raise kbfiles.KbFileError("the domain router has no table to add a row to")


def existing_domains(root):
    domains = os.path.join(root, "domains")
    for name in sorted(os.listdir(domains)):
        if name.startswith(".") or name == "_skeleton":
            continue
        yield name


def find_duplicate(root, entry_id):
    for name in existing_domains(root):
        if os.path.lexists(os.path.join(root, "domains", name, "playbook", "entries", f"{entry_id}.md")):
            return name
    return None


def main(argv=None, today=None):
    parser = argparse.ArgumentParser(description="Scaffold a playbook entry and a router stub.")
    parser.add_argument("domain")
    parser.add_argument("slug", help="lowercase letters, digits, and hyphens; the entry id is pb-<slug>")
    parser.add_argument("--title", help="fill in the title now")
    parser.add_argument("--root", help="the store root (default: the parent of this tool's directory)")
    args = parser.parse_args(argv)
    today = today or datetime.date.today()
    try:
        root = kbfiles.find_root(args.root, os.path.dirname(os.path.abspath(__file__)))
        if not kbfiles.valid_name(args.domain) or args.domain == "_skeleton":
            raise kbfiles.KbFileError("the domain name is not valid")
        if not kbfiles.valid_name(args.slug) or len("pb-" + args.slug) > kbfiles.MAX_NAME:
            raise kbfiles.KbFileError("the slug uses lowercase letters, digits, and hyphens (the entry id pb-<slug> "
                                      "is at most 100 characters)")
        if args.title is not None:
            kblife.validate_title(args.title)
        entry_id = f"pb-{args.slug}"
        base = os.path.join(root, "domains", args.domain)
        kbfiles.real_dir(os.path.join(root, "domains"), "domains/")
        kbfiles.real_dir(base, f"domains/{args.domain}/")
        charter = kblife.charter_issues(kbfiles.read_text(os.path.join(base, "README.md"), MAX_FILE))
        if charter.state != "set" or charter.issues:
            reason = charter.issues[0].message if charter.issues else "the charter is a draft"
            raise kbfiles.KbFileError(f"domains/{args.domain} has no complete, set charter ({reason}); "
                                      "finish its README.md and set `charter: set` first")
        kbfiles.real_dir(os.path.join(base, "playbook"), f"domains/{args.domain}/playbook/")
        kbfiles.real_dir(os.path.join(base, "playbook", "entries"), f"domains/{args.domain}/playbook/entries/")
        router_path = os.path.join(base, "playbook", "README.md")
        other = find_duplicate(root, entry_id)
        if other:
            hint = ""
            if other == args.domain:
                try:
                    if f"entries/{entry_id}.md" not in kbfiles.read_text(router_path, MAX_FILE):
                        hint = (f"; its row is missing from domains/{args.domain}/playbook/README.md "
                                f"(an earlier run was cut short), so add this row to its table: {entry_row(entry_id)}")
                except (kbfiles.KbFileError, OSError):
                    pass
            raise kbfiles.KbFileError(f"entry {entry_id} already exists in domain {other}{hint}")
        router = with_router_row(kbfiles.read_text(router_path, MAX_FILE), entry_id)
        template = kbfiles.read_text(TEMPLATE, MAX_FILE)
        entry = template.replace("@ID@", entry_id).replace("@DATE@", today.isoformat())
        if args.title is not None:
            entry = entry.replace('title: "REPLACE_WITH_TITLE"', f"title: {kblife.fm_value(args.title)}")
            entry = entry.replace("# REPLACE_WITH_TITLE", f"# {args.title}")
        entry_path = os.path.join(base, "playbook", "entries", f"{entry_id}.md")
        kbfiles.write_atomic(entry_path, entry.encode("utf-8"))
    except (kbfiles.KbFileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote domains/{args.domain}/playbook/entries/{entry_id}.md")
    try:
        kbfiles.write_atomic(router_path, router.encode("utf-8"))
    except (kbfiles.KbFileError, OSError) as exc:
        print(f"error: the entry was created, but the domain router could not be updated: {exc}", file=sys.stderr)
        print(f"To finish, add this row to the table in domains/{args.domain}/playbook/README.md:", file=sys.stderr)
        print(entry_row(entry_id), file=sys.stderr)
        return 1
    print(f"updated domains/{args.domain}/playbook/README.md")
    print("Fill in the REPLACE_WITH_ text in both files (the check rejects it), tag every claim [V], [A], or [U], "
          "and list the sources in `sources:`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
