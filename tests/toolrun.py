"""Run one of the store's tools in-process with a fixed date, returning (code, stdout, stderr)."""
import contextlib
import datetime
import io

TODAY = datetime.date(2026, 10, 18)


def run_tool(module, root, *argv, today=TODAY):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = module.main(["--root", str(root), *argv], today=today)
        except SystemExit as exit_:
            code = exit_.code if isinstance(exit_.code, int) else 1
    return code, out.getvalue(), err.getvalue()
