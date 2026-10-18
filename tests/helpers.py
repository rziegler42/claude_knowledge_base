"""Shared helpers for the starter's tests. Standard library only."""
import contextlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # never leave .pyc files in the kit

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "kit"
KIT_TOOLS = KIT / "files" / "tools"

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
