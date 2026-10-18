# REPLACE_WITH_PROJECT_NAME

## Knowledge base

Start at [playbook/README.md](playbook/README.md). The format and procedures are in
[docs/kb/](docs/kb/). Run `python3 tools/check_kb.py` to validate the project.
To start a domain run `python3 tools/new_domain.py <name> --title "Title"`; `new_entry.py`, `add_source.py`, and
`kb_status.py` do the other mechanical parts (see [docs/kb/domain-lifecycle.md](docs/kb/domain-lifecycle.md)).
To scan and convert saved PDFs, run `tools/convert_sources.py` with an interpreter that has
`pymupdf` and `pymupdf4llm` (see [docs/kb/source-pipeline.md](docs/kb/source-pipeline.md)).

## Copyright and licensing

This note is guidance only, not legal advice. The rules differ by jurisdiction, so you are
responsible for what you save, quote, and publish.

- The starter's MIT license covers the starter's code and documents only. This project has no
  `LICENSE` until you choose one, and saved sources keep their own terms.
- By default `sources/` and `text/` are untracked, and entries are meant to be written in
  your own words with attribution to the catalog stem. Changing those defaults is your
  decision.
- Before sharing or publishing this project, review what is tracked, including any quoted
  material, and the terms of the sources.
- Web-page terms of service become relevant once web capture exists.
