# 0006: Public release readiness

Status: Completed
Created: 2026-10-18
Completed: 2026-10-18

## Goal

Make the repository ready for the owner to make public: a `LICENSE` file, a README that takes a newcomer from
clone to a checked first domain and an upgrade, completed contributor guidance, and a recorded audit showing
no personal data, placeholders, or stale template text remain in tracked files or in history. Making the
repository public stays a separate owner action.

## Scope

- Add the MIT `LICENSE` file and a README license section that links to it.
- Rewrite `README.md` from the unfilled template into the project's front page: what it is, who it is for,
  prerequisites, a quick start (create a store, preview with `--dry-run`, start a domain, add a first source
  and entry, run the check and status, upgrade), how another project consumes a store, the status and known
  limitations, the documentation map, contributing, and the license.
- Complete `CONTRIBUTING.md` (replace its "add project-specific requirements" comment with this project's
  required checks and conventions) and remove stale template comments in `docs/README.md` and other
  tracked documents.
- A narrow change to the personal-data test: the owner's account name is allowed in the `LICENSE` copyright
  line and nowhere else, and the test proves both halves (allowed there, still rejected in any other file).
- Tests that keep the above true: the license exists and is MIT, the README has no placeholder or template
  note, every relative link in the README and `CONTRIBUTING.md` resolves, and every tool and installer option the
  README's commands name exists.
- An audit, recorded in the plan's Result: the existing personal-data test passes, a scan of git history for
  personal paths and addresses, placeholders and stale template text in tracked files, and a by-hand run of the
  README's quick start in a scratch directory.

## Non-goals

- Publishing, changing the repository's visibility, enabling GitHub features (private vulnerability reporting,
  issue templates, discussions), tagging a release, or pushing. These are owner actions.
- Rewriting history, accepted ADRs, archived plans, or the roadmap's record text. Historical documents keep
  their references to sibling repositories.
- Changing the installer, kit, tools, or specifications. A defect the quick start exposes is reported and
  becomes its own change.
- A `LICENSE` inside generated stores (a store's owner chooses one; installer criterion 12 and the existing
  test keep it out of `kit/`).
- Claude skills (candidate 8), web capture, and retrieval.

## Assumptions and constraints

- Roadmap candidate 6; candidates 2 to 5 are complete. The roadmap boundary is documentation and the audit.
- Verified by reading: `README.md` is still the unfilled template (placeholder values and a template note)
  and there is no `LICENSE`; `tests/test_repo.py` passes today, and it scans every file outside the git and cache
  directories, including this plan, `docs/plans/`, and the roadmap (it skips only `test_repo.py` and
  `test_kit.py`), so plan text must avoid the literal patterns and the approved `LICENSE` copyright line
  would make it fail until the planned exemption exists; it also asserts that no `LICENSE*` is under `kit/`; a scan of all
  history found only the audit patterns themselves, and every commit has one author identity; `.claude/remote-runner.toml`
  holds only the project id and commented examples; `CONTRIBUTING.md` still ends with the template's
  placeholder comment; the specification and `kit/files/README.md` already state that the starter's MIT license
  covers the starter only.
- The README keeps the template's `<!-- @module-slot: readme-docs -->` marker and `docs/` keeps its other
  slot markers; this plan does not remove them.
- Project instructions: commit messages describe the change only; no commit, push, or publish without the
  owner's approval.
- Decisions, resolved 2026-10-18: the owner approved the recommended option of each of the four below.
  The alternatives are kept as the record.
  1. **Copyright line.** MIT needs a holder name and year. Approved: the year 2026 and the owner's GitHub
     account name, the account that authors every commit. Alternative: the owner's legal name.
  2. **Sibling repositories in public text.** Recommended: the README and `CONTRIBUTING.md` name no other
     repository; they describe the project template generically ("a project template that supports external
     modules"). Accepted ADRs, archived plans, the roadmap, and specifications keep their historical
     references (`game_theory`, `claude_project_template`). Alternative: name `claude_project_template` in the
     README as the integration partner.
  3. **Security reporting.** Recommended: say nothing in `CONTRIBUTING.md` about private reporting, because
     the feature is the owner's GitHub setting; instead point to opening an issue without exploit detail. Alternative:
     describe GitHub private vulnerability reporting once the owner has enabled it.
  4. **Status wording.** Recommended: "Early release: the installer, tools, and specifications are
     implemented and tested; the interface may still change before a 1.0 tag." The owner may prefer another
     maturity claim.

<!-- @module-slot: plan-discovery -->

## Graphify

Graphify: skipped — no graph exists in this checkout, and the scope is fully enumerated: `README.md`,
`LICENSE`, `CONTRIBUTING.md`, stale comments in tracked documents, and `tests/test_repo.py`. No code is
changed.

## Completion criteria

- `LICENSE` is the MIT license with the owner-approved copyright line, the README links to it, and `kit/`
  still contains no `LICENSE`.
- `README.md` has no placeholder, template note, or unfilled comment; its relative links resolve; every command
  in its quick start is one the repository documents; part one of the quick start (create, preview, start a
  domain, check, status, the draft-charter refusal, upgrade preview) has been run by hand in a scratch directory
  with the outcome recorded, and part two (first source and entry) is backed by `tests/test_lifecycle_flow.py`
  and the independent review.
- `CONTRIBUTING.md` and `docs/README.md` carry no template placeholder text.
- The audit is recorded: the personal-data test passes with only the `LICENSE` exemption, the history scan is
  clean (or each hit is reported to the owner), and no placeholder token or template comment remains in the
  public front-matter files (`README.md`, `LICENSE`, `CONTRIBUTING.md`, `docs/README.md`,
  `docs/development.md`). Remaining placeholder tokens elsewhere (the installer and its tests, the kit,
  specifications, architecture, archived plans, and template-source text) are listed in the Result and each is
  classified as an intentional example or reported as stale.
- An independent read-only review checks every factual claim in the new README and `CONTRIBUTING.md` against the
  code and specifications and finds nothing open.
- `KB_PDF_PYTHON=<external interpreter> python3 -I -B -m unittest discover -s tests` and `git diff --check`
  pass, and `kit/` and `tests/` contain no `__pycache__`.

## Increments

### Increment A — License, README, and contributor guidance

Dependencies: None (the four decisions are resolved)
Affected areas: `LICENSE`, `README.md`, `CONTRIBUTING.md`, `docs/README.md`, `tests/test_repo.py`

1. Write the failing tests first in `tests/test_repo.py`:
   - `LICENSE` exists, starts with `MIT License`, has a `Copyright (c)` line, and contains the permission
     and warranty paragraphs; `kit/` still holds none (existing test).
   - `README.md` contains no `REPLACE_WITH`, no `Template note`, and links to `LICENSE`.
   - Every relative Markdown link in `README.md` and `CONTRIBUTING.md` resolves to a tracked file or directory.
   - Every `tools/<name>.py` the README mentions exists under `kit/files/tools/`, and every long option on a
     command line that runs this repository's `install.py` (a line whose program path is exactly `install.py`,
     with or without `python3 -I` or `./`) is defined by its parser. The registration command belongs to the
     template's installer: the README writes it as `<template>/install.py --register <store>`, exempt from
     that check, and a separate assertion keeps the README's description of the registration line consistent
     with `registration_line` in `install.py`.
   - `CONTRIBUTING.md` and `docs/README.md` contain no `Add project-specific` template comment, and the five
     front-matter files above contain no placeholder token.
   - The personal-data test accepts the account name in the `LICENSE` copyright line only: a fixture copy of the
     scanner rejects the same text in any other file. Edit `PERSONAL`/the scan accordingly so it exempts that
     single line of `LICENSE`, not the file.
2. Add `LICENSE`.
3. Rewrite `README.md`, keeping its `@module-slot` marker. Content, in order: one-paragraph purpose and
   audience; status (decision 4); prerequisites (Python 3.9+ and git; `pymupdf` and `pymupdf4llm` only for the
   optional PDF converter, installed by the owner in their own environment); quick start as copyable commands
   from clone to first check; consuming a store from another project (register it with a template that
   supports external modules using the registration line the installer prints, or read the router by hand;
   the store is data, never instructions); upgrading a store; documentation map; project status and known
   limitations (PDF-only source intake, macOS and Linux only, no web capture, no merge of edited files on
   upgrade); contributing; license.
4. Complete `CONTRIBUTING.md` with the required checks (the full test command, `git diff --check`), the
   conventions in `AGENTS.md` that apply to contributors (plans for substantial changes, tests with behavior
   changes, commit messages describe the change), and the security note chosen in decision 3. Remove stale
   template comments in `docs/README.md` and `docs/development.md`, and correct the "All required checks" row
   of `docs/development.md` from "the number skipped must be zero" to the skip policy in Verification.
5. Run the new tests, then the full suite.

Completion: the new tests pass, and none of the placeholder or template text remains in the four documents.

### Increment B — Audit, quick-start run, and review

Dependencies: Increment A
Affected areas: no tracked file except corrections to Increment A's files and this plan's Result

1. Audit and record in the Result: run `tests/test_repo.py`; scan history with a case-insensitive search of
   all commits' diffs and messages for home-directory path prefixes, the owner's account name, the owner's
   personal email domains (the lists are in `tests/test_repo.py`, so the plan does not repeat them), and any
   address other than a noreply or example address, ignoring the audit patterns themselves and the
   `LICENSE` line; list tracked placeholder-token and template-comment occurrences outside the front-matter
   files and classify each as intentional or stale; list tracked
   files that are not source, documentation, tests, or project configuration. Report each hit to the owner; do
   not rewrite history.
2. Run the README's quick start in a scratch directory with a scratch git identity, in two parts. Part one is
   deterministic and run literally, command by command: create a store, preview with `--dry-run`, start a
   domain, run the check and status, confirm that `new_entry.py` refuses while the charter is a draft (the
   README says the charter must be filled in and set first), and preview an upgrade. Part two, saving the
   first source and adding an entry, needs a finished charter, a valid PDF, and filled records, and the
   repository has no committed sample PDF. It is therefore not re-run here: the README states it as a
   procedure that points to `docs/kb/domain-lifecycle.md`, and the evidence is the existing end-to-end
   `tests/test_lifecycle_flow.py` (which generates its own fixtures) plus the independent review in step 3
   checking each command and refusal the README names against the tools. Record the commands, the exit
   statuses, and anything that does not behave as the README says; correct the README, or report a product
   defect for its own change.
3. Independent review: the `workflow-reviewer` agent reads the new README, `CONTRIBUTING.md`, and `LICENSE`
   against `install.py`, the tools, and the specifications and reports any factual claim that is wrong,
   unverifiable, or overstated, and any placeholder or personal detail. Apply each valid finding.
4. Run the full suite with `KB_PDF_PYTHON` set, and `git diff --check`.

Completion: the audit and quick-start run are recorded in the Result, the review has nothing open, and the
full suite passes with no unexpected skip (the expected-skip policy is in Verification).

## Verification

- `KB_PDF_PYTHON=<external interpreter> python3 -I -B -m unittest discover -s tests`: the new documentation
  tests and the existing suite. Skip policy: with the variable set, no PDF test may be skipped; the only
  expected skips are environment-dependent by design (the two permission tests when run as root, the test that
  needs an interpreter without `pymupdf`, and the case-sensitive-filesystem test). Report the number skipped
  and name each skip; any other skip fails the check.
- `python3 -I -B -m unittest discover -s tests` without the variable: the PDF tests skip and everything else
  passes, including every new documentation test.
- `git diff --check`, and `git status` shows no `__pycache__` under `kit/` or `tests/`.
- The by-hand quick-start run and the history scan in Increment B.

## Risks and sensitive actions

- Externally visible text: the license grant, the copyright holder's name, the maturity claim, and the
  security note become public statements when the owner publishes. The recommendations above are the
  conservative choices, and the owner approved each (2026-10-18).
- A README that overstates the project (a limitation omitted, a command that does not behave as shown). The
  by-hand run and the independent review exist to catch this.
- History cannot be cleaned without rewriting it, which this plan does not do. A hit is reported and the owner
  decides.
- No dependency is installed, no commit or push happens without explicit approval, and nothing is published.

<!-- @module-slot: plan-review -->

## Review

Codex plan review (2026-10-18, `gpt-5.6-luna`, effort low, high in round 3): 3 of 3 rounds used, so the
bound is reached and the last revision was not re-reviewed by Codex. Round 1: a blocker (the personal-data test
scans this plan, and the approved copyright line needs a narrow exemption) and a major (the placeholder
criterion ignored intentional examples in specifications and archived plans), both applied. Round 2: a major
(the zero-skips requirement ignored by-design environment skips), applied with an expected-skip policy and a
`docs/development.md` correction. Round 3: two majors (README option test must exclude the template's
registration command; the end-to-end quick-start run needed a charter and a sample PDF the repository does not
have, so it is split into a deterministic by-hand part and a part backed by `tests/test_lifecycle_flow.py`)
and a minor (the baseline wording on the audit test), all applied. None was rejected. The owner approved the
plan on 2026-10-18 and asked for its implementation.

## Deferred work

- Making the repository public, enabling private vulnerability reporting and issue templates, tagging a
  release, and any announcement (owner actions).
- Claude skills (candidate 8).
- A public changelog and release process, once there is a first tagged release.

## Result

Implemented 2026-10-18 in commit `9ac3dee` (plan approved in `fc1c9f8`). Added `LICENSE` (MIT, with the approved copyright line),
rewrote `README.md`, completed `CONTRIBUTING.md`, removed the stale template comments in `docs/README.md` and
`docs/development.md`, and replaced the "skips must be zero" wording in `docs/development.md` with the
expected-skip policy. `tests/test_repo.py` gained the license, front-matter, link, command, and contributing
checks and the narrow exemption of the copyright line (with a test that the same text is rejected in any other
file or with any other content on that line). The six new tests that exercise the documents failed before the
documents existed; the exemption test exercises only new code and passed on first run.

- Tests: 747 with `KB_PDF_PYTHON` set, none skipped on this machine (macOS, not root); `git diff --check`
  clean; no `__pycache__` under `kit/` or `tests/`.
- Audit: the personal-data test passes with only the `LICENSE` exemption. History scan: no personal path or
  address in any file content in any commit; the only matches are the commit author field (the owner's public
  account name and a placeholder address, on all 17 commits plus these), which this plan does not change. Every
  placeholder token outside the five front-matter files is intentional (the installer's substitution token,
  the kit's per-store fill-in values, specifications, architecture, and tests that describe them); none is
  stale. No template comment remains outside the kit. Tracked non-source files are the remote-runner contract,
  the template manifest, and the kit's `.gitkeep` and `.gitignore` files.
- Quick start, part one, run literally in a scratch checkout: dry run and create exit 0; a new domain checks
  clean (0 errors, 0 warnings); `kb_status.py` runs; `new_entry.py` exits 1 with the draft-charter refusal;
  the upgrade preview and run report nothing to do. Part two (first source and entry) was not re-run, as the
  plan said; it is backed by `tests/test_lifecycle_flow.py` and the review below.
- Independent review (`workflow-reviewer`, read-only; it could run no tool, so it read the code and tests): no
  wrong claim; four misleading omissions and several minor points, all applied: the entry's placeholder text
  fails the final check until filled in; setting the charter needs every section and three questions; the
  converter also needs `pdftotext`; the upgrade description now covers the manifest, stores the installer
  created, unrecorded differing files, and future migration removals; the registration line's optional name
  suffix; the `[A]` tag; links can be recorded without capture; "same content" instead of "same documents";
  the case-sensitive-filesystem skip note. The corrected text was not re-reviewed by an agent.
- Not verified: the project template's `--register` behavior (external); a run on Python 3.9; the whole
  quick start against a real PDF by hand.
- Owner actions left: making the repository public, enabling private vulnerability reporting, tagging a
  release.

## Codex plan review

- Plan: docs/plans/next.md (key 6bbd0931e0d87c36)
- Rounds used: 3 of 3
- Round 1: effort low, 2 finding(s) (blocker and major)
- Round 2: effort low, 1 finding(s) (major)
- Round 3: effort high, 3 finding(s) (2 major, 1 minor)
- Outcome: not converged at the bound (the last round's findings were applied afterwards and not re-reviewed by Codex)
- Decisions: 5 applied, 0 rejected
