from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys

import openpyxl
import pymupdf as fitz
import pytest

from cyct_report import paths
from cyct_report.orders.export import files_for, MANUAL
from cyct_report.orders.extract import extract_pages
from cyct_report.orders.pdf import inspect_pdf, preview
from cyct_report.orders.store import Conflict, ReviewRequired, Store
from cyct_report.orders.validation import validate
from . import synthetic


def extracted(path, ocr=None):
    pages, _, supplemental = inspect_pdf(path, ocr)
    return validate(extract_pages(pages, supplemental), pages), pages


def codes(row):
    return {a["code"]: a["level"] for a in row.alerts}


def test_immersion_duration_and_physical_quantity_are_independent(tmp_path):
    rows, _ = extracted(synthetic.immersion(tmp_path / "immersion.pdf"))
    peel = next(r for r in rows if r.item == "Peel after immersion")
    assert all(t in peel.verbatim for t in ("28 days", "≥0.75", "N/mm"))
    assert (peel.requirement, peel.unit, peel.quantity_kind) == (
        "≥0.75",
        "N/mm",
        "force_per_length",
    )
    assert peel.test_temp == "80°C / 23°C" and peel.conditioning == "28 days"
    assert peel.condition == "28 days in water at 80°C; test at 23°C"
    assert (
        peel.source_pages == [1]
        and peel.bindings["condition"] != peel.bindings["requirement"]
    )
    assert (
        codes(peel)["duration_difference"]
        == codes(peel)["quantity_difference"]
        == "RED"
    )
    assert peel.clarification_suggestions
    assert {ref["tier"] for ref in peel.reference} == {"external_standard_ref"}
    assert (
        peel.reference[0]["days"] == 100 and peel.reference[0]["section"] == "Table 17"
    )
    execution = " ".join(
        [peel.item, peel.condition, peel.requirement, peel.unit, peel.method]
    )
    assert "100" not in execution and "P100/P0" not in execution
    aged = next(r for r in rows if r.item == "Heat aged elongation")
    assert aged.quantity_kind == "ratio" and aged.reference[0]["limit"] == "≥0.75"
    assert aged.coating_type == "14B-2" and "typed_limit_difference" not in codes(aged)


def test_two_scenarios_all_three_stages_and_escalation(tmp_path):
    rows, _ = extracted(synthetic.matrix(tmp_path / "matrix.pdf"))
    matrix = [r for r in rows if r.channel == "frequency"]
    assert Counter(r.scenario for r in matrix) == {"Scenario A": 22, "Scenario B": 22}
    for scenario in ("Scenario A", "Scenario B"):
        scoped = [r for r in matrix if r.scenario == scenario]
        for i, r in enumerate(scoped, 1):
            assert r.item == (
                "Surface roughness" if i == 3 else f"Coupon feature {i:02d}"
            )
            assert (r.pqt, r.ppt, r.production) == (
                "4 coupons",
                "By Agreement" if i % 2 else "-",
                "Each lot",
            )
            assert r.phase_roles["ppt"] == (
                "by_agreement" if i % 2 else "dash_not_listed"
            )
            assert all(
                r.bindings[k] for k in ("item", "pqt", "ppt", "production", "method")
            )
            assert r.method == (
                "ISO 8501-1"
                if (scenario, i) == ("Scenario A", 3)
                else "EN 12068"
                if scenario == "Scenario B" and i > 12
                else "ISO 21809-3"
            )
    third = matrix[2]
    assert codes(third)["method_conflict"] == "RED" and "ISO 8501-1" in third.verbatim
    assert third.links[0]["pages"] == [1] and third.links[0]["target"]
    assert not any(
        "method_conflict" in codes(r) for r in matrix if r.scenario == "Scenario B"
    )
    escalation = next(r for r in rows if "trial strips fail" in r.verbatim)
    assert " ".join(escalation.verbatim.split()) == synthetic.ESCALATION
    assert (
        escalation.sampling_basis == "≥10% of the trial strips"
        and escalation.failure_action == escalation.verbatim
    )
    assert synthetic.SUPPLIER in [r.verbatim for r in rows if r.channel == "prose"]

    store = Store(tmp_path / "matrix-store")
    doc = store.import_pdf(tmp_path / "matrix.pdf", "Fixture", "Matrix", "A")["id"]
    for row in store.records(doc):
        store.review(
            doc,
            row["id"],
            version=0,
            action="confirm",
            user="Synthetic engineer",
            checked=True,
            note="Verified against the generated fixture.",
        )
    exported = files_for(store.snapshot("Fixture"))
    assert len(json.loads(exported["confirmed.json"])["frequencies"]) == 44
    sheet = openpyxl.load_workbook(BytesIO(exported["confirmed.xlsx"]))["Frequencies"]
    columns = {c.value: c.column for c in sheet[1]}
    assert sheet.max_row == 45
    assert [sheet.cell(2, columns[k]).value for k in ("PQT", "PPT", "Production")] == [
        "4 coupons",
        "By Agreement",
        "Each lot",
    ]


def test_scan_continuation_role_preservation_and_cell_specific_note(tmp_path):
    path, stub = synthetic.across_pages(tmp_path / "scanned.pdf")
    rows, pages = extracted(path, stub)
    assert [p.carrier for p in pages] == [
        "native",
        "native",
        "scan",
    ] and stub.calls == [3]
    with fitz.open(path) as pdf:
        assert not pdf[2].get_text().strip()
        assert fitz.Pixmap(preview(pdf[2])).width == 2100
    entries = {r.item: r for r in rows if r.channel == "performance"}
    assert len(entries) == 10
    assert (
        entries["Coupon seal"].source_pages == [1, 2]
        and codes(entries["Coupon seal"])["typical_outside"] == "RED"
    )
    split = entries["Joint offset"]
    assert (split.source_pages, split.requirement, split.unit) == ([2, 3], "≥4.2", "mm")
    assert split.bindings["item"][0].startswith("2.") and split.bindings["requirement"][
        0
    ].startswith("3.")
    assert (
        entries["Elastic index"].requirement,
        entries["Elastic index"].value_role,
    ) == ("", "typical_only")
    pressure = entries["Test load"]
    assert (
        pressure.value_role == "test_condition"
        and not pressure.requirement
        and "10 N/mm²" in pressure.condition
    )
    assert (
        entries["Residual thickness"].requirement == "≥0.6"
        and entries["Residual thickness"].unit == "mm"
    )
    assert (entries["Batch label"].value_role, entries["Batch label"].requirement) == (
        "tba",
        "TBA",
    )
    assert (entries["Band width"].value_role, entries["Band width"].requirement) == (
        "by_vendor",
        "By Vendor",
    )
    one, two = entries["Adhesion pad one"], entries["Adhesion pad two"]
    assert one.notes[0]["field"] == "requirement" and one.notes[0]["marker"] == "a"
    assert one.notes[0]["evidence"][0].startswith("3.") and not two.notes
    assert "10^13" == entries["Insulator"].requirement and "visual_check" in codes(
        entries["Insulator"]
    )
    assert any(
        "√t" in r.verbatim and codes(r).get("visual_check") == "CHECK" for r in rows
    )


def protected_files():
    candidates = (
        list(paths.STANDARDS_DIR.glob("*.json"))
        + list(paths.TEMPLATES_DIR.glob("*"))
        + [paths.APP_DIR / "data" / "custom_templates.json"]
    )
    return {
        p: sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        for p in candidates
    }


def cli(db, *args, success=True):
    result = subprocess.run(
        [
            sys.executable,
            str(paths.APP_DIR / "tools" / "order_review.py"),
            "--data-dir",
            str(db),
            *map(str, args),
        ],
        capture_output=True,
        text=True,
        encoding="utf8",
    )
    if success:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0
    return result.stderr


def test_cli_review_export_blank_cells_and_preset_isolation(tmp_path):
    before = protected_files()
    db = tmp_path / "private"
    path = synthetic.workflow(tmp_path / "order.pdf")
    doc = cli(
        db,
        "import",
        path,
        "--order",
        "SYN-ONE",
        "--number",
        "LAB-EXAMPLE",
        "--revision",
        "A",
    )["id"]
    width, field, tba = cli(db, "show", doc)
    assert width["status"] == tba["status"] == "candidate"
    assert cli(db, "export", "SYN-ONE", tmp_path / "out", success=False)
    cli(
        db,
        "review",
        doc,
        width["id"],
        "edit",
        "--user",
        "Synthetic reviewer",
        "--version",
        0,
        "--changes",
        json.dumps({"item": "Cooling coupon width"}),
        "--note",
        "Reviewed the original row label.",
    )
    cli(
        db,
        "review",
        doc,
        width["id"],
        "confirm",
        "--user",
        "Synthetic reviewer",
        "--version",
        1,
        "--checked",
        "--note",
        "Verified width on page 1.",
    )
    cli(
        db,
        "review",
        doc,
        field["id"],
        "confirm",
        "--user",
        "Synthetic reviewer",
        "--version",
        0,
        "--checked",
        "--note",
        "Checked field conditions.",
    )
    cli(
        db,
        "review",
        doc,
        tba["id"],
        "clarify",
        "--user",
        "Synthetic reviewer",
        "--version",
        0,
        "--question",
        "Which pressure applies?",
        "--respondent",
        "Fixture owner",
    )
    dest = Path(cli(db, "export", "SYN-ONE", tmp_path / "out"))
    snap = json.loads((dest / "confirmed.json").read_bytes())
    assert (
        snap["confirmed_rev"] == 1
        and len(snap["requirements"]) == 2
        and len(snap["clarifications"]) == 1
    )
    assert (
        snap["clarifications"][0]["requirement"] == "TBA"
        and snap["clarifications"][0]["respondent"] == "Fixture owner"
    )
    width_out = snap["requirements"][0]
    assert (
        width_out["verbatim"] == width["verbatim"]
        and width_out["item"] == "Cooling coupon width"
    )
    assert width_out["regions"] and all(
        f["page"] == 1 and len(f["box"]) == 4 for f in width_out["regions"]
    )
    assert (
        width_out["file_sha256"] == sha256(path.read_bytes()).hexdigest()
        and width_out["doc_rev"] == "A"
    )
    assert (
        snap["audit"][0]["detail"]["before"] == {"item": "Sample width"}
        and snap["audit"][0]["user"] == "Synthetic reviewer"
    )
    assert cli(db, "export", "SYN-ONE", tmp_path / "out") == str(dest)
    lab = openpyxl.load_workbook(dest / "laboratory.xlsx")
    assert lab.sheetnames == ["Laboratory", "Field inspection", "Clarifications"]
    for ws in lab:
        headers = {c.value: c.column for c in ws[1]}
        assert ws.protection.sheet and ws.max_row == 2
        assert ws.cell(2, headers["Customer wording"]).protection.locked
        assert ws.cell(2, headers["PDF pages"]).hyperlink.location.startswith(
            "'Evidence'!"
        )
        for name in MANUAL:
            cell = ws.cell(2, headers[name])
            assert (
                cell.value is None
                and not cell.protection.locked
                and cell.fill.fgColor.rgb.endswith("FFF1B8")
            )
    assert lab["Laboratory"].cell(2, headers["Specified requirement"]).value == "≥8"
    assert lab["Laboratory"].cell(2, headers["Test condition"]).value == "After cooling"
    full = openpyxl.load_workbook(dest / "confirmed.xlsx")
    assert set(full.sheetnames) == {
        "Order",
        "Documents",
        "Evidence",
        "Confirmed",
        "Frequencies",
        "References",
        "Audit",
        "Clarifications",
    }
    wh = {c.value: c.column for c in full["Confirmed"][1]}
    assert (
        full["Confirmed"].protection.sheet
        and full["Confirmed"].cell(2, wh["Customer wording"]).value == width["verbatim"]
    )
    assert (
        full["Confirmed"]
        .cell(2, wh["PDF pages"])
        .hyperlink.location.startswith("'Evidence'!")
    )
    assert before == protected_files()


def test_idempotence_revision_history_duplicate_alias_and_stale_edit(tmp_path):
    st = Store(tmp_path / "private")
    file = synthetic.workflow(tmp_path / "one.pdf")
    doc = st.import_pdf(file, "Order", "Synthetic", "A")
    assert st.import_pdf(file, "Order", "Synthetic", "A") == doc
    with fitz.open(file) as pdf:
        pdf.set_metadata({"title": "Alternate synthetic title"})
        pdf.save(tmp_path / "alias.pdf")
    alias = st.import_pdf(tmp_path / "alias.pdf", "Order", "Copy", "A")
    assert alias["alias_of"] == doc["id"] and alias["sha256"] != doc["sha256"]
    width, field, tba = st.records(alias["id"])
    st.review(
        alias["id"],
        width["id"],
        version=0,
        action="confirm",
        user="Reviewer",
        checked=True,
        note="Original inspected.",
    )
    assert st.records(doc["id"])[0]["status"] == "confirmed"
    with pytest.raises(Conflict):
        st.review(doc["id"], width["id"], version=0, action="edit", user="Reviewer")
    with pytest.raises(ReviewRequired):
        st.review(doc["id"], tba["id"], version=0, action="confirm", user="Reviewer")
    with pytest.raises(ValueError):
        st.review(
            doc["id"],
            tba["id"],
            version=0,
            action="confirm",
            user="Reviewer",
            changes={"requirement": "17"},
            note="Changed",
        )
    st.review(
        doc["id"],
        tba["id"],
        version=0,
        action="clarify",
        user="Reviewer",
        question="Supply value?",
        respondent="Author",
    )
    first = st.snapshot("Order")
    assert (
        len(first["requirements"]) == 1
        and first["omitted_pending"] == 1
        and first["confirmed_rev"] == 1
    )
    st.review(doc["id"], field["id"], version=0, action="confirm", user="Reviewer")
    assert st.snapshot("Order")["confirmed_rev"] == 2
    with st.connection() as db:
        assert (
            json.loads(
                db.execute("SELECT detail FROM snapshots WHERE revision=1").fetchone()[
                    0
                ]
            )
            == first
        )
    new = st.import_pdf(file, "Order", "Synthetic", "B")
    assert st.records(new["id"])[0]["status"] == "candidate"
    independent = st.import_pdf(file, "Another order", "Synthetic", "A")
    assert (
        not independent["alias_of"] and st.records(independent["id"])[0]["version"] == 0
    )


def test_scan_without_ocr_is_blocked_and_can_be_transcribed(tmp_path):
    path, _ = synthetic.across_pages(tmp_path / "scan.pdf")
    st = Store(tmp_path / "local")
    doc = st.import_pdf(path, "Synthetic", "Scan", "A", providers=(None, None))["id"]
    coverage = next(r for r in st.records(doc) if r["channel"] == "coverage")
    with pytest.raises(ReviewRequired):
        st.review(
            doc,
            coverage["id"],
            version=0,
            action="confirm",
            user="Reviewer",
            checked=True,
            note="Visited",
        )
    rid = st.add_manual(
        doc,
        page=3,
        box=[0.04, 0.18, 0.65, 0.27],
        text="3.1 The gauge voltage shall follow 2.2 √t on the trial strip.",
        user="Reviewer",
    )
    st.review(
        doc,
        rid,
        version=0,
        action="confirm",
        user="Reviewer",
        checked=True,
        note="Transcribed from pixels.",
    )
    st.review(
        doc,
        coverage["id"],
        version=0,
        action="confirm",
        user="Reviewer",
        checked=True,
        note="All remaining regions reviewed.",
    )


def test_export_keeps_leading_equals_literal(tmp_path):
    st = Store(tmp_path / "local")
    doc = st.import_pdf(
        synthetic.workflow(tmp_path / "book.pdf"),
        "Synthetic",
        "Formula-looking text",
        "A",
    )["id"]
    for r in st.records(doc):
        st.review(
            doc,
            r["id"],
            version=0,
            action="clarify",
            user="Reviewer",
            question="=SYNTHETIC()",
            respondent="Fixture owner",
        )
    book = openpyxl.load_workbook(
        BytesIO(files_for(st.snapshot("Synthetic"))["confirmed.xlsx"])
    )
    sheet = book["Clarifications"]
    j = [c.value for c in sheet[1]].index("Question") + 1
    assert (
        sheet.cell(2, j).value == "=SYNTHETIC()" and sheet.cell(2, j).data_type == "s"
    )
