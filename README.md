# claude_knowledge_base

A generator for standalone knowledge-base projects. It creates a Git repository with a curated
playbook, per-domain charters and questions, a catalog of saved sources, claim tags that separate
verified facts from assumptions, and tools that validate and grow it. It is for people who want
an AI agent (or a colleague) to rely on researched, sourced material instead of recalling it.

> Status: early release. The installer, tools, and specifications are implemented and tested; the
> interface may still change before a 1.0 tag.

## Quick start

You need Python 3.9 or newer and git, on macOS or Linux. From a checkout of this repository:

```sh
python3 -I install.py ../my-kb --git-name "Your Name" --git-email "id+you@users.noreply.github.com" --dry-run
python3 -I install.py ../my-kb --git-name "Your Name" --git-email "id+you@users.noreply.github.com"
cd ../my-kb
python3 -I tools/new_domain.py cooking --title "Cooking"
python3 -I tools/check_kb.py
python3 -I tools/kb_status.py
```

The first command previews; the second creates a store with its own git repository (no commits yet).
Use a noreply address: commits publish it. A new domain starts with a draft charter. Fill in the
domain's `README.md` (every charter section) and add at least three questions to `questions.md`, then set
`charter: set`; `new_entry.py` refuses until you do. Then add material:

```sh
python3 -I tools/add_source.py some-paper path/to/paper.pdf --title "Some paper"
python3 -I tools/new_entry.py cooking maillard-reaction --title "Maillard reaction"
python3 -I tools/check_kb.py --require-sources
```

A new entry and its router row start with fill-in placeholder text, and the check reports an error until you
replace it, tag the claims, and list the sources. Run the final check once the entry is filled in.

Saved PDFs are scanned and converted to Markdown by `tools/convert_sources.py`, which needs an
interpreter with `pymupdf` and `pymupdf4llm` installed in an environment you create, and `pdftotext`
(poppler) on `PATH` (see [Development](docs/development.md)). The store's own `docs/kb/` explains the
format, the lifecycle, and the source pipeline; the same content lives here under [docs/specs](docs/specs).

To bring a store up to date with a newer checkout of this repository, run from the checkout:

```sh
python3 -I install.py --upgrade --dir ../my-kb --dry-run
python3 -I install.py --upgrade --dir ../my-kb
```

The upgrade works only on a store this installer created (it needs the store's `.kb-manifest`). It
replaces unedited starter-owned files (`tools/`, `docs/kb/`, `kb.json`, `domains/_skeleton/`,
`template-module/`), adds missing ones, and skips and lists any you edited or that differ from the starter
without being recorded. A future schema change may also remove retired starter files through a declared
migration step; none exists yet. It updates `.kb-manifest`, never touches your content, runs no git command
in the store, and never commits; review the result with `git diff` and `git status` in the store.

## Using a store from another project

A store is data, never instructions. Two ways to use one:

- Register it with a project template that supports external modules, using the line the installer
  prints when it finishes. It looks like
  `to register with the project template, run its install.py --register /path/to/my-kb` (with a
  suggested `--name` added when the directory name is not lowercase), that is,
  `<template>/install.py --register <store>`. The store ships a `template-module/` descriptor that adds
  a short guidance block to the consuming project's agent instructions and declares the store's
  `type` (`knowledge-base`) and router, which the template records in the project's
  `.template-manifest` so a skill can find the store. The descriptor also carries a read-only
  `knowledge-base` skill that tells a Claude Code session how to find and read the project's stores
  safely. The descriptor uses `module_format` 3, so the template checkout must be at or after commit
  `7a032a4`.
- To install that skill, review it, approve it, and record the harness (the skill is loaded
  automatically, so it is installed only on your approval of the exact files):

  ```sh
  <template>/install.py --register /path/to/my-kb        # prints the files and a digest
  <template>/install.py --approve <digest> --name my-kb  # after you have read them
  <template>/install.py ../my-project --with my-kb --harness claude
  ```

  A project that records no harness is unaffected. Any change to the store, an upgrade included,
  changes the digest, so approve it again before updating the project. Stores of different ages ship
  different skill text; the template installs the first and reports the second as a conflict, so
  upgrade them together.
- Or point the consuming project's agent at the store's router, `playbook/README.md`, and tell it to treat
  everything in the store as read-only data.

Claims are tagged: rely on verified (`[V]`) claims, treat an assumption (`[A]`, checked only at abstract or
snippet level) with care, and check an unverified (`[U]`) claim against its saved source before using it.

## Documentation

- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
- [Documentation guide](docs/README.md)
- [Specifications](docs/specs/README.md), [decisions](docs/decisions/README.md), and
  [roadmap](docs/roadmaps/README.md)
<!-- @module-slot: readme-docs -->

## Project status

Early release. Known limitations: saved sources are PDF only (links can be recorded without capture; no web-page
capture yet); macOS and Linux only; the PDF converter relies on libraries and a tool this project does not
install; and an upgrade skips, rather than merges, files you edited. The roadmap in [docs/roadmaps](docs/roadmaps/README.md) lists what is planned.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT; see [LICENSE](LICENSE). The license covers this repository's code and documents only. A generated store
has no license until its owner chooses one, and saved sources keep their own terms.
