# Development

## Setup

Python 3.9 or newer and git, standard library only; macOS and Linux (the installer
uses `O_NOFOLLOW`, FIFOs, and POSIX permissions). Nothing to install. Tests write only to
temporary directories and set `GIT_CONFIG_GLOBAL` to an empty file, so they never read or
change your git or Claude configuration. Run Python with `-I` so a stray module in the
working directory cannot be imported.

## Commands

Keep this table accurate. Use `not applicable` rather than leaving an
ambiguous blank.

| Purpose | Command |
|---|---|
| Setup | not applicable (Python 3.9+ and git; standard library only) |
| Run locally | `python3 -I install.py <target> --git-name "N" --git-email "id+user@users.noreply.github.com"`; add `--dry-run` to preview, or `--add-to <dir>` to layer onto a project |
| One focused test | `python3 -I -m unittest discover -s tests -p 'test_kbparse.py'` (any `test_*.py` name) |
| Full tests | `python3 -I -m unittest discover -s tests` |
| Check a project | `python3 -I <project>/tools/check_kb.py` (`--require-sources` once sources are saved) |
| Format | not applicable |
| Lint or static analysis | not applicable |
| Type check | not applicable |
| Build | not applicable |
| All required checks | `python3 -I -m unittest discover -s tests && git diff --check` |

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

<!-- Explain how to run one test, enable useful logging, locate generated
artifacts, reproduce common failures, and distinguish environment problems from
product defects. -->

## Tool-specific guidance

Use the repository's documented command interface. Add guidance for a build
system, language server, generated files, or other tool only when the project
uses it. Keep project-wide tool configuration committed and distinguish each
tool's exclusions from other tools' input filters.

<!-- @module-slot: development-tools -->
