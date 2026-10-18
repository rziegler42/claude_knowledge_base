# Contributing

Thanks for contributing.

## Before you begin

- Read the [project README](README.md).
- Read the [development guide](docs/development.md).
- Check existing issues, decisions, plans, and pull requests for related work.
- For a substantial, risky, or architectural change, discuss the approach before
  beginning implementation.

## Development workflow

1. Make a focused change that addresses one coherent outcome.
2. Add or update proportionate tests and documentation.
3. Run the relevant checks documented in `docs/development.md`.
4. Review the diff for unrelated changes, generated artifacts, and accidental
   secrets before opening a pull request.

## Pull requests

Describe the problem, the approach, verification performed, and any remaining
limitations or follow-up work. Keep pull requests reviewable; separate unrelated
refactoring or cleanup into another change.

## Required checks

Run the full suite and the whitespace check before opening a pull request (the commands and the PDF
test setup are in [docs/development.md](docs/development.md)):

```sh
KB_PDF_PYTHON=<venv>/bin/python python3 -I -B -m unittest discover -s tests
git diff --check
```

Without `KB_PDF_PYTHON` the tests that open PDFs are skipped and the rest still run. Leave no `__pycache__`
under `kit/` or `tests/`.

## Conventions

- Standard library and git only for the installer and for the tools in `kit/files/tools/`, except the PDF
  worker, which needs `pymupdf`, `pymupdf4llm`, and `pdftotext`; do not add a dependency without discussing it first.
- A behavior change comes with a test, and a durable design choice with a decision record in
  `docs/decisions/`. Substantial work follows the plan lifecycle described in [docs/plans/README.md](docs/plans/README.md).
- Commit messages describe the change only.
- Tracked files carry no personal paths, addresses, or subject-specific content; a repository test enforces this.

## Security

If you find a security problem, open an issue that names the affected area without exploit details.
