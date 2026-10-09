"""Tests for data/regulations.json and the table generated from it.

Run: uv run --with pytest pytest tests/test_regulations.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_regulations_table as build  # noqa: E402

DATA_PATH = ROOT / "data" / "regulations.json"
DOC_PATH = ROOT / "docs" / "regulations-table.md"

ROW_FIELDS = ("pack", "standard", "clause", "topic", "requirement", "cue")
PACKS = ("OSHA", "cGMP", "ISO")
CFR_CLAUSE = {
    "OSHA": re.compile(r"^1910\.\d+(\([A-Za-z0-9]+\))*$"),
    "cGMP": re.compile(r"^211\.\d+(\([A-Za-z0-9]+\))*$"),
}


def load():
    return json.loads(DATA_PATH.read_text())


# --- data shape -----------------------------------------------------------


def test_every_row_has_all_fields_filled():
    for row in load()["rows"]:
        for field in ROW_FIELDS:
            assert row.get(field, "").strip(), f"{row.get('clause')}: empty {field}"


def test_packs_are_known():
    assert {r["pack"] for r in load()["rows"]} <= set(PACKS)


def test_clause_is_unique_within_standard():
    seen = set()
    for row in load()["rows"]:
        key = (row["standard"], row["clause"])
        assert key not in seen, f"duplicate {key}"
        seen.add(key)


def test_cfr_clauses_have_valid_format():
    for row in load()["rows"]:
        pattern = CFR_CLAUSE.get(row["pack"])
        if pattern:
            assert pattern.match(row["clause"]), row["clause"]


def test_table_is_much_longer_than_the_overview_table():
    assert len(load()["rows"]) >= 80


def test_each_pack_has_sources():
    data = load()
    for pack in PACKS:
        assert data["sources"].get(pack), f"missing source for {pack}"


def test_not_visible_entries_have_reasons():
    for item in load()["not_visible"]:
        assert item["clause"] and item["topic"] and item["reason"]


# --- generator ------------------------------------------------------------


def test_escape_cell_escapes_pipes_and_newlines():
    assert build.escape_cell("a|b\nc") == "a\\|b c"


def test_render_table_has_header_and_one_line_per_row():
    rows = [
        {"clause": "1910.22(c)", "topic": "T", "requirement": "R", "cue": "C"},
        {"clause": "1910.23(b)(8)", "topic": "T2", "requirement": "R2", "cue": "C2"},
    ]
    lines = build.render_table(rows).splitlines()
    assert lines[0] == "| Clause | Topic | Requirement | Violation cue |"
    assert lines[1] == "|---|---|---|---|"
    assert lines[2] == "| 1910.22(c) | T | R | C |"
    assert len(lines) == 2 + len(rows)


def test_group_by_pack_keeps_file_order():
    rows = [
        {"pack": "OSHA", "clause": "a"},
        {"pack": "cGMP", "clause": "b"},
        {"pack": "OSHA", "clause": "c"},
    ]
    groups = build.group_by_pack(rows)
    assert [r["clause"] for r in groups["OSHA"]] == ["a", "c"]
    assert list(groups) == ["OSHA", "cGMP"]


def test_render_document_has_one_section_per_pack_and_counts():
    doc = build.render_document(load())
    for pack in PACKS:
        assert f"## {pack}" in doc
    assert f"{len(load()['rows'])} rules" in doc


def test_committed_doc_matches_generated_output():
    assert DOC_PATH.read_text() == build.render_document(load()), (
        "docs/regulations-table.md is out of date. "
        "Run: uv run scripts/build_regulations_table.py"
    )
