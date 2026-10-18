#!/usr/bin/env python3
"""Create a domain from the skeleton (docs/kb/domain-lifecycle.md, operation 1).

    python3 tools/new_domain.py <name> --title "Human-readable title" [--root DIR]

Copies domains/_skeleton/ to domains/<name>/, sets the domain, title, creation date, and
`charter: draft`, writes the domain router and the first `charter` log entry, and adds the
domain's row between the root-router markers. The charter and the first questions are for a
person to write. The domain is built in a hidden temporary directory and renamed into place in one
step, so a refusal or a failure leaves no half-made domain. Standard library only.
"""
import argparse
import datetime
import os
import secrets
import shutil
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbfiles  # noqa: E402
import kblife  # noqa: E402
import kbparse  # noqa: E402

ROOT_HEADER = "| Domain | Router | Purpose |"
BEGIN, END = "<!-- BEGIN kb:domains -->", "<!-- END kb:domains -->"
MAX_SKELETON_FILE = 1024 * 1024
MAX_SKELETON_FILES = 200
MAX_DEPTH = 8


def validate_name(name):
    if not kbfiles.valid_name(name):
        raise kbfiles.KbFileError("a domain name uses lowercase letters, digits, and hyphens, and does not start "
                                  "with a hyphen (at most 100 characters)")


def read_skeleton(root):
    """{relative path: bytes} for domains/_skeleton, refusing symlinks, special files, and anything unusual."""
    base = os.path.join(root, "domains", "_skeleton")
    kbfiles.real_dir(base, "domains/_skeleton/")
    files = {}

    def visit(directory, prefix, depth):
        if depth > MAX_DEPTH:
            raise kbfiles.KbFileError("domains/_skeleton/ is nested too deeply")
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            rel = prefix + name
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                raise kbfiles.KbFileError(f"domains/_skeleton/{rel} is a symlink; refused")
            if stat.S_ISDIR(st.st_mode):
                visit(path, rel + "/", depth + 1)
            elif stat.S_ISREG(st.st_mode):
                if len(files) >= MAX_SKELETON_FILES:
                    raise kbfiles.KbFileError("domains/_skeleton/ has too many files")
                files[rel] = kbfiles.read_head(path, MAX_SKELETON_FILE + 1)
                if len(files[rel]) > MAX_SKELETON_FILE:
                    raise kbfiles.KbFileError(f"domains/_skeleton/{rel} is too large; refused")
            else:
                raise kbfiles.KbFileError(f"domains/_skeleton/{rel} is a special file; refused")

    visit(base, "", 0)
    for required in ("README.md", "log.md", "questions.md", "playbook/README.md"):
        if required not in files:
            raise kbfiles.KbFileError(f"domains/_skeleton/{required} is missing")
    return files


def fill(rel, data, name, title, today):
    text = data.decode("utf-8")
    if rel == "README.md":
        text = text.replace("domain: REPLACE_WITH_DOMAIN", f"domain: {kblife.fm_value(name)}")
        text = text.replace('title: "REPLACE_WITH_TITLE"', f"title: {kblife.fm_value(title)}")
        text = text.replace("created: 2000-01-01", f"created: {today.isoformat()}")
        text = text.replace("# REPLACE_WITH_TITLE", f"# {title}")
    elif rel == "playbook/README.md":
        text = text.replace("REPLACE_WITH_TITLE", title)
    elif rel == "log.md":
        text = text.rstrip("\n") + (f"\n\n## {today.isoformat()} charter\n\n"
                                    "Change: Created the domain with a draft charter.\nReason: New domain.\n")
    return text.encode("utf-8")


def build_tree(temp, files, name, title, today):
    for rel, data in files.items():
        path = os.path.join(temp, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "xb") as handle:
            handle.write(fill(rel, data, name, title, today))


def root_row(name, title):
    return f"| {name} | [{title}](../domains/{name}/playbook/README.md) | {title} |"


def with_root_row(text, name, title):
    """The root router with the domain's row added before the end marker, or a refusal."""
    lines = text.split("\n")
    try:
        begin, end = lines.index(BEGIN), lines.index(END)
    except ValueError:
        raise kbfiles.KbFileError("playbook/README.md is missing the kb:domains markers") from None
    if begin >= end:
        raise kbfiles.KbFileError("the kb:domains markers in playbook/README.md are out of order")
    if lines[begin + 1:begin + 2] != [ROOT_HEADER]:
        raise kbfiles.KbFileError(f"the root router table header must be exactly {ROOT_HEADER!r}")
    for line in lines[begin + 3:end]:
        cells = [c.strip() for c in line.split("|")[1:-1]] if line.startswith("|") else []
        if cells and cells[0] == name:
            raise kbfiles.KbFileError(f"domain {name!r} is already listed in the root router")
    lines.insert(end, root_row(name, title))
    return "\n".join(lines)


def missing_row_hint(root, router_path, final, name, typed_title):
    """What to add when a domain exists but the root router has no row for it (an earlier run was cut
    short): the row, built from the domain's own title."""
    try:
        text = kbfiles.read_text(router_path, 1024 * 1024)
        with_root_row(text, name, typed_title)  # raises when the domain is already listed
    except (kbfiles.KbFileError, OSError):
        return ""
    title = typed_title
    try:
        front, _ = kbparse.parse_front_matter(kbfiles.read_text(os.path.join(final, "README.md"), 1024 * 1024))
        if isinstance(front.get("title"), str):
            kblife.validate_title(front["title"])
            title = front["title"]
    except (kbfiles.KbFileError, OSError, kbparse.FrontMatterError):
        pass
    return ("; it is not in the root router, so add this row between the kb:domains markers in "
            f"playbook/README.md: {root_row(name, title)}")


def main(argv=None, today=None):
    parser = argparse.ArgumentParser(description="Create a domain from the skeleton.")
    parser.add_argument("name", help="domain name: lowercase letters, digits, and hyphens")
    parser.add_argument("--title", required=True, help="human-readable title")
    parser.add_argument("--root", help="the store root (default: the parent of this tool's directory)")
    args = parser.parse_args(argv)
    today = today or datetime.date.today()
    try:
        root = kbfiles.find_root(args.root, os.path.dirname(os.path.abspath(__file__)))
        validate_name(args.name)
        kblife.validate_title(args.title)
        kbfiles.real_dir(os.path.join(root, "domains"), "domains/")
        kbfiles.real_dir(os.path.join(root, "playbook"), "playbook/")
        final = os.path.join(root, "domains", args.name)
        router_path = os.path.join(root, "playbook", "README.md")
        if os.path.lexists(final):
            raise kbfiles.KbFileError(f"domains/{args.name} already exists; choose another name"
                                      + missing_row_hint(root, router_path, final, args.name, args.title))
        router = with_root_row(kbfiles.read_text(router_path, 1024 * 1024), args.name, args.title)
        files = read_skeleton(root)
        temp = os.path.join(root, "domains", f"{kbfiles.TEMP_PREFIX}{os.getpid()}-{secrets.token_hex(4)}")
        os.mkdir(temp, 0o755)
        try:
            build_tree(temp, files, args.name, args.title, today)
            if os.path.lexists(final):
                raise kbfiles.KbFileError(f"domains/{args.name} appeared while it was being made; refused")
            os.rename(temp, final)
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise
    except (kbfiles.KbFileError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for rel in sorted(files):
        print(f"wrote domains/{args.name}/{rel}")
    try:
        kbfiles.write_atomic(router_path, router.encode("utf-8"))
    except (kbfiles.KbFileError, OSError) as exc:
        print(f"error: the domain was created, but the root router could not be updated: {exc}", file=sys.stderr)
        print("To finish, add this row between the kb:domains markers in playbook/README.md:", file=sys.stderr)
        print(root_row(args.name, args.title), file=sys.stderr)
        return 1
    print("updated playbook/README.md")
    print(f"The charter in domains/{args.name}/README.md is a draft. Fill it in, add at least three questions to "
          "questions.md, then set `charter: set`; entries cannot be added until it is set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
