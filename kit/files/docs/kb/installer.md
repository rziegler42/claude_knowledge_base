# Installer

Status: Approved (2026-10-17)
Updated: 2026-10-17

Requirements for the installer that creates a new, independently tracked knowledge-base
project from this starter, adds the knowledge-base layer to an existing project, and upgrades
such a project later. The layer it installs follows
[knowledge-base-format.md](knowledge-base-format.md). Acceptance criteria are tagged with the
roadmap candidate that delivers them: `[C2]` create, layer, and check; `[C5]` upgrade.

## Scope

- Creating a project in an empty directory: files, a fresh git repository, an explicit local
  identity.
- Adding the knowledge-base layer to an existing project.
- Recording what was installed so the project can be upgraded.
- Upgrading the starter-owned files and blocks of an existing project.

## Non-goals

- Cloning this repository as the way to start. The starter is a generator; a clone of it is
  not a knowledge base.
- Depending on `claude_project_template` or any other repository. The installer is standalone
  and uses only Python 3.9+ and git.
- Shipping plans, roadmaps, ADRs, or other process documents. A project that wants them gets
  them from elsewhere (for example the project template) or adds its own.
- Creating domains, entries, or sources. The project's own tools do that
  ([domain-lifecycle.md](domain-lifecycle.md)).
- Merging a project's own edits to starter-owned files or blocks. They are skipped and
  reported, never overwritten.
- Defending against a concurrent local attacker, or against a malicious starter checkout.

## The kit is a module

The knowledge-base layer is a single module in the project template's current module format,
so a template that supports remote modules can load it unchanged and this installer needs no
format of its own:

```text
kit/
  module.json        module metadata, validated as below
  migrations.json    ordered schema migration steps; at schema 1: {"steps": []}
  files/             copied verbatim to the same relative path
  slots/<slot>.md    fragments inserted at @module-slot: <slot> marker lines
  base/              files used only when the target is an empty directory
```

- A fragment is inserted at the marker line `@module-slot: <slot>` inside the host file's own
  comment syntax, wrapped in `BEGIN module:knowledge-base slot:<slot>` and
  `END module:knowledge-base slot:<slot>` lines, and the marker stays so a later run is a
  deterministic patch.
- The slots used are `agents-guidance` (`AGENTS.md`), `readme-docs` (`README.md`), `docs-index`
  (`docs/README.md`), and `gitignore` (`.gitignore`). These names are the project template's,
  so a project that came from the template already has the markers.
- `base/` holds a small `README.md`, `AGENTS.md`, `docs/README.md`, and `.gitignore`
  containing those markers, used only to start an empty directory. A slot whose host file is
  neither present in the target nor in `base/` is not installed.
- The installer implements only what this one module needs: files, slots, markers, and the
  hint. It does not resolve `requires` or other modules.
- If the template's module format changes, this kit follows it deliberately in a later change;
  it is not tracked automatically.

### `module.json`

A JSON object of at most 64 KiB with these keys; the installer refuses a kit that fails any
rule, before writing anything:

| Key | Type | Rule |
|---|---|---|
| `name` | string | Always `knowledge-base` |
| `kit_version` | string | Printable single-line text; recorded in the manifest |
| `description` | string | Printable single-line text |
| `order` | integer | Present for the template's format; ignored here |
| `requires` | list of strings | Must be empty; this installer does not resolve other modules |
| `hint` | string | Printable single-line text, printed after a successful run |

Unknown keys are ignored. A missing key, a wrong type, or a non-empty `requires` refuses the
run.

### `migrations.json`

A JSON object of at most 1 MiB, `{"steps": [...]}`. Each step is
`{"from": N, "to": N+1, "ops": [...]}`, and the steps must form one contiguous chain starting
at schema 1. Each op is one of a closed set, and every path is relative, has no `..` or
`.git` component, and lies under a starter-owned prefix (the check for owned prefixes uses
the same rule as the owned set below):

| Op | Fields | Effect |
|---|---|---|
| `add` | `path`, `source` | Write `kit/files/<source>` to `path` if `path` is absent; if present and equal, the op is complete; if present and different, it is a conflict |
| `replace` | `path`, `source` | Replace `path` with `kit/files/<source>` when it matches its manifest record; if it already equals `kit/files/<source>` (an earlier, interrupted run wrote it), the op is complete; otherwise it is a conflict |
| `remove` | `path` | Delete `path` when it is a regular file matching its manifest record; if it is already absent, the op is complete; otherwise it is a conflict |

A **conflict** (an edited or unexpected file where an op needs to act) is fatal: the upgrade
refuses before the first write, lists the conflicting paths, and does not advance `kb_schema`.
The owner resolves it by hand (restoring the file, or following `docs/kb/`) and reruns. A
conflict on an `add` (the path exists and differs) is the same. After an op completes the
manifest changes as follows: `add` and `replace` record the checksum of the written file,
and `remove` deletes the path's key from `files`.

Ops run in order within a step and steps in order. Each op is idempotent, so a rerun after a
crash completes the remaining ops and reaches the same final state as an uninterrupted
upgrade, and an op that is
invalid, names a path outside the owned prefixes, or names a missing `source` refuses the
whole upgrade before the first write. `remove` is the only way the installer ever deletes a
project file.

### Block parsing

A host file is read as UTF-8 and refused if it is not valid UTF-8 or contains a NUL byte. For
each slot the file must contain exactly one of: the marker line alone, or one well-formed
`BEGIN`/`END` pair for this module and slot (with the marker line after the `END` line). The
installer refuses, writing nothing, when:

- the marker occurs inside a fenced code block;
- a marker or a `BEGIN` or `END` line occurs more than once for the slot;
- a `BEGIN` has no matching `END`, or pairs are nested or interleaved.

A block whose marker has since been deleted is still recognized by its `BEGIN`/`END` lines;
an upgrade replaces it in place and restores the marker line after the `END` line.

**Serialized form.** The `BEGIN`, `END`, and marker lines are written in the host file's
comment syntax: `<!-- text -->` in Markdown files and `# text` in `.gitignore`. A block
appended to a host file that has no marker is written as the `BEGIN` line, the fragment, the
`END` line, then the marker line, each on its own line, preceded by one blank line.

## Starter repository layout

```text
install.py          the installer (stdlib only)
kit/                the module above
tests/              unittest suite; creates and extends projects in scratch directories
docs/               this repository's own decisions, specs, plans, roadmaps
LICENSE             MIT; the starter's license, never copied into a project
```

The starter has no `domains/`, `catalog/`, `sources/`, or `text/`, and no `kb.json`. It is not
itself a knowledge base. `kit/files/docs/kb/` holds copies of the four specifications
(`knowledge-base-format.md`, `source-pipeline.md`, `domain-lifecycle.md`, `installer.md`); a test
asserts each copy equals its source in `docs/specs/` once lines linking to `../roadmaps/` are
removed.

## Create a project

```sh
./install.py ../my-kb --git-name "Your Name" --git-email "id+user@users.noreply.github.com"
./install.py ../my-kb --dry-run
```

- The project name is the target directory's name unless `--name` is given. A name matches
  `[A-Za-z0-9._ -]{1,64}` and does not start with a space, dot, or hyphen, because it is
  substituted into JSON and front matter.
- The target must not exist or must be an empty directory. It must not be, or be inside, this
  repository, checked by comparing resolved real paths (see Trust model).
- The base files are written, then the module is applied as in the next section.
- `git init` runs and `HEAD` is pointed at `main` with `symbolic-ref`, so no minimum git
  feature version is needed beyond a working `git`. There is no remote and there are no
  commits. The project is independent: nothing links it to this repository except the
  manifest.
- Git identity is explicit: `--git-name`/`--git-email` or an interactive prompt. It never
  silently inherits the global identity; `--use-global-git-identity` opts in and is reported.
  An email that does not contain `noreply` produces a warning.
- `/.debug/` is added to the new repository's `.git/info/exclude`.
- `REPLACE_WITH_PROJECT_NAME` is replaced by the project name in `base/` files, slot
  fragments, and `kb.json`; it is never replaced under `docs/kb/` or `tools/`, whose copies
  are verbatim (the specifications mention the placeholder as text). Any other
  `REPLACE_WITH_*` placeholder in the substituted files is listed after the run. Recorded
  checksums are of the content as written.
- `--dry-run` prints what would be written and writes nothing.
- If a failure occurs after the first write, the installer reports the paths it wrote and
  leaves them; it never deletes anything.

No `LICENSE` is created. The project's owner chooses one.

## Add to an existing project

```sh
./install.py --add-to ../existing-project [--dry-run]
```

- The target must be an existing directory that is not, and is not inside, this repository.
  The installer runs no git command against the target and does not set an identity or
  commit. (It reads git state of the starter only, for the manifest.)
- Each `files/` entry is written if absent, left alone if identical, and a conflict if
  different; any conflict aborts the run before the first write.
- Preflight: the run aborts, writing nothing, if the target already has a non-empty `catalog/`,
  `domains/`, `playbook/`, `sources/`, or `text/` directory, because the layer's ignore rules
  and layout would silently change its meaning. A directory holding only files identical to
  the kit's (left by an earlier run that failed before the manifest) is not non-empty.
- Each fragment is inserted at its marker if the host file has one. If the host file exists
  without the marker, the fragment is appended in a managed block with the same `BEGIN`/`END`
  lines. If the host file is absent, the `base/` version is written.
- A project can receive the layer after the template (or any other tool) has created the rest
  of the project.
- The run writes `.kb-manifest` last. A second run is therefore refused: it exits with the
  distinct status "already installed", writes nothing, and points at `--upgrade`. A run that
  failed before the manifest was written can be repeated, because identical files are left
  alone.

## Manifest

`.kb-manifest` is a JSON object, at most 1 MiB, written last:

```json
{
  "schema": 1,
  "kb_schema": 1,
  "name": "my-kb",
  "kit_version": "1",
  "starter_commit": "",
  "starter_dirty": false,
  "files": { "kb.json": "<sha256>", "tools/check_kb.py": "<sha256>" },
  "blocks": { "AGENTS.md#agents-guidance": "<sha256 of the inserted block>" }
}
```

- `schema` is the manifest's own version. `kb_schema` is the format version the project
  currently conforms to; it always equals `kb.json`'s `schema`, and the check reports a
  difference.
- `files` lists only **starter-owned** files: `kb.json`, `tools/`, `docs/kb/`, and
  `domains/_skeleton/`. `blocks` lists each inserted block by `path#slot`.
- Content is never listed: `domains/<name>/`, `catalog/`, `sources/`, `text/`, `playbook/`, and
  any text outside the managed blocks in `AGENTS.md`, `README.md`, `docs/README.md`, and
  `.gitignore`.
- The manifest is tracked in the project's repository.
- `starter_commit` and `starter_dirty` come from running `git` in the starter checkout; they
  are empty and false when the starter is not a git checkout.

## Upgrade a project

```sh
./install.py --upgrade --dir ../my-kb [--dry-run]
```

Run from the starter checkout against a project. The **owned set** is derived from the kit,
never from the manifest: the kit's `files/` paths under the starter-owned prefixes, plus the
kit's slot blocks. A manifest key outside the starter-owned prefixes (or not a valid block
key) is ignored and reported, so a crafted manifest cannot make the upgrade replace project
content. For each owned file and block, and for each recorded one no longer in the kit:

| On-disk state | Action |
|---|---|
| Recorded; matches the record; the kit differs | Replace with the kit version; record the new checksum |
| Recorded; matches the record and the kit | Nothing |
| Recorded; differs from the record (edited by the owner) | Skip and report; keep the owner's version. If it equals the kit, record it |
| Not recorded; exists; equals the kit | Adopt: record the checksum |
| Not recorded; exists; differs from the kit | Conflict: skip and report |
| Missing; the kit has it | Add it (a block is re-inserted at its marker, or appended if the marker is gone) |
| Recorded; no longer in the kit | Report; never delete |

- Content paths and text outside managed blocks are never read for modification or written.
- Checksums are compared after the same name substitution used at install, using the
  manifest's `name`, which is first validated against the name rule; an invalid name refuses
  the upgrade.
- If the project's `kb_schema` is lower than the kit's, `kit/migrations.json` must hold a
  contiguous chain of steps from the project's schema to the kit's; otherwise the upgrade
  refuses before writing anything and points at `docs/kb/` for the manual route. If the
  project's schema is higher than the kit's, it refuses. Steps and their ops are defined
  under `migrations.json` above; at schema 1 there are none. After the chain has been applied
  the ordinary table above runs against the new kit.
- Staging: all results, including migration output, are computed and validated before the
  first rename. `kb.json` is renamed second to last and the manifest last. A crash during the
  rename phase leaves some files replaced; rerunning completes the work because each step is
  idempotent and the remaining work is detected from `kb.json`'s schema and the checksums.
- Upgrade runs no git command against the project, because an untrusted project's `.git` can
  configure helpers. It never commits. It prints a summary and a reminder to review the
  changes with `git diff` and `git status`, and leaves them in the working tree.

## Trust model

These are this specification's own requirements. They are modelled on the project
template's installer, but nothing here depends on that repository. Candidate 1 records them
in ADR 0002 in this repository; this section holds the detailed requirements.

- Trusted: the starter checkout run from the owner's clone, and the owner's command line as
  intent.
- Untrusted data: every command-line value; everything in a project under `--add-to` or
  `--upgrade` (files, symlinks, special files, the manifest); the caller's environment and git
  configuration, as far as `git` is concerned.
- Out of scope: the owner deliberately installing a malicious starter or fork, and what a
  generated project's own tools do later.
- Writes happen only inside the target or project directory and, for a new project,
  `<target>/.git/info/exclude`.

Hardening requirements:

- Files are read only as regular files, opened with `O_NOFOLLOW` and `O_NONBLOCK`, after an
  `lstat`, capped at 16 MiB, so a symlink or FIFO cannot redirect or hang a read.
- Symlinks and special files inside a project, a symlinked target directory (the final path
  component), and a symlinked kit tree entry (`files/`, `slots/`, `base/`, the module
  directory, `module.json`, `migrations.json`) are refused. Ancestors above the target are
  resolved with `realpath` for identity checks only and may be symlinks (for example `/tmp` on
  macOS).
- A target equal to, or inside, the starter is refused by comparing resolved real paths by
  identity, not by string.
- Writes go through a temporary sibling and a rename, manifest last. A path with a symlinked
  or non-directory component is refused before the first write, as is a read-only target.
- Path components are compared case-insensitively against `.git` and the manifest name, and
  any `.git` component is refused (macOS and Windows resolve `.Git` to `.git`). The manifest
  name is reserved and may not appear in the kit.
- `--skip-unsafe-entries` (for `--add-to` and `--upgrade` only; rejected when creating)
  skips and lists symlinks, special files, and files over the size cap in the project walk. A
  skipped entry is never read, patched, or written through. A marker that exists only in a
  skipped file fails the run.
- `git` runs only in the starter checkout (for the manifest) and in the new directory when
  creating. It runs with `GIT_*` variables dropped except the three config selectors, with
  `core.fsmonitor`, `core.untrackedCache`, and `core.hooksPath` neutralized, and
  `git init --template=` so no sample hook is copied. It never runs in a project given to
  `--add-to` or `--upgrade`.
- The manifest is validated: an object, known `schema`, bounded size, relative paths with no
  `..` or `.git` component, checksums of exactly 64 lowercase hex digits, and a `name` that
  satisfies the name rule.
- Names and every command-line value must be printable single-line text.

Accepted residuals (also recorded in ADR 0002):

- A concurrent local attacker can swap a parent directory for a symlink between the
  pre-write check and the rename; closing it needs directory-descriptor-relative operations.
- A failure after renaming has begun can leave some files replaced and others not; the
  manifest is replaced last, so a rerun completes the work.
- `.git/info/exclude` is appended with a normal open, and `git init` follows its own
  conventions.
- Name aliases on NTFS or HFS+ volumes (short names, Unicode normalization) are not
  exercised beyond case folding.
- Kit sources are trusted once they are regular files in the starter checkout.

## Acceptance criteria

1. `[C2]` Creating a project into a scratch directory writes exactly the base files, the kit's
   files with slots applied, and `.kb-manifest`; substitutes the project name; initializes
   `main` with no remote and no commits; sets the local identity; and adds `/.debug/` to the
   exclude file.
2. `[C2]` The created project passes `tools/check_kb.py` with no domain.
3. `[C2]` Creation refuses, writing nothing: a non-empty or existing non-directory target, a
   target equal to or inside the starter, a symlinked target directory, a read-only target,
   missing identity in a non-interactive run, and a name that breaks the name rule. A target
   under a symlinked ancestor (for example a temporary directory) succeeds.
4. `[C2]` `--dry-run` writes nothing and lists every path it would write, for all modes.
5. `[C2]` `--add-to` on a fixture project with the template's markers inserts each fragment at
   its marker; on a fixture without markers it appends managed blocks; where a host file is
   absent it writes the `base/` version. Existing differing files abort the run with nothing
   written, text outside the blocks is unchanged, and a non-empty `catalog/`, `domains/`,
   `playbook/`, `sources/`, or `text/` aborts it.
6. `[C2]` Block parsing refuses, writing nothing: a marker inside a fenced block, duplicate
   markers or blocks, a `BEGIN` without `END`, nested or interleaved pairs, a non-UTF-8 host
   file, and a host file containing a NUL byte.
7. `[C2]` `--add-to` runs no git command against the target (a fixture `.git` with a configured
   helper is never run). A second run exits with the "already installed" status and writes
   nothing; a run repeated after a simulated failure before the manifest completes. A target
   inside the starter is refused. The kit is validated before any write: a `module.json` with
   a missing key, a wrong type, or a non-empty `requires`, and a `migrations.json` with a gap,
   a non-contiguous chain, an unknown op, or a path outside the owned prefixes, each refuses
   the run. Substitution leaves `docs/kb/` and `tools/` byte-identical to the kit.
8. `[C2]` Hardening: a FIFO or symlink in a fixture project does not hang or redirect a read; a
   `.GIT` path component is refused; a symlink in the kit is refused; `--skip-unsafe-entries`
   is rejected when creating and fails when a needed marker lives in a skipped file; a hostile
   project (a `.git` with configured helpers, `GIT_*` in the environment) causes no program to
   run.
9. `[C2]` The starter has no tracked content under `domains/`, `catalog/`, `sources/`, or
   `text/`, and a search of tracked files finds no personal path or address.
10. `[C2]` A created project's `README.md` contains the copyright and licensing note, and each
    `kit/files/docs/kb/` copy equals its source specification as described above.
11. `[C5]` Upgrade follows the table above: edited files and blocks skipped and reported, unedited
    ones replaced, new ones added, adopted and conflicting unrecorded files handled as listed,
    none deleted. A checksum of `domains/<name>/`, `catalog/`, `sources/`, `text/`, `playbook/`,
    and the text outside managed blocks is identical before and after.
12. `[C5]` Upgrade is idempotent: a second run reports nothing to do. Replacing `kb.json` is
    allowed and is the only change to a project-root marker.
13. `[C5]` Upgrade ignores and reports a manifest key outside the starter-owned prefixes (for
    example `playbook/README.md`), and refuses a malformed manifest, a path that escapes the
    project or names `.git`, a bad checksum, an invalid `name`, and a symlinked project
    directory.
14. `[C5]` Upgrade refuses before any write when the project's `kb_schema` is lower than the kit's
    and `migrations.json` has no contiguous chain, or is higher than the kit's. A fixture chain
    of two steps using `add`, `replace`, and `remove` is applied whole, with `kb.json` and the
    manifest renamed last, and the manifest ends with the written checksums and without the
    removed key. An edited file named by `add`, `replace`, or `remove` makes the run refuse
    before any write, lists the path, and leaves `kb_schema` unchanged; `remove` deletes
    nothing else.
15. `[C5]` Upgrade runs no git command against the project (a fixture `.git` with a configured
    helper is never run) and prints the review reminder.
16. `[C5]` After an interrupted upgrade (a simulated failure between renames, including
    immediately after a migration `replace` or `remove`), rerunning completes it and leaves the
    project equal to an uninterrupted upgrade.

## Related

- [knowledge-base-format.md](knowledge-base-format.md)
- [domain-lifecycle.md](domain-lifecycle.md)
- [source-pipeline.md](source-pipeline.md)
