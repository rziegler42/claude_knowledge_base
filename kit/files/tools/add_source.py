#!/usr/bin/env python3
"""Save a source and record it in the catalog (docs/kb/domain-lifecycle.md, operation 2, step 3).

    python3 tools/add_source.py <stem> <file.pdf> --title "Title" [options]
    python3 tools/add_source.py <stem> --record-only --title "Title" --note "why not saved" [options]
    python3 tools/add_source.py <stem> <new.pdf> --replace

Copies a PDF to sources/<stem>.pdf, computes its SHA-256, and writes catalog/<stem>.md with
`state: saved` and `scan: none`. A source that is not saved (a link, a site, a repository) is
recorded with `state: recorded`. `--replace` swaps in a changed file: it updates `sha256`, resets
`state` and `scan`, removes `released`, and sets `replaced`. The file is copied first and the record
written second, and a rerun with the same file finishes an interrupted run. Nothing is deleted, no
file is parsed, and a quarantined stem is refused. Standard library only.
"""
import argparse
import datetime
import hashlib
import os
import re
import secrets
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kbfiles  # noqa: E402
import kblife  # noqa: E402
import kbparse  # noqa: E402

MAX_SOURCE = 200 * 1024 * 1024
MAX_RECORD = 1024 * 1024
KINDS = ("document", "site", "repo")
TIERS = ("primary", "secondary", "practitioner", "community", "unknown")
CONFIRMED = ("full", "abstract", "snippet", "memory")
URL_RE = re.compile(r"^https?://[^\s\"'<>\\]{1,2000}\Z")


def parse_date(text):
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from None


def plain_text(label, value, maximum):
    if (not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > maximum
            or not value.isprintable() or kbparse.bad_chars(value)):
        raise kbfiles.KbFileError(f"{label} must be 1 to {maximum} printable characters on one line, with no "
                                  "invisible characters and no space at either end")
    return value


def check_file(path):
    """Refuse anything but a regular, PDF-looking file of a sane size; return its size."""
    if not path.lower().endswith(".pdf"):
        raise kbfiles.KbFileError("only PDF files can be saved so far; use --record-only to record this source "
                                  "as a link without a file")
    head = kbfiles.read_head(path, 1024)  # refuses a symlink, a special file, or a directory
    if b"%PDF-" not in head:
        raise kbfiles.KbFileError(f"{os.path.basename(path)} does not start like a PDF; refused")
    size = os.lstat(path).st_size
    if size > MAX_SOURCE:
        raise kbfiles.KbFileError(f"{os.path.basename(path)} is larger than {MAX_SOURCE} bytes; refused")
    return size


def copy_pdf(src, dest, expected=None):
    """Copy src to dest through a temporary sibling and a rename; return the SHA-256 of what was copied.
    With `expected`, a copy whose hash differs (the source changed after it was hashed) is discarded
    before the rename, so the destination is left as it was."""
    fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise kbfiles.KbFileError(f"{os.path.basename(src)} is not a regular file; refused")
        temp = os.path.join(os.path.dirname(dest), f"{kbfiles.TEMP_PREFIX}{os.getpid()}-{secrets.token_hex(4)}")
        out_fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        digest, total = hashlib.sha256(), 0
        try:
            with os.fdopen(out_fd, "wb") as out:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    if total == 0 and b"%PDF-" not in block[:1024]:
                        raise kbfiles.KbFileError(f"{os.path.basename(src)} does not start like a PDF; refused")
                    total += len(block)
                    if total > MAX_SOURCE:
                        raise kbfiles.KbFileError(f"{os.path.basename(src)} is larger than {MAX_SOURCE} bytes; refused")
                    digest.update(block)
                    out.write(block)
            if expected is not None and digest.hexdigest() != expected:
                raise kbfiles.KbFileError(f"{os.path.basename(src)} changed while it was copied; nothing was replaced")
            os.replace(temp, dest)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise
    return digest.hexdigest()


def regular_or_absent(path, what):
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise kbfiles.KbFileError(f"{what} is a symlink or not a regular file; refused")
    return True


def record_text(fields, note):
    return kblife.front_matter(fields) + (f"\n{note}\n" if note else "")


def main(argv=None, today=None):
    parser = argparse.ArgumentParser(description="Save a PDF source and record it in the catalog.")
    parser.add_argument("stem", help="the catalog stem")
    parser.add_argument("file", nargs="?", help="the PDF to save")
    parser.add_argument("--title")
    parser.add_argument("--kind", choices=KINDS, default="document")
    parser.add_argument("--author", action="append", default=[], help="an author or owner (repeat for more)")
    parser.add_argument("--url")
    parser.add_argument("--retrieved", type=parse_date, help="date retrieved (default: today)")
    parser.add_argument("--confirmed", choices=CONFIRMED)
    parser.add_argument("--tier", choices=TIERS, default="unknown")
    parser.add_argument("--note", help="a one-line note for the record body")
    parser.add_argument("--record-only", action="store_true", help="record a source that is not saved as a file")
    parser.add_argument("--replace", action="store_true", help="replace the saved file of an existing record")
    parser.add_argument("--root", help="the store root (default: the parent of this tool's directory)")
    args = parser.parse_args(argv)
    today = today or datetime.date.today()
    if not args.replace and not args.title:
        parser.error("--title is required for a new record")
    try:
        return run(args, today)
    except (kbfiles.KbFileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def run(args, today):
    root = kbfiles.find_root(args.root, os.path.dirname(os.path.abspath(__file__)))
    if not kbparse.valid_stem(args.stem):
        raise kbfiles.KbFileError("a stem uses lowercase letters, digits, and hyphens (at most 100 characters) "
                                  "and is not readme or quarantine")
    if args.replace and args.record_only:
        raise kbfiles.KbFileError("--replace and --record-only cannot be combined")
    sources, catalog = os.path.join(root, "sources"), os.path.join(root, "catalog")
    kbfiles.real_dir(sources, "sources/")
    kbfiles.real_dir(catalog, "catalog/")
    dest = os.path.join(sources, f"{args.stem}.pdf")
    record_path = os.path.join(catalog, f"{args.stem}.md")
    if os.path.lexists(os.path.join(sources, "quarantine", f"{args.stem}.pdf")):
        raise kbfiles.KbFileError(f"{args.stem} is in sources/quarantine/; the owner reviews and releases it first")
    fields_only = [("title", args.title, 500), ("note", args.note, 500)]
    for label, value, maximum in fields_only:
        if value is not None:
            plain_text(label, value, maximum)
    for author in args.author:
        plain_text("an author", author, 200)
    if args.url is not None and (not URL_RE.match(args.url) or kbparse.bad_chars(args.url)):
        raise kbfiles.KbFileError("the url must be an http or https address with no spaces or invisible characters")
    if args.replace:
        return replace(args, today, dest, record_path)
    if args.record_only or args.kind in ("site", "repo"):
        return record_only(args, today, record_path)
    return save_new(args, today, dest, record_path)


def new_fields(args, today, sha):
    fields = {"stem": args.stem, "kind": args.kind, "title": args.title}
    if args.author:
        fields["authors"] = list(args.author)
    if args.url:
        fields["url"] = args.url
    fields["retrieved"] = args.retrieved or today
    if sha:
        fields["sha256"] = sha
    fields["confirmed"] = args.confirmed or ("full" if sha else None)
    fields["tier"] = args.tier
    fields["state"] = "saved" if sha else "recorded"
    fields["scan"] = "none"
    return fields


def save_new(args, today, dest, record_path):
    if not args.file:
        raise kbfiles.KbFileError("give the PDF to save, or use --record-only")
    if os.path.lexists(record_path):
        raise kbfiles.KbFileError(f"catalog/{args.stem}.md already exists; use --replace to swap in a changed file")
    check_file(args.file)
    copied = False
    if regular_or_absent(dest, f"sources/{args.stem}.pdf"):
        sha = kbfiles.sha256_file(args.file)
        if kbfiles.sha256_file(dest) != sha:
            raise kbfiles.KbFileError(f"sources/{args.stem}.pdf already exists with different content; "
                                      "move it aside or choose another stem")
    else:
        sha = copy_pdf(args.file, dest)
        copied = True
    text = record_text(new_fields(args, today, sha), args.note)
    try:
        kbfiles.write_atomic(record_path, text.encode("utf-8"))
    except (kbfiles.KbFileError, OSError) as exc:
        raise kbfiles.KbFileError(f"{exc}; sources/{args.stem}.pdf is in place, so run the same command again "
                                  "to write the record") from None
    if copied:
        print(f"wrote sources/{args.stem}.pdf")
    print(f"wrote catalog/{args.stem}.md (state saved, sha256 {sha})")
    print("Run the converter next: <interpreter> tools/convert_sources.py")
    return 0


def record_only(args, today, record_path):
    if args.file:
        raise kbfiles.KbFileError("a link-only record takes no file; drop the file or drop --record-only")
    if os.path.lexists(record_path):
        raise kbfiles.KbFileError(f"catalog/{args.stem}.md already exists")
    if args.kind in ("site", "repo"):
        if not args.url:
            raise kbfiles.KbFileError(f"a {args.kind} record needs --url")
    elif not args.note:
        raise kbfiles.KbFileError("a link-only document needs --note saying why it is not saved")
    if not args.confirmed:
        raise kbfiles.KbFileError("say how the source was confirmed with --confirmed (abstract, snippet, or memory)")
    text = record_text(new_fields(args, today, None), args.note)
    kbfiles.write_atomic(record_path, text.encode("utf-8"))
    print(f"wrote catalog/{args.stem}.md (state recorded)")
    return 0


def replace(args, today, dest, record_path):
    if not args.file:
        raise kbfiles.KbFileError("--replace needs the new PDF")
    if not regular_or_absent(record_path, f"catalog/{args.stem}.md"):
        raise kbfiles.KbFileError(f"catalog/{args.stem}.md does not exist; --replace changes an existing record")
    text = kbfiles.read_text(record_path, MAX_RECORD)
    try:
        record, _ = kbparse.parse_front_matter(text)
    except kbparse.FrontMatterError as exc:
        raise kbfiles.KbFileError(f"catalog/{args.stem}.md has invalid front matter ({exc.message})") from None
    if record.get("kind") != "document":
        raise kbfiles.KbFileError(f"{args.stem} is a {record.get('kind')} record and has no file to replace")
    if record.get("scan") == "flagged" and record.get("released") is None:
        raise kbfiles.KbFileError(f"{args.stem} is flagged and awaiting the owner's review; it cannot be replaced")
    check_file(args.file)
    exists = regular_or_absent(dest, f"sources/{args.stem}.pdf")
    new_sha = kbfiles.sha256_file(args.file)
    saved_sha = kbfiles.sha256_file(dest) if exists else None
    if record.get("sha256") == new_sha:
        if saved_sha == new_sha:
            print(f"{args.stem}: this is already the saved file; nothing to do")
        else:
            copy_pdf(args.file, dest, expected=new_sha)
            print(f"{'repaired' if exists else 'restored'} sources/{args.stem}.pdf (the record already has this hash)")
        return 0
    if saved_sha == new_sha:
        digest = new_sha
    else:
        digest = copy_pdf(args.file, dest, expected=new_sha)
        print(f"wrote sources/{args.stem}.pdf")
    updates = {"sha256": digest, "state": "saved", "scan": "none", "released": None, "replaced": today}
    try:
        new_text = kblife.edit_front_matter(text, updates)
        kbfiles.write_atomic(record_path, new_text.encode("utf-8"))
    except (kbfiles.KbFileError, OSError) as exc:
        raise kbfiles.KbFileError(f"{exc}; sources/{args.stem}.pdf is in place, so run the same command "
                                  "again to update the record") from None
    print(f"updated catalog/{args.stem}.md (state saved, scan none, replaced {today.isoformat()}, sha256 {digest})")
    print("Entries that cite this source need re-verification; kb_status.py lists them. "
          "Run the converter to convert the new file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
