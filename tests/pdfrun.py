"""Run the converter's worker in a child process, the way the command does."""
import json
import os
import subprocess

import helpers

WORKER = helpers.KIT_TOOLS / "convert_worker.py"
KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k in KEEP}
    env.update(extra or {})
    return env


def run_worker(request, *, timeout=120, env=None, cwd=None):
    """Return the worker's JSON answer (the last stdout line)."""
    proc = subprocess.run([helpers.pdf_python(), "-I", "-B", str(WORKER)], input=json.dumps(request),
                          capture_output=True, text=True, timeout=timeout, env=clean_env(env), cwd=cwd)
    lines = [line for line in proc.stdout.split("\n") if line.strip()]
    if not lines:
        raise AssertionError(f"the worker printed nothing (exit {proc.returncode}): {proc.stderr[-500:]}")
    return json.loads(lines[-1])


def scan_bytes(data, tmp, name="fixture.pdf", **extra):
    path = tmp / name
    path.write_bytes(data)
    return run_worker({"mode": "scan", "pdf": str(path), **extra})
