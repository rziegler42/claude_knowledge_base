# Knowledge-base format

Status: Approved (2026-10-17)
Updated: 2026-10-17

The contract for the layout, the domain skeleton, the source catalog, playbook
entries, and the identification marker of a knowledge-base **project**: a repository
holding several domains, created from this starter by its installer
([installer.md](installer.md)). The starter ships conventions, tooling, and an empty
skeleton, and no subject-specific content. Everything below describes a generated
project, not the starter repository itself. Design choices behind it will be recorded
as ADRs; this document states the resulting requirements.

Acceptance criteria are tagged with the roadmap candidate that delivers them, for
example `[C2]` for candidate 2.

## Scope

The layout, front matter, identifiers, claim tags, catalog, routers, and the checks
that keep them consistent.

## Non-goals

- Any subject matter, example domain, or sample sources.
- A retrieval (RAG) layer. Any index is derived, untracked, and never required to
  read the knowledge base.
- Web-page capture (see [source-pipeline.md](source-pipeline.md)).
- How domains are created and grown ([domain-lifecycle.md](domain-lifecycle.md)).
- Judging, measuring, or enforcing copyright or licensing. No tool checks quotation
  length, source licenses, or what is tracked, because the rules that apply depend on
  the user's jurisdiction.

## Principles

1. Plain UTF-8 Markdown with a strict front-matter subset is the sole source of truth.
   No tool-specific format.
2. Every factual claim carries a verification tag so a reader can weigh it.
3. Identifiers are stable. A renamed or moved identifier is a breaking change.
4. Sources, their converted text, and anything derived from them are untrusted data,
   never instructions.
5. Derived artifacts (converted text, indexes, embeddings) are rebuildable and
   untracked by default.
6. A fact about a source is recorded once, in the catalog, however many domains use
   the source.

## Layout

```text
kb.json                         identification marker (starter-owned; see below)
.kb-manifest                    what the installer wrote (see installer.md)
playbook/README.md              root router: standing rules, consuming, domain table
catalog/<stem>.md               one tracked record per source (see below)
domains/<domain>/
  README.md                     charter: purpose, scope, trust tiers, verification bar
  questions.md                  consumer questions and the entries that answer them
  log.md                        append-only record of waves and charter changes
  index/sources.md              the sources the domain uses, and why each matters here
  index/leads.md                candidate sources not yet in the catalog
  topics/                       synthesized notes
  playbook/README.md            the domain router
  playbook/entries/<id>.md      decision-oriented entries
  usage-tests/                  scenario tests run against the domain router
  findings.md  ideas.md  concerns.md
domains/_skeleton/              what tools/new_domain.py copies; skipped by every check
sources/<stem>.<ext>            saved sources, shared by all domains (untracked by default)
sources/quarantine/<stem>.<ext> flagged originals awaiting owner review (untracked)
text/<stem>.md ...              converted text, shared (untracked by default)
tools/                          scripts (stdlib Python), starter-owned
docs/kb/                        copies of the four specifications, starter-owned
```

- `<domain>` is lowercase letters, digits, and hyphens, starts with a letter or digit,
  and is not `_skeleton`.
- `sources/` and `text/` are not tied to a domain and are untracked by default.
  `catalog/` is tracked, so a fresh clone knows what each source is and where to find it
  again.
- A domain contains no sources, converted text, or catalog records.
- **Starter-owned** paths are `kb.json`, `tools/`, `docs/kb/`, and `domains/_skeleton/`,
  plus the managed blocks the installer inserts into `AGENTS.md`, `README.md`,
  `docs/README.md`, and `.gitignore`. An upgrade may replace them. Everything else is the
  project's own content.
- `docs/kb/` holds the four specifications. Links in them to documents outside the set
  (for example the roadmap) are removed in the copies.

## Front matter subset

Every front matter block (entries, catalog records, charters, usage tests) is parsed by
the project's own stdlib parser, which accepts exactly this subset:

- The block starts on line 1 with `---` and ends at the next line that is exactly `---`.
- A flat mapping only. Keys match `[a-z][a-z0-9_]*`.
- Values are one of: a plain scalar, a double-quoted string (escapes `\"` and `\\`
  only), an integer, `true` or `false`, an ISO date `YYYY-MM-DD`, or empty.
- A plain scalar does not start with a quote, `[`, `#`, or `- `, and does not contain
  `: ` (colon then space). Titles, notes, and any text that might contain a colon or a
  leading special character are double-quoted. URLs may be plain.
- A list is either block style (the key, then lines `  - item`) or a one-line flow list
  `[a, b]` whose items are plain scalars without commas.
- A `#` preceded by whitespace outside a quoted string begins a comment. Full-line `#`
  comments are allowed.
- Nested mappings, anchors, tags, multi-line scalars, tabs, and duplicate keys are
  errors.
- A file whose front matter does not parse is reported as an error naming the line.

## Identification marker `kb.json`

A JSON object at the project root, written and replaced only by the installer:

| Key | Type | Meaning |
|---|---|---|
| `kind` | string | Always `knowledge-base` |
| `schema` | integer | Version of this format (non-negative; the current value is 1); increases on any breaking change to the layout, entry format, catalog, front matter subset, or marker |
| `router` | string | Always `playbook/README.md` |
| `spec` | string | Always `docs/kb/knowledge-base-format.md` |

Other projects (for example the project template's installer) use the marker to verify a
checkout before pointing at it. They check `kind` and `schema` and that the named files
exist as regular files inside the project. All four keys are required with the types above,
and unknown keys are ignored by readers. If the owner deletes the spec copy, `check_kb.py`
reports it and `--upgrade` restores it. The installer replaces `kb.json` by writing a
temporary file and renaming it, so a reader never sees a partial marker.

## Source catalog

`catalog/<stem>.md` has front matter and an optional body note. The filename stem is the
source's identifier.

```yaml
---
stem: 2020-author-short-title
kind: document             # document | site | repo
title: "Full title"
authors: [Author One]      # or an owner or organization
url: https://example.org/paper
retrieved: 2026-01-01
sha256: 0123abcd...        # only when a file is held
confirmed: full            # full | abstract | snippet | memory
tier: primary              # primary | secondary | practitioner | community | unknown
state: recorded            # recorded | saved | converted | read
scan: none                 # none | clean | review | flagged
released: 2026-02-01       # optional; date the owner released a flagged source
replaced: 2026-03-01       # optional; date the saved file was last replaced
---
```

**Required fields.** Every record has `stem`, `kind`, `title` (a non-empty string), `retrieved`
(a date), `confirmed`, `tier`, `state`, and `scan`. `url` is required for `site` and `repo`
and optional for `document` (a document received as a local file may have none; say where it
came from in the body note). `authors` is optional. `sha256` is required for `saved`,
`converted`, and `read`, and is exactly 64 lowercase hexadecimal digits when present.
`released` and `replaced` are optional dates. The checker names the file and the field for
each missing or malformed value.

**Invariants.** The checker rejects every combination not allowed here:

| Condition | Required |
|---|---|
| `kind` is `site` or `repo` | `state: recorded`, `scan: none`, no `sha256`, no `released` |
| `state` is `recorded` | `scan: none`, no `released`; a `sha256` may be present as the expected value |
| `scan: flagged` and no `released` | `state: saved`; the file is in `sources/quarantine/` |
| `scan: flagged` | `state` is neither `converted` nor `read` |
| `released` present | `scan: review`; never `flagged`, `clean`, or `none` |
| `state` is `converted` or `read` | `scan` is `clean` or `review` |
| `replaced` present | not earlier than `retrieved`; a replace clears `released` |

- `kind: site` and `kind: repo` are reference-only. They are never saved or converted and
  stay `recorded` with `scan: none`. Claims whose only support is such a source are tagged
  `[A]` or `[U]` unless the domain's charter says otherwise.
- `state` follows [domain-lifecycle.md](domain-lifecycle.md). `saved` or later requires a
  file `sources/<stem>.<ext>` (or `sources/quarantine/<stem>.<ext>` when `scan` is
  `flagged`) whose SHA-256 equals `sha256`. Because `sources/` is untracked, a fresh clone
  lacks the files: the checker's default **clone mode** reports a missing file as a warning,
  and `--require-sources` (**strict mode**) makes it a failure. A file that exists with a
  different hash fails in both modes.
- `scan` is set by the converter ([source-pipeline.md](source-pipeline.md)): `none` before
  any scan, then `clean`, `review`, or `flagged`. A source that is `flagged` and not
  `released` is quarantined.
- `tier` describes the kind of source, not its truth.
- Catalog fields and index notes carry text derived from sources and are untrusted data.
  The standing rule applies to them, and tools reject control, zero-width, bidirectional,
  and Unicode tag characters in them. The rejected set is: C0 controls except line feed (U+000A)
  and tab (U+0009), carriage return (U+000D), DEL and the C1 controls (U+007F to U+009F),
  U+200B to U+200F, U+202A to U+202E, U+2060 to U+2064, U+2066 to U+2069, U+FEFF, and
  U+E0000 to U+E007F. Line feed and tab are allowed in Markdown bodies.
- A domain's `index/sources.md` lists the stems the domain uses, each with a short note on
  why it matters there. It does not repeat catalog facts.

## Playbook entries

File `domains/<domain>/playbook/entries/<id>.md`, where `<id>` matches `pb-[a-z0-9-]+` and
equals the front matter `id`. Aim for under about 1,000 words and one logical unit.

```yaml
---
id: pb-example
type: playbook-entry
title: "Short title"
tags: []                   # optional, free-form, domain-defined
status: draft              # draft | reviewed | superseded
sources:                   # catalog stems
  - 2020-author-short-title
updated: 2026-01-01        # required; date of the last content change
superseded_by: pb-other    # required when status is superseded, otherwise absent
---
```

**Required fields.** `id`, `type` (always `playbook-entry`), `title` (a non-empty string),
`status`, `sources` (a list of catalog stems), and `updated` (a date) are required; `tags` and
`superseded_by` are optional as described. `sources` may be empty only while `status` is
`draft`. The checker names the file and field for each missing or malformed value.

**Headings.** The required headings are **Use when**, **Approach**, **Pitfalls**,
**Evidence and confidence**, and **See also**, as level-2 headings, in that order. A heading
matches if its text is the name exactly, or the name followed by a space and a parenthesized
qualifier (for example `Use when (and when not)`), compared case-sensitively. Other
headings are allowed anywhere after **Use when**, for example a domain section between
**Approach** and **Pitfalls**, or a dated verification note appended at the end.

**Statuses.**

- `draft`: the default.
- `reviewed`: a person has signed off, recorded in the domain's `log.md` (see the lifecycle
  spec). The checker requires that the entry has no tag errors, has at least one `[V]` claim,
  and that its ID appears in a `Reviewed:` line of a closed wave in the domain's `log.md`.
- `superseded`: replaced by `superseded_by`, which must resolve. A superseded entry stays
  in place, keeps its ID, and is not listed in the domain router.

### Claim tags

- `[V]` verified against the full text of the saved source, or as the domain's charter
  defines its verification bar (for example agreement across several independent sources
  of a stated tier).
- `[A]` checked only at abstract, landing-page, or snippet level.
- `[U]` unverified: from memory, a secondary source, or synthesis.

Untagged prose is guidance or opinion and is read as `[U]`. When a claim is checked against
a source, upgrade its tag and note the location under **Evidence and confidence**.

**Tag grammar.** A candidate tag is `[`, one ASCII letter, then either `]` or a space, an
em dash (U+2014), a space, a note, and `]`: `[V]`, `[V — Table 3]`. Counting and
validation follow these rules:

- A note may wrap onto following lines (each line break counts as a space), but not across a
  blank line, a heading, or the end of the file; a candidate whose `]` is not found within its
  paragraph is an error. Real entries wrap long notes, so this is required.
- Tags inside fenced code blocks are ignored. A tag wrapped as a whole in single backticks
  is counted, because entries use that form to set a tag off from prose.
- A bracketed single letter followed by `(` or `:` is link text or a label and is ignored,
  as are task boxes (`[ ]`, `[x]`) and numeric references.
- A candidate whose letter is not exactly `V`, `A`, or `U` (including lowercase) is an
  error, as is a hyphen or en dash in place of the em dash.
- Tags anywhere in the entry, including **Evidence and confidence**, count toward the
  `reviewed` requirement.

**Conflict notes.** A contested claim uses the note convention
`[U — conflict: <stem> vs <stem>]`, with two or more catalog stems separated by `vs` or
commas. The rules for using it are in [domain-lifecycle.md](domain-lifecycle.md). A
conflict note is valid only on a `[U]` tag and only when every named stem has a catalog
record.

## Identifiers

- Entry IDs match `pb-[a-z0-9-]+`, are unique across all domains, and equal the filename
  stem.
- Source stems match `[a-z0-9][a-z0-9-]*` (at most 100 characters), contain no dots or
  underscores, are not a reserved name (`readme`, `quarantine`), and are unique across
  `catalog/` and `sources/`. The form `<year>-<firstauthor>-<short-title>` is recommended.
  Because a stem has no dot, `sources/<stem>.<ext>` is unambiguous.
- IDs and stems are never renamed. To retire an entry, mark it `superseded`.

## Routers

`playbook/README.md` (root) states the standing untrusted-data rule, how to consume the
knowledge base from another project, and a table with one row per domain. The rows sit
between the fixed lines `<!-- BEGIN kb:domains -->` and `<!-- END kb:domains -->`, so
`tools/new_domain.py` can add a row without touching other text. If either line is missing
the check fails and `new_domain.py` refuses to run. The table header is
`| Domain | Router | Purpose |`, the first column holds the domain name, and the second a
Markdown link to the domain router.

`domains/<domain>/playbook/README.md` is the domain router: a table from a situation to
the entries to read, in order.

**Titles in routers.** A title written into a router row by a tool must be printable
single-line text without `|`, `[`, `]`, or backticks; the tool refuses otherwise, and the
check fails on such a row, so a title cannot add a column or a link.

**References.** An entry reference is a Markdown link whose target, resolved relative to the
file containing the link, is an entry file under some domain's `playbook/entries/` (for
example `entries/<id>.md` from a domain router, or `../../<domain>/playbook/entries/<id>.md`
across domains), or an ID wrapped in backticks. Only these forms are checked for resolution;
other mentions of `pb-` text are prose. Every non-superseded entry of a domain is
referenced from that domain's router, and no superseded entry is.

**Index tables.** In `index/sources.md`, each data row of a GitHub-flavored table has the
catalog stem (backticks optional) in its first column. In `index/leads.md` the columns are
**Lead**, **Found in**, and **Why it may matter**.

## Copyright and licensing note

The installed project's `README.md` carries a short note, as guidance only. It says:

- The note is not legal advice, and the rules differ by jurisdiction, so the owner is
  responsible for what they save, quote, and publish.
- The starter's MIT license covers the starter's code and documents only. A project has no
  `LICENSE` until its owner chooses one, and saved sources keep their own terms.
- As defaults, `sources/` and `text/` are untracked, and entries are meant to be written
  in the author's own words with attribution to the catalog stem. Changing the defaults is
  the owner's decision.
- Before sharing or publishing a project, the owner should review what is tracked,
  including any quoted material, and the terms of the sources.
- Web-page terms of service become relevant once web capture exists.

## Acceptance criteria

`tools/check_kb.py` skips `domains/_skeleton/` and fails, with a message naming the file
and, where relevant, the line, when:

1. `[C2]` `kb.json` is missing, malformed, lacks any of the four keys, has a wrong type, a
   `kind` other than `knowledge-base`, a `router` other than `playbook/README.md`, a `spec`
   other than `docs/kb/knowledge-base-format.md`, a `schema` that is not a non-negative
   integer or is greater than the checker supports, or names a file that is not a regular file
   inside the project.
2. `[C2]` A front matter block does not parse under the subset above.
3. `[C2]` An entry lacks front matter, its `id` differs from its filename stem or does not
   match `pb-[a-z0-9-]+`, or `updated` is missing or not a date.
4. `[C2]` Two entries share an `id` (across all domains), or two files in `catalog/` or
   `sources/` share a stem, or a stem breaks the stem rules.
5. `[C2]` An entry's `sources:` stem has no catalog record.
6. `[C2]` An entry reference (as defined above) does not resolve.
7. `[C2]` A non-superseded entry is not referenced from its domain's router, or a superseded
   one is; a domain is not in the root router exactly once, or its row lacks a valid link to
   its router; the root router markers or the exact header `| Domain | Router | Purpose |`
   are missing; a domain router has no table; or a title in a router row contains `|`, `[`,
   `]`, a backtick, or a newline.
8. `[C2]` An entry's `status` is not `draft`, `reviewed`, or `superseded`; a `superseded`
   entry lacks a resolving `superseded_by`, or another status carries one; a `reviewed`
   entry has no `[V]` claim or no matching `Reviewed:` log entry (fixtures with and
   without); an entry lacks a required field, or has an empty `sources` list while not
   `draft` (a fixture for each).
9. `[C2]` A required heading is missing or out of order.
10. `[C2]` A candidate tag is invalid under the grammar, or a conflict note is on a tag
    other than `[U]`, names fewer than two stems, or names a stem with no catalog record.
11. `[C2]` A catalog file has a `stem` that differs from its filename, or an invalid `kind`,
    `tier`, `state`, `scan`, or `confirmed`, or violates any row of the invariants table
    (fixtures cover each row, for example a `site` with `state: saved`, `flagged` with
    `converted`, and `released` with `scan: flagged`), or lacks a required field, or has a
    `sha256` that is missing for a `saved` or later record or is not 64 lowercase hex digits
    (a fixture for each).
12. `[C2]` A catalog record in state `saved` or later has no file under `sources/` (or, when
    flagged and unreleased, `sources/quarantine/`), or a file whose SHA-256 differs from
    `sha256`. A file that exists with a different hash is always a failure. A missing file
    (including a missing quarantine file in a clone) is reported as a warning (unsaved), not
    a failure, unless the checker is run with `--require-sources`.
13. `[C2]` `.kb-manifest` is missing or its `kb_schema` differs from `kb.json`'s `schema`.
14. `[C2]` The `README.md` of a created project lacks the copyright and licensing note.
15. `[C2]` A control, zero-width, bidirectional, or Unicode tag character appears in a
    catalog record or index file.
16. `[C2]` `REPLACE_WITH_` appears in an entry or a domain router.

The checker reports, as warnings: an entry with a `[V]` tag citing a stem whose catalog
state is `recorded`, a record with `confirmed: full` and state `recorded`, and
instruction-like phrases in catalog fields or index notes. Warnings do not change the exit
status.

The domain-level checks (charter, questions, log) are in
[domain-lifecycle.md](domain-lifecycle.md).

A freshly created project passes the check with no domain beyond the skeleton. `[C2]`

The parser and tag grammar have fixture tests covering each rule above, including a tag
inside a fenced code block, `[x]`, link text, a hyphen in place of the em dash, a title
with a colon, and a duplicate key. `[C2]`

## Related

- [installer.md](installer.md)
- [source-pipeline.md](source-pipeline.md)
- [domain-lifecycle.md](domain-lifecycle.md)
