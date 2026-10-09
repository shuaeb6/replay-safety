"""Build docs/regulations-table.md from docs/regulations.json.

The JSON file is the single source of truth. Never edit the markdown by hand.

Run:   uv run scripts/build_regulations_table.py          (write the file)
Check: uv run scripts/build_regulations_table.py --check  (fail if out of date)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "docs" / "regulations.json"
DOC_PATH = ROOT / "docs" / "regulations-table.md"

PACK_TITLES = {
    "OSHA": "OSHA: 29 CFR Part 1910",
    "cGMP": "cGMP: 21 CFR Part 211",
    "ISO": "ISO: 45001 and 14644",
}

INTRO = """\
# Regulations table

This table lists specific clauses that the Video Compliance Agent can check.
Each row has the requirement and the cue that a camera can show.
Use it to write rule packs and ingestion prompts.
See [the project description](261009-video-agents-hackathon-project-description.md) for the overview.
"""

HOW_TO_READ = """\
## How to read this table

- **Clause:** the paragraph to cite in a finding.
- **Requirement:** the rule in plain words. It is a summary, not the legal text.
- **Violation cue:** an example of what the camera can see when the rule is broken.
  The cue is a detection idea. It is not part of the regulation.
- Read the full clause before you cite it in a report.
"""


def escape_cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def render_row(row):
    cells = (row["clause"], row["topic"], row["requirement"], row["cue"])
    return "| " + " | ".join(escape_cell(c) for c in cells) + " |"


def render_table(rows):
    header = ["| Clause | Topic | Requirement | Violation cue |", "|---|---|---|---|"]
    return "\n".join(header + [render_row(r) for r in rows])


def group_by_pack(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["pack"], []).append(row)
    return groups


def render_pack_section(pack, rows, source):
    title = PACK_TITLES.get(pack, pack)
    return f"## {title}\n\nSource: {source}\n\n{render_table(rows)}\n"


def render_not_visible(items):
    lines = ["| Clause | Topic | Why |", "|---|---|---|"]
    for item in items:
        cells = (f"{item['pack']} {item['clause']}", item["topic"], item["reason"])
        lines.append("| " + " | ".join(escape_cell(c) for c in cells) + " |")
    return (
        "## Not visible in video\n\n"
        "The app cannot check these clauses from video alone.\n"
        "Do not make rules for them.\n\n" + "\n".join(lines) + "\n"
    )


def render_summary(data):
    counts = group_by_pack(data["rows"])
    parts = ", ".join(f"{pack} {len(rows)}" for pack, rows in counts.items())
    return (
        f"The table has {len(data['rows'])} rules ({parts}).\n"
        f"Retrieved {data['retrieved']}. Source text: eCFR for OSHA and cGMP.\n"
    )


def render_document(data):
    groups = group_by_pack(data["rows"])
    sections = [
        render_pack_section(pack, rows, data["sources"][pack])
        for pack, rows in groups.items()
    ]
    parts = [
        INTRO,
        render_summary(data),
        HOW_TO_READ,
        *sections,
        render_not_visible(data["not_visible"]),
    ]
    return "\n".join(parts)


def main(argv):
    data = json.loads(DATA_PATH.read_text())
    document = render_document(data)
    if "--check" in argv:
        if DOC_PATH.read_text() != document:
            print(f"{DOC_PATH} is out of date. Run this script without --check.")
            return 1
        print("regulations-table.md is up to date.")
        return 0
    DOC_PATH.write_text(document)
    print(f"Wrote {DOC_PATH} ({len(data['rows'])} rules).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
