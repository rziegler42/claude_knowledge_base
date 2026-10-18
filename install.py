#!/usr/bin/env python3
"""Create a knowledge-base project from this starter, or add the layer to an existing one.

    ./install.py ../my-kb --git-name "Your Name" --git-email "id+user@users.noreply.github.com"
    ./install.py ../my-kb --dry-run
    ./install.py --add-to ../existing-project [--dry-run] [--skip-unsafe-entries]

Standard library and git only. See docs/specs/installer.md and docs/decisions/0002-*.md.
Exit status: 0 success, 1 refusal or error, 2 usage error, 3 already installed.
"""
import argparse
import hashlib
import json
import os
import posixpath
import re
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path

STARTER = Path(__file__).resolve().parent
MAX_READ = 16 * 1024 * 1024
MAX_JSON = 1024 * 1024
MODULE = "knowledge-base"
MANIFEST = ".kb-manifest"
NAME_PLACEHOLDER = "REPLACE_WITH_PROJECT_NAME"
NAME_RE = re.compile(r"^[A-Za-z0-9._ -]{1,64}\Z")
OWNED_PREFIXES = ("tools/", "docs/kb/", "domains/_skeleton/")
SLOT_HOSTS = {
    "agents-guidance": "AGENTS.md",
    "readme-docs": "README.md",
    "docs-index": "docs/README.md",
    "gitignore": ".gitignore",
}
SKIPPED_NAMES = {"__pycache__", ".DS_Store"}
GIT_KEEP = {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM"}
EXIT_ALREADY_INSTALLED = 3
MAX_DEPTH = 32


class InstallError(Exception):
    pass


def scrub(text):
    """Escape control characters so a hostile file name cannot drive the terminal."""
    return "".join(c if c.isprintable() else ascii(c)[1:-1] for c in str(text))


def say(message):
    print(scrub(message))


def printable(value):
    return isinstance(value, str) and value != "" and value.isprintable()


def owned(rel):
    return rel == "kb.json" or rel.startswith(OWNED_PREFIXES)


# ---- safe reads and path rules ----------------------------------------------------


def check_rel(rel, what="path"):
    if not rel or rel.startswith("/") or "\\" in rel or "\x00" in rel:
        raise InstallError(f"unsafe {what}: {rel!r}")
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            raise InstallError(f"unsafe {what}: {rel!r}")
        if part.lower() == ".git":
            raise InstallError(f"{what} {rel!r} has a .git component")
    if rel.split("/")[-1].lower() == MANIFEST:
        raise InstallError(f"{what} {rel!r} uses the reserved manifest name")


def read_regular(path, cap=MAX_READ):
    """Read a regular file without following symlinks or blocking on a FIFO."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise InstallError(f"cannot read {path}: {exc.strerror}") from None
    if stat.S_ISLNK(st.st_mode):
        raise InstallError(f"{path} is a symlink; refused")
    if not stat.S_ISREG(st.st_mode):
        raise InstallError(f"{path} is not a regular file; refused")
    if st.st_size > cap:
        raise InstallError(f"{path} is larger than {cap} bytes; refused")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            data = handle.read(cap + 1)
    except OSError as exc:
        raise InstallError(f"cannot read {path}: {exc.strerror}") from None
    if len(data) > cap:
        raise InstallError(f"{path} is larger than {cap} bytes; refused")
    return data


def read_text(path):
    data = read_regular(path)
    if b"\x00" in data:
        raise InstallError(f"{path} contains a NUL byte; refused")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise InstallError(f"{path} is not valid UTF-8; refused") from None


def read_json(path, what):
    try:
        data = json.loads(read_regular(path, MAX_JSON).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise InstallError(f"{what} is not valid JSON") from None
    if not isinstance(data, dict):
        raise InstallError(f"{what} must be a JSON object")
    return data


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ---- the kit ----------------------------------------------------------------------


class Kit:
    def __init__(self, files, slots, base, module, migrations):
        self.files = files
        self.slots = slots
        self.base = base
        self.module = module
        self.migrations = migrations


def real_dir(path, what):
    try:
        st = os.lstat(path)
    except OSError:
        raise InstallError(f"kit is missing {what}") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise InstallError(f"kit {what} must be a real directory (symlinks are refused)")


def walk_tree(root):
    """Return {relative path: (bytes, executable)} for a kit tree, refusing unsafe entries."""
    found = {}

    def visit(directory, prefix):
        for name in sorted(os.listdir(directory)):
            if name in SKIPPED_NAMES:
                continue
            path = os.path.join(directory, name)
            rel = prefix + name
            check_rel(rel, "kit path")
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                raise InstallError(f"kit entry {rel} is a symlink; refused")
            if stat.S_ISDIR(st.st_mode):
                visit(path, rel + "/")
            elif stat.S_ISREG(st.st_mode):
                found[rel] = (read_regular(path), bool(st.st_mode & stat.S_IXUSR))
            else:
                raise InstallError(f"kit entry {rel} is a special file; refused")

    visit(str(root), "")
    return found


def validate_module(module):
    for key in ("name", "kit_version", "description", "hint"):
        if not printable(module.get(key)):
            raise InstallError(f"module.json: {key} must be printable single-line text")
    if module["name"] != MODULE:
        raise InstallError(f"module.json: name must be {MODULE!r}")
    if isinstance(module.get("order"), bool) or not isinstance(module.get("order"), int):
        raise InstallError("module.json: order must be an integer")
    if module.get("requires") != []:
        raise InstallError("module.json: requires must be an empty list")


def validate_migrations(migrations, files):
    steps = migrations.get("steps")
    if not isinstance(steps, list):
        raise InstallError("migrations.json: steps must be a list")
    expected = 1
    for step in steps:
        if not isinstance(step, dict) or type(step.get("from")) is not int or type(step.get("to")) is not int \
                or step["from"] != expected or step["to"] != expected + 1 or not isinstance(step.get("ops"), list):
            raise InstallError(f"migrations.json: steps must form a contiguous chain from schema 1 (at {expected})")
        expected += 1
        for op in step["ops"]:
            kind = op.get("op") if isinstance(op, dict) else None
            if kind not in ("add", "replace", "remove"):
                raise InstallError(f"migrations.json: unknown operation {kind!r}")
            path = op.get("path")
            if not isinstance(path, str):
                raise InstallError("migrations.json: an operation needs a path")
            check_rel(path, "migration path")
            if not owned(path):
                raise InstallError(f"migrations.json: {path} is outside the starter-owned paths")
            if kind != "remove" and op.get("source") not in files:
                raise InstallError(f"migrations.json: source {op.get('source')!r} is not in the kit")


def load_kit(kit_dir):
    kit_dir = str(kit_dir)
    real_dir(kit_dir, "directory")
    for name in ("files", "slots", "base"):
        real_dir(os.path.join(kit_dir, name), name + "/")
    module = read_json(os.path.join(kit_dir, "module.json"), "module.json")
    migrations = read_json(os.path.join(kit_dir, "migrations.json"), "migrations.json")
    files = walk_tree(os.path.join(kit_dir, "files"))
    base = {rel: data for rel, (data, _) in walk_tree(os.path.join(kit_dir, "base")).items()}
    slots = {}
    for rel, (data, _) in walk_tree(os.path.join(kit_dir, "slots")).items():
        slot = rel[:-3] if rel.endswith(".md") and "/" not in rel else None
        if slot not in SLOT_HOSTS:
            raise InstallError(f"kit slot {rel!r} is not one of {', '.join(sorted(SLOT_HOSTS))}")
        try:
            slots[slot] = data.decode("utf-8")
        except UnicodeDecodeError:
            raise InstallError(f"kit slot {rel!r} is not valid UTF-8") from None
    validate_module(module)
    validate_migrations(migrations, files)
    if "kb.json" not in files:
        raise InstallError("kit files/ has no kb.json")
    return Kit(files, slots, base, module, migrations)


# ---- managed blocks ---------------------------------------------------------------


def decorate(host_rel, text):
    return f"# {text}" if host_rel.endswith(".gitignore") else f"<!-- {text} -->"


def undecorate(host_rel, line):
    """The text of a comment line, or None. Lines indented four or more columns are code."""
    if line.startswith(("    ", "\t")):
        return None
    s = line.strip()
    if host_rel.endswith(".gitignore"):
        return s[2:] if s.startswith("# ") else None
    if s.startswith("<!-- ") and s.endswith(" -->"):
        return s[5:-4]
    return None


FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t\r]*\Z")
BEGIN_RE = re.compile(rf"^BEGIN module:{MODULE} slot:(\S+)$")
END_RE = re.compile(rf"^END module:{MODULE} slot:(\S+)$")
MARKER_RE = re.compile(r"^@module-slot: (\S+)$")


def scan_markers(host_rel, lines):
    """Return {slot: {'marker': [i], 'begin': [i], 'end': [i]}}, validating nesting and fences."""
    slots = {}
    fence = None  # (character, length) of the open fenced code block
    open_slot = None
    for i, line in enumerate(lines):
        if not host_rel.endswith(".gitignore"):
            if fence is None:
                opening = FENCE_OPEN_RE.match(line)
                if opening:
                    fence = (opening.group(1)[0], len(opening.group(1)))
                    continue
            else:
                closing = FENCE_CLOSE_RE.match(line)
                if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= fence[1]:
                    fence = None
                    continue
        fenced = fence is not None
        inner = undecorate(host_rel, line)
        if inner is None:
            continue
        for kind, regex in (("marker", MARKER_RE), ("begin", BEGIN_RE), ("end", END_RE)):
            match = regex.match(inner)
            if not match:
                continue
            slot = match.group(1)
            if fenced:
                raise InstallError(f"{host_rel}: a {kind} line for slot {slot} is inside a fenced code block")
            if kind == "begin":
                if open_slot is not None:
                    raise InstallError(f"{host_rel}: managed blocks are nested or interleaved")
                open_slot = slot
            elif kind == "end":
                if open_slot != slot:
                    raise InstallError(f"{host_rel}: END for slot {slot} has no matching BEGIN")
                open_slot = None
            slots.setdefault(slot, {"marker": [], "begin": [], "end": []})[kind].append(i)
    if fence is not None:
        raise InstallError(f"{host_rel}: a fenced code block is never closed")
    if open_slot is not None:
        raise InstallError(f"{host_rel}: BEGIN for slot {open_slot} has no END")
    return slots


def apply_fragment(host_rel, text, slot, fragment):
    """Return (new_text, block_text); raises InstallError on malformed or conflicting hosts."""
    lines = text.split("\n")
    found = scan_markers(host_rel, lines).get(slot, {"marker": [], "begin": [], "end": []})
    marker, begin, end = found["marker"], found["begin"], found["end"]
    if len(marker) > 1 or len(begin) > 1 or len(end) > 1:
        raise InstallError(f"{host_rel}: slot {slot} appears more than once")
    begin_line = decorate(host_rel, f"BEGIN module:{MODULE} slot:{slot}")
    end_line = decorate(host_rel, f"END module:{MODULE} slot:{slot}")
    marker_line = decorate(host_rel, f"@module-slot: {slot}")
    body = fragment.rstrip("\n").split("\n")
    block = [begin_line, *body, end_line]
    block_text = "\n".join(block)
    eol = "\r\n" if "\r\n" in text else "\n"
    if begin:
        if marker and marker[0] != end[0] + 1:
            raise InstallError(f"{host_rel}: the marker for slot {slot} must directly follow its END line")
        if [l.rstrip("\r") for l in lines[begin[0] + 1:end[0]]] != body:
            raise InstallError(f"{host_rel}: the managed block for slot {slot} differs from the kit")
        return text, block_text
    if marker:
        i = marker[0]
        cr = eol[:-1]
        return "\n".join(lines[:i] + [b + cr for b in block] + [lines[i]] + lines[i + 1:]), block_text
    appended = text
    if appended and not appended.endswith("\n"):
        appended += eol
    if appended:
        appended += eol
    return appended + eol.join([*block, marker_line]) + eol, block_text


# ---- git --------------------------------------------------------------------------


def git_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in GIT_KEEP}


def run_git(args, cwd, check=True, isolated=False):
    """Run git with a cleaned environment. isolated=True also ignores every user and system
    configuration file and attributes, so no configured filter or helper can run."""
    cmd = ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
           "-c", "core.hooksPath=" + os.devnull]
    env = git_env()
    if isolated:
        cmd += ["-c", "core.attributesFile=" + os.devnull, "--no-optional-locks"]
        env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "HOME": os.devnull})
        env.pop("XDG_CONFIG_HOME", None)
        env.pop("GIT_CONFIG_SYSTEM", None)
    cmd += args
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError(f"git failed: {exc}") from None
    if check and result.returncode != 0:
        raise InstallError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result


def starter_state():
    head = run_git(["rev-parse", "HEAD"], str(STARTER), check=False, isolated=True)
    if head.returncode != 0:
        return "", False
    dirty = run_git(["status", "--porcelain"], str(STARTER), check=False, isolated=True)
    return head.stdout.strip(), bool(dirty.stdout.strip())


# ---- planning ---------------------------------------------------------------------


def substitute(data, name):
    return data.replace(NAME_PLACEHOLDER.encode(), name.encode())


def validate_name(name):
    if not NAME_RE.match(name) or name[0] in " .-":
        raise InstallError(f"invalid project name {name!r}: use 1-64 of A-Z a-z 0-9 . _ - and space, "
                           "not starting with a space, dot, or hyphen")


def plan_files(kit, name):
    """Kit files as {rel: (bytes, executable)}; only kb.json is name-substituted."""
    plan = {}
    for rel, (data, executable) in kit.files.items():
        plan[rel] = (substitute(data, name) if rel == "kb.json" else data, executable)
    return plan


def plan_hosts(kit, name, load_host):
    """Apply every slot. load_host(rel) returns existing text, or None when the host is absent."""
    texts, blocks, reports = {}, {}, []
    for slot in sorted(kit.slots):
        host = SLOT_HOSTS[slot]
        if host not in texts:
            existing = load_host(host)
            if existing is not None:
                texts[host] = existing
            elif host in kit.base:
                texts[host] = substitute(kit.base[host], name).decode("utf-8")
            else:
                reports.append(f"slot {slot}: no {host} in the project or base; not installed")
                continue
        fragment = substitute(kit.slots[slot].encode(), name).decode("utf-8")
        texts[host], block = apply_fragment(host, texts[host], slot, fragment)
        blocks[f"{host}#{slot}"] = sha256(block.encode())
    return texts, blocks, reports


def build_manifest(kit, name, files, blocks):
    commit, dirty = starter_state()
    schema = json.loads(kit.files["kb.json"][0].decode("utf-8")).get("schema", 1)
    return {
        "schema": 1,
        "kb_schema": schema,
        "name": name,
        "kit_version": kit.module["kit_version"],
        "starter_commit": commit,
        "starter_dirty": dirty,
        "files": {rel: sha256(data) for rel, (data, _) in sorted(files.items()) if owned(rel)},
        "blocks": dict(sorted(blocks.items())),
    }


def manifest_bytes(manifest):
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


# ---- writing ----------------------------------------------------------------------


def check_parents(root, rel):
    """Refuse a symlinked or non-directory component below root before anything is written."""
    current = root
    parts = rel.split("/")
    for part in parts[:-1]:
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise InstallError(f"{current} is a symlink or not a directory; refused")
    final = os.path.join(root, rel)
    try:
        st = os.lstat(final)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise InstallError(f"{final} is a symlink or not a regular file; refused")


def write_file(root, rel, data, executable=False):
    current = root
    for part in rel.split("/")[:-1]:
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            os.mkdir(current)
            continue
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise InstallError(f"{current} is a symlink or not a directory; refused")
    final = os.path.join(root, rel)
    mode = 0o755 if executable else 0o644
    try:
        existing = os.lstat(final)
        if stat.S_ISREG(existing.st_mode):
            mode = stat.S_IMODE(existing.st_mode)  # keep the owner's permissions on a file we replace
    except FileNotFoundError:
        pass
    temp = os.path.join(os.path.dirname(final), f".kbtmp-{os.getpid()}-{secrets.token_hex(4)}")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
        os.replace(temp, final)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def write_all(root, items, written):
    for rel, data, executable in items:
        write_file(root, rel, data, executable)
        written.append(rel)


# ---- create mode ------------------------------------------------------------------


def is_starter_or_inside(path):
    """True when path, or any ancestor of it, is the starter directory (compared by identity,
    so case-insensitive filesystems and aliases cannot slip past)."""
    starter = os.stat(STARTER)
    current = path
    while True:
        try:
            if os.path.samestat(os.stat(current), starter):
                return True
        except OSError:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def contains_starter(path):
    """True when the starter directory lies inside path."""
    try:
        target = os.stat(path)
    except OSError:
        return False
    current = str(STARTER)
    while True:
        try:
            if os.path.samestat(os.stat(current), target):
                return True
        except OSError:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def resolve_target(target, create):
    """Return the resolved real path of a target, refusing symlinks and the starter."""
    absolute = os.path.abspath(target)
    if any(part.lower() == ".git" for part in absolute.split(os.sep)):
        raise InstallError("the target path has a .git component")
    try:
        st = os.lstat(absolute)
    except FileNotFoundError:
        st = None
    except (OSError, ValueError) as exc:
        raise InstallError(f"cannot inspect {target}: {getattr(exc, 'strerror', None) or 'invalid path'}") from None
    if st is not None and stat.S_ISLNK(st.st_mode):
        raise InstallError(f"{target} is a symlink; refused")
    if st is None:
        if not create:
            raise InstallError(f"{target} does not exist")
        parent = os.path.dirname(absolute)
        if not os.path.isdir(parent):
            raise InstallError(f"the parent directory {parent} does not exist")
        real = os.path.join(os.path.realpath(parent), os.path.basename(absolute))
    else:
        if not stat.S_ISDIR(st.st_mode):
            raise InstallError(f"{target} exists and is not a directory")
        real = os.path.realpath(absolute)
    if any(part.lower() == ".git" for part in real.split(os.sep)):
        raise InstallError("the target resolves to a path with a .git component")
    if is_starter_or_inside(real) or contains_starter(real):
        raise InstallError("the target is, contains, or is inside the starter repository")
    return absolute, real, st is not None


def resolve_identity(args):
    if args.use_global_git_identity:
        name = run_git(["config", "--global", "--get", "user.name"], None, check=False).stdout.strip()
        email = run_git(["config", "--global", "--get", "user.email"], None, check=False).stdout.strip()
        if not name or not email:
            raise InstallError("--use-global-git-identity was given but the global git identity is not set")
        say(f"Using the global git identity: {name} <{email}>")
        return name, email
    name, email = args.git_name, args.git_email
    if (not name or not email) and sys.stdin.isatty():
        name = name or input("Git author name for this project: ").strip()
        email = email or input("Git author email (a noreply address is recommended): ").strip()
    if not name or not email:
        raise InstallError("a git identity is required: pass --git-name and --git-email "
                           "(or --use-global-git-identity); no identity was given in a non-interactive run")
    return name, email


def run_create(args, kit):
    if args.skip_unsafe_entries:
        raise InstallError("--skip-unsafe-entries applies only to --add-to and --upgrade")
    absolute, real, exists = resolve_target(args.target, create=True)
    name = args.name if args.name is not None else os.path.basename(os.path.normpath(absolute))
    validate_name(name)
    if exists:
        if os.listdir(absolute):
            raise InstallError(f"{args.target} is not empty")
        if not os.access(absolute, os.W_OK):
            raise InstallError(f"{args.target} is not writable")
    elif not os.access(os.path.dirname(absolute), os.W_OK):
        raise InstallError(f"the parent of {args.target} is not writable")
    git_name, git_email = resolve_identity(args)
    for value in (git_name, git_email):
        if not printable(value):
            raise InstallError("the git identity must be printable single-line text")
    if "noreply" not in git_email:
        say(f"warning: {git_email} is not a noreply address; commits will publish it")
    if shutil.which("git") is None:
        raise InstallError("git was not found")

    files = plan_files(kit, name)
    texts, blocks, reports = plan_hosts(kit, name, lambda rel: None)
    manifest = manifest_bytes(build_manifest(kit, name, files, blocks))
    items = [(rel, data, ex) for rel, (data, ex) in sorted(files.items())]
    items += [(rel, text.encode("utf-8"), False) for rel, text in sorted(texts.items())]
    for rel, _, _ in items:
        check_rel(rel)
    paths = [rel for rel, _, _ in items] + [MANIFEST]
    for line in reports:
        say(f"note: {line}")
    if args.dry_run:
        say(f"Would create {args.target} (project name {name!r}) with:")
        for rel in sorted(paths):
            say(f"  would write {rel}")
        say("  would run git init, set HEAD to main, set a local identity, and exclude /.debug/")
        return 0

    written = []
    try:
        if not exists:
            os.mkdir(absolute)
        write_all(absolute, items, written)
        run_git(["init", "--template=", "-q"], absolute)
        run_git(["symbolic-ref", "HEAD", "refs/heads/main"], absolute)
        run_git(["config", "--local", "user.name", git_name], absolute)
        run_git(["config", "--local", "user.email", git_email], absolute)
        info = os.path.join(absolute, ".git", "info")
        if not os.path.isdir(info):
            os.mkdir(info)
        with open(os.path.join(info, "exclude"), "a", encoding="utf-8") as handle:
            handle.write("/.debug/\n")
        write_all(absolute, [(MANIFEST, manifest, False)], written)
    except (OSError, InstallError) as exc:
        say(f"failed after writing {len(written)} path(s): {', '.join(written) or 'none'}")
        say("nothing was deleted; fix the cause and remove or empty the directory to retry")
        raise InstallError(str(exc)) from None
    leftovers = sorted({m for text in texts.values() for m in re.findall(r"REPLACE_WITH_[A-Z_]+", text)})
    say(f"Created {args.target} ({len(paths)} files, git repository on main, no commits).")
    if leftovers:
        say("placeholders left to fill: " + ", ".join(leftovers))
    say(f"Next: {kit.module['hint']}")
    return 0


# ---- add-to mode ------------------------------------------------------------------

CONTENT_DIRS = ("catalog", "domains", "playbook", "sources", "text")


def unsafe_reason(st):
    if stat.S_ISLNK(st.st_mode):
        return "a symlink"
    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
        return "a special file"
    if stat.S_ISREG(st.st_mode) and st.st_size > MAX_READ:
        return "over the size cap"
    return None


def walk_content(root, top, kit, skip, skipped):
    """Refuse existing content below top/ unless it is identical to the kit's files."""
    def visit(rel, depth=0):
        if depth > MAX_DEPTH:
            raise InstallError(f"{top}/ is nested deeper than {MAX_DEPTH} levels; refused")
        path = os.path.join(root, rel)
        try:
            names = sorted(os.listdir(path))
        except OSError as exc:
            raise InstallError(f"cannot list {rel}: {exc.strerror}") from None
        for name in names:
            child = f"{rel}/{name}"
            try:
                st = os.lstat(os.path.join(root, child))
            except OSError as exc:
                raise InstallError(f"cannot inspect {child}: {exc.strerror}") from None
            reason = unsafe_reason(st)
            if reason:
                if not skip:
                    raise InstallError(f"{child} is {reason}; refused (use --skip-unsafe-entries to skip it)")
                skipped.append(f"{child} ({reason})")
            elif stat.S_ISDIR(st.st_mode):
                visit(child, depth + 1)
            else:
                kit_file = kit.files.get(child)
                if kit_file is None or read_regular(os.path.join(root, child)) != kit_file[0]:
                    raise InstallError(f"{child}: {top}/ already has content; the layer's layout and ignore "
                                       "rules would change its meaning")

    try:
        st = os.lstat(os.path.join(root, top))
    except FileNotFoundError:
        return
    reason = unsafe_reason(st)
    if reason:
        if not skip:
            raise InstallError(f"{top} is {reason}; refused (use --skip-unsafe-entries to skip it)")
        skipped.append(f"{top} ({reason})")
    elif not stat.S_ISDIR(st.st_mode):
        raise InstallError(f"{top} exists and is not a directory")
    else:
        visit(top)


def run_add_to(args, kit):
    if args.git_name or args.git_email or args.use_global_git_identity:
        raise InstallError("--git-name, --git-email, and --use-global-git-identity apply only when creating a project")
    absolute, real, _ = resolve_target(args.add_to, create=False)
    name = args.name if args.name is not None else os.path.basename(os.path.normpath(absolute))
    validate_name(name)
    if os.path.lexists(os.path.join(absolute, MANIFEST)):
        print(scrub(f"{args.add_to} already has {MANIFEST}: the layer is installed; use --upgrade"), file=sys.stderr)
        return EXIT_ALREADY_INSTALLED
    if not os.access(absolute, os.W_OK):
        raise InstallError(f"{args.add_to} is not writable")
    skipped = []
    for top in CONTENT_DIRS:
        walk_content(absolute, top, kit, args.skip_unsafe_entries, skipped)

    files = plan_files(kit, name)
    conflicts, writes, kept = [], [], {}
    for rel, (data, executable) in sorted(files.items()):
        check_rel(rel)
        try:
            check_parents(absolute, rel)
            existing = read_regular(os.path.join(absolute, rel)) if os.path.lexists(os.path.join(absolute, rel)) else None
        except InstallError as exc:
            if not args.skip_unsafe_entries:
                raise
            skipped.append(f"{rel} ({exc})")
            continue
        if existing is None:
            writes.append((rel, data, executable))
        elif existing != data:
            conflicts.append(rel)
        kept[rel] = (data, executable)
    if conflicts:
        raise InstallError("existing files differ from the kit and would be overwritten: " + ", ".join(conflicts))

    def load_host(rel):
        check_rel(rel)
        check_parents(absolute, rel)
        path = os.path.join(absolute, rel)
        return read_text(path) if os.path.lexists(path) else None

    texts, blocks, reports = plan_hosts(kit, name, load_host)
    host_writes = []
    for rel, text in sorted(texts.items()):
        path = os.path.join(absolute, rel)
        if not os.path.lexists(path) or read_text(path) != text:
            host_writes.append((rel, text.encode("utf-8"), False))
    manifest = manifest_bytes(build_manifest(kit, name, kept, blocks))

    for line in reports:
        say(f"note: {line}")
    for line in skipped:
        say(f"skipped unsafe entry: {line}")
    if args.dry_run:
        say(f"Would add the knowledge-base layer to {args.add_to}:")
        for rel, _, _ in writes:
            say(f"  would write {rel}")
        for rel, _, _ in host_writes:
            slots = sorted(key.split("#")[1] for key in blocks if key.startswith(rel + "#"))
            say(f"  would write {rel} (managed blocks: {', '.join(slots)})")
        say(f"  would write {MANIFEST}")
        return 0

    written = []
    try:
        write_all(absolute, writes + host_writes, written)
        write_all(absolute, [(MANIFEST, manifest, False)], written)
    except (OSError, InstallError) as exc:
        say(f"failed after writing {len(written)} path(s): {', '.join(written) or 'none'}")
        say("nothing was deleted; fix the cause and run the same command again")
        raise InstallError(str(exc)) from None
    say(f"Added the knowledge-base layer to {args.add_to} ({len(written)} paths written).")
    say("No git command was run; review the changes with git status and git diff.")
    say(f"Next: {kit.module['hint']}")
    return 0


# ---- command line -----------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(description="Create a knowledge-base project or add the layer to one.")
    parser.add_argument("target", nargs="?", help="directory for a new project")
    parser.add_argument("--add-to", metavar="DIR", help="add the layer to an existing project")
    parser.add_argument("--name", help="project name (default: the directory name)")
    parser.add_argument("--git-name", help="git author name for a new project")
    parser.add_argument("--git-email", help="git author email for a new project")
    parser.add_argument("--use-global-git-identity", action="store_true",
                        help="copy the global git identity into the new project (reported)")
    parser.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    parser.add_argument("--skip-unsafe-entries", action="store_true",
                        help="with --add-to: skip symlinks, special files, and oversize files in the walk")
    return parser


def main(argv=None, kit_dir=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.target) == bool(args.add_to):
        parser.error("give either a target directory or --add-to DIR")
    try:
        kit = load_kit(kit_dir if kit_dir is not None else STARTER / "kit")
        if args.add_to:
            return run_add_to(args, kit)
        return run_create(args, kit)
    except InstallError as exc:
        print(scrub(f"error: {exc}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
