# Roadmap: knowledge-base starter

Status: Active
Updated: 2026-10-18

This roadmap is direction only. It does not authorize work, change
`docs/plans/next.md`, or commit the project to any item below.

## Purpose

Make this repository a public, generic starter that **generates** independent
knowledge-base projects: someone runs its installer, gets a fresh repository with
the tools and an empty skeleton, adds domains of their own, saves sources, and
distils them into verified, decision-oriented playbook entries. It generalizes the
approach proven in the sibling `game_theory` project (curated playbook, claim tags,
stable IDs, scanned source conversion, research in bounded waves) without carrying
any of its subject matter.

## Current state

- Owner decisions (2026-10-17): the starter carries no `game_theory` content; it is
  public under the MIT license; a standalone installer, modelled on the project
  template's, creates a new independently tracked project (fresh `git init`, explicit
  identity, a manifest for later upgrades) and does not depend on
  `claude_project_template`; one project holds many domains under `domains/`; saved
  sources and converted text are shared across domains at the project root and
  untracked by default, with a tracked `catalog/` record per source holding its URL
  and checksum.
- Process documents (plans, roadmaps, ADRs) are not shipped. Candidate 2 delivered the
  installer with `--add-to` layering and a kit in the template's module format.
  Owner decision (2026-10-18): that was the wrong shape. Stores are standalone and need
  no way to be injected into an existing project; the template now registers or names a
  store and inserts its slot fragments (its `external-modules` specification, implemented
  in its plans 0006 to 0008 and recorded in its ADR 0003). Candidate 2a (done 2026-10-18) removed
  `--add-to` and ships the descriptor the template expects
  ([ADR 0003](../decisions/0003-standalone-stores-coordinated-by-the-template.md)).
- This repository is the generator, not a knowledge base. It will hold `install.py`,
  `kit/` (the files a project receives), tests, and its own docs. Today it is the
  project template output (documentation skeleton only); nothing else is built.
- The directory was renamed from a misspelling to `claude_knowledge_base`
  (2026-10-17), matching the existing `origin` remote.
- A paper walkthrough of the `game_theory` structure against the specs (2026-10-17)
  found and fixed: sites and repositories needed catalog records, source facts were
  at risk of duplication across domains, entries append dated sections, 185 of 351
  tags carry an annotation, one entry lacked `updated`, and entries had no
  `superseded` status. Its 215 saved papers have unique stems, so a later adoption
  would only need to drop the topic prefix from citations.
- An independent read-only review of the four specs (2026-10-17) returned 27 findings:
  contradictions between specs and candidate boundaries, installer hardening dropped
  from the template's trust model, parsing ambiguities, and source-pipeline security
  gaps. All were addressed in the specs, with these choices: machine-readable schema
  migrations, quarantine for flagged originals, opt-in image extraction, and a strict
  front-matter subset. Every acceptance criterion now names the candidate that delivers
  it.
- Codex reviewed the roadmap and the four specs (2026-10-17, up to three rounds each) and
  all its findings were applied; the last round on the installer, format, and source-pipeline
  specs was not re-reviewed. A grammar check of the 21 `game_theory` entries found 351
  well-formed tags, 8 notes that wrap across lines (the spec now allows this), and four
  adoption fixes for a later import: one missing `updated`, two unquoted titles containing a
  colon, and one heading (`Evaluation pitfalls`) where `Pitfalls` is required.
- Approved specifications (2026-10-17): [installer](../specs/installer.md),
  [knowledge-base-format](../specs/knowledge-base-format.md),
  [source-pipeline](../specs/source-pipeline.md), and
  [domain-lifecycle](../specs/domain-lifecycle.md).
- The sibling `claude_project_template` has implemented external modules (`--register`,
  `--unregister`, `--list`, `name=path` in `--with` and `--add`). Its roadmap
  (`external-modules`) lists the store-side contract as its candidate 4, owned by this
  repository, and an end-to-end check as its candidate 5.

## Ordered plan candidates

### 1. Ratify the design (done 2026-10-17)

The owner approved the four specifications and ADRs 0001 and 0002 were written and
accepted. The text below is kept as the record of the boundary.

**Outcome:** the four specifications reviewed and accepted, and ADRs recording the
structure decision (generator, independent projects, shared catalog; alternatives:
clone-and-merge, separate tools and content, template-repo only) and the installer's
trust model.
**Dependencies:** owner review of the specs.
**Boundary:** documents only; no code and no kit.
**Promotion trigger:** the owner is satisfied with the specs and asks to proceed.

### 2. Installer, kit skeleton, and checker

**Outcome:** `install.py` create and `--add-to` modes, and a `kit/` in the project
template's module format (`module.json`, `migrations.json`, `files/`, `slots/`, `base/`)
containing `kb.json`, the root and domain routers, `domains/_skeleton/`, `catalog/`, the
README copyright note, the `AGENTS.md` guidance slot, copies of the four specs in
`docs/kb/` with a drift test, the strict front-matter parser, and `tools/check_kb.py`.
It meets every criterion tagged `[C2]` in the installer, format, and lifecycle specs,
with tests that create and extend projects in scratch directories.
**Dependencies:** candidate 1.
**Boundary:** creation, layering, and validation. No upgrade, no source conversion, no
domain tools, no domain content, no process documents.
**Promotion trigger:** candidate 1 is complete. This fixes the `kb.json` contract the
template integration depends on, so it should land before candidate 7.

### 2a. Standalone stores (done 2026-10-18)

Plan [0002](../plans/0002-standalone-stores-and-template-descriptor.md) delivered this. The text
below is kept as the record of the boundary.

**Outcome:** `install.py` only creates stores: `--add-to`, `--skip-unsafe-entries`, marker
and block handling, and exit status 3 are removed; the kit becomes `kit.json`,
`migrations.json`, and a single `files/` tree; every store ships the template's
`template-module/` descriptor (`module.json` and an `agents-guidance` fragment); the
installer prints a registration hint with a suggested `--name` when the directory name
is not a valid template module name; and the installer spec is revised to match. It meets
every criterion tagged `[C2a]`, and a created store is registered with the template and
installed into a scratch project by hand.
**Dependencies:** candidate 2, and the template's external-module work (complete).
**Boundary:** this repository only. No change to `claude_project_template`, no upgrade, no
source pipeline.
**Promotion trigger:** ADR 0003 accepted and the revised installer specification approved
(both 2026-10-18). This is the store-side contract (candidate 4 of the template's
`external-modules` roadmap).

### 3. Source pipeline

**Outcome:** the converter, scan, quarantine and `--release`, opt-in images, resource
limits, and catalog updates in the source-pipeline spec, shipped in `kit/files/tools/`,
meeting every `[C3]` criterion with fixture tests, written for the generic layout. The
`game_theory` converter and its scan tests are a design reference only.
**Dependencies:** candidate 2.
**Boundary:** PDFs only.
**Promotion trigger:** candidate 2 is complete.

### 4. Domain lifecycle tooling

**Outcome:** `new_domain.py`, `new_entry.py`, `add_source.py`, and `kb_status.py` as
specified in the lifecycle spec, and the lifecycle checks added to `check_kb.py`,
meeting every `[C4]` criterion. The written procedure (including the delegate brief) is
the lifecycle spec itself, which candidate 2 already ships in `docs/kb/`.
**Dependencies:** candidates 2 and 3.
**Boundary:** mechanical tools and the procedure. No searching, summarizing, or
judging by tools, and no harness-specific wrapping.
**Promotion trigger:** candidates 2 and 3 are complete.

### 5. Upgrade

**Outcome:** `install.py --upgrade` meeting every `[C5]` criterion: ownership derived
from the kit, skip-and-report for edited files, staged renames with
`kb.json` and the manifest last, the no-git-in-the-store rule, and the `migrations.json` chain
mechanism (empty at schema 1; the declarative operation set is defined when the first
schema change ships), with tests.
**Dependencies:** candidates 2 and 2a (the manifest is written at creation, and
`template-module/` is starter-owned).
**Boundary:** starter-owned paths only; project content is never touched.
**Promotion trigger:** candidate 2 is complete and the owner wants projects
upgradeable. It must land before the first `kb_schema` change after release, and
before candidate 6 if the scanner is to be fixable in the field.

### 6. Public release readiness

**Outcome:** a README with a quick start (run the installer, create a domain, add a
first wave, run the check and status, upgrade), the consume-from-another-project
guidance, and completed starter docs, plus an audit that no personal paths, addresses,
or subject-specific content remain in tracked files. It also adds the MIT `LICENSE` file
and replaces the README's license placeholder; neither exists yet, although the owner has
decided on MIT. (The copyright and licensing note for generated projects ships earlier, in
candidate 2.)
**Dependencies:** candidates 2 to 5.
**Boundary:** documentation and the audit. No publishing; making the repository
public is a separate owner action.
**Promotion trigger:** candidates 2 to 5 are complete.

### 7. Template integration (superseded by 2a)

The template's external-module mechanism is built and its store-side contract is
candidate 2a, so this candidate no longer exists as separate work. The remaining
integration step, an end-to-end check of a created store registered and installed through
the template, is part of 2a's by-hand verification and the template's own candidate 5.
**Dependencies:** candidate 2a.
**Boundary:** none left in this repository beyond 2a. Nothing here depends on the template.
**Promotion trigger:** none; delete this entry when the roadmap is next revised.

### 8. Claude skills

**Outcome:** personal skills, kept in `claude_global_config`, that wrap the lifecycle
procedures: create a project, create a domain, run a content wave, expand a domain
from its status report, and consume the knowledge base from another project.
**Dependencies:** candidates 2 to 4, so the skills describe working tooling and a
written procedure.
**Boundary:** the skills and their mirror in `~/.claude`; the committed content of
this repository stays tool-neutral.
**Promotion trigger:** the owner asks for them after candidate 4.

## Open decisions

None. Resolved 2026-10-17: copyright and licensing is guidance only (a note in the
generated README, no numeric limits and no tool enforcement), because the applicable
rules depend on the user's jurisdiction.

## Deferred

- Web-page and blog capture (an extension of the source-pipeline spec).
- Retrieval (RAG) over the Markdown; any index stays derived and untracked.
- Splitting, merging, and retiring domains.
- Importing the `game_theory` content into a generated project, or any other
  migration of existing material.
- Domain-specific entry formats (for example recipes with quantities); the charter's
  verification bar covers what counts as verified, not a different body structure.
- Merging a project's edits to starter-owned files during an upgrade.
- A per-domain conflicts register (ID, claim, sides, status, resolution); revisit when
  a domain accumulates enough conflicts that annotations are not enough.

## Related decisions

- [ADR 0001](../decisions/0001-generator-with-independent-projects.md): a generator that
  creates independent knowledge-base projects.
- [ADR 0002](../decisions/0002-installer-trust-model.md): installer trust model.
