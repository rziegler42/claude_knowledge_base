# Architecture

## Scope and goals

This repository is a generator, not a knowledge base. Its installer creates a standalone,
independently tracked knowledge-base store: a fresh git repository holding the tools, the
specifications, and an empty skeleton, to which the owner adds domains of their own. It carries
no subject matter. A store needs nothing from this repository once it exists.

Not built yet: upgrading a store. The roadmap orders the remaining work
(`docs/roadmaps/knowledge-base-starter.md`).

## Components and responsibilities

- `install.py` creates a store and upgrades one (`--upgrade`). It uses only the Python standard library and git.
- `kit/` is the tree the installer copies: `files/` (everything a store receives),
  `kit.json` (kit version and the closing hint), and `migrations.json` (schema migration steps,
  empty at schema 1).
- `kit/files/tools/` holds the store's own tools: `kbparse.py` (the strict front-matter and claim-tag
  parser), `check_kb.py` (the validator), and the source pipeline: `convert_sources.py` (the command),
  `convert_worker.py` (opens one PDF), `kbscan.py` (the scan rules that need no PDF library), and
  `scan_phrases.txt` (the phrase list). The lifecycle tools are `new_domain.py`, `new_entry.py` (with
  `templates/entry.md`), `add_source.py`, and `kb_status.py`; `kblife.py` reads the lifecycle artifacts
  (question table, log, charter, reading notes, usage tests) for the checker, the status report, and the
  tools, and `kbfiles.py` holds the safe reads and atomic writes they and the converter share.
  `kit/files/docs/kb/` holds copies of the four specifications, guarded by a drift test.
- `kit/files/template-module/` is the descriptor that lets `claude_project_template` register a store
  and insert guidance into other projects. Its `harness/claude/` directory holds the one skill a project
  can install from the store after the owner approves it.
- `tests/` is a `unittest` suite that creates stores in scratch directories.
- `docs/` holds this repository's own decisions, specifications, plans, and roadmaps. None of them is
  shipped to a store.

## Data and control flow

1. `load_kit` validates the kit before any write: `kit.json`, the `migrations.json` chain, and a walk
   of `files/` that refuses symlinks, special files, `.git` components, and oversize files.
2. `run_create` resolves the target by real path, refuses the starter and anything inside it, requires
   an empty or absent directory, and resolves an explicit git identity.
3. Every kit file is written through a temporary sibling and a rename. The project name replaces
   `REPLACE_WITH_PROJECT_NAME` everywhere except `tools/`, `docs/kb/`, and `template-module/`, which are
   copied byte for byte.
4. `git init` runs on the new directory only, with `HEAD` on `main`, a local identity, and `/.debug/`
   excluded. `.kb-manifest` is written last, listing a checksum for each starter-owned file.
5. The installer prints the kit hint and one registration line for the template. It runs nothing else.

### Upgrading a store

`install.py --upgrade --dir <store>` reads the starter's kit and an existing store, and changes only
starter-owned paths (`kb.json`, `tools/`, `docs/kb/`, `domains/_skeleton/`, `template-module/`).

1. The owned set comes from the kit, never from the store's manifest. A manifest key outside the owned
   prefixes is ignored and reported, and a malformed manifest, an unsafe path, or a bad checksum refuses
   the run. The store is untrusted: a symlink, special file, oversize file, or symlinked parent at an owned
   path refuses the whole run before anything is written.
2. The schema check compares the manifest's `kb_schema` with `kb.json` and with the kit. A lower store
   needs a contiguous chain in `kit/migrations.json` (`add`, `replace`, `remove`, each idempotent); a
   higher store, a missing chain, or a disagreement refuses. A conflicting migration operation refuses
   before the first write and leaves `kb_schema` unchanged.
3. The plan is computed in memory (`Stage`): the chain first, then the ordinary table (replace unedited,
   add missing, skip and report edited, adopt or record files equal to the kit, report conflicts, keep
   recorded files no longer in the kit). `--dry-run` prints it and stops.
4. Applying stages every new file as a hidden sibling, verifies the copies, re-reads each target to
   detect an edit made since planning, then renames owned files, performs deletions, renames `kb.json`
   (second to last), and renames the manifest last. A crash leaves some files replaced; a rerun detects the
   rest from the manifest, `kb.json`, and checksums and finishes. Nothing is rewritten when nothing changed.
5. Git runs only in the starter checkout, to record `starter_commit` and `starter_dirty`. The upgrade
   never runs git in the store and never commits; it prints a reminder to review with `git diff` and
   `git status`.

### The source pipeline

A store's `convert_sources.py` uses only the standard library. For each saved PDF it starts
`convert_worker.py` as a child under the interpreter that has `pymupdf` and `pymupdf4llm`, in isolated
mode, with a scrubbed environment, a time limit, and an output limit; the child is killed when it
overruns either. The worker scans the file (structure, links, hidden text, annotations, metadata) with
the rules in `kbscan.py` and converts it to Markdown; `pdftotext` makes the plain-text copy. The
command writes both under `text/` with front matter and an untrusted-content banner, moves a flagged
original to `sources/quarantine/` and leaves a stub, and updates the catalog fields it owns (`state`,
`scan`, `released`). The source is never modified and nothing is deleted. The worker makes no network
connection. Requirements: `docs/specs/source-pipeline.md`.

### The lifecycle tools

The writing tools validate every name, stem, and title before it reaches a path, refuse symlinks and special
files, write through a temporary sibling and a rename, never delete, and print what they changed. A change
that spans files is ordered so an interruption leaves a state the checker names: `new_domain.py` builds the
domain in a hidden temporary directory, renames it into place, and then adds the root-router row;
`new_entry.py` writes the entry and then the router row; `add_source.py` copies the file and then writes the
record, and a rerun with the same file finishes it. The first two print the one row to add if the last write
fails. `kb_status.py` and `check_kb.py` only read.

## External interfaces

- Command line: `install.py <target>` with `--name`, `--git-name`, `--git-email`,
  `--use-global-git-identity`, and `--dry-run`; or `install.py --upgrade --dir <store>` with `--dry-run`.
  Exit status 0 success (including an upgrade that skipped edited files, which it lists), 1 refusal or
  error, 2 usage.
- The `template-module/` descriptor: `module.json`, an `agents-guidance` fragment and the consuming
  `knowledge-base` skill under `harness/claude/`, in the format the project template defines
  (`module_format` 3). It is the only coupling between the two repositories, and
  neither reads the other's code.
- The registration line, which tells the owner how to register the store with the template, with a
  suggested `--name` when the directory name is not a valid template module name.
- Inside a store, `python3 tools/check_kb.py` validates the layout, front matter, catalog, and claims,
  `python3 tools/kb_status.py` reports what each domain has and lacks, `new_domain.py`, `new_entry.py`, and
  `add_source.py` do the mechanical parts of adding content, and `<interpreter> tools/convert_sources.py`
  scans and converts sources (`--scan`, `--check`,
  `--images`, `--snippets`, `--release <stem>`, and limit flags).

## Constraints and tradeoffs

- Standard library and git only for the installer, so a store can be created anywhere Python 3.9 and git
  exist. The installer relies on POSIX file semantics (`O_NOFOLLOW`, FIFOs), so macOS and Linux only.
  The converter's PDF library (`pymupdf`, `pymupdf4llm`) and `pdftotext` are not installed by anything
  here; the converter reports what is missing.
- The installer treats the command line as intent and everything else as untrusted: it reads kit files as
  regular files with a size cap, refuses symlinks and `.git` path components, and runs git only in the
  starter checkout and, when creating, in the new directory with a scrubbed environment; an upgrade runs
  no git command in the store.
- Four root files (`README.md`, `AGENTS.md`, `docs/README.md`, `.gitignore`) are written once and belong to
  the store afterwards. Starter-owned files are the ones listed in the manifest.
- A store's descriptor follows the template's `module_format` by deliberate change, not automatically.

## Related decisions

- [ADR 0002](decisions/0002-installer-trust-model.md): installer trust model.
- [ADR 0003](decisions/0003-standalone-stores-coordinated-by-the-template.md): standalone stores,
  coordinated by the project template (supersedes
  [ADR 0001](decisions/0001-generator-with-independent-projects.md)).
- [Installer specification](specs/installer.md) and the other specifications in `specs/`.
