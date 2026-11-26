import json
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

import pymupdf as fitz
import pytest
from cyct_report.orders.adapters import adapters
from cyct_report.orders.extract import extract_pages
from cyct_report.orders.model import Fragment, Page, Requirement
from cyct_report.orders.pdf import inspect_pdf
from cyct_report.orders.validation import validate
from . import synthetic


def test_reference_resolution_and_calibrated_edition(tmp_path):
    doc = fitz.open()
    page = synthetic.page_in(doc)
    synthetic.write(page, 40, 30, "Scenario A")
    synthetic.write(page, 40, 60, "Section 4.2 Laminate assessment")
    synthetic.write(
        page,
        40,
        92,
        "Peel performance shall meet Table 3. Verify custody using Clause 4.9.",
    )
    synthetic.write(page, 40, 133, "Table 3 Synthetic laminate criteria, Type 14B-2")
    cols = [40, 255, 465, 605]
    synthetic.line(page, 157, cols, ["Property", "Condition", "Requirement", "Unit"])
    synthetic.line(
        page, 190, cols, ["Peal after immersion", "28 days at 80°C", "≥0.75", "N/mm"]
    )
    synthetic.write(page, 40, 243, "Section 4.3 Secondary coupon")
    synthetic.write(
        page,
        40,
        269,
        "The gauge shall satisfy Table 5. Inspect as specified in Section 4.2.",
    )
    synthetic.write(page, 40, 307, "Table 5 Abbreviations")
    synthetic.write(page, 40, 330, "The mark shall be legible.")
    path = synthetic.store_file(doc, tmp_path / "reference.pdf")
    pages, *_ = inspect_pdf(path)
    rows = validate(extract_pages(pages), pages, reference_edition="ISO 21809-3:2016")
    direct = next(r for r in rows if r.item == "Peal after immersion")
    assert "Peal" in direct.verbatim and not direct.standard
    assert direct.reference[0]["edition_source"] == "reviewer_selection"
    assert {"duration_difference", "quantity_difference"} <= {
        a["code"] for a in direct.alerts
    }
    pointer = next(r for r in rows if "custody" in r.verbatim)
    link = next(l for l in pointer.links if l["label"] == "Table 3")
    assert (
        link["targets"] == [direct.id]
        and link["resolved_fields"][0]["requirement"] == "≥0.75"
    )
    assert link["tier"] == "same_doc_cross_ref"
    assert any(
        a["code"] == "unresolved_reference" and "4.9" in a["message"]
        for a in pointer.alerts
    )
    wrong = next(r for r in rows if "Table 5." in r.verbatim)
    assert any(a["code"] == "reference_mismatch" for a in wrong.alerts)
    assert any(
        l["label"] == "Section 4.2" and pointer.id in l["targets"] for l in wrong.links
    )
    no_edition = next(
        r for r in validate(extract_pages(pages), pages) if r.item == direct.item
    )
    assert not no_edition.reference and "reference_edition" in {
        a["code"] for a in no_edition.alerts
    }


def test_type_18a_and_annex_a_remain_read_only_reference(tmp_path):
    doc = fitz.open()
    for i in range(2):
        page = synthetic.page_in(doc)
        if not i:
            synthetic.write(page, 40, 30, "ISO 21809-3:2016 / Type 18A")
            synthetic.write(page, 40, 62, "Table 1 Impact comparison")
            cols = [40, 250, 442, 610]
            synthetic.line(
                page, 100, cols, ["Property", "Condition", "Requirement", "Unit"]
            )
            synthetic.line(page, 140, cols, ["Impact coupon", "23°C", ">3", "J"])
        else:
            synthetic.write(page, 40, 30, "Scenario B")
            synthetic.write(page, 40, 60, "ISO 21809-3:2016 / Type 14B-2")
            synthetic.write(page, 40, 91, "Minimum Frequency")
            cols = [40, 245, 480, 590, 698]
            synthetic.line(
                page, 130, cols, ["Activity", "Method", "PQT", "PPT", "Production"]
            )
            synthetic.line(
                page,
                169,
                cols,
                ["Impact evaluation", "Annex D", "7 coupons", "By Agreement", "-"],
            )
    pages, *_ = inspect_pdf(synthetic.store_file(doc, tmp_path / "iso.pdf"))
    rows = validate(extract_pages(pages), pages)
    impact = next(r for r in rows if r.item == "Impact coupon")
    assert (
        impact.reference[0]["section"] == "Table 30"
        and impact.reference[0]["limit"] == "≥3"
    )
    assert impact.requirement == ">3" and impact.unit == "J"
    assert {"quantity_difference", "strict_operator"} <= {
        a["code"] for a in impact.alerts
    }
    matrix = next(r for r in rows if r.channel == "frequency")
    assert (
        matrix.pqt == "7 coupons"
        and matrix.reference[0]["section"] == "Annex A / Table A.1"
    )
    assert (
        matrix.reference[0]["pqt"] == "3 joints"
        and matrix.reference[0]["tier"] == "external_standard_ref"
    )


def test_weather_table_does_not_hide_normative_paragraph_and_square_root(tmp_path):
    doc = fitz.open()
    p = synthetic.page_in(doc)
    synthetic.write(p, 40, 45, "Table 1 Weather observations")
    for y, t, v in [
        (89, "Month", "Value"),
        (121, "Vernal period", "72"),
        (153, "Dry period", "63"),
    ]:
        synthetic.line(p, y, [40, 285], [t, v])
    synthetic.write(p, 40, 201, "Section 6.1 Field verification")
    clauses = [
        "The field inspector shall use 3.1 √t to check the witness seam.",
        "Minimum overlap shall be ≥26 mm after assembly.",
        "Store coupons below 31°C for at most 6 months.",
        "Warranty inspections must occur every 2 months.",
    ]
    for i, t in enumerate(clauses):
        synthetic.write(p, 40, 229 + 35 * i, t)
    pages, *_ = inspect_pdf(synthetic.store_file(doc, tmp_path / "weather.pdf"))
    rows = validate(extract_pages(pages), pages)
    assert all(any(t in r.verbatim for r in rows) for t in clauses)
    overlap = next(r for r in rows if "overlap" in r.item)
    assert overlap.requirement == "≥26 mm" and overlap.unit == "mm"
    assert (
        next(r for r in rows if "Warranty" in r.verbatim).frequency == "every 2 months"
    )


def test_physical_row_check_rejects_an_identical_value_on_another_row():
    fragments = [
        Fragment(f"1.{i}", 1, [x, y, x + 0.1, y + 0.02], text, text, row=row)
        for i, (x, y, text, row) in enumerate(
            [
                (0.1, 0.20, "Pad strength", 3),
                (0.4, 0.20, "16°C", 3),
                (0.6, 0.20, "≥6", 3),
                (0.1, 0.40, "Another pad", 8),
                (0.6, 0.40, "≥6", 8),
            ],
            1,
        )
    ]
    pg = Page(1, 600, 700, "native", fragments, [[0.08, 0.33, 0.8, 0.33]])
    r = Requirement(
        "R", "performance", item="Pad strength", condition="16°C", requirement="≥6"
    )
    r.bind("item", fragments[:1])
    r.bind("condition", fragments[1:2])
    r.bind("requirement", fragments[-1:])
    validate([r], [pg])
    assert any(a["code"] == "row_alignment" and a["level"] == "RED" for a in r.alerts)


def test_two_openai_slots_validate_real_http_contract_on_loopback(
    tmp_path, monkeypatch
):
    requests = []

    class Mock(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body, self.headers["Authorization"]))
            prompt = body["messages"][1]["content"][0]["text"]
            answer = (
                {"words": [{"text": "Fixture", "box": [0.1, 0.1, 0.2, 0.2]}]}
                if '"words"' in prompt
                else {"rows": [{"item": ["1.1"], "requirement": ["1.2"]}]}
            )
            result = json.dumps(
                {"choices": [{"message": {"content": json.dumps(answer)}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(result)))
            self.end_headers()
            self.wfile.write(result)

    with HTTPServer(("127.0.0.1", 0), Mock) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            slot = dict(
                provider="openai",
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                model="synthetic-vision",
            )
            file = tmp_path / "config.yaml"
            file.write_text(json.dumps({"ocr_parser": slot, "llm_extractor": slot}))
            monkeypatch.setenv("ORDER_VISION_KEY", "fixture-only-value")
            ocr, extractor = adapters(file)
            assert ocr.recognize(b"synthetic", 1, 600, 700)[0][0] == "Fixture"
            p = Page(
                1,
                600,
                700,
                "native",
                [
                    Fragment("1.1", 1, [0.1, 0.1, 0.2, 0.2], "Test tile", row=1),
                    Fragment("1.2", 1, [0.6, 0.6, 0.7, 0.7], "≥3", row=4),
                ],
            )
            drafts = extractor.extract(b"synthetic", p)
            rows = validate(extract_pages([p], {1: drafts + [{"item": ["9.9"]}]}), [p])
            suggestion = next(r for r in rows if r.channel == "vision")
            assert suggestion.requirement == "≥3" and any(
                a["code"] == "row_alignment" for a in suggestion.alerts
            )
        finally:
            server.shutdown()
            worker.join()
    assert len(requests) == 2
    assert all(
        path == "/v1/chat/completions"
        and body["temperature"] == 0
        and auth == "Bearer fixture-only-value"
        and body["messages"][1]["content"][1]["type"] == "image_url"
        for path, body, auth in requests
    )
    file.write_text(
        'ocr_parser: {provider: openai, base_url: "https://fixture.invalid/v1", model: fixture}'
    )
    with pytest.raises(ValueError, match="allow_external_pages"):
        adapters(file)


def test_long_source_cell_can_be_reassembled_without_losing_a_character():
    from io import BytesIO
    from openpyxl import Workbook, load_workbook
    from cyct_report.orders.export import worksheet

    book = Workbook()
    original = ("=SYNTHETIC √ " * 3400) + "finish"
    ws = worksheet(
        book,
        "Synthetic",
        ["Customer wording", "Actual Test Result"],
        [[original, None]],
        editable=["Actual Test Result"],
    )
    buf = BytesIO()
    book.save(buf)
    sheet = load_workbook(BytesIO(buf.getvalue()))[ws.title]
    columns = [c.column for c in sheet[1] if c.value.startswith("Customer wording")]
    assert (
        len(columns) > 1
        and "".join(sheet.cell(2, j).value for j in columns) == original
    )
    assert all(
        sheet.cell(2, j).protection.locked and sheet.cell(2, j).data_type == "s"
        for j in columns
    )
    assert sheet["B2"].value is None
