"""Tests for data/regulations.json and the tables generated from it.

Run: uv run --with pytest pytest tests/test_regulations.py
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_regulations_table as build  # noqa: E402

DATA_PATH = ROOT / "data" / "regulations.json"
ALL_DOC_PATH = ROOT / "docs" / "regulations-table.md"
SETTING_DOC_PATH = ROOT / "docs" / "regulations-by-setting.md"
CSV_PATH = ROOT / "data" / "regulations.csv"
RULES_JS_PATH = ROOT / "app" / "rules.js"

ROW_FIELDS = ("pack", "standard", "clause", "topic", "requirement", "cue")
PACKS = ("OSHA", "OSHA-CONST", "cGMP", "EPA", "ISO")
CFR_CLAUSE = {
    "OSHA": re.compile(r"^1910\.\d+(\([A-Za-z0-9]+\))*$"),
    "OSHA-CONST": re.compile(r"^1926\.\d+(\([A-Za-z0-9]+\))*$"),
    "cGMP": re.compile(r"^211\.\d+(\([A-Za-z0-9]+\))*$"),
    "EPA": re.compile(r"^262\.\d+(\([A-Za-z0-9]+\))*$"),
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
    assert len(load()["rows"]) >= 140


def test_each_pack_has_sources():
    data = load()
    for pack in PACKS:
        assert data["sources"].get(pack), f"missing source for {pack}"


def test_not_visible_entries_have_reasons():
    for item in load()["not_visible"]:
        assert item["clause"] and item["topic"] and item["reason"]


# --- settings column ------------------------------------------------------


def test_settings_registry_has_label_and_description():
    for sid, info in load()["settings"].items():
        assert info["label"].strip(), sid
        assert info["description"].strip(), sid


def test_every_row_has_valid_settings():
    known = set(load()["settings"])
    for row in load()["rows"]:
        assert row["settings"], f"{row['clause']}: no settings"
        assert set(row["settings"]) <= known, f"{row['clause']}: unknown setting"
        assert len(set(row["settings"])) == len(row["settings"]), row["clause"]


def test_every_setting_has_rows():
    used = {s for r in load()["rows"] for s in r["settings"]}
    assert used == set(load()["settings"])


def test_general_industry_rules_are_not_tagged_construction():
    # 29 CFR 1910.12 sends construction work to part 1926.
    for row in load()["rows"]:
        if row["pack"] == "OSHA":
            assert "construction" not in row["settings"], row["clause"]


def test_construction_pack_is_tagged_construction_only():
    for row in load()["rows"]:
        if row["pack"] == "OSHA-CONST":
            assert row["settings"] == ["construction"], row["clause"]


def test_chem_lab_has_lab_specific_rules():
    chem = {r["clause"] for r in load()["rows"] if "chem-lab" in r["settings"]}
    assert "1910.1450(e)(3)(iii)" in chem  # fume hoods work
    assert "262.15(a)(4)" in chem  # waste container closed


# --- detector modules -----------------------------------------------------


def app_module_ids():
    text = RULES_JS_PATH.read_text()
    block = text[text.index("export const modules") : text.index("};")]
    return set(re.findall(r"^\s*(\w+):\s*\{name:", block, re.MULTILINE))


def test_module_registry_matches_app_rules_js():
    assert set(load()["modules"]) == app_module_ids()


def test_row_modules_are_known():
    known = set(load()["modules"])
    for row in load()["rows"]:
        if "module" in row:
            assert row["module"] in known, f"{row['clause']}: unknown module"


def test_modules_map_to_expected_clauses():
    by_clause = {r["clause"]: r.get("module") for r in load()["rows"]}
    assert by_clause["1910.178(n)(4)"] == "load"  # load blocks forward view
    assert by_clause["1910.303(g)(2)"] == "panel"  # open panel, live parts
    assert by_clause["1910.22(a)(1)"] is None


def test_modules_summary_lists_mapped_clauses_and_unmapped_modules():
    text = build.render_modules_summary(load())
    assert "| Load visibility | `load` | 1910.178(n)(4) |" in text
    assert "| Walkway watch | `zone` | None |" in text


# --- csv export -----------------------------------------------------------


def test_render_csv_has_one_record_per_row_with_joined_settings():
    data = load()
    records = list(csv.DictReader(io.StringIO(build.render_csv(data))))
    assert len(records) == len(data["rows"])
    assert list(records[0]) == list(build.CSV_FIELDS)
    first = data["rows"][0]
    assert records[0]["clause"] == first["clause"]
    assert records[0]["settings"] == ";".join(first["settings"])


def test_render_csv_round_trips_commas_and_quotes():
    data = {
        "rows": [
            {
                "pack": "OSHA",
                "standard": "29 CFR 1910",
                "clause": "x",
                "topic": "T",
                "settings": ["chem-lab"],
                "requirement": 'Mark "Exit", always.',
                "cue": "C",
            }
        ]
    }
    record = next(csv.DictReader(io.StringIO(build.render_csv(data))))
    assert record["requirement"] == 'Mark "Exit", always.'
    assert record["module"] == ""


def test_committed_csv_matches_generated_output():
    assert CSV_PATH.read_text() == build.render_csv(load()), (
        "data/regulations.csv is out of date. "
        "Run: uv run scripts/build_regulations_table.py"
    )


# --- generator ------------------------------------------------------------


def test_escape_cell_escapes_pipes_and_newlines():
    assert build.escape_cell("a|b\nc") == "a\\|b c"


def test_render_table_without_labels_has_four_columns():
    rows = [
        {"clause": "1910.22(c)", "topic": "T", "requirement": "R", "cue": "C"},
        {"clause": "1910.23(b)(8)", "topic": "T2", "requirement": "R2", "cue": "C2"},
    ]
    lines = build.render_table(rows).splitlines()
    assert lines[0] == "| Clause | Topic | Requirement | Violation cue |"
    assert lines[1] == "|---|---|---|---|"
    assert lines[2] == "| 1910.22(c) | T | R | C |"
    assert len(lines) == 2 + len(rows)


def test_render_table_with_labels_adds_settings_column():
    labels = {"chem-lab": "Chem lab", "pharma": "Pharma"}
    rows = [
        {
            "clause": "x",
            "topic": "T",
            "settings": ["chem-lab", "pharma"],
            "requirement": "R",
            "cue": "C",
        }
    ]
    lines = build.render_table(rows, labels).splitlines()
    assert lines[0] == "| Clause | Topic | Settings | Requirement | Violation cue |"
    assert lines[1] == "|---|---|---|---|---|"
    assert lines[2] == "| x | T | Chem lab, Pharma | R | C |"


def test_group_by_pack_keeps_file_order():
    rows = [
        {"pack": "OSHA", "clause": "a"},
        {"pack": "cGMP", "clause": "b"},
        {"pack": "OSHA", "clause": "c"},
    ]
    groups = build.group_by_pack(rows)
    assert [r["clause"] for r in groups["OSHA"]] == ["a", "c"]
    assert list(groups) == ["OSHA", "cGMP"]


def test_filter_by_setting_keeps_matching_rows_in_order():
    rows = [
        {"clause": "a", "settings": ["chem-lab", "pharma"]},
        {"clause": "b", "settings": ["construction"]},
        {"clause": "c", "settings": ["chem-lab"]},
    ]
    assert [r["clause"] for r in build.filter_by_setting(rows, "chem-lab")] == ["a", "c"]


def test_filter_by_setting_rejects_unknown_setting():
    with pytest.raises(ValueError):
        build.filter_by_setting(load()["rows"], "moon-base", known=set(load()["settings"]))


def test_main_reports_unknown_setting_without_traceback(capsys):
    assert build.main(["--setting", "moon-base"]) == 2
    assert "unknown setting: moon-base" in capsys.readouterr().err


def test_main_prints_one_setting_view(capsys):
    assert build.main(["--setting", "chem-lab"]) == 0
    out = capsys.readouterr().out
    assert "1910.1450(e)(3)(iii)" in out
    assert "1926.501(b)(1)" not in out  # construction only


def test_all_view_has_one_section_per_pack_and_counts():
    doc = build.render_document(load())
    for pack in PACKS:
        assert f"## {build.PACK_TITLES[pack]}" in doc
    assert f"{len(load()['rows'])} rules" in doc


def test_setting_view_has_one_section_per_setting_with_counts():
    data = load()
    doc = build.render_setting_document(data)
    for sid, info in data["settings"].items():
        expected = len(build.filter_by_setting(data["rows"], sid))
        assert f"## {info['label']} ({expected} rules)" in doc


def test_committed_all_doc_matches_generated_output():
    assert ALL_DOC_PATH.read_text() == build.render_document(load()), (
        "docs/regulations-table.md is out of date. "
        "Run: uv run scripts/build_regulations_table.py"
    )


def test_committed_setting_doc_matches_generated_output():
    assert SETTING_DOC_PATH.read_text() == build.render_setting_document(load()), (
        "docs/regulations-by-setting.md is out of date. "
        "Run: uv run scripts/build_regulations_table.py"
    )
