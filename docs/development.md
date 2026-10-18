# Development

## Setup

Python 3.9 or newer and git, standard library only; macOS and Linux (the installer
uses `O_NOFOLLOW`, FIFOs, and POSIX permissions). Nothing to install for the installer. Tests
write only to temporary directories and set `GIT_CONFIG_GLOBAL` to an empty file, so they never
read or change your git or Claude configuration. Run Python with `-I` so a stray module in the
working directory cannot be imported.

The source pipeline (`kit/files/tools/convert_*.py`) needs two things this repository does not
install: a virtual environment outside the repository with `pymupdf` and `pymupdf4llm`, and
`pdftotext` (poppler) on `PATH`. For example, create the environment once with
`python3 -m venv ~/.venvs/pdf-md` and `~/.venvs/pdf-md/bin/pip install pymupdf pymupdf4llm`. The tests
that open PDFs run only when `KB_PDF_PYTHON` names that environment's interpreter; without it they
are reported as skipped, and the rest of the suite still passes. Run the converter itself with the
same interpreter.

## Commands

Keep this table accurate. Use `not applicable` rather than leaving an
ambiguous blank.

| Purpose | Command |
|---|---|
| Setup | not applicable (Python 3.9+ and git; standard library only) |
| Run locally | `python3 -I install.py <target> --git-name "N" --git-email "id+user@users.noreply.github.com"`; add `--dry-run` to preview. It creates a standalone store and prints how to register it with the project template |
| Upgrade a store | `python3 -I install.py --upgrade --dir <store> [--dry-run]`, run from the starter checkout. It replaces unedited starter-owned files, adds missing ones, skips and reports the owner's edits, never touches content, runs no git command against the store, and never commits; review the result with `git diff` and `git status` in the store |
| One focused test | `python3 -I -m unittest discover -s tests -p 'test_kbparse.py'` (any `test_*.py` name) |
| Full tests | `KB_PDF_PYTHON=<venv>/bin/python python3 -I -B -m unittest discover -s tests` (about 100 seconds; without the variable the PDF tests are skipped) |
| Run the converter | `<venv>/bin/python -I <project>/tools/convert_sources.py` (`--scan`, `--check`, `--images`, `--release <stem>`; see `docs/kb/source-pipeline.md`) |
| Check a project | `python3 -I <project>/tools/check_kb.py` (`--require-sources` once sources are saved) |
| Lifecycle tools | `python3 -I <project>/tools/new_domain.py <name> --title T`, `new_entry.py <domain> <slug>`, `add_source.py <stem> <file.pdf> --title T`, `kb_status.py [domain] [--json]`; each takes `--root DIR`; see `docs/kb/domain-lifecycle.md` |
| Format | not applicable |
| Lint or static analysis | not applicable |
| Type check | not applicable |
| Build | not applicable |
| All required checks | `KB_PDF_PYTHON=<venv>/bin/python python3 -I -B -m unittest discover -s tests && git diff --check`; with `KB_PDF_PYTHON` set no PDF test may be skipped; the only expected skips are by design (the two permission tests when run as root, the test that needs an interpreter without `pymupdf`, and the case-sensitive-filesystem test, which skips on case-sensitive filesystems such as most Linux setups), so report the number skipped and name each |

## Verification workflow

1. Run the narrowest check covering the change.
2. Inspect the complete useful failure output and correct the root cause.
3. Rerun the failed check.
4. Run the broader required check when practical.

Document checks that intentionally update snapshots, fixtures, generated code,
or tracked artifacts.

## Local debug artifacts

Keep retained, untracked diagnostics in
`/.debug/<YYYY-MM-DD>-<topic>/`. Opt in locally; do not add this directory to
the tracked `.gitignore`:

```sh
printf '/.debug/\n' >> .git/info/exclude
mkdir -p .debug
```

Include a local README with the source commit, command and tool versions,
purpose, and conclusion. These artifacts are not portable to fresh clones or
worktrees. Record durable findings in tracked documentation, decisions, or
tests instead.

## Debugging

Run one test file with `python3 -I -B -m unittest discover -s tests -p 'test_upgrade_plan.py'` (add `-k`
to select a test by name). Tests build their stores and kits in temporary directories under the system
temp directory and remove them afterwards. Preview an installer or upgrade run with `--dry-run` before
writing anything. A skipped PDF test means `KB_PDF_PYTHON` is not set; a failure in a converter test with the
variable set is more likely the environment (missing `pymupdf`, `pymupdf4llm`, or `pdftotext`) than the
product, so check those first.

## Tool-specific guidance

Use the repository's documented command interface. Add guidance for a build
system, language server, generated files, or other tool only when the project
uses it. Keep project-wide tool configuration committed and distinguish each
tool's exclusions from other tools' input filters.

<!-- @module-slot: development-tools -->
