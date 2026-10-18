# Installer

Status: Approved (2026-10-18), revising the text approved 2026-10-17
Updated: 2026-10-18

Requirements for the installer that creates a new, independently tracked knowledge-base
store from this starter and upgrades such a store later. A store ships a small descriptor so
the project template can register it and insert guidance into other projects; this
repository does not do that insertion. The layer it installs follows
[knowledge-base-format.md](knowledge-base-format.md). Acceptance criteria are tagged with the
roadmap candidate that delivers them: `[C2]` create and check (delivered, kept where
unchanged), `[C2a]` standalone stores (this revision), `[C5]` upgrade.

This revision replaces the earlier `--add-to` layering and the kit's slot and marker
machinery; ADR 0003 (listed under Related) records the decision.

## Scope

- Creating a store in an empty directory: files, a fresh git repository, an explicit local
  identity.
- Shipping the template descriptor, `template-module/`, in every store.
- Printing how to register the store with the template.
- Recording what was installed so the store can be upgraded.
- Upgrading the starter-owned files of an existing store.

## Non-goals

- Layering the knowledge-base layer onto an existing project. The template's `--with` and
  `--add` do that with the descriptor; this installer has no `--add-to`.
- Registering a store with the template, locating the template, or running any of its code.
  The installer prints a hint and runs nothing.
- Cloning this repository as the way to start. The starter is a generator; a clone of it is
  not a knowledge base.
- Depending on `claude_project_template` or any other repository. The installer is standalone
  and uses only Python 3.9+ and git.
- Shipping plans, roadmaps, ADRs, or other process documents. A store that wants them gets
  them from elsewhere (for example the project template) or adds its own.
- Creating domains, entries, or sources. The store's own tools do that
  ([domain-lifecycle.md](domain-lifecycle.md)).
- Merging a store's own edits to starter-owned files. They are skipped and reported, never
  overwritten.
- Defending against a concurrent local attacker, or against a malicious starter checkout.

## The kit

The kit is the tree the installer copies into a new store:

```text
kit/
  kit.json           kit metadata, validated as below
  migrations.json    ordered schema migration steps; at schema 1: {"steps": []}
  files/             copied to the same relative path in the store
```

There is no `module.json`, `slots/`, or `base/` in the kit. The name `module.json` belongs to
the template descriptor inside the store (below), so the kit's own metadata is `kit.json`.

`files/` holds everything a new store receives, including the root `README.md`, `AGENTS.md`,
`docs/README.md`, and `.gitignore`, which are ordinary files with no markers or managed
blocks.

### Ownership

- **Starter-owned** (replaced by an upgrade, listed in the manifest): `kb.json`, `tools/`,
  `docs/kb/`, `domains/_skeleton/`, and `template-module/`.
- **Project-owned** from the moment of creation: every other path, including the four root
  files above, `catalog/`, `playbook/`, `sources/`, `text/`, and `domains/<name>/`. An upgrade
  never reads them for modification or writes them.
- **Verbatim** (no placeholder substitution): `docs/kb/`, `tools/`, and `template-module/`.
  The specifications mention the placeholder as text, and the descriptor's placeholders
  belong to the template.

### `kit.json`

A JSON object of at most 64 KiB; the installer refuses a kit that fails any rule, before
writing anything:

| Key | Type | Rule |
|---|---|---|
| `kit_version` | string | Printable single-line text; recorded in the manifest |
| `hint` | string | Printable single-line text, printed after a successful run |

Unknown keys are ignored. A missing key or a wrong type refuses the run.

### `migrations.json`

A JSON object of at most 1 MiB, `{"steps": [...]}`. Each step is
`{"from": N, "to": N+1, "ops": [...]}`, and the steps must form one contiguous chain starting
at schema 1. Each op is one of a closed set, and every path is relative, has no `..` or
`.git` component, and lies under a starter-owned prefix:

| Op | Fields | Effect |
|---|---|---|
| `add` | `path`, `source` | Write `kit/files/<source>` to `path` if `path` is absent; if present and equal, the op is complete; if present and different, it is a conflict |
| `replace` | `path`, `source` | Replace `path` with `kit/files/<source>` when it matches its manifest record; if it already equals `kit/files/<source>` (an earlier, interrupted run wrote it), the op is complete; otherwise it is a conflict |
| `remove` | `path` | Delete `path` when it is a regular file matching its manifest record; if it is already absent, the op is complete; otherwise it is a conflict |

A **conflict** (an edited or unexpected file where an op needs to act) is fatal: the upgrade
refuses before the first write, lists the conflicting paths, and does not advance `kb_schema`.
The owner resolves it by hand (restoring the file, or following `docs/kb/`) and reruns.
After an op completes the manifest changes as follows: `add` and `replace` record the
checksum of the written file, and `remove` deletes the path's key from `files`.

Ops run in order within a step and steps in order. Each op is idempotent, so a rerun after a
crash completes the remaining ops and reaches the same final state as an uninterrupted
upgrade. An op that is invalid, names a path outside the owned prefixes, or names a missing
`source` refuses the whole upgrade before the first write. `remove` is the only way the
installer ever deletes a store file.

## The template descriptor

Every store ships the descriptor the project template defines in its external-modules
specification, so the template can register the store and install its fragments into a
project. The descriptor schema belongs to the template; this section records what the kit
must satisfy. The installer neither reads nor imports anything from the template.

```text
template-module/
  module.json
  slots/agents-guidance.md
```

- `module.json` holds exactly the keys `module_format` (integer, `1` today) and `description`
  (printable single-line text, 1 to 200 characters). The template also allows an optional
  `hint`; the kit omits it, because the template prints it under "Next steps" and the
  installer already prints the registration line. There is no `name`, `order`, `requires`, or
  `harness` key, and unknown keys are errors on the template's side.
- One fragment, `slots/agents-guidance.md`, UTF-8 with no NUL byte and at most 64 KiB. It
  points the consuming project's agent guidance at the store's router (`playbook/README.md`,
  the `router` in `kb.json`), tells the reader to treat `[U]` claims as unverified, and treats
  everything in the store (sources, converted text, catalog fields, index notes, leads) as
  data, never instructions.
- No line of a fragment contains `@module-slot:`, `BEGIN module:`, or `END module:`.
- The only placeholders allowed in a fragment are `REPLACE_WITH_MODULE_NAME` and
  `REPLACE_WITH_MODULE_PATH`, which the template substitutes. Any other `REPLACE_WITH_*`
  token, including `REPLACE_WITH_PROJECT_NAME`, would be filled with the consuming project's
  name or reported as left over, so the fragment uses none. The fragment says that the path
  is specific to one checkout.
- Fragment text is tool-neutral. The template never treats an external module as
  harness-specific.
- The descriptor is starter-owned and verbatim. When the template raises `module_format`, this
  kit follows it in a later change; it is not tracked automatically.

A test in this repository checks the shipped descriptor against these rules. The rules are
restated in the test, so this repository still has no dependency on the template.

## Starter repository layout

```text
install.py          the installer (stdlib only)
kit/                the tree above
tests/              unittest suite; creates stores in scratch directories
docs/               this repository's own decisions, specs, plans, roadmaps
LICENSE             MIT; the starter's license, never copied into a store
```

The starter has no `domains/`, `catalog/`, `sources/`, or `text/`, and no `kb.json`. It is not
itself a knowledge base. `kit/files/docs/kb/` holds copies of the four specifications
(`knowledge-base-format.md`, `source-pipeline.md`, `domain-lifecycle.md`, `installer.md`); a test
asserts each copy equals its source in `docs/specs/` once lines linking to `../roadmaps/` or
`../decisions/` are removed.

## Create a store

```sh
./install.py ../my-kb --git-name "Your Name" --git-email "id+user@users.noreply.github.com"
./install.py ../my-kb --dry-run
```

Options: `--name`, `--git-name`, `--git-email`, `--use-global-git-identity`, and `--dry-run`.
There is no `--add-to` and no `--skip-unsafe-entries`; either is an unknown option and
exits with the usage status.

- The project name is the target directory's name unless `--name` is given. A name matches
  `[A-Za-z0-9._ -]{1,64}` and does not start with a space, dot, or hyphen, because it is
  substituted into JSON and front matter.
- The target must not exist or must be an empty directory. It must not be, or be inside, this
  repository, checked by comparing resolved real paths (see Trust model).
- The kit's `files/` are written, with `REPLACE_WITH_PROJECT_NAME` replaced by the project name
  outside the verbatim prefixes. Any other `REPLACE_WITH_*` placeholder in the substituted
  files is listed after the run. Recorded checksums are of the content as written.
- `git init` runs and `HEAD` is pointed at `main` with `symbolic-ref`, so no minimum git
  feature version is needed beyond a working `git`. There is no remote and there are no
  commits. The store is independent: nothing links it to this repository except the manifest.
- Git identity is explicit: `--git-name`/`--git-email` or an interactive prompt. It never
  silently inherits the global identity; `--use-global-git-identity` opts in and is reported.
  An email that does not contain `noreply` produces a warning.
- `/.debug/` is added to the new repository's `.git/info/exclude`.
- `.kb-manifest` is written last.
- `--dry-run` prints what would be written and writes nothing.
- If a failure occurs after the first write, the installer reports the paths it wrote and
  leaves them; it never deletes anything.
- Exit status: 0 success, 1 error, 2 usage.

No `LICENSE` is created. The store's owner chooses one.

### Registration hint

After a successful, non-dry-run creation the installer prints the kit's `hint` and then one
line, with the store's absolute real path:

```text
to register with the project template, run its install.py --register <absolute store path>
```

The template's location is left to the reader, because the generator does not know where it
is. The installer runs nothing, writes no registry, and has no flag for this.

- The template registers a store under its directory name and refuses a name that does not
  match `[a-z0-9][a-z0-9_-]*`. Project names here are wider (capitals, spaces, dots), so when
  the target directory's name does not match that pattern, the line ends with
  ` --name <suggestion>`. The suggestion is the directory name lowercased, with each run of
  characters outside `[a-z0-9_-]` replaced by one hyphen and leading characters outside
  `[a-z0-9]` removed; if nothing is left it is `kb`. It is a suggestion only; the owner may
  choose another valid name.
- The path is shell-quoted when it contains characters a shell would split or expand. It is
  printable single-line text, as every command-line value must be.

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
  "files": { "kb.json": "<sha256>", "tools/check_kb.py": "<sha256>" }
}
```

- `schema` is the manifest's own version. `kb_schema` is the format version the store
  currently conforms to; it always equals `kb.json`'s `schema`, and the check reports a
  difference. Schema 1 has no `blocks` key.
- `files` lists only **starter-owned** files: `kb.json`, `tools/`, `docs/kb/`,
  `domains/_skeleton/`, and `template-module/`.
- Content is never listed: `domains/<name>/`, `catalog/`, `sources/`, `text/`, `playbook/`, and
  the four root files.
- The manifest is tracked in the store's repository.
- `starter_commit` and `starter_dirty` come from running `git` in the starter checkout; they
  are empty and false when the starter is not a git checkout.

## Upgrade a store

```sh
./install.py --upgrade --dir ../my-kb [--dry-run]
```

Run from the starter checkout against a store. The **owned set** is derived from the kit,
never from the manifest: the kit's `files/` paths under the starter-owned prefixes. A manifest
key outside the starter-owned prefixes is ignored and reported, so a crafted manifest cannot
make the upgrade replace store content. For each owned file, and for each recorded one no
longer in the kit:

| On-disk state | Action |
|---|---|
| Recorded; matches the record; the kit differs | Replace with the kit version; record the new checksum |
| Recorded; matches the record and the kit | Nothing |
| Recorded; differs from the record (edited by the owner) | Skip and report; keep the owner's version. If it equals the kit, record it |
| Not recorded; exists; equals the kit | Adopt: record the checksum |
| Not recorded; exists; differs from the kit | Conflict: skip and report |
| Missing; the kit has it | Add it |
| Recorded; no longer in the kit | Report; never delete |

- Content paths and the four root files are never read for modification or written.
- Checksums are compared after the same name substitution used at creation (outside the
  verbatim prefixes), using the manifest's `name`, which is first validated against the name
  rule; an invalid name refuses the upgrade.
- If the store's `kb_schema` is lower than the kit's, `kit/migrations.json` must hold a
  contiguous chain of steps from the store's schema to the kit's; otherwise the upgrade
  refuses before writing anything and points at `docs/kb/` for the manual route. If the
  store's schema is higher than the kit's, it refuses. After the chain has been applied the
  ordinary table above runs against the new kit.
- Staging: all results, including migration output, are computed and validated before the
  first rename. `kb.json` is renamed second to last and the manifest last. A crash during the
  rename phase leaves some files replaced; rerunning completes the work because each step is
  idempotent and the remaining work is detected from `kb.json`'s schema and the checksums.
- Upgrade runs no git command against the store, because an untrusted store's `.git` can
  configure helpers. It never commits. It prints a summary and a reminder to review the
  changes with `git diff` and `git status`, and leaves them in the working tree. A change to
  `template-module/` does not reach projects that already installed the store. The template
  records a digest of the descriptor when it installs a store, so a future template refresh
  feature could detect the change; nothing checks it today.

## Trust model

These are this specification's own requirements, recorded in ADR 0002 and narrowed by ADR 0003.
They are modelled on the project template's installer, but nothing here depends on that
repository.

- Trusted: the starter checkout run from the owner's clone, and the owner's command line as
  intent.
- Untrusted data: every command-line value; everything in a store under `--upgrade` (files,
  symlinks, special files, the manifest); the caller's environment and git configuration, as
  far as `git` is concerned.
- Out of scope: the owner deliberately installing a malicious starter or fork, and what a
  store's own tools do later.
- Writes happen only inside the target or store directory and, for a new store,
  `<target>/.git/info/exclude`. The installer writes nothing in the template, a registry, or any
  other project.

Hardening requirements:

- Files are read only as regular files, opened with `O_NOFOLLOW` and `O_NONBLOCK`, after an
  `lstat`, capped at 16 MiB, so a symlink or FIFO cannot redirect or hang a read.
- Symlinks and special files inside a store under `--upgrade`, a symlinked target directory
  (the final path component), and a symlinked kit tree entry (`files/`, the kit directory,
  `kit.json`, `migrations.json`) are refused. Ancestors above the target are resolved with
  `realpath` for identity checks only and may be symlinks (for example `/tmp` on macOS).
- A target equal to, or inside, the starter is refused by comparing resolved real paths by
  identity, not by string.
- Writes go through a temporary sibling and a rename, manifest last. A path with a symlinked
  or non-directory component is refused before the first write, as is a read-only target.
- Path components are compared case-insensitively against `.git` and the manifest name, and
  any `.git` component is refused (macOS and Windows resolve `.Git` to `.git`). The manifest
  name is reserved and may not appear in the kit.
- `git` runs only in the starter checkout (for the manifest) and in the new directory when
  creating. It runs with `GIT_*` variables dropped except the three config selectors, with
  `core.fsmonitor`, `core.untrackedCache`, and `core.hooksPath` neutralized, and
  `git init --template=` so no sample hook is copied. It never runs in a store given to
  `--upgrade`.
- The manifest is validated: an object, known `schema`, bounded size, relative paths with no
  `..` or `.git` component, checksums of exactly 64 lowercase hex digits, and a `name` that
  satisfies the name rule.
- Names and every command-line value must be printable single-line text.

Accepted residuals (recorded in ADR 0002):

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

1. `[C2]` Creating a store into a scratch directory writes exactly the kit's files and
   `.kb-manifest`; substitutes the project name outside the verbatim prefixes; initializes
   `main` with no remote and no commits; sets the local identity; and adds `/.debug/` to the
   exclude file.
2. `[C2]` The created store passes `tools/check_kb.py` with no domain.
3. `[C2]` Creation refuses, writing nothing: a non-empty or existing non-directory target, a
   target equal to or inside the starter, a symlinked target directory, a read-only target,
   missing identity in a non-interactive run, and a name that breaks the name rule. A target
   under a symlinked ancestor (for example a temporary directory) succeeds.
4. `[C2]` `--dry-run` writes nothing and lists every path it would write.
5. `[C2a]` `--add-to` and `--skip-unsafe-entries` are unknown options and exit 2. The kit has no
   `slots/` or `base/`; the only `module.json` is `template-module/module.json`; no file in
   `kit/` outside `kit/files/docs/kb/`, and no line of `install.py`, contains `@module-slot`;
   and exit status 3 no longer exists.
6. `[C2a]` The created store contains `template-module/module.json` and
   `template-module/slots/agents-guidance.md`, byte-identical to the kit (not substituted). A
   test checks them against the descriptor rules above: exact keys and types (`module_format`
   and `description` only), description length and single-line text, slot name, size, UTF-8
   and no NUL, no line with
   `@module-slot:`, `BEGIN module:`, or `END module:`, and no `REPLACE_WITH_*` token other than
   `REPLACE_WITH_MODULE_NAME` and `REPLACE_WITH_MODULE_PATH`. The fragment names the store's
   router and the `[U]` and data-not-instructions guidance.
7. `[C2a]` After a successful creation the installer prints the kit's hint and exactly one
   registration line with the store's absolute real path, shell-quoted when needed. When the
   target directory's name does not match `[a-z0-9][a-z0-9_-]*` (for example `My KB`,
   `my.kb`, or a name made only of symbols) the line ends with `--name` and the
   suggestion described above; otherwise it has no suffix. The line is absent with `--dry-run`
   and after a failed run. The installer runs no program for it, writes nothing outside the
   target, and accepts no registration flag.
8. `[C2a]` The root `README.md`, `AGENTS.md`, `docs/README.md`, and `.gitignore` are written
   once, contain the knowledge-base guidance, the copyright note, the docs index, and the
   `sources/` and `text/` ignore rules, and contain no marker or `BEGIN`/`END` line. The
   manifest lists no blocks.
9. `[C2]` The kit is validated before any write: a `kit.json` with a missing key or a wrong
   type, and a `migrations.json` with a gap, a non-contiguous chain, an unknown op, or a path
   outside the owned prefixes, each refuses the run. Substitution leaves `docs/kb/`, `tools/`,
   and `template-module/` byte-identical to the kit.
10. `[C2]` Hardening: a symlink or special file in the kit is refused; a `.GIT` path component is
    refused; a hostile environment (`GIT_*` variables, a global git configuration naming hooks
    or helpers) causes no program to run.
11. `[C2]` The starter has no tracked content under `domains/`, `catalog/`, `sources/`, or
    `text/`, and a search of tracked files finds no personal path or address.
12. `[C2]` A created store's `README.md` contains the copyright and licensing note, and each
    `kit/files/docs/kb/` copy equals its source specification as described above.
13. `[C5]` Upgrade follows the table above: edited files skipped and reported, unedited ones
    replaced, new ones added, adopted and conflicting unrecorded files handled as listed, none
    deleted. A checksum of `domains/<name>/`, `catalog/`, `sources/`, `text/`, `playbook/`, and
    the four root files is identical before and after.
14. `[C5]` Upgrade is idempotent: a second run reports nothing to do. Replacing `kb.json` is
    allowed and is the only change to a store-root marker.
15. `[C5]` Upgrade ignores and reports a manifest key outside the starter-owned prefixes (for
    example `playbook/README.md`), and refuses a malformed manifest, a path that escapes the
    store or names `.git`, a bad checksum, an invalid `name`, and a symlinked store
    directory. It adds a missing `template-module/` file.
16. `[C5]` Upgrade refuses before any write when the store's `kb_schema` is lower than the kit's
    and `migrations.json` has no contiguous chain, or is higher than the kit's. A fixture chain
    of two steps using `add`, `replace`, and `remove` is applied whole, with `kb.json` and the
    manifest renamed last, and the manifest ends with the written checksums and without the
    removed key. An edited file named by `add`, `replace`, or `remove` makes the run refuse
    before any write, lists the path, and leaves `kb_schema` unchanged; `remove` deletes
    nothing else.
17. `[C5]` Upgrade runs no git command against the store (a fixture `.git` with a configured
    helper is never run) and prints the review reminder.
18. `[C5]` After an interrupted upgrade (a simulated failure between renames, including
    immediately after a migration `replace` or `remove`), rerunning completes it and leaves the
    store equal to an uninterrupted upgrade.
19. `[C2a]` By hand, recorded in the plan's Result and not a dependency of the test suite: a
    store created by the installer is registered with the template into a scratch registry
    (`--register <store> --registry <scratch file>`), verified by `--list`, and installed into a
    scratch project with `--with`, and the project's `AGENTS.md` then holds a block that points at
    the store's router. A store whose directory name is not a valid module name is registered
    with the suggested `--name`.

## Related

- [ADR 0003](../decisions/0003-standalone-stores-coordinated-by-the-template.md)
- [knowledge-base-format.md](knowledge-base-format.md)
- [domain-lifecycle.md](domain-lifecycle.md)
- [source-pipeline.md](source-pipeline.md)
- Roadmap: [knowledge-base-starter](../roadmaps/knowledge-base-starter.md)
- Template side: `claude_project_template/docs/specs/external-modules.md` and its ADR 0003
