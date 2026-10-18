# 0002: Installer trust model

Status: Accepted (2026-10-17, approved by the owner)
Date: 2026-10-17

## Context

The installer writes files into directories the owner names, including existing projects
that may hold symlinks, special files, hostile git configuration, or a crafted manifest.
It is modelled on the project template's installer, but this repository must not depend on
that one.

## Decision

- **Trusted:** the starter checkout run from the owner's clone, and the owner's command
  line as intent. **Untrusted data:** every command-line value, everything in a project
  given to `--add-to` or `--upgrade` (files, symlinks, special files, the manifest), and the
  caller's environment and git configuration.
- **Out of scope:** installing a malicious starter or fork deliberately, and what a
  generated project's own tools do later.
- Writes stay inside the target (and, for a new project, its `.git/info/exclude`), through a
  temporary sibling and a rename, with the manifest last. Reads use `lstat`, `O_NOFOLLOW`,
  `O_NONBLOCK`, and a size cap. Symlinks, special files, `.git` path components
  (case-insensitively), and a target inside the starter are refused.
- The owned set for an upgrade is derived from the kit, never from the manifest, and the
  manifest is validated. Edited files are skipped and reported. Migrations use a closed set
  of operations limited to starter-owned paths.
- Git runs only in the starter checkout and in a newly created directory, with `GIT_*`
  dropped, fsmonitor and hooks neutralized, and no template hooks. It never runs in a
  project given to `--add-to` or `--upgrade`.

Details and the per-rule acceptance criteria are in `docs/specs/installer.md`.

### Accepted residuals

- A concurrent local attacker can swap a parent directory for a symlink between the
  pre-write check and the rename; closing it needs directory-descriptor-relative operations.
- A failure after renaming has begun can leave some files replaced; the manifest is
  replaced last, so a rerun completes the work.
- `.git/info/exclude` is appended with a normal open, and `git init` follows its own
  conventions.
- Name aliases on NTFS or HFS+ volumes beyond case folding are not exercised.
- Kit sources are trusted once they are regular files in the starter checkout.

## Alternatives considered

- **Depend on the template's installer.** Rejected: ties this repository to another one's
  release and ADRs.
- **Run git in the target to guard against a dirty tree.** Rejected: an untrusted project's
  `.git` can configure programs that git would run.
- **Take the owned set from the manifest.** Rejected: a crafted manifest could make an
  upgrade replace project content.
- **Directory-descriptor-relative writes.** Deferred: it closes the race above at the cost
  of platform-specific code.

## Consequences

- The installer needs its own hardening tests, listed as criteria in the installer spec.
- Users get no dirty-tree warning from the installer and are told to review with `git diff`.

## Verification

Acceptance criteria 3, 6 to 8, 13, 15, and 16 in `docs/specs/installer.md`. None is
implemented yet.

## Related files and decisions

- `docs/specs/installer.md`
- ADR 0001
