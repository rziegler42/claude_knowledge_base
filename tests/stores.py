"""Helpers for the upgrade tests: make a kit and a store from it, run the installer in-process."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
from pathlib import Path
from unittest import mock

import helpers

sys.path.insert(0, str(helpers.ROOT))
import install  # noqa: E402

IDENT = ["--git-name", "T", "--git-email", "t@users.noreply.github.com"]
SAFE_ENV = helpers.SAFE_ENV


def run_main(*argv, kit=None, env=None):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {**SAFE_ENV, **(env or {})}), mock.patch("sys.stdin", io.StringIO("")), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = install.main(list(argv), kit_dir=kit)
        except SystemExit as exit_:
            code = exit_.code if isinstance(exit_.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def make_kit(tmp, name="kit"):
    kit = Path(tmp) / name
    shutil.copytree(helpers.KIT, kit, ignore=shutil.ignore_patterns("__pycache__"))
    return kit


def make_store(tmp, kit=None, name="store"):
    store = Path(tmp) / name
    code, out, err = run_main(str(store), *IDENT, kit=kit)
    assert code == 0, out + err
    return store


def upgrade(store, *extra, kit=None):
    return run_main("--upgrade", "--dir", str(store), *extra, kit=kit)


def manifest(store):
    return json.loads((Path(store) / ".kb-manifest").read_text(encoding="utf-8"))


def write_manifest(store, data):
    (Path(store) / ".kb-manifest").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def content_checksums(store):
    """Checksums of everything an upgrade must never touch: content directories and the root files."""
    state = {}
    store = Path(store)
    for rel in ("domains", "catalog", "sources", "text", "playbook", "README.md", "AGENTS.md", "docs/README.md", ".gitignore"):
        path = store / rel
        if path.is_file():
            state[rel] = path.read_bytes()
        elif path.is_dir():
            for sub in sorted(path.rglob("*")):
                relative = sub.relative_to(store).as_posix()
                if relative.startswith("domains/_skeleton"):
                    continue
                if sub.is_file() and not sub.is_symlink():
                    state[relative] = sub.read_bytes()
    return state
