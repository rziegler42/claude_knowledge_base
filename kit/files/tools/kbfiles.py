"""Safe file helpers shared by the store's tools.

Real directories only, bounded reads that follow no symlink and never block on a FIFO, and
writes through a temporary sibling and a rename. Standard library only.
"""
import hashlib
import os
import re
import secrets
import stat

TEMP_PREFIX = ".kbtmp-"  # hidden, so the checker and the tools ignore a leftover
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")
MAX_NAME = 100


class KbFileError(Exception):
    """A refusal that carries a message with no file content in it."""


def valid_name(name):
    """A domain name or entry slug: lowercase letters, digits, and hyphens, not starting with a hyphen."""
    return isinstance(name, str) and len(name) <= MAX_NAME and bool(NAME_RE.match(name))


def inside(root, rel):
    """The path root/rel for a relative path made only of ordinary components."""
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel or "\x00" in rel:
        raise KbFileError(f"unsafe path: {rel!r}")
    parts = rel.split("/")
    for part in parts:
        if part in ("", ".", "..") or part.lower() == ".git":
            raise KbFileError(f"unsafe path: {rel!r}")
    return os.path.join(root, *parts)


def find_root(arg, here):
    """The store root: `arg`, or the parent of the tools directory `here`. It must hold a kb.json."""
    root = os.path.abspath(arg) if arg else os.path.dirname(os.path.abspath(here))
    real_dir(root, "the store root")
    try:
        st = os.lstat(os.path.join(root, "kb.json"))
    except OSError:
        raise KbFileError("not a knowledge-base store (no kb.json)") from None
    if not stat.S_ISREG(st.st_mode):
        raise KbFileError("not a knowledge-base store (kb.json is not a regular file)")
    return root


def real_dir(path, what):
    try:
        st = os.lstat(path)
    except OSError:
        raise KbFileError(f"{what} is missing") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise KbFileError(f"{what} is not a real directory (symlinks are refused)")


def read_head(path, cap):
    """The first `cap` bytes of a regular file, without following a symlink or blocking on a FIFO."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise KbFileError(f"cannot read {os.path.basename(path)}: {exc.strerror}") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise KbFileError(f"{os.path.basename(path)} is a symlink or not a regular file; refused")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            return handle.read(cap)
    except OSError as exc:
        raise KbFileError(f"cannot read {os.path.basename(path)}: {exc.strerror}") from None


def read_text(path, cap):
    """UTF-8 text of a regular file of at most `cap` bytes with no NUL byte."""
    data = read_head(path, cap + 1)
    name = os.path.basename(path)
    if len(data) > cap:
        raise KbFileError(f"{name} is larger than {cap} bytes; refused")
    if b"\x00" in data:
        raise KbFileError(f"{name} contains a NUL byte; refused")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise KbFileError(f"{name} is not valid UTF-8; refused") from None


def sha256_file(path):
    """SHA-256 of a regular file, read without following a symlink or blocking on a FIFO."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise KbFileError(f"cannot read {os.path.basename(path)}: {exc.strerror}") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise KbFileError(f"{os.path.basename(path)} is a symlink or not a regular file; refused")
    digest = hashlib.sha256()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    except OSError as exc:
        raise KbFileError(f"cannot read {os.path.basename(path)}: {exc.strerror}") from None
    return digest.hexdigest()


def write_atomic(path, data):
    """Write through a temporary sibling and a rename; refuse to replace anything but a regular
    file, and keep the permissions of the file being replaced."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        st = None
    if st is not None and (stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode)):
        raise KbFileError(f"{os.path.basename(path)} is a symlink or not a regular file; refused")
    mode = stat.S_IMODE(st.st_mode) if st is not None else 0o644
    temp = os.path.join(os.path.dirname(path), f"{TEMP_PREFIX}{os.getpid()}-{secrets.token_hex(4)}")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
