# 0001: Installer, kit skeleton, and checker

Status: Completed
Created: 2026-10-17
Completed: 2026-10-18

## Outcome

`./install.py` creates a working, independently tracked knowledge-base project, or layers the
knowledge-base kit onto an existing project, and the project's `tools/check_kb.py` validates
it. This is roadmap candidate 2 ("Installer, kit skeleton, and checker").

## Scope

- `install.py` create mode and `--add-to` mode, with `--dry-run`, the manifest, and the
  hardening in the installer spec and ADR 0002.
- The `kit/` in the template's module format: `module.json`, `migrations.json` (empty chain),
  `files/`, `slots/`, `base/`.
- Kit contents: `kb.json`, the root and domain routers, `domains/_skeleton/`, `catalog/`,
  the README copyright note, the `AGENTS.md` guidance slot, the four specifications under
  `docs/kb/`, the strict front-matter parser, the tag grammar, and `tools/check_kb.py`.
- A `unittest` suite that creates and extends projects in scratch directories.
- Every criterion tagged `[C2]` in the installer, knowledge-base-format, and domain-lifecycle
  specifications.

## Non-goals

- `--upgrade` and migrations beyond validating the empty chain (candidate 5).
- Source conversion, scanning, and quarantine (candidate 3).
- `new_domain.py`, `new_entry.py`, `add_source.py`, `kb_status.py`, and the lifecycle checks
  of the domain-lifecycle spec tagged `[C4]` (candidate 4).
- Any domain content, sample sources, or process documents in the kit.
- Public-release documentation and the `LICENSE` file (candidate 6), and any change to
  `claude_project_template` (candidate 7).

## Assumptions

- The governing documents are the four approved specifications and ADRs 0001 and 0002.
  Where this plan and a specification differ, the specification wins and the plan is
  corrected.
- Python 3.9+ and git only; standard library only. Tests use `unittest`.
- Tests write only to temporary directories. No test touches `~/.claude`, the network, or
  another repository.
- The template's module format is read-only reference; step A.1 confirms its field names
  before the kit is shaped.
- The kit's `tools/` holds only the parser and `check_kb.py`; candidate 3 and 4 tools are
  added later and are starter-owned the same way.
- The checker has no domain-level checks from the lifecycle spec beyond what `[C2]` names
  (the `AGENTS.md` guidance items); it must not fail on a `domains/_skeleton/` tree or on a
  project with no domain.
- Graphify: skipped — the repository contained documents only (no code and no graph), and the
  plan enumerated every file and specification involved.

## Completion criteria

- `python3 -m unittest discover -s tests` passes and covers every `[C2]` criterion in the
  three specifications, each by a named test.
- Creating a project in a scratch directory yields the files, manifest, `main` branch,
  identity, and exclude entry the installer spec lists, and `tools/check_kb.py` passes in it.
- `--add-to` works on fixtures with markers, without markers, and with missing host files.
- The hardening cases in installer criteria 3, 6, 7, 8 and the kit validation in criterion 7
  fail closed with nothing written.
- A tracked-file search finds no personal path, address, or subject-specific content.
- An adversarial security review of the installer has no unresolved finding.
- `docs/development.md` records the commands used here.

## Constraints

- The installer writes into directories the owner names and runs git in a new directory; all
  of this is security-sensitive (ADR 0002). Tests stay in temporary directories, and the
  security review is a completion requirement.
- `--add-to` modifies an existing project, but only in tests against fixtures during this
  plan. Pointing it at a real project is a separate owner action.
- Nothing is committed, pushed, or published without explicit approval, and no dependency is
  installed.
- Ambiguous specification criteria are recorded and raised with the owner rather than
  resolved silently.

## Increments

### Increment A — Test harness and front-matter parser

Dependencies: None
Affected areas: `tests/`, `kit/files/tools/kbparse.py`, `docs/development.md`

1. Read the template's module format (read-only) and record any difference from the
   installer spec in a note for the owner; do not change the specification without approval.
2. Add the `tests/` package with a helper that builds scratch projects.
3. Write failing tests for the strict front-matter subset (every rule, including a title
   with a colon, a duplicate key, a tab, a flow list, a comment) and for the tag grammar
   (valid tags, `[x]`, link text, a hyphen for the em dash, a tag in a fenced block, a note
   wrapped across lines, a wrap across a blank line, a conflict note).
4. Implement `kbparse.py` (front matter, tags, stems, characters) until the tests pass.
5. Record the test commands in `docs/development.md`.

Completion: parser and grammar tests pass; format spec criteria 2 and the parser-fixture
paragraph are covered.

### Increment B — Kit skeleton and module files

Dependencies: Increment A
Affected areas: `kit/module.json`, `kit/migrations.json`, `kit/files/`, `kit/slots/`,
`kit/base/`

1. Write `module.json` and `migrations.json` per the installer spec.
2. Write `files/`: `kb.json`, `playbook/README.md` (with the `kb:domains` markers and exact
   header), `catalog/README.md`, `sources/README.md` and `text/README.md`, `domains/_skeleton/`
   (charter template, `questions.md`, `log.md`, `index/`, domain router, `topics/`,
   `usage-tests/`, the three notes files), and `docs/kb/` copies of the four specifications
   with lines linking to `../roadmaps/` removed.
3. Write `slots/`: `agents-guidance` (the four items in the lifecycle spec), `readme-docs`
   (the copyright and licensing note), `docs-index`, `gitignore` (ignore the contents of
   `sources/` and `text/` except their READMEs).
4. Write `base/` with the `README.md`, `AGENTS.md`, and `.gitignore` carrying the markers.
5. Add tests: the `docs/kb/` drift test (installer criterion 10) and a search that the kit
   has no subject-specific content. Kit validation by the installer (criterion 7) is built in
   Increment D, where the validating code exists.

Completion: the drift and content-search tests pass against the kit.

### Increment C — `check_kb.py`

Dependencies: Increment B
Affected areas: `kit/files/tools/check_kb.py`, `tests/`

1. For each of format criteria 1 to 16, write a fixture project that violates only that rule
   and a test expecting the failure message to name the file and, where relevant, the line;
   include the catalog invariants, required fields, clone and strict modes, router
   structure, superseded handling, and the `Reviewed:` link.
2. Implement the checker, skipping `domains/_skeleton/`, with the warnings the spec lists,
   `--require-sources`, and exit statuses that match failures and warnings.
3. Test that a freshly built skeleton project with no domain passes, and that a clone with an
   empty `sources/` directory warns rather than fails.

Completion: all format criteria fixtures pass; the checker passes on a skeleton project.

### Increment D — Installer: create mode

Dependencies: Increment B
Affected areas: `install.py`, `tests/`

1. Write tests for installer criteria 1 to 4 and 9 to 10 first: exact file set, name
   substitution limited to the allowed files, `main` with no remote or commits, the local
   identity, the `.debug/` exclude, the refusals (existing target, target inside the starter,
   symlinked target, read-only target, bad name, missing identity), `--dry-run`, and the
   manifest contents and checksums. `--dry-run` is tested for create mode: a complete path
   listing and a byte-for-byte unchanged (still absent or empty) target. Also test the kit
   validation cases of criterion 7 (`module.json` and `migrations.json` rules, substitution
   leaving `docs/kb/` and `tools/` untouched) and, in a created project, a named test that
   `AGENTS.md` contains each of the four guidance items (domain-lifecycle criterion 7).
2. Implement the safe-write layer (lstat, `O_NOFOLLOW`, `O_NONBLOCK`, size cap, temporary
   sibling and rename, case-insensitive `.git` refusal), kit validation, the manifest, the
   sanitized git runner, and create mode.
3. Run the created project through `tools/check_kb.py` in a test (installer criterion 2).

Completion: criteria 1 to 4 (create mode), 7 (kit validation), 9, and 10 and domain-lifecycle
criterion 7 pass; a created project passes the checker.

### Increment E — Installer: `--add-to` and block parsing

Dependencies: Increment D
Affected areas: `install.py`, `tests/`

1. Write tests for installer criteria 5 to 7: markers, appended managed blocks in the
   specified serialized form, `base/` for missing host files, conflicts, non-empty content
   directories, the block-parsing refusals, no git command against the target, and the
   "already installed" status with a repeated run after a simulated early failure. Test
   `--dry-run` with `--add-to` on a fixture: a complete listing of every path and block it
   would write, and a byte-for-byte unchanged fixture.
2. Implement block parsing and insertion, preflight, and the add-to flow, writing the
   manifest last.

Completion: criteria 5 to 7 and criterion 4 (add-to mode) pass.

### Increment F — Hardening and review

Dependencies: Increments D and E
Affected areas: `install.py`, `tests/`, `docs/development.md`

1. Write the hardening tests for installer criterion 8: a FIFO and a symlink in a fixture,
   an over-cap (above 16 MiB) regular file (refused by default; with `--skip-unsafe-entries`
   skipped, listed, and never read, patched, or written through), `.GIT` components, a
   symlinked kit entry, `--skip-unsafe-entries` behavior, and a hostile `.git` with
   configured helpers and `GIT_*` in the environment.
2. Fix what the tests expose.
3. Run the full suite and the tracked-file search for personal paths or addresses.
4. Request an adversarial review using the owner's global `security-review` skill and
   `security-reviewer` agent. Evidence is the review's findings list with a disposition for
   each, recorded in the Result. Fix confirmed findings, add a named test for each, and rerun
   the suite.
5. Update `docs/development.md` with the final command table.

Completion: every `[C2]` criterion has a passing named test, the security review has no open
finding, and the commands are documented.

## Verification

- `python3 -I -B -m unittest discover -s tests` is the full check; 262 tests pass.
- `git diff --check` is clean.
- A manual run of `./install.py` into a scratch directory, `tools/check_kb.py` inside it, a
  repeat `--add-to` refused as already installed, and `--add-to --dry-run` listing its writes.
- A search of tracked files for personal paths and addresses (`test_repo.AuditTests`).
- Codex plan review: 3 of 3 rounds, 5 findings applied, 0 rejected. The last round did not
  converge; its findings were applied before approval.

## Deferred work

- Upgrade (candidate 5), source pipeline (candidate 3), and domain tools plus lifecycle
  checks (candidate 4).
- Adding `LICENSE` and the README quick start (candidate 6).
- Template-side loading of this kit (candidate 7).
- Security review areas not covered: end-to-end checker timing on a hostile project with many
  files, a CRLF fuzz of host files, hashing a huge sparse source (`hash_file` has no size
  cap), a starter-local `.git/config` or `.gitattributes`, and case variants beyond
  uppercase.

## Result

Implemented in commit `15dfbb1` and accepted by the owner on 2026-10-18.

- **Suite:** 262 tests, all passing. The manual run created a project that passed
  `tools/check_kb.py`.
- **Template format (step A.1):** the template's `module.json` has `description`, `requires`,
  `order`, an optional `harness`, and `hint`. The kit adds `name` and `kit_version`. The
  owner confirmed on 2026-10-18 that the template rewrite tolerates them.
- **Specification edits made during the work:** `base/` also holds `docs/README.md`, and a
  directory holding only kit-identical files is not "non-empty" (a retry after a failure).
  Both are in `docs/specs/installer.md` and its `docs/kb/` copy.
- **Security review:** two adversarial passes by the `security-reviewer` agent. Pass 1 found
  5 Medium and 6 Low issues; pass 2 (partial, stopped at its turn limit) found 1 Medium and
  5 Low. Every finding was fixed with a regression test that failed first
  (`tests/test_security_regressions.py`). Pass 2 was not re-run after the last fixes.
  Residual risks are those listed in ADR 0002 plus the uncovered areas under Deferred work.

### Codex plan review

- Rounds used: 3 of 3 (models and effort: low, low, high).
- Outcome: not converged in round 3; 5 findings applied, 0 rejected.

### Traceability of every `[C2]` criterion to its tests

| Criterion | Tests |
|---|---|
| Installer 1 | `test_install_create.Criterion1ExactOutput` |
| Installer 2 | `test_install_create.Criterion2CheckerPasses` |
| Installer 3 | `test_install_create.Criterion3Refusals` |
| Installer 4 | `test_install_create.Criterion4DryRun`, `test_install_addto.Criterion4DryRunAddTo` |
| Installer 5 | `test_install_addto.Criterion5Insertion` |
| Installer 6 | `test_install_addto.Criterion6BlockParsing`, `test_security_regressions.L5BlockParserFidelity` |
| Installer 7 | `test_install_addto.Criterion7Behaviour`, `test_install_create.Criterion7KitValidation` |
| Installer 8 | `test_install_hardening` (FIFO, symlink, size-cap, path-rule, hostile-git classes) |
| Installer 9 | `test_repo.AuditTests` |
| Installer 10 | `test_install_create.Criterion2CheckerPasses`, `test_kit.DriftTests` |
| Format 1 to 16 | `test_check_kb` classes `Criterion1Marker` to `Criterion14To16Hygiene` |
| Format parser fixtures | `test_kbparse` |
| Lifecycle 7 | `test_install_create.Criterion2CheckerPasses`, `test_kit.SlotContentTests` |
