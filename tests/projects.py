"""Build scratch knowledge-base projects for checker and installer tests.

The builder copies the kit's files and applies the slot contents by hand, so checker tests
do not depend on the installer.
"""
import json
import shutil
from pathlib import Path

import helpers

CATALOG_DEFAULTS = {
    "kind": "document",
    "title": '"A source"',
    "authors": "[Author One]",
    "url": "https://example.org/paper",
    "retrieved": "2026-01-01",
    "confirmed": "full",
    "tier": "primary",
    "state": "recorded",
    "scan": "none",
}

SHA = "0123456789abcdef" * 4

ENTRY_BODY = """# Title

## Use when

When something happens.

## Approach

Do the thing [V].

## Pitfalls

Avoid the other thing [U].

## Evidence and confidence

Checked at page 3 [V — p. 3].

## See also

Nothing yet.
"""


def build_project(dest, with_manifest=True):
    dest = Path(dest)
    shutil.copytree(helpers.KIT / "files", dest, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    readme = (helpers.KIT / "base" / "README.md").read_text(encoding="utf-8")
    note = (helpers.KIT / "slots" / "readme-docs.md").read_text(encoding="utf-8")
    (dest / "README.md").write_text(
        readme.replace("REPLACE_WITH_PROJECT_NAME", "demo").replace(
            "<!-- @module-slot: readme-docs -->", note), encoding="utf-8")
    if with_manifest:
        (dest / ".kb-manifest").write_text(
            json.dumps({"schema": 1, "kb_schema": 1, "name": "demo", "files": {}, "blocks": {}}),
            encoding="utf-8")
    return dest


def front_matter(fields):
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def add_catalog(proj, stem, **overrides):
    fields = {"stem": stem, **CATALOG_DEFAULTS, **overrides}
    ordered = {k: fields[k] for k in fields}
    helpers.write(proj, f"catalog/{stem}.md", front_matter(ordered) + "\nNote.\n")


def add_domain(proj, name, title="Demo", charter="draft", router_rows=(), root_row=True):
    proj = Path(proj)
    d = proj / "domains" / name
    shutil.copytree(proj / "domains" / "_skeleton", d)
    charter_path = d / "README.md"
    text = charter_path.read_text(encoding="utf-8")
    text = text.replace("REPLACE_WITH_DOMAIN", name).replace("REPLACE_WITH_TITLE", title)
    text = text.replace("charter: draft", f"charter: {charter}")
    for token in ("PURPOSE", "SCOPE", "NON_GOALS", "SOURCE_TYPES", "BAR", "NOTES"):
        text = text.replace(f"REPLACE_WITH_{token}", "filled in")
    charter_path.write_text(text, encoding="utf-8")
    router = d / "playbook" / "README.md"
    body = router.read_text(encoding="utf-8").replace("REPLACE_WITH_TITLE", title)
    router.write_text(body + "".join(router_rows), encoding="utf-8")
    if root_row:
        root = proj / "playbook" / "README.md"
        row = f"| {name} | [{title}](../domains/{name}/playbook/README.md) | Purpose |\n"
        root.write_text(root.read_text(encoding="utf-8").replace(
            "<!-- END kb:domains -->", row + "<!-- END kb:domains -->"), encoding="utf-8")
    return d


def add_entry(proj, domain, entry_id, body=ENTRY_BODY, route=True, **overrides):
    fields = {
        "id": entry_id,
        "type": "playbook-entry",
        "title": '"An entry"',
        "status": "draft",
        "sources": ["src-one"],
        "updated": "2026-01-01",
    }
    fields.update(overrides)
    fields = {k: v for k, v in fields.items()}
    path = Path(proj) / "domains" / domain / "playbook" / "entries" / f"{entry_id}.md"
    helpers.write(path.parent, path.name, front_matter(fields) + "\n" + body)
    if route and fields.get("status") != "superseded":
        router = Path(proj) / "domains" / domain / "playbook" / "README.md"
        router.write_text(router.read_text(encoding="utf-8") +
                          f"| A situation | [{entry_id}](entries/{entry_id}.md) |\n", encoding="utf-8")
    return path


def good_project(dest):
    """A project with one domain, one source, and one entry that passes the check."""
    proj = build_project(dest)
    add_catalog(proj, "src-one", state="recorded")
    add_domain(proj, "demo")
    add_entry(proj, "demo", "pb-one")
    return proj
