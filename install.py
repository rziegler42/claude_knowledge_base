#!/usr/bin/env python3
"""Create a standalone knowledge-base store from this starter.

    ./install.py ../my-kb --git-name "Your Name" --git-email "id+user@users.noreply.github.com"
    ./install.py ../my-kb --dry-run
    ./install.py --upgrade --dir ../my-kb [--dry-run]

Standard library and git only. See docs/specs/installer.md and docs/decisions/0002-*.md
and 0003-*.md. Exit status: 0 success, 1 refusal or error, 2 usage error.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

STARTER = Path(__file__).resolve().parent
MAX_READ = 16 * 1024 * 1024
MAX_JSON = 1024 * 1024
MANIFEST = ".kb-manifest"
NAME_PLACEHOLDER = "REPLACE_WITH_PROJECT_NAME"
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_LISTED = 10
NAME_RE = re.compile(r"^[A-Za-z0-9._ -]{1,64}\Z")
OWNED_PREFIXES = ("tools/", "docs/kb/", "domains/_skeleton/", "template-module/")
VERBATIM_PREFIXES = ("tools/", "docs/kb/", "template-module/")
MODULE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
REGISTER_HINT = "to register with the project template, run its install.py --register "
SKIPPED_NAMES = {"__pycache__", ".DS_Store"}
GIT_KEEP = {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM"}


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
    def __init__(self, files, meta, migrations):
        self.files = files
        self.meta = meta
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


def validate_kit_json(meta):
    for key in ("kit_version", "hint"):
        if not printable(meta.get(key)):
            raise InstallError(f"kit.json: {key} must be printable single-line text")


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
            if kind != "remove" and path in files and op["source"] != path:
                raise InstallError(f"migrations.json: the source of {path} must be {path} itself "
                                   "while the kit also ships that path")


def load_kit(kit_dir):
    kit_dir = str(kit_dir)
    real_dir(kit_dir, "directory")
    real_dir(os.path.join(kit_dir, "files"), "files/")
    meta = read_json(os.path.join(kit_dir, "kit.json"), "kit.json")
    migrations = read_json(os.path.join(kit_dir, "migrations.json"), "migrations.json")
    files = walk_tree(os.path.join(kit_dir, "files"))
    validate_kit_json(meta)
    validate_migrations(migrations, files)
    if "kb.json" not in files:
        raise InstallError("kit files/ has no kb.json")
    return Kit(files, meta, migrations)


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


def verbatim(rel):
    return rel.startswith(VERBATIM_PREFIXES)


def plan_files(kit, name):
    """Kit files as {rel: (bytes, executable)}; the project name is substituted everywhere
    except under the verbatim prefixes."""
    plan = {}
    for rel, (data, executable) in kit.files.items():
        plan[rel] = (data if verbatim(rel) else substitute(data, name), executable)
    return plan


def leftover_placeholders(kit, name):
    """REPLACE_WITH_* tokens left in the files where the project name was substituted."""
    found = set()
    for rel, (data, _) in kit.files.items():
        if verbatim(rel) or NAME_PLACEHOLDER.encode() not in data:
            continue
        text = substitute(data, name).decode("utf-8", "replace")
        found.update(re.findall(r"REPLACE_WITH_[A-Z_]+", text))
    return sorted(found)


def suggest_module_name(dirname):
    """A name the project template accepts, derived from a directory name."""
    text = re.sub(r"[^a-z0-9_-]+", "-", dirname.lower())
    return re.sub(r"^[^a-z0-9]+", "", text) or "kb"


def registration_line(real):
    line = REGISTER_HINT + shlex.quote(real)
    dirname = os.path.basename(real)
    if not MODULE_NAME_RE.match(dirname):
        line += " --name " + suggest_module_name(dirname)
    return line


def build_manifest(kit, name, files):
    commit, dirty = starter_state()
    schema = json.loads(kit.files["kb.json"][0].decode("utf-8")).get("schema", 1)
    return {
        "schema": 1,
        "kb_schema": schema,
        "name": name,
        "kit_version": kit.meta["kit_version"],
        "starter_commit": commit,
        "starter_dirty": dirty,
        "files": {rel: sha256(data) for rel, (data, _) in sorted(files.items()) if owned(rel)},
    }


def manifest_bytes(manifest):
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


# ---- writing ----------------------------------------------------------------------


def stage_file(root, rel, data, executable=False, created=None):
    """Write data to a hidden temporary sibling of rel, creating missing parent directories and
    refusing a symlinked or non-directory component. Returns (temp, final); nothing is renamed."""
    current = root
    for part in rel.split("/")[:-1]:
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            os.mkdir(current)
            if created is not None:
                created.append(current)
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
    except BaseException:
        discard(temp)
        raise
    return temp, final


def discard(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def rename_into_place(temp, final):
    os.replace(temp, final)


def delete_file(path):
    os.unlink(path)


def write_file(root, rel, data, executable=False):
    temp, final = stage_file(root, rel, data, executable)
    try:
        rename_into_place(temp, final)
    except BaseException:
        discard(temp)
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
    if not args.target:
        raise InstallError("the target directory must not be empty")
    absolute, real, exists = resolve_target(args.target, create=True)
    if not printable(real):
        raise InstallError("the target's real path is not printable single-line text; refused")
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
    manifest = manifest_bytes(build_manifest(kit, name, files))
    items = [(rel, data, ex) for rel, (data, ex) in sorted(files.items())]
    for rel, _, _ in items:
        check_rel(rel)
    paths = [rel for rel, _, _ in items] + [MANIFEST]
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
    leftovers = leftover_placeholders(kit, name)
    say(f"Created {args.target} ({len(paths)} files, git repository on main, no commits).")
    if leftovers:
        say("placeholders left to fill: " + ", ".join(leftovers))
    say(f"Next: {kit.meta['hint']}")
    say(registration_line(real))
    return 0


# ---- upgrade mode -----------------------------------------------------------------


def _no_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def read_manifest(root):
    """Read and validate a store's manifest. The store is untrusted: nothing in it is believed
    until it passes. Returns (name, kb_schema, {owned path: digest}, [ignored keys])."""
    path = os.path.join(root, MANIFEST)
    try:
        data = json.loads(read_regular(path, MAX_JSON).decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise InstallError(f"{MANIFEST} is not valid JSON (or repeats a key)") from None
    if not isinstance(data, dict):
        raise InstallError(f"{MANIFEST} must be a JSON object")
    if type(data.get("schema")) is not int or data["schema"] != 1:
        raise InstallError(f"{MANIFEST} has an unknown schema; this installer reads schema 1")
    if type(data.get("kb_schema")) is not int or data["kb_schema"] < 1:
        raise InstallError(f"{MANIFEST}: kb_schema must be a positive integer")
    name = data.get("name")
    if not isinstance(name, str):
        raise InstallError(f"{MANIFEST}: name must be text")
    validate_name(name)
    recorded = data.get("files")
    if not isinstance(recorded, dict):
        raise InstallError(f"{MANIFEST}: files must be an object")
    files, ignored = {}, []
    for rel, digest in recorded.items():
        check_rel(rel, "manifest path")
        if not isinstance(digest, str) or not DIGEST_RE.match(digest):
            raise InstallError(f"{MANIFEST}: the checksum for {rel!r} is not 64 lowercase hex digits")
        if owned(rel):
            files[rel] = digest
        else:
            ignored.append(rel)
    return name, data["kb_schema"], files, sorted(ignored)


def read_owned(root, rel):
    """The bytes of an owned path in the store, or None when it (or a parent) is missing.
    A symlink, special file, oversize file, or non-directory parent raises."""
    current = root
    for part in rel.split("/")[:-1]:
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise InstallError(f"{rel}: cannot inspect {part}: {exc.strerror}") from None
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise InstallError(f"{rel}: {part} is a symlink or not a directory")
    final = os.path.join(root, rel)
    try:
        os.lstat(final)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise InstallError(f"{rel}: cannot inspect it: {exc.strerror}") from None
    try:
        return read_regular(final)
    except InstallError as exc:
        raise InstallError(f"{rel}: {exc}") from None


def classify(recorded, disk, kit):
    """The action for one owned file, from the specification's table."""
    if disk is None:
        return "add"
    digest = sha256(disk)
    if recorded is None:
        return "adopt" if digest == kit else "conflict"
    if digest == recorded:
        return "nothing" if digest == kit else "replace"
    return "record" if digest == kit else "skip"


REASONS = {
    "add": "missing from the store",
    "replace": "unedited, and the starter has a newer version",
    "adopt": "equals the starter's version; its checksum will be recorded",
    "record": "edited to match the starter's version; its checksum will be recorded",
    "skip": "edited since it was recorded; the store's version is kept",
    "conflict": "not recorded and differs from the starter's version; the store's version is kept",
    "report": "recorded, but no longer in the starter; kept",
}


def kit_schema(kit):
    schema = json.loads(kit.files["kb.json"][0].decode("utf-8")).get("schema", 1)
    if type(schema) is not int or schema < 1:
        raise InstallError("kit kb.json: schema must be a positive integer")
    return schema


def store_schema(root):
    """The schema in the store's own kb.json, or None when the file is missing."""
    data = read_owned(root, "kb.json")
    if data is None:
        return None
    schema = store_schema_of(data)
    if schema is None:
        raise InstallError("the store's kb.json is not valid JSON with an integer schema; "
                           "fix it by hand (see docs/kb/installer.md) before upgrading")
    return schema


def store_schema_of(data):
    try:
        meta = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        meta = None
    schema = meta.get("schema") if isinstance(meta, dict) else None
    return schema if type(schema) is int and schema >= 1 else None


def steps_to_run(kit, recorded_schema, file_schema, target):
    """The migration steps to apply, or a refusal. The interrupted state (kb.json already at the
    kit's schema, the manifest not yet) is accepted; the idempotent steps then complete it."""
    if recorded_schema > target:
        raise InstallError(f"the store's schema ({recorded_schema}) is newer than this starter's ({target}); "
                           "use a newer starter")
    if file_schema is not None and file_schema != recorded_schema \
            and not (recorded_schema < target and file_schema == target):
        raise InstallError(f"the store's kb.json schema ({file_schema}) disagrees with {MANIFEST} "
                           f"({recorded_schema}); resolve it by hand (see docs/kb/installer.md)")
    if recorded_schema == target:
        return []
    steps = [step for step in kit.migrations["steps"] if recorded_schema <= step["from"] < target]
    if len(steps) != target - recorded_schema:
        raise InstallError(f"this starter has no migration chain from schema {recorded_schema} to {target}; "
                           "follow docs/kb/ to upgrade the store by hand")
    return steps


class Stage:
    """The store's owned files as the upgrade would leave them, computed without writing."""

    def __init__(self, root, recorded):
        self.root = root
        self.record = dict(recorded)
        self.disk = {}
        self.seen = {}
        self.writes = {}
        self.deletes = []

    def read(self, rel):
        if rel not in self.disk:
            self.disk[rel] = self.seen[rel] = read_owned(self.root, rel)
        return self.disk[rel]

    def put(self, rel, data, executable):
        self.disk[rel] = data
        self.writes[rel] = (data, executable)
        self.record[rel] = sha256(data)
        if rel in self.deletes:
            self.deletes.remove(rel)

    def drop(self, rel):
        self.disk[rel] = None
        self.record.pop(rel, None)
        self.writes.pop(rel, None)
        self.deletes.append(rel)


CONFLICT_WHY = {
    "add": "exists and differs from the starter's file",
    "replace": "is missing or edited since it was recorded",
    "remove": "is edited or not recorded",
}


def apply_op(stage, op, files, lines, problems, conflicts):
    kind, rel = op["op"], op["path"]
    try:
        disk = stage.read(rel)
    except InstallError as exc:
        problems.append(str(exc))
        return
    recorded = stage.record.get(rel)
    if kind == "remove":
        if disk is None:
            stage.record.pop(rel, None)
            note = "already absent"
        elif recorded is not None and sha256(disk) == recorded:
            stage.drop(rel)
            note = "deleted"
        else:
            conflicts.append(f"{rel} ({CONFLICT_WHY[kind]})")
            return
    else:
        data, executable = files[op["source"]]
        if disk == data:
            stage.record[rel] = sha256(data)
            note = "already done"
        elif (kind == "add" and disk is None) or (kind == "replace" and disk is not None
                                                  and recorded == sha256(disk)):
            stage.put(rel, data, executable)
            note = "written from the starter"
        else:
            conflicts.append(f"{rel} ({CONFLICT_WHY[kind]})")
            return
    lines.append((f"migrate {kind}", rel, note))


class Upgrade:
    def __init__(self, name, schema_from, schema_to, steps, lines, stage, ignored, recorded):
        self.name, self.schema_from, self.schema_to, self.steps = name, schema_from, schema_to, steps
        self.lines, self.stage, self.ignored, self.recorded = lines, stage, ignored, recorded


def plan_upgrade(root, kit):
    """Read-only plan of the whole upgrade: the schema check, the migration chain, then the
    ordinary table against the post-migration state. Nothing is written."""
    name, recorded_schema, recorded, ignored = read_manifest(root)
    target = kit_schema(kit)
    steps = steps_to_run(kit, recorded_schema, store_schema(root), target)
    files = plan_files(kit, name)
    expected = {rel: pair for rel, pair in files.items() if owned(rel)}
    stage = Stage(root, recorded)
    lines, problems, conflicts = [], [], []
    for step in steps:
        for op in step["ops"]:
            apply_op(stage, op, files, lines, problems, conflicts)
    for rel in sorted(expected):
        data, executable = expected[rel]
        try:
            disk = stage.read(rel)
        except InstallError as exc:
            problems.append(str(exc))
            continue
        action = classify(stage.record.get(rel), disk, sha256(data))
        if action in ("add", "replace"):
            stage.put(rel, data, executable)
        elif action in ("adopt", "record"):
            stage.record[rel] = sha256(data)
        if action != "nothing":
            lines.append((action, rel, REASONS[action]))
    if steps and not problems and not conflicts:
        final = stage.disk.get("kb.json")
        if final is None or store_schema_of(final) != target:
            conflicts.append("kb.json (edited, so the schema marker cannot advance to "
                             f"{target}; merge the starter's kb.json by hand)")
    if problems:
        unique = list(dict.fromkeys(problems))
        more = f" (and {len(unique) - MAX_LISTED} more)" if len(unique) > MAX_LISTED else ""
        raise InstallError("unsafe owned paths in the store, nothing was written: "
                           + "; ".join(unique[:MAX_LISTED]) + more)
    if conflicts:
        raise InstallError("migration conflict, nothing was written and kb_schema is unchanged; resolve by hand "
                           "(restore the file, or follow docs/kb/) and rerun: " + "; ".join(conflicts[:MAX_LISTED]))
    lines += [("report", rel, REASONS["report"]) for rel in sorted(stage.record) if rel not in expected]
    return Upgrade(name, recorded_schema, target, steps, lines, stage, ignored, dict(recorded))


def new_manifest(plan, kit):
    commit, dirty = starter_state()
    return manifest_bytes({
        "schema": 1,
        "kb_schema": plan.schema_to,
        "name": plan.name,
        "kit_version": kit.meta["kit_version"],
        "starter_commit": commit,
        "starter_dirty": dirty,
        "files": dict(sorted(plan.stage.record.items())),
    })


def verify_unchanged(root, stage, paths):
    """Just before the first rename: every file the plan will replace or delete is still what the
    plan read, so an edit made while the upgrade ran is never overwritten."""
    for rel in paths:
        try:
            now = read_owned(root, rel)
        except InstallError as exc:
            raise InstallError(f"{rel} changed while the upgrade was planned ({exc}); nothing was replaced, "
                               "rerun the upgrade") from None
        if now != stage.seen.get(rel):
            raise InstallError(f"{rel} changed while the upgrade was planned; nothing was replaced, "
                               "rerun the upgrade")


def apply_upgrade(root, plan, kit):
    """Stage and validate everything, then rename: owned files, deletions, kb.json, the manifest.
    A crash leaves some files replaced; a rerun detects the rest from kb.json's schema and the
    checksums and completes the work."""
    stage = plan.stage
    changed = bool(stage.writes or stage.deletes or stage.record != plan.recorded
                   or plan.schema_from != plan.schema_to)
    if not changed:
        return False
    order = sorted(rel for rel in stage.writes if rel != "kb.json")
    if "kb.json" in stage.writes:
        order.append("kb.json")
    manifest_data = new_manifest(plan, kit)
    staged, temps, made = [], [], []
    try:
        for rel in order:
            data, executable = stage.writes[rel]
            temp, final = stage_file(root, rel, data, executable, made)
            temps.append(temp)
            staged.append((rel, temp, final, data))
        temp, final = stage_file(root, MANIFEST, manifest_data)
        temps.append(temp)
        staged.append((MANIFEST, temp, final, manifest_data))
        for rel, temp, _, data in staged:
            if read_regular(temp) != data:
                raise InstallError(f"the staged copy of {rel} does not match what was planned")
        verify_unchanged(root, stage, [rel for rel in order] + list(stage.deletes))
    except (OSError, InstallError) as exc:
        for temp in temps:
            discard(temp)
        for directory in reversed(made):
            try:
                os.rmdir(directory)
            except OSError:
                pass
        raise InstallError(f"{exc}; nothing was replaced") from None
    done = []
    try:
        for rel, temp, final, _ in staged[:-1]:
            if rel == "kb.json":
                continue
            rename_into_place(temp, final)
            done.append(rel)
        for rel in stage.deletes:
            delete_file(os.path.join(root, rel))
            done.append(f"{rel} (deleted)")
        for rel, temp, final, _ in staged[:-1]:
            if rel == "kb.json":
                rename_into_place(temp, final)
                done.append(rel)
        rename_into_place(staged[-1][1], staged[-1][2])
    except (OSError, InstallError) as exc:
        for temp in temps:
            discard(temp)
        say(f"failed after completing {len(done)} step(s): {', '.join(done) or 'none'}")
        raise InstallError(f"{getattr(exc, 'strerror', None) or exc}; rerun the same command to finish the "
                           "upgrade (a rerun is safe and completes the remaining work)") from None
    return True


def run_upgrade(args, kit):
    if not args.dir:
        raise InstallError("the store directory must not be empty")
    _, real, _ = resolve_target(args.dir, create=False)
    if not printable(real):
        raise InstallError("the store's real path is not printable single-line text; refused")
    plan = plan_upgrade(real, kit)
    say(f"{'Would upgrade' if args.dry_run else 'Upgrading'} {args.dir} (project name {plan.name!r}):")
    for key in plan.ignored:
        say(f"ignored manifest entry {key} (outside the starter-owned paths)")
    if plan.schema_from != plan.schema_to:
        say(f"kb_schema {plan.schema_from} -> {plan.schema_to} ({len(plan.steps)} migration step"
            f"{'' if len(plan.steps) == 1 else 's'})")
    for label, rel, note in plan.lines:
        say(f"{label} {rel} ({note})")
    if not plan.lines and not plan.ignored and plan.schema_from == plan.schema_to:
        say("nothing to do")
    if args.dry_run:
        return 0
    if not apply_upgrade(real, plan, kit):
        say("Nothing was written.")
        return 0
    skipped = sum(1 for label, _, _ in plan.lines if label in ("skip", "conflict"))
    say(f"Upgraded {args.dir}: {len(plan.stage.writes)} file(s) written, {len(plan.stage.deletes)} deleted, "
        f"{skipped} left as they are.")
    say("Review the changes with `git diff` and `git status` in the store; the upgrade never commits.")
    return 0


# ---- command line -----------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(description="Create or upgrade a standalone knowledge-base store.")
    parser.add_argument("target", nargs="?", help="directory for the new store")
    parser.add_argument("--upgrade", action="store_true",
                        help="bring an existing store's starter-owned files up to date (needs --dir)")
    parser.add_argument("--dir", help="the store to upgrade")
    parser.add_argument("--name", help="project name (default: the directory name)")
    parser.add_argument("--git-name", help="git author name for a new project")
    parser.add_argument("--git-email", help="git author email for a new project")
    parser.add_argument("--use-global-git-identity", action="store_true",
                        help="copy the global git identity into the new project (reported)")
    parser.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    return parser


def check_usage(parser, args):
    if args.upgrade:
        if args.dir is None:
            parser.error("--upgrade needs --dir <store>")
        if args.target is not None:
            parser.error("--upgrade takes --dir, not a target directory")
        for option, value in (("--name", args.name), ("--git-name", args.git_name), ("--git-email", args.git_email),
                              ("--use-global-git-identity", args.use_global_git_identity)):
            if value:
                parser.error(f"{option} is for creating a store and cannot be used with --upgrade")
    else:
        if args.dir is not None:
            parser.error("--dir is only used with --upgrade")
        if args.target is None:
            parser.error("the target directory is required")


def main(argv=None, kit_dir=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    check_usage(parser, args)
    try:
        kit = load_kit(kit_dir if kit_dir is not None else STARTER / "kit")
        return run_upgrade(args, kit) if args.upgrade else run_create(args, kit)
    except InstallError as exc:
        print(scrub(f"error: {exc}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
