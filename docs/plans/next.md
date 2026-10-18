# Domain lifecycle tools

Status: Approved (2026-10-18, by the owner; implementation authorized in the same request)
Created: 2026-10-18

## Goal

Ship the domain lifecycle tooling in every store's `tools/`: `new_domain.py`, `new_entry.py`,
`add_source.py`, and `kb_status.py`, and extend `check_kb.py` with the lifecycle checks in
`docs/specs/domain-lifecycle.md`. A person or agent can then create a domain, save a source, scaffold
an entry, see what a domain lacks, and have the checker enforce the artifacts, with fixture tests for
every criterion tagged `[C4]`.

## Scope

- `kit/files/tools/new_domain.py`, `new_entry.py`, `add_source.py`, and `kb_status.py`.
- `kit/files/tools/kblife.py` (readers for the lifecycle artifacts: charter, question table, log,
  reading notes, usage tests, conflict notes) and `kit/files/tools/kbfiles.py` (the safe reads and
  atomic writes the tools share). The converter's copies of those helpers move to `kbfiles.py`.
- `kit/files/tools/templates/entry.md`, the entry template `new_entry.py` copies.
- The lifecycle checks in `check_kb.py` (acceptance criterion 4) and the clone-mode behavior (criterion 6).
- Documentation: `docs/development.md`, `docs/architecture.md`, and the store README.

## Non-goals

- Searching, summarizing, or judging sources: tools only do the mechanical parts (the specification's
  principle 5). No crawling, no URL fetching.
- Web pages and other source formats (candidate 3 stayed PDF-only); splitting, merging, or retiring domains.
- Upgrade (candidate 5), the README quick start and `LICENSE` (candidate 6), and Claude skills (candidate 8).
- Changing the installer, the manifest, or `kb_schema`: new files under `tools/` are starter-owned and
  need no schema change. The specification is not amended by this plan.

## Assumptions and constraints

- Roadmap candidate 4, after candidates 2, 2a, and 3 (done). The specification
  (`docs/specs/domain-lifecycle.md`, Approved 2026-10-17) is the requirement; criterion 7 (`AGENTS.md`
  guidance) was delivered by candidate 2 and only needs to keep passing.
- Verified by reading: the skeleton already holds `questions.md`, `log.md`, `index/sources.md`,
  `index/leads.md`, the charter with `REPLACE_WITH_` text, and the domain router; the root router has the
  `kb:domains` markers and a three-column table; `check_kb.py` already checks entries, both routers, the
  catalog, and `REPLACE_WITH_` text, and imports `kbparse` by inserting its own directory into `sys.path`;
  the converter owns `state`, `scan`, and `released`, and `add_source.py` owns `saved` and `replaced`.
- Standard library only, Python 3.9+, no new dependency, nothing installed. The new tools never open a PDF,
  so their tests need no `KB_PDF_PYTHON`.
- Every tool reads and writes only inside the store, refuses symlinks and special files, writes through a
  temporary sibling and a rename, never deletes, and prints what it changed. Names and stems are validated
  by the same rules as `kbparse` before they reach a path.
- Interruption protocol (a process killed between two writes). Each multi-file change is ordered so the
  interrupted state is one the checker names exactly, and each tool either resumes it safely or refuses with
  a precise repair instruction; no tool ever leaves a state it cannot describe:
  - `new_domain.py` builds the whole domain tree in a hidden temporary directory under `domains/` (the
    checker skips names starting with a dot), renames it into place in one step, and only then adds the
    root-router row. A kill before the rename leaves only a hidden temporary directory, ignored by the
    checker and by the next run (which refuses nothing because the name is free). A kill after the rename
    leaves a complete domain missing only its root-router row: the checker reports exactly that, the tool
    refuses the existing name, and its message says to add the one row by hand (the row is printed).
  - `new_entry.py` writes the entry file, then the domain-router row. A kill between them leaves an entry
    the router does not reference: the checker reports it, the tool refuses the duplicate ID, and the
    message prints the row to add.
  - `add_source.py` copies the file into place, then writes the record. It is idempotent by hash: with the
    same bytes already in `sources/` and no record (or, for `--replace`, a record that still has the old
    hash), a rerun completes the missing write; with different bytes it refuses.
- Choices made in this draft that the owner may overrule:
  - New modules `kblife.py` and `kbfiles.py`; the entry template is `tools/templates/entry.md`, outside
    `domains/`, because the checker reads every `*.md` under a domain's `playbook/entries/` as an entry.
  - `add_source.py` accepts a `.pdf` file only (it must start like a PDF), because the converter is
    PDF-only. A source in another format is recorded link-only (`state: recorded`) until a later candidate
    adds that format.
  - An entry ID is `pb-<slug>`, the slug matching `[a-z0-9-]+`, unique across all domains.
  - `new_domain.py` fills the root-router "Purpose" cell with the title (the charter's purpose is
    written later by a person).
  - `kb_status.py --json` prints one object with `schema: 1`, sorted keys, and the section names used in
    the human report; the section list is fixed in Increment D.
  - Dates come from one function that tests replace, so output is deterministic.

## Graphify

Graphify: skipped — no graph exists in this checkout. The scope is enumerated by the approved lifecycle
specification and by direct reading of the skeleton, `check_kb.py`, `kbparse.py`, and the converter. The
new tools are self-contained under `tools/`; the only existing code they change is the helper functions
the converter will import from `kbfiles.py` and the additions to `check_kb.py`.

## Completion criteria

- Every `[C4]` criterion (1 to 6) in `docs/specs/domain-lifecycle.md` has a passing test, and criterion 7
  still passes.
- A store made by the installer can, with only these tools and by hand where the specification says a person
  writes (charter, questions, entry body): create a domain, save a PDF, convert it, scaffold and fill in an
  entry, and pass `check_kb.py --require-sources`; `kb_status.py` then reports the domain.
- A security review of the new tools' file handling and parsing finds nothing open.
- `KB_PDF_PYTHON=<external interpreter> python3 -I -B -m unittest discover -s tests` and `git diff --check`
  pass, and `kit/` contains no `__pycache__`.

## Increments

### Increment A — Shared readers and safe writes

Dependencies: None
Affected areas: `kit/files/tools/kbfiles.py`, `kit/files/tools/kblife.py`,
`kit/files/tools/convert_sources.py`, `tests/test_kbfiles.py`, `tests/test_kblife.py`

1. Write the failing tests first for `kblife.py`: the question table (columns, `q-<number>` IDs, duplicate
   IDs, status rules: `open` lists no entry, `answered` and `partial` list at least one, `partial` needs a
   Notes cell); the log grammar (`wave N opened` with `Goal:`, `Targets:`, `Limit:`, and optional `Gaps:`;
   `closed` with `Added:`, `Left open:`, `Reviewed:`, and `Gap result:` when `Gaps:` was given; `abandoned`
   with `Reason:` and `Resume from:`; `charter` with `Change:` and `Reason:`; numbering from 1 with no gap;
   closed or abandoned only after opened and not both); the charter's six headings in order; reading notes
   (front matter `source`, `read`, `by`, and a non-empty `## Findings`); usage-test front matter; conflict
   notes with at least two stems.
2. Implement `kblife.py` as pure readers over text, bounded by line and table sizes, returning positioned
   errors and no side effects.
3. Move the converter's `real_dir`, `write_atomic`, `read_head`, and `sha256_file` into `kbfiles.py`, have
   `convert_sources.py` import them, and add tests for the moved behavior (symlink, special file, size cap,
   permission-keeping rename). The existing converter tests must still pass unchanged.
4. Run the new tests and the converter tests.

Completion: the readers and shared helpers pass their tests, and the converter suite is unchanged.

### Increment B — Lifecycle checks in `check_kb.py`

Dependencies: Increment A
Affected areas: `kit/files/tools/check_kb.py`, `tests/projects.py`, `tests/test_check_lifecycle.py`

1. Write the failing tests first, one per clause of criterion 4: a set charter missing any of the six
   headings or containing `REPLACE_WITH_`; fewer than three questions in a set domain; a domain with
   entries and `charter: draft`; question-table failures (missing column, duplicate ID, missing entry,
   `open` with entries, `answered` without, `partial` with an empty Notes cell); a stem in
   `index/sources.md` with no catalog record; a usage test without a valid `result`; each log-grammar
   failure including the `Gap result:` rules; a conflict note naming a stem with no catalog record; a source
   in state `read` with no valid reading note in a domain that lists it, an empty Findings section, or
   `REPLACE_WITH_` text. Add the matching passing fixtures, and the clone-mode case (criterion 6): records
   whose sources are absent stay valid.
2. Extend `tests/projects.py` with builders for a set domain (charter, questions, log) and a reading note.
3. Implement the checks in `check_kb.py` using `kblife.py`. Findings name the file and line and never
   repeat source-derived text beyond a short label.
4. Run the checker tests and the full suite. The skeleton and a store with no domain must still pass.

Completion: every clause of criterion 4 has a failing-then-passing test, and existing checker tests pass.

### Increment C — The writing tools

Dependencies: Increment A (Increment B for the combined checks in step 5)
Affected areas: `kit/files/tools/new_domain.py`, `new_entry.py`, `add_source.py`,
`kit/files/tools/templates/entry.md`, `tests/test_new_domain.py`, `tests/test_new_entry.py`,
`tests/test_add_source.py`

1. Write the failing tests first.
   - `new_domain.py <name> --title <title>`: copies the skeleton, sets `domain`, `title`, `created`, and
     `charter: draft`, writes the domain router, adds the root-router row between the markers, writes the
     first `charter` log entry; the result passes the check. It refuses a duplicate or invalid name, a
     missing or out-of-order marker pair, a symlinked `domains/`, and an existing path, and writes nothing
     when it refuses.
   - `new_entry.py <domain> <slug>`: refuses an unset charter, an unknown domain, a duplicate ID across
     domains, and an invalid slug; creates the entry from the template with a unique `pb-` ID and a
     domain-router row stub; the check then fails on `REPLACE_WITH_` until both are filled in.
   - `add_source.py <stem> <file>` (with `--title`, `--tier`, `--confirmed`, `--kind`, `--url`, `--authors`):
     copies a PDF to `sources/<stem>.pdf`, writes the record with the correct SHA-256 and `state: saved`,
     `scan: none`; refuses an invalid stem, a symlink or special file, a file that does not start like a
     PDF, a quarantined stem, and an existing stem without `--replace`. `--replace` updates `sha256`,
     resets `state` to `saved` and `scan` to `none`, removes `released`, and sets `replaced`. A link-only
     record (`--record-only`, or a non-PDF source) stays `state: recorded` with a note why.
2. Create the entry template under `tools/templates/entry.md` (front matter, the five required headings,
   `REPLACE_WITH_` placeholders for the title and situation).
3. Implement the three tools on `kbfiles.py` and `kblife.py`: validate every name and stem before it reaches a
   path, check every directory is real, write through a temporary sibling and a rename, follow the
   interruption protocol in the assumptions above, and print each path changed. Dates come from one
   replaceable function.
4. Add a test that runs each tool with a symlink, a FIFO, and an over-size file in the way, and tests for the
   interruption protocol by stopping each tool between its writes (a patched writer that raises): the
   checker's message names the missing piece; `add_source.py` resumes by hash; `new_domain.py` and
   `new_entry.py` refuse and print the one row to add; after adding it by hand the check passes.
5. Run a combined scenario: create a domain, save a fixture PDF, scaffold an entry, fill the placeholders,
   and run the checker; it passes. Run the tool tests and the full suite.

Completion: criteria 1, 2, and 3 pass, and the combined scenario passes the check.

### Increment D — The status report

Dependencies: Increments A and B
Affected areas: `kit/files/tools/kb_status.py`, `tests/test_kb_status.py`

1. Write the failing tests first, over a fixture domain with known counts, for every item in operation 3
   step 1: sources by state, tier, and scan; recorded-but-never-saved; quarantined awaiting release;
   sources in the domain index that no entry cites; entries citing a replaced source; entries by status and
   claim-tag counts, with entries that have no `[V]`; open and partial questions; open conflicts with
   entry and stems, and a malformed conflict note (fewer than two stems); waves still open or abandoned;
   the leads backlog; stale entries with `--stale-days`; the charter state; the latest usage test and its
   result; and each `Gap result:` category. Also: the report writes nothing and changes no entry; `--json`
   output is stable (sorted keys, `schema: 1`); a clone with no sources shows sources as unsaved rather than
   failing.
2. Implement `kb_status.py [domain]` on `kblife.py`: a read-only report, plain text by default and `--json`,
   bounded reads, and the section names fixed by the tests.
3. Run the status tests and the full suite.

Completion: criteria 5 and 6 pass.

### Increment E — Documents, review, and the real-store check

Dependencies: Increments A to D
Affected areas: `docs/development.md`, `docs/architecture.md`, `kit/files/README.md`, `kit/kit.json`

1. Update `docs/development.md` (commands table), `docs/architecture.md` (components and the lifecycle
   tools), the store README (one line on the tools), and the kit hint if it should name the first command.
2. Security verification. The tests are the repository-executable evidence: named hostile-input tests for
   path traversal through a domain name, slug, or stem; a symlink or FIFO at every file the tools touch; a
   catalog or log file with injected front matter or table rows; control and bidirectional characters in a
   title, URL, or author argument; a huge table or log (cost, with a time bound); a half-finished run
   (the interruption protocol); and `--replace` on a quarantined or converted source. In addition, run the
   owner's personal `security-review` skill with the `security-reviewer` agent (neither is part of this
   repository; both are owner-provided tooling, used the same way for the previous plans). If either is
   unavailable, record that in the Result and substitute a written checklist of the same cases with the
   result of each. Add a regression test that fails first for each finding.
3. Real-store check: create a store with the installer, then use only the tools to create a domain, save a
   PDF, convert it, scaffold an entry, and fill in the placeholders; run `check_kb.py --require-sources` and
   `kb_status.py`; confirm a second `kb_status.py` run changes nothing.
4. Run the full suite with `KB_PDF_PYTHON` set, and `git diff --check`.

Completion: documents match the built tools, the review has nothing open, the real-store check passes, and
the full suite passes with no test skipped.

## Verification

- `KB_PDF_PYTHON=<external interpreter> python3 -I -B -m unittest discover -s tests`: the new `[C4]`
  tests plus the existing suite; report the number skipped, which must be zero.
- `python3 -I -B -m unittest discover -s tests` without the variable: the PDF tests skip and everything
  else, including every new lifecycle test, passes.
- `git diff --check`, and `git status` shows no `__pycache__` under `kit/` or `tests/`.
- The real-store check in Increment E.

## Risks and sensitive actions

- Writes into a store's tracked files (catalog records, routers, logs). Each tool validates names, refuses
  symlinks, and writes atomically; none deletes. A multi-file change follows the interruption protocol in the
  assumptions: the interrupted state is one the checker names, and each tool resumes it (`add_source.py`) or
  refuses and prints the single repair step (`new_domain.py`, `new_entry.py`).
- Parsing untrusted markdown (question tables, logs, reading notes, `index/` files, catalog fields). The
  readers are bounded in line length and table size and run in linear time; findings never echo long
  source-derived text.
- `add_source.py` reads a user-named file. It opens it as a regular file without following symlinks, hashes
  it, and checks only its first bytes; it never parses a PDF.
- Moving the converter's helpers into `kbfiles.py` touches working code; the converter suite must stay
  unchanged and green.
- No dependency is installed. No commit, push, or deletion happens without explicit owner approval.

## Review

Codex plan review (2026-10-18, `gpt-5.6-luna`, effort low): converged in 2 of 3 rounds. Round 1 returned two
major findings, both applied: the plan now defines an interruption protocol for each tool (a partial
`new_domain.py` or `new_entry.py` is named by the checker and repaired by one printed step, and
`add_source.py` resumes by hash) in place of an unconditional "a rerun completes it", and the security
verification step is stated as named hostile-input tests plus the owner's personal skill and agent, with a
written checklist as the fallback when they are unavailable. Round 2 found nothing. The plan stays Proposed
until the owner approves it; the owner approved it on 2026-10-18. (The review slot for the earlier plan titles was closed; the owner patched the
helper so a plan is identified by its title and creation date, and this plan was reviewed under its own
title, `Domain lifecycle tools`.)

## Deferred work

- Other source formats and web capture (a later candidate) and `add_source.py` support for them.
- Splitting, merging, or retiring domains; a per-domain stale threshold; a conflicts register.
- Upgrade, release readiness, and skills (candidates 5, 6, and 8).

## Result

<!-- Complete this only after verification. Archive the plan according to
README.md, then reset this file to the empty template. -->
