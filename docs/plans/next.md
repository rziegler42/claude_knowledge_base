# Next plan

Status: In Progress (approved 2026-10-18 by the owner; implementation started 2026-10-18 on the owner's request)
Created: 2026-10-18

## Goal

Ship the source pipeline in every store's `tools/`: a converter that scans each saved PDF, writes a
Markdown and a plain-text conversion with the untrusted-content banner, quarantines a flagged
original, updates the catalog, and bounds every run with the limits in
`docs/specs/source-pipeline.md`. It meets every criterion tagged `[C3]`, with fixture tests and no
network.

## Scope

- `kit/files/tools/convert_sources.py` (the command), `convert_worker.py` (the part that opens a PDF),
  `kbscan.py` (the scan rules that need no PDF library), and `scan_phrases.txt` (the phrase list).
- Scan levels, hidden-text rules, the scan numbers, finding labels, and `--snippets`.
- Conversion to `text/<stem>.md` and `.txt` with front matter, page markers, banners, and opt-in images.
- Quarantine, stubs, `--release`, and the catalog fields the converter owns (`state`, `scan`,
  `released`).
- Freshness rules, `--check`, `--scan`, and the resource limits and isolation.
- Fixture PDFs built by a small test helper, and tests for criteria 1 to 12.
- Documentation: `docs/development.md`, `docs/architecture.md`, and the store's README.
- Revision approved by the owner (2026-10-18, after the security review): a small amendment to the
  specification and its kit copy (Increment F).

## Non-goals

- Web pages, other formats, OCR, and fetching from URLs (the specification's non-goals).
- `add_source.py`, `new_domain.py`, `new_entry.py`, `kb_status.py`, and the lifecycle checks added to
  `check_kb.py` (candidate 4). The converter reads and updates catalog records itself, and does not
  create them or replace a source file.
- Upgrade (candidate 5), the README quick start and `LICENSE` (candidate 6), and Claude skills
  (candidate 8).
- Installing a PDF library. The converter reports what is missing.
- Changing the installer, the manifest, or `kb_schema`: new files under `tools/` are starter-owned
  and need no schema change.

## Assumptions and constraints

- Roadmap candidate 3, after candidate 2a (done). The specification is Approved (2026-10-17) and the
  numbers in it are accepted defaults.
- Verified on this machine: a virtual environment outside the repository holds `pymupdf` and
  `pymupdf4llm` 1.28.2, `pdftotext` 26.10.0 is installed, and `pymupdf` exposes the data the hidden-text
  rules need (`Page.get_texttrace()` gives render mode, opacity, fill colour, and glyph box;
  `get_drawings()`, `embfile_count`, and `is_encrypted` exist). No dependency has to be installed.
- The game_theory converter (`research/tools/convert_pdfs.py`) is a design reference only. It uses
  `pymupdf`, `pymupdf4llm`, and `pdftotext`, runs under the external interpreter in isolated mode, and
  has the same quarantine idea; its topic folders, thresholds, and extra safe schemes differ from the
  specification and are not copied.
- Architecture: `convert_sources.py` uses only the standard library and can run under any Python 3.9+.
  It starts `convert_worker.py` as a child (`sys.executable -I`) for each PDF, so the time and output
  limits can be enforced by killing the child. The worker imports `pymupdf` and `pymupdf4llm`. Run the
  command with the external interpreter (`<venv>/bin/python -I tools/convert_sources.py`) and the
  worker inherits it. A missing library or `pdftotext` is reported by name.
- The command loads `kbparse.py` by file path with `importlib`, not through `sys.path`, so a decoy
  module in the working directory or `PYTHONPATH` is never imported. The child's environment is
  scrubbed (`PYTHON*`, `GIT_*`, and proxies dropped).
- The converter and the scanner record: converter identity `"pymupdf4llm <version>; pdftotext <version>"`
  (one string, because the `.md` and `.txt` must agree, freshness rule 6) and scanner version `1`.
- Catalog edits change only the `state`, `scan`, and `released` lines of a record, by line, then
  re-parse the result with `kbparse` before an atomic replace. Any record the strict parser refuses is
  reported and skipped.
- Tests run under the system Python. Those that need `pymupdf` start the converter with the
  interpreter named by the environment variable `KB_PDF_PYTHON` and are skipped, with a visible message,
  when it is unset. The plan's completion requires them to run. No personal path is committed.
- Choices made in this draft that the owner may overrule: the file names above (the specification names
  only `convert_sources.py` and `tools/scan_phrases.txt`); the worker split; `KB_PDF_PYTHON` for tests;
  scanner version `1`.
- Owner decision (2026-10-18): keep the link-scheme rule strict, as the specification states. Any link
  whose scheme is not `http`, `https`, `mailto`, or `doi` is high and quarantines the source. A LaTeX
  paper that leaves a citation key such as `gomez:ab97` as a link target will be flagged, and the
  owner releases it by hand with `--release` after review. The specification does not change.

## Graphify

Graphify: skipped — no graph exists in this checkout. The scope is enumerated by the approved
specification and by direct reading of the reference converter, the format specification's catalog
rules, and the lifecycle specification's tool table. The new files are self-contained under `tools/`;
the only existing code they touch is `kbparse.py`, read through its public functions.

## Completion criteria

- Every `[C3]` criterion (1 to 12) in `docs/specs/source-pipeline.md` has a passing test, run with
  `KB_PDF_PYTHON` set so the PDF tests are not skipped.
- A real fixture PDF saved in a store converts, the store passes `check_kb.py --require-sources`, and a
  second run writes nothing.
- A security review of the PDF reading, subprocess handling, and file writes finds nothing open.
- `python3 -I -B -m unittest discover -s tests` (with the variable set) and `git diff --check` pass,
  and the kit's `tools/` contains no `__pycache__`.

## Increments

### Increment A — The scan rules that need no PDF

Dependencies: None
Affected areas: `kit/files/tools/kbscan.py`, `kit/files/tools/scan_phrases.txt`, `tests/test_kbscan.py`

1. Write the failing tests first for the text-level rules: the phrase list (loaded from
   `scan_phrases.txt`, one case-insensitive expression per line, matched after NFKC) with a pattern for
   each required category; zero-width and bidirectional control counting at 5 and 6; any Unicode tag
   character; hidden text over 200 characters or 5% of extracted text; level aggregation (the highest
   level wins); finding labels that never carry the matched text unless snippets are on.
2. Implement `kbscan.py` as standard-library code with a `SCANNER_VERSION = 1` and a function that
   turns collected facts into a level and a list of labelled findings. Bound the phrase list (line
   count and expression length) and refuse an expression that does not compile, so the list cannot
   hang or crash the run.
3. Ship `scan_phrases.txt` with patterns for ignoring prior instructions, claiming the reader is an AI
   or that text is a system prompt, requesting a command or URL fetch, and asking to conceal something.
4. Run the new tests.

Completion: the text-level cases of criteria 1 and 6 pass without a PDF library.

### Increment B — PDF fixtures and the PDF scan

Dependencies: Increment A
Affected areas: `tests/pdffixtures.py`, `kit/files/tools/convert_worker.py`, `tests/test_scan_pdf.py`

1. Write a test helper that assembles fixture PDFs from raw objects: ordinary text, white text with and
   without a filled shape behind it, text at 1.2 and 1.1 points, opacity 0.05 and 0.04, render mode 3,
   text outside the page, an embedded file, each active-content key (`/JavaScript`, `/JS`, `/Launch`,
   `/RichMedia`, `/SubmitForm`, `/ImportData`, `/OpenAction` and `/AA` with a non-`GoTo` action), link
   annotations with allowlisted and non-allowlisted schemes, phrase text in visible text, an
   annotation, and metadata, control and tag characters in text and metadata, and an encrypted file
   (built with `pymupdf` and skipped when it is absent). Open each fixture with `pymupdf` to check it.
2. Write the failing scan tests: every trigger in the specification's table, a fixture on each side of
   each numeric threshold, one per allowlisted and non-allowlisted scheme, a fixture with several
   triggers taking the highest level, and an ordinary PDF as `clean`.
3. Implement the scan in `convert_worker.py` (`--scan` mode): embedded files, active content, link
   schemes judged by scheme and not label, encryption, hidden text from the text trace and drawn
   shapes, text in annotations and metadata, and the facts passed to `kbscan`. Treat the converted
   Markdown separately in Increment C for image links.
4. Run the tests with `KB_PDF_PYTHON` set.

Completion: criterion 1 passes for every fixture, and without `KB_PDF_PYTHON` the PDF tests are
reported as skipped, not passed.

### Increment C — Conversion, limits, and isolation

Dependencies: Increment B
Affected areas: `kit/files/tools/convert_worker.py`, `kit/files/tools/convert_sources.py`,
`tests/test_convert.py`

1. Write the failing tests first: the converted `.md` and `.txt` start with front matter that parses
   under the strict subset (`source`, `source_sha256`, `converter`, `scanner`, `images`, `scan`,
   `scan_findings`, `converted`, `caveat`), then the exact banner marker and text for `clean` and
   `review`, a source link near the top, and page markers; no `img/` directory without `--images`, images
   written with it, and nothing marked `REVIEWED`; the Markdown image-link rule (an `http`, `https`, or
   `data` image link makes the source high and nothing is written); each limit in the table refused with
   a stub and a message while the run continues; a child that prints more than 1 MiB is killed and
   reported failed; a decoy `json.py` in the working directory and in `PYTHONPATH` is never imported;
   the worker opens no network connection (a test starts it with `socket` patched to fail).
2. Implement the worker's conversion: `pymupdf4llm` Markdown with page markers, relative image links,
   the page and text-size limits, and the image count limit.
3. Implement the command's child management: start the worker with `-I` and a scrubbed environment,
   read both pipes with a bounded buffer, enforce the 300-second and 1 MiB limits by killing the child,
   and refuse a file over 200 MiB before starting one. Produce `.txt` with `pdftotext -layout` under the
   same time and output bounds.
4. Write outputs through a temporary sibling and a rename, and never modify the source.
5. Run the tests with `KB_PDF_PYTHON` set.

Completion: criteria 3 (front matter and hash), 6, 9, 10, 11, and 12 pass.

### Increment D — Catalog, quarantine, release, freshness, and commands

Dependencies: Increment C
Affected areas: `kit/files/tools/convert_sources.py`, `tests/test_convert_catalog.py`

1. Write the failing tests first: a flagged fixture yields only a stub with `scan: flagged`, the
   original lands in `sources/quarantine/`, and the record shows `scan: flagged` with `state: saved`;
   a converted fixture sets `state: converted` and `scan`, and a second run writes nothing; each of
   the six freshness rules taken alone makes `--check` report the conversion stale with that rule's
   number, damaged front matter is `unreadable metadata` without a crash, and a conversion made with
   images stays current without `--images`; `--scan` and `--check` write nothing; a missing
   dependency is reported by name; `--release` moves a quarantined fixture back, records `released`,
   converts it as `review` with the release statement and the high finding in `scan_findings`, does not
   flag it again, flags a replaced file with the same trigger, and nothing converts a quarantined file
   without `--release`; a `.txt` whose marker or `scan` disagrees with the `.md` or the catalog is stale.
2. Implement the catalog editor (line-based, re-parsed before replace), the convert loop over records in
   state `saved` or stale, quarantine moves, stubs, `--release`, the freshness check, `--check`,
   `--scan`, `--snippets`, `--images`, and the limit flags.
3. Run the tests with `KB_PDF_PYTHON` set, then the full suite.

Completion: criteria 2, 3, 4, 5, 7, and 8 pass, and with the earlier increments all twelve `[C3]`
criteria pass.

### Increment E — Documents, review, and the real-store check

Dependencies: Increment D
Affected areas: `docs/development.md`, `docs/architecture.md`, `kit/files/README.md`

1. Update `docs/development.md` with the interpreter requirement, `KB_PDF_PYTHON`, the changed "All
   required checks" command, and how to build the external environment (as text, not run). Update
   `docs/architecture.md` with the new components and the converter's isolation. Add one line to the
   store's README on running the converter.
2. Run the owner's `security-review` skill on the new code with the `security-reviewer` agent and
   hostile fixtures: malformed and truncated PDFs, an enormous page count, decompression bombs, a
   FIFO or symlink in `sources/` and `text/`, a stem that tries to leave the directory, a symlinked
   `text/`, a `catalog/` record that tries to inject front matter, hostile text in a converted file
   reaching the banner or the `--check` output, race-free atomic writes, child cleanup after a kill,
   and environment leakage into the child. Add a regression test that fails first for each finding.
3. Real-store check: create a store with the installer, save a fixture PDF and its catalog record by
   hand, run the converter with the external interpreter, then run `check_kb.py --require-sources`,
   and convert again to confirm nothing is rewritten.
4. Run the full suite with `KB_PDF_PYTHON` set, and `git diff --check`.

Completion: documents match the built tools, the review has nothing open, the real-store check passes,
and the full suite passes with no PDF test skipped.

### Increment F — Align the specification with the reviewed behavior

Dependencies: Increment E (revision approved by the owner on 2026-10-18)
Affected areas: `docs/specs/source-pipeline.md`, `kit/files/docs/kb/source-pipeline.md`,
`kit/files/tools/convert_worker.py`, `tests/test_scan_pdf.py`

1. Write the failing test first: a PDF whose AcroForm carries an `/XFA` entry is `high`; one without is
   unchanged.
2. Add `/XFA` to the active-content keys in the worker.
3. Amend the specification: add `/XFA` to the active-content list; say a shape or image counts as "behind"
   white text only when it is visibly drawn (a fill that is not itself white and is at least half opaque);
   say text the renderer does not report as drawn (pattern fills) is checked against the phrase list only and a
   hit is treated as hidden text; and add the unflagged `Named` link actions and the absent memory limit to
   the accepted residuals. The scanner version stays 1: nothing has been released with an earlier rule set.
4. Regenerate the `docs/kb/source-pipeline.md` copy by the drift rule, and run the full suite.

Completion: the amended specification, its kit copy, and the code agree, and the suite passes.

## Verification

- `KB_PDF_PYTHON=<external interpreter> python3 -I -B -m unittest discover -s tests`: all twelve `[C3]`
  criteria, plus the existing suite. Report the number skipped; it must be zero.
- `python3 -I -B -m unittest discover -s tests` without the variable: the PDF tests report as skipped
  and everything else passes, so the suite is still usable without the library.
- `git diff --check`, and `git status` shows no `__pycache__` under `kit/`.
- The real-store check in Increment E.

## Risks and sensitive actions

- Untrusted input: the whole feature parses hostile PDFs. The library parses in a killed-on-limit child
  with a scrubbed environment, but a vulnerability in `pymupdf` can still be exploited (an accepted
  residual in the specification). The security review is part of the plan.
- Filesystem writes: the converter moves an original into `sources/quarantine/` and rewrites catalog
  records. Both go through temporary siblings or a single rename, refuse symlinks, and are tested against
  hostile names.
- Fixture PDFs with active content and tag characters are generated into temporary directories at test
  time. Nothing hostile is committed.
- No dependency is installed. The external environment is only used. No commit, push, or deletion
  happens without explicit owner approval.

## Review

Codex plan review: not run. The plan-review slot for `docs/plans/next.md` was closed when plan 0002
was archived, and `ask-codex reset` refuses a closed review. The owner approved the plan without a
Codex review (2026-10-18). The security review in Increment E covers the risky surface.

## Deferred work

- Web pages and other formats; OCR; fetching sources; and extracting text from images (the
  specification's residuals).
- `add_source.py --replace`, which clears `released` and sets `replaced` (candidate 4). The converter
  only honours those fields.
- Writing the `REVIEWED` marker for extracted images; it is a human action by design.
- A test that checks the converter against `pymupdf` versions other than the one installed.
- Upgrade, release readiness, and skills (candidates 5, 6, and 8).

## Result

Implemented 2026-10-18, uncommitted at the time of writing. Verification run:

- `KB_PDF_PYTHON=<external interpreter> python3 -I -B -m unittest discover -s tests`: 422 tests pass,
  none skipped (about 125 seconds). Without the variable the same command passes with 128 tests reported
  as skipped. The count was 242 before this plan. `git diff --check` is clean and no `__pycache__` is left
  under `kit/` or `tests/`.
- Criteria: 1 (every trigger and threshold) in `tests/test_kbscan.py` and `tests/test_scan_pdf.py`; 2, 3, 4,
  5, 7, and 8 in `tests/test_convert_catalog.py`; 3 (front matter), 6, 9, 10, 11, and 12 in
  `tests/test_convert.py`. The worker is also tested to open no connection (a child with `socket` patched),
  to ignore a decoy `json.py` and `pymupdf.py` in the working directory, `PYTHONPATH`, and beside the
  worker, and to receive a scrubbed environment.
- Real-store check: a store made by the installer, one fixture PDF saved with a hand-written record,
  converted with the external interpreter (`clean`, `state: converted`), `check_kb.py --require-sources`
  reported 0 errors and 0 warnings, a second run rewrote nothing, and `--check` reported all conversions
  current. It found a defect no unit test had (`--check` listed the shipped `text/README.md` as orphaned);
  fixed with a regression test. It was repeated on a fresh store with the final tools: `clean`, 0 errors and 0
  warnings, a second run rewrote nothing, and `--check` reported all conversions current.
- Security review: three rounds of an independent `security-reviewer` with scratch experiments, every
  reproduced finding fixed with a regression test that failed first.
  - Round 1 (six findings): a phrase wrapped over lines or drawn with a kerning array evaded the phrase list
    (High); remote image links in reference style, entity-encoded, or with a long alt text; a URI in an
    annotation or chained action was not judged by scheme; an action chain over six deep hid a non-GoTo
    action; white text over a fully transparent shape was not hidden; a catalog write failure left a record
    inconsistent. It also found `run_bounded` could wait forever on a child that closed its pipes and let a
    grandchild outlive the run.
  - Round 2 re-verified those fixes, ran hostile catalog records, a fork storm, and a flooding grandchild,
    and found two more: ordinary short words could use up the letters of pattern-filled text in the
    untraced-text comparison, and a released record over a now-clean file kept `scan: clean` (now `review`).
  - Round 3 broke the position-based replacement for that comparison (a visible line of the same words
    beside the pattern text; hidden text whose word gaps barely exceed its letter gaps; thousands of stacked
    spans make it quadratic). The comparison is now a count of the page-text characters the text trace does
    not account for: a phrase in the page text is treated as hidden when at least as many characters are
    untraced as the phrase has (capped at 24). It is linear and does not depend on where words sit. Word
    breaks inside a span are rebuilt at two gap factors.
  - **Not independently reviewed:** the final character-count comparison, the two-factor word breaks, and
    the recheck of visible text through the trace (`check_phrases`, `check_untraced`). The reviewer's third-
    round reproductions are all tests that pass, and the false-positive cases it listed (quoted phrases in
    letter-spaced, justified, kerned, and mid-word font-change text) are tests that stay `review`, but no
    reviewer has tried to defeat this last design. Type3 fonts were never exercised by anyone.
- Two guards in the tests were added without a failing case to prove them (the many-`/AA` object and the
  figure-name spoof); they pass and stay as guards.

Owner decisions, made 2026-10-18 after the security review and carried out in Increment F:

1. White text and shapes: a shape counts as drawn behind white text only when its fill is not itself white and
   is at least half opaque. The code already did this; the specification now says so.
2. Pattern-filled text and anything else the text trace does not report as drawn: judged by the phrase list only,
   through the character count above, and never toward the 200-character or 5% rule. The specification now
   says so.
3. XFA forms are flagged as high (`/XFA` joins the active-content keys, with a test). `Named` link actions stay
   unflagged and the missing memory limit stays, both recorded as accepted residuals in the specification.
   The scanner version stays 1: nothing was released with an earlier rule set.
4. The 5% hidden-text rule uses the characters of the whole page text, including the hidden ones, and fires
   for a single hidden character on a short page, as the specification states (unchanged).

The amended `docs/specs/source-pipeline.md` and its regenerated `docs/kb/` copy are part of this plan's commit.

Other interpretations made here: stubs carry `stub: <reason>` and `scan: flagged` (flagged) or `scan: none`
(limit or read failures), and a stub is never current, so a failed source is retried on every run; a source
whose record is already flagged but whose original is still in `sources/` is moved into quarantine by the next
run, and a `--release` cut short is completed by running it again; `--release` and conversion update the
catalog record before they move a file.

Accepted residuals. The specification's own: text inside images, text clipped away or covered by a later shape,
novel phrasings, a library exploit in `pymupdf`. New: a grandchild that calls `setsid` survives the kill; the
race between hashing a source and the worker opening it is within ADR 0002's accepted concurrent-local-attacker
residual; the phrase list and hidden-text rules are heuristics that a determined author can still evade.

Unresolved: none open. Next: commit, and archive (`ask-codex archive` is closed for this plan path, so no plan
review summary can be pasted; record that in the archive).
