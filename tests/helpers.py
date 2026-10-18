"""Shared helpers for the starter's tests. Standard library only."""
import contextlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # never leave .pyc files in the kit

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "kit"
KIT_TOOLS = KIT / "files" / "tools"
SAFE_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

if str(KIT_TOOLS) not in sys.path:
    sys.path.insert(0, str(KIT_TOOLS))


@contextlib.contextmanager
def scratch():
    """A temporary directory under the system temp dir, removed afterwards."""
    path = Path(tempfile.mkdtemp(prefix="kbtest-")).resolve()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write(base, relative, text="", mode=None):
    """Write text under base, creating parents; return the path."""
    target = Path(base) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    if mode is not None:
        os.chmod(target, mode)
    return target


def snapshot(root):
    """Map every path under root to its kind and content, without following symlinks or
    opening special files (a FIFO would block a read)."""
    state = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root)
            if os.path.islink(path):
                state[rel] = ("link", os.readlink(path))
            elif os.path.isdir(path):
                state[rel] = ("dir",)
            elif not os.path.isfile(path):
                state[rel] = ("special",)
            else:
                with open(path, "rb") as handle:
                    state[rel] = ("file", handle.read())
    return state


def pdf_python():
    """The interpreter named by KB_PDF_PYTHON (one with pymupdf and pymupdf4llm), or None."""
    path = os.environ.get("KB_PDF_PYTHON", "")
    return path if path and os.path.isfile(path) and os.access(path, os.X_OK) else None


requires_pdf = unittest.skipUnless(
    pdf_python(), "set KB_PDF_PYTHON to an interpreter with pymupdf and pymupdf4llm to run the PDF tests")
