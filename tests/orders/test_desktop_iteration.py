"""Regression cases use generated documents and local doubles only."""

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import openpyxl
import pymupdf as fitz
import pytest
from PIL import Image

from cyct_report.orders.adapters import adapters, response_json
from cyct_report.orders.api_config import (
    authorization,
    desktop_config,
    endpoint,
    load_settings,
    save_settings,
)
from cyct_report.orders.export import files_for, MANUAL
from cyct_report.orders.extract import extract_pages
from cyct_report.orders.model import Page
from cyct_report.orders.pdf import inspect_pdf, selected_pages, visual_png
from cyct_report.orders.store import Store, ReviewRequired, Conflict
from cyct_report.orders.validation import validate
from . import synthetic
from .desktop_fixture import SCAN_QUOTE, SCAN_ROW


def coupon_table(path, typed, rows):
    doc = fitz.open()
    pg = synthetic.page_in(doc)
    if typed:
        synthetic.write(pg, 40, 42, "ISO 21809-3:2016 / Type 14B-2")
    synthetic.write(pg, 40, 95, "Table 23 Coupon checks")
    x = [40, 300, 470, 650]
    synthetic.line(pg, 130, x, ["Item", "Test condition", "Requirement", "Unit"])
    for i, row in enumerate(rows):
        synthetic.line(pg, 163 + i * 35, x, row)
    return synthetic.store_file(doc, path)


def requirements(file):
    pages, _, drafts = inspect_pdf(file)
    return [
        r
        for r in validate(extract_pages(pages, drafts), pages)
        if r.channel == "performance"
    ]


def codes(row):
    return {a["code"]: a["level"] for a in row.alerts}


def test_explicit_warm_temperature_selects_the_hot_row(tmp_path):
    rows = requirements(
        coupon_table(
            tmp_path / "warm.pdf",
            True,
            [
                ["Peel strength", "23°C", "≥5", "N/mm"],
                ["Peel strength", "80°C", "≥2", "N/mm"],
                ["Peel strength", "After conditioning", "≥7", "N/mm"],
            ],
        )
    )
    assert len(rows) == 3
    assert (
        "23" in rows[0].reference[0]["temp"]
        and "max" in rows[1].reference[0]["temp"].lower()
    )
    assert rows[0].reference[0]["limit"] != rows[1].reference[0]["limit"]
    assert "80°C" in rows[1].condition and rows[1].requirement == "≥2"
    assert not rows[2].reference and "missing_temperature" in codes(rows[2])


@pytest.mark.parametrize(
    "item,unit,flag,level",
    [
        ("Peel strength", "N/cm", "peel_unit_scale", "YELLOW"),
        ("Peal strength", "N/m", "peel_unit_scale", "YELLOW"),
        ("Peel strength", "N/mm²", "peel_area_unit", "RED"),
        ("Impact resistance", "J", "impact_energy_basis", "YELLOW"),
        ("Impact resistance", "J/mm", "impact_energy_basis", "YELLOW"),
        ("Indentation", "mm", "missing_temperature", "YELLOW"),
    ],
)
def test_units_and_missing_temperature_without_type_or_edition(
    tmp_path, item, unit, flag, level
):
    [row] = requirements(
        coupon_table(tmp_path / "units.pdf", False, [[item, "Dry", "8", unit]])
    )
    assert codes(row)[flag] == level and row.unit == unit and not row.reference


def test_exclude_reason_reversible_audited_and_lab_self_contained(tmp_path):
    file = synthetic.workflow(tmp_path / "all.pdf")
    s = Store(tmp_path / "records")
    doc = s.import_pdf(file, "sample", "demo", "B")["id"]
    first, second, third = s.records(doc)
    with pytest.raises(ValueError, match="reason"):
        s.review(doc, first["id"], version=0, action="exclude", user="Demo")
    with pytest.raises(ReviewRequired):
        s.snapshot("sample")
    s.review(
        doc,
        first["id"],
        version=0,
        action="exclude",
        user="Demo",
        note="Not a lab activity in this order.",
    )
    with pytest.raises(Conflict):
        s.review(doc, first["id"], version=0, action="edit", user="Demo")
    s.review(doc, second["id"], version=0, action="confirm", user="Demo")
    s.review(
        doc,
        third["id"],
        version=0,
        action="clarify",
        user="Demo",
        question="What is the agreed pressure?",
        respondent="Design",
    )
    snap = s.snapshot("sample")
    assert [r["id"] for r in snap["excluded"]] == [first["id"]]
    assert (
        s.audit(doc, first["id"])[0]["detail"]["note"]
        == "Not a lab activity in this order."
    )
    result = files_for(snap)
    wb = openpyxl.load_workbook(BytesIO(result["laboratory.xlsx"]))
    for ws in wb:
        head = [c.value for c in ws[1]]
        assert len(head) <= 17 and not set(head) & {
            "ID",
            "Source SHA-256",
            "Stage value roles",
            "Field sources",
        }
        for row in list(ws.rows)[1:]:
            assert row[head.index("Inspection activity")].value != first["item"]
            assert "demo (B)" in row[head.index("PDF pages")].value
            assert row[head.index("Customer wording")].protection.locked
            assert all(
                row[head.index(k)].value is None
                and not row[head.index(k)].protection.locked
                for k in MANUAL
            )
    with ZipFile(BytesIO(result["laboratory.xlsx"])) as z:
        assert all(
            b'TargetMode="External"' not in z.read(n)
            for n in z.namelist()
            if n.endswith(".rels")
        )
    s.review(doc, first["id"], version=1, action="edit", user="Second", note="Reopened")
    with pytest.raises(ReviewRequired):
        s.snapshot("sample")
    assert s.record(doc, first["id"])["verbatim"] == first["verbatim"]


@pytest.mark.parametrize(
    "address,expected",
    [
        ("192.168.5.7:8042", "http://192.168.5.7:8042/v1/chat/completions"),
        ("http://10.5.4.3:8080/custom", "http://10.5.4.3:8080/custom/chat/completions"),
        ("[fd00::23]:9090", "http://[fd00::23]:9090/v1/chat/completions"),
        (
            "https://service.invalid/bridge/chat/completions",
            "https://service.invalid/bridge/chat/completions",
        ),
    ],
)
def test_freely_configurable_endpoints(address, expected):
    assert endpoint(address) == expected
    cfg = {
        "enabled": True,
        "base_url": address,
        "model": "fixture",
        "allow_external_pages": True,
    }
    _, client = adapters(desktop_config(cfg))
    assert client.url == expected
    cfg["allow_external_pages"] = False
    with pytest.raises(ValueError, match="allow_external_pages"):
        adapters(desktop_config(cfg))


def test_private_config_auth_and_fenced_json(tmp_path):
    cfg = {
        "enabled": True,
        "base_url": "http://127.0.0.1:9211",
        "model": "offline-stub",
        "auth_header": "X-Model",
        "auth_prefix": "",
        "api_key": "synthetic-token",
    }
    path = tmp_path / "private" / "api.json"
    save_settings(path, cfg)
    assert load_settings(path) == cfg and authorization(cfg) == {
        "X-Model": "synthetic-token"
    }
    import os

    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError):
        endpoint("http://93.184.216.34:9080")
    fence = chr(96) * 3
    assert response_json(fence + "json\n" + '{"rows": []}' + "\n" + fence) == {
        "rows": []
    }
    with pytest.raises(ValueError):
        response_json(fence + 'json\n{"rows": [' + fence)
    with pytest.raises(ValueError):
        authorization(dict(cfg, auth_header="X-Bad\r\nAnother"))


def test_native_page_screening_and_isolated_api_failures(tmp_path):
    doc = fitz.open()
    for text in [
        "Cover sheet",
        "Table of contents",
        "Revision history",
        "4.1 Coupon width shall exceed 4 mm.",
        "5.1 Coupon edges shall be dry.",
    ]:
        pg = synthetic.page_in(doc)
        synthetic.write(pg, 40, 70, text)
    path = synthetic.store_file(doc, tmp_path / "selection.pdf")

    class Visual:
        def __init__(self):
            self.calls = []

        def extract(self, png, page):
            self.calls.append(page.number)
            with Image.open(BytesIO(png)) as img:
                img.load()
                assert img.width > 1000
            if page.number == 4:
                raise ValueError("truncated response")
            return []

    model = Visual()
    pages, _, supplement = inspect_pdf(path, vision=model)
    assert model.calls == [4, 5] and pages[3].issue and not pages[4].issue
    assert any(
        r.channel == "coverage" and r.source_pages == [4]
        for r in extract_pages(pages, supplement)
    )
    model.calls.clear()
    inspect_pdf(path, vision=model, vision_pages="2")
    assert model.calls == [2]
    with pytest.raises(ValueError):
        selected_pages("4-7", 5)


def test_image_only_context_notes_cross_reference_and_exact_field_binding():
    pages = [Page(i, 600, 800, "scan", []) for i in range(1, 3)]
    header = lambda text: dict(kind="heading", quote=text)

    def draft(label, crit, **kw):
        return dict(item=label, requirement=crit, quote=label + " | " + crit, **kw)

    first = draft("First coupon", "≥11", markers={"requirement": "a"})
    first["quote"] += "ᵃ"
    second = draft("Second coupon", "≥12")
    note = "(a) Only the first coupon is immersed."
    rows = validate(
        extract_pages(
            pages,
            {
                1: [
                    header("2.2 Coupon checks"),
                    header("Scenario Bay"),
                    header("Component: Pad"),
                    header("Table 77 Coupon limits"),
                    first,
                    second,
                    dict(kind="footnote", quote=note),
                ],
                2: [
                    header("3.1 Finishing checks"),
                    draft("Test per Table 77", "≥4"),
                    dict(
                        quote="Gauge index Typical 8",
                        item="Gauge index",
                        requirement="8",
                    ),
                    dict(quote="Peal mark | ≥3", item="Peal mark", requirement="≥9"),
                ],
            },
        ),
        pages,
    )
    by = {r.item: r for r in rows}
    assert (
        by["First coupon"].notes[0]["field"] == "requirement"
        and not by["Second coupon"].notes
    )
    assert (
        by["First coupon"].component == "Pad"
        and by["First coupon"].scenario == "Scenario Bay"
    )
    assert by["Test per Table 77"].links[0]["pages"] == [1]
    assert by["Gauge index"].requirement == "" and by["Gauge index"].typical == "8"
    assert by["Peal mark"].requirement == "" and "unverified_field" in codes(
        by["Peal mark"]
    )


def test_regionless_scan_and_no_local_ocr(tmp_path):
    src = fitz.open()
    pg = synthetic.page_in(src)
    synthetic.write(pg, 40, 100, SCAN_QUOTE)
    pdf = fitz.open()
    p = synthetic.page_in(pdf)
    p.insert_image(p.rect, stream=pg.get_pixmap().tobytes("png"))
    src.close()
    file = synthetic.store_file(pdf, tmp_path / "raster.pdf")

    class V:
        def extract(self, png, page):
            return [{k: v for k, v in SCAN_ROW.items() if k != "box"}]

    pages, _, drafts = inspect_pdf(file, vision=V())
    assert not drafts and pages[0].issue
    pages, _, drafts = inspect_pdf(file, vision=V(), vision_pages="1")
    [r] = extract_pages(pages, drafts)
    assert r.requirement == "≥4.7" and r.verbatim == SCAN_QUOTE
    assert pages[0].fragments[
        -1
    ].origin == "vision_page" and "visual_transcription" in codes(r)


def test_banded_png_matches_original_color_render():
    with fitz.open() as doc:
        page = doc.new_page(width=591.7, height=831.1)
        page.draw_rect((90, 97, 333, 601), fill=(0.1, 0.6, 0.2), color=(0.1, 0.6, 0.2))
        expected = Image.open(BytesIO(page.get_pixmap(dpi=160).tobytes("png")))
        actual = Image.open(BytesIO(visual_png(page)))
        assert actual.size == expected.size and actual.tobytes() == expected.tobytes()


def test_explicit_heat_maps_to_table30_tmax_without_changing_order(tmp_path):
    doc = fitz.open()
    pg = synthetic.page_in(doc)
    synthetic.write(pg, 40, 42, "ISO 21809-3:2016 / Type 18A")
    synthetic.write(pg, 40, 95, "Table 7 Fixture checks")
    x = [40, 300, 470, 650]
    synthetic.line(pg, 130, x, ["Item", "Test condition", "Requirement", "Unit"])
    synthetic.line(pg, 168, x, ["Cathodic disbondment", "78°C", "≤11", "mm"])
    [row] = requirements(synthetic.store_file(doc, tmp_path / "table30.pdf"))
    assert (
        row.reference[0]["section"] == "Table 30" and row.reference[0]["temp"] == "Tmax"
    )
    assert "reference_temperature" in codes(row) and row.requirement == "≤11"


def test_visually_recovered_comparator_keeps_local_reading_and_flags_both(tmp_path):
    pages, _, _ = inspect_pdf(
        coupon_table(
            tmp_path / "reading.pdf", False, [["Coupon gap", "Dry", "6", "mm"]]
        )
    )
    original = next(f for f in pages[0].fragments if f.text == "Coupon gap")
    quote = "Coupon gap | Dry | ≥6 | mm"
    drafts = {
        1: [
            dict(
                item="Coupon gap",
                condition="Dry",
                requirement="≥6",
                unit="mm",
                box=[0, original.box[1], 1, original.box[3]],
                quote=quote,
            )
        ]
    }
    rows = extract_pages(pages, drafts)
    assert len(rows) == 2
    assert {r.requirement for r in rows} == {"6", "≥6"} and all(
        codes(r)["visual_alternative"] == "RED" for r in rows
    )


def test_windows_icon_sizes_and_pinned_dependency_lock():
    root = Path(__file__).resolve().parents[2]
    assets = root / "src/cyct_report/orders/icons"
    with Image.open(assets / "application.ico") as icon:
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= icon.ico.sizes()
    lock = json.loads((root / "tools/orders-win64-lock.json").read_text())
    assert all(
        v["url"].startswith("https://") and len(bytes.fromhex(v["sha256"])) == 32
        for v in lock
    )
    assert any("pymupdf-1.26.6-" in v["filename"] for v in lock)
    assert (
        "PyMuPDF==1.26.6" in (root / "requirements-orders.txt").read_text().splitlines()
    )


def test_local_service_can_answer_on_private_nic_with_custom_auth(monkeypatch):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import socket
    from threading import Thread
    from cyct_report.orders.api_config import lan_host

    try:
        interfaces = socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM
        )
    except OSError:
        interfaces = []
    host = next(
        (
            a[4][0]
            for a in interfaces
            if not a[4][0].startswith("127.") and lan_host(a[4][0])
        ),
        "127.0.0.1",
    )
    received = []

    class Mock(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            received.append(
                (
                    self.path,
                    self.headers.get("X-Model-Auth"),
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            data = b'{"choices":[{"message":{"content":"OK"}}]}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with HTTPServer((host, 0), Mock) as server:
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        cfg = desktop_config(
            dict(
                enabled=True,
                allow_external_pages=True,
                base_url=f"{host}:{server.server_port}/custom",
                model="synthetic",
                auth_header="X-Model-Auth",
                auth_prefix="",
                api_key="fixture-auth-value",
            )
        )
        thread = Thread(target=server.handle_request, daemon=True)
        thread.start()
        _, client = adapters(cfg)
        client.test_connection()
        thread.join(timeout=2)
    assert received[0][:2] == ("/custom/chat/completions", "fixture-auth-value")
    assert all(isinstance(m["content"], str) for m in received[0][2]["messages"])


@pytest.mark.parametrize("placeholder", ["TBA", "By Vendor", "By Agreement", "-"])
def test_vision_cannot_fill_a_missing_limit_from_the_temperature(placeholder):
    page = Page(1, 600, 800, "scan", [])
    quote = f"Coupon swell | 23°C | {placeholder} | mm"
    draft = dict(
        quote=quote, item="Coupon swell", condition="23°C", requirement="23", unit="mm"
    )
    [r] = extract_pages([page], {1: [draft]})
    assert (
        not r.requirement
        and r.verbatim == quote
        and codes(r)["unverified_field"] == "RED"
    )
