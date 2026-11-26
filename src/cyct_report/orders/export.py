"""Consistent review snapshots; textual Excel cells never execute as formulas."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import filecmp
import os
import tempfile
import shutil

COMMON = [
    ("id", "ID"),
    ("doc_no", "Document"),
    ("doc_rev", "Document revision"),
    ("component", "Component"),
    ("scenario", "Scenario"),
    ("stage", "Stage"),
    ("interface", "Interface"),
    ("item", "Inspection activity"),
    ("condition", "Test condition"),
    ("test_temp", "Test temperature"),
    ("conditioning", "Conditioning"),
    ("requirement", "Specified requirement"),
    ("typical", "Typical value"),
    ("unit", "Unit"),
    ("quantity_kind", "Quantity kind"),
    ("sampling_basis", "Sample basis"),
    ("frequency", "Inspection frequency"),
    ("failure_action", "Failure disposition"),
    ("value_role", "Value role"),
    ("method", "Test method"),
    ("verbatim", "Customer wording"),
    ("source_tier", "Source tier"),
    ("source_pages", "PDF pages"),
    ("field_sources", "Field sources"),
    ("file_sha256", "Source SHA-256"),
    ("id_note", "Notes and exceptions"),
]
PHASES = [
    ("pqt", "PQT"),
    ("ppt", "PPT"),
    ("production", "Production"),
    ("phase_roles", "Stage value roles"),
]
MANUAL = ["Actual Test Result", "Test Specimen/Date", "Lab Judgement"]


def stringify(v):
    if isinstance(v, list) and all(isinstance(i, int) for i in v):
        return ", ".join(map(str, v))
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return v


def worksheet(wb, name, headers, rows, *, editable=(), links=None):
    if hasattr(wb, "add_worksheet"):
        return _stream_sheet(wb, name, headers, rows, editable, links or {})
    # Retain the existing helper for callers editing their own openpyxl workbook.
    from openpyxl.styles import Alignment, Font, PatternFill, Protection
    from openpyxl.utils import get_column_letter

    ws = wb.create_sheet(name)
    headers = list(headers)
    ws.append(headers)
    continuation_columns = {}
    for i, row in enumerate(rows, 2):
        for j, val in enumerate(row, 1):
            value = stringify(val)
            # Excel limits a cell to 32,767 characters. Keep the primary row and all anchors stable.
            if isinstance(value, str) and len(value.encode("utf-16-le")) > 65534:
                chunks = [value[n : n + 16000] for n in range(0, len(value), 16000)]
            else:
                chunks = [value]
            for part, text in enumerate(chunks):
                column = j
                if part:
                    key = (j, part)
                    if key not in continuation_columns:
                        headers.append(f"{headers[j - 1]} (continued {part + 1})")
                        continuation_columns[key] = len(headers)
                        ws.cell(1, len(headers), headers[-1])
                    column = continuation_columns[key]
                cell = ws.cell(i, column)
                if text is not None:
                    cell.value = text
                    if isinstance(text, str):
                        cell.data_type = "s"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if headers[j - 1] in editable:
                    cell.fill = PatternFill("solid", fgColor="FFF1B8")
                    cell.protection = Protection(locked=False)
    for cell in ws[1]:
        cell.font = Font(name="Calibri", bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1C4952")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 34
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = (
            52
            if h in {"Customer wording", "Evidence text", "Question", "Details"}
            else (
                32
                if h
                in {
                    "Test method",
                    "Inspection activity",
                    "Specified requirement",
                    "Test condition",
                }
                else max(13, min(27, len(h) + 5))
            )
        )
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.showGridLines = False
    ws.protection.sheet = True
    ws.protection.autoFilter = False
    return ws


def _stream_sheet(book, name, titles, rows, editable, links):
    ws = book.add_worksheet(name)
    header = book.add_format(
        {
            "bold": True,
            "font_color": "white",
            "bg_color": "#1C4952",
            "text_wrap": True,
            "valign": "vcenter",
        }
    )
    body = book.add_format({"text_wrap": True, "valign": "top"})
    blank = book.add_format({"locked": False, "bg_color": "#FFF1B8", "valign": "top"})
    titles = list(titles)
    base = len(titles)
    extra = {}
    # Some evidence exceeds Excel's cell limit. Discover continuation columns before emitting row 1.
    with tempfile.SpooledTemporaryFile(
        max_size=64 * 1024, mode="w+t", encoding="utf-8", dir=book.tmpdir
    ) as spool:
        for row in rows:
            values = [stringify(v) for v in row]
            cells = []
            for col, v in enumerate(values):
                chunks = (
                    [v[i : i + 16000] for i in range(0, len(v), 16000)]
                    if isinstance(v, str) and len(v.encode("utf-16-le")) > 65534
                    else [v]
                )
                for part, value in enumerate(chunks):
                    j = col
                    if part:
                        key = (col, part)
                        if key not in extra:
                            extra[key] = len(titles)
                            titles.append(f"{titles[col]} (continued {part + 1})")
                        j = extra[key]
                    cells.append((j, value))
            spool.write(json.dumps(cells, ensure_ascii=False) + "\n")
        ws.write_row(0, 0, titles, header)
        ws.set_row(0, 34)
        for i, title in enumerate(titles):
            width = (
                52
                if title in {"Customer wording", "Evidence text", "Question", "Details"}
                else 32
                if title
                in {
                    "Test method",
                    "Inspection activity",
                    "Specified requirement",
                    "Test condition",
                }
                else max(13, min(27, len(title) + 5))
            )
            ws.set_column(i, i, width)
        spool.seek(0)
        total = 0
        for total, row in enumerate(spool, 1):
            for col, val in json.loads(row):
                style = blank if col < base and titles[col] in editable else body
                if (total, col) in links:
                    ws.write_url(
                        total, col, "internal:" + links[total, col], body, str(val)
                    )
                elif isinstance(val, str):
                    ws.write_string(total, col, val, style)
                elif val is None:
                    ws.write_blank(total, col, None, style)
                else:
                    ws.write(total, col, val, style)
    ws.freeze_panes(
        1, 3 if name not in {"Laboratory", "Field inspection", "Clarifications"} else 1
    )
    ws.autofilter(0, 0, total, len(titles) - 1)
    ws.hide_gridlines(2)
    ws.protect("", {"autofilter": True})
    return ws


def _values(r, columns):
    data = dict(r, id_note=[n["text"] for n in r["notes"]])
    return [data.get(k, "") for k, _ in columns]


OUTPUTS = ("confirmed.json", "confirmed.xlsx", "laboratory.xlsx")


def _write_outputs(snapshot, folder):
    from xlsxwriter import Workbook

    with (folder / "confirmed.json").open("w", encoding="utf-8", newline="") as out:
        json.dump(snapshot, out, ensure_ascii=False, indent=2)
    options = {
        "constant_memory": True,
        "tmpdir": str(folder),
        "strings_to_urls": False,
        "strings_to_formulas": False,
    }
    full = Workbook(folder / "confirmed.xlsx", options)
    lab = Workbook(folder / "laboratory.xlsx", options)
    _write_workbooks(snapshot, full, lab)
    full.close()
    lab.close()


def files_for(snapshot):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        _write_outputs(snapshot, folder)
        return {name: (folder / name).read_bytes() for name in OUTPUTS}


def _write_workbooks(snapshot, full, lab):
    tq = snapshot["clarifications"]
    freq = snapshot["frequencies"]
    req = snapshot["requirements"]
    rows = req + freq + tq + snapshot.get("reviewed_pages", [])
    worksheet(
        full,
        "Order",
        ["Order", "Confirmed revision", "Snapshot UTC", "Pending rows omitted"],
        [
            [
                snapshot["order_id"],
                snapshot["confirmed_rev"],
                snapshot["created"],
                snapshot["omitted_pending"],
            ]
        ],
    )
    worksheet(
        full,
        "Documents",
        [
            "Document",
            "Revision",
            "Source SHA-256",
            "Content signature",
            "ID",
            "Alias of",
            "Active",
        ],
        (
            [
                d[k]
                for k in (
                    "doc_no",
                    "doc_rev",
                    "sha256",
                    "signature",
                    "id",
                    "alias_of",
                    "active",
                )
            ]
            for d in snapshot["documents"]
        ),
    )
    anchors = {}
    pos = 2
    for r in rows:
        anchors[(r["doc"], r["id"])] = pos
        pos += max(1, len(r["regions"]))

    def evidence_rows():
        for r in rows:
            for f in r["regions"]:
                roles = [k for k, ids in r["bindings"].items() if f["id"] in ids]
                yield [
                    r["id"],
                    r["doc_no"],
                    f["page"],
                    f["id"],
                    f["box"],
                    f["row"],
                    roles,
                    f["text"],
                    f["notation"],
                    f["origin"],
                    f.get("runs", []),
                ]
            if not r["regions"]:
                yield [
                    r["id"],
                    r["doc_no"],
                    r["source_pages"],
                    "",
                    None,
                    None,
                    None,
                    "Page requires transcription",
                    None,
                    None,
                ]

    worksheet(
        full,
        "Evidence",
        [
            "ID",
            "Document",
            "PDF page",
            "Fragment",
            "Normalized box",
            "Geometry row",
            "Fields",
            "Evidence text",
            "Script notation",
            "Carrier",
            "Original text runs",
        ],
        evidence_rows(),
    )
    extras = [("question", "Question"), ("respondent", "Responsible party")]
    for name, batch, cols in [
        ("Confirmed", req, COMMON),
        ("Frequencies", freq, COMMON + PHASES),
        ("Clarifications", tq, COMMON + PHASES + extras),
    ]:
        idx = next(i for i, (key, _) in enumerate(cols) if key == "source_pages")
        links = {
            (i, idx): f"'Evidence'!A{anchors[(r['doc'], r['id'])]}"
            for i, r in enumerate(batch, 1)
        }
        worksheet(
            full,
            name,
            [v for _, v in cols],
            (_values(r, cols) for r in batch),
            links=links,
        )
    if snapshot.get("reviewed_pages"):
        worksheet(
            full,
            "Page reviews",
            ["ID", "Document", "PDF pages", "Resolution"],
            (
                [
                    r["id"],
                    r["doc_no"],
                    r["source_pages"],
                    "Manual page verification recorded",
                ]
                for r in snapshot["reviewed_pages"]
            ),
        )
    worksheet(
        full,
        "References",
        ["ID", "Document", "Source tier", "Evidence or reference", "Alerts"],
        (
            [
                r["id"],
                r["doc_no"],
                v.get("tier", "client_explicit") if v else "client_explicit",
                v,
                r["alerts"],
            ]
            for r in rows
            for v in (r["reference"] + r["links"] or [{}])
        ),
    )
    worksheet(
        full,
        "Audit",
        [
            "Sequence",
            "Document ID",
            "ID",
            "Reviewer",
            "UTC",
            "Version",
            "Action",
            "Details",
        ],
        (
            [
                a[k]
                for k in (
                    "seq",
                    "doc",
                    "rid",
                    "user",
                    "stamp",
                    "version",
                    "action",
                    "detail",
                )
            ]
            for a in snapshot["audit"]
        ),
    )
    ordered = sorted(
        req + freq, key=lambda r: (r["component"], r["scenario"], r["stage"], r["id"])
    )
    for name, batch in [
        ("Laboratory", [r for r in ordered if r["destination"] == "laboratory"]),
        ("Field inspection", [r for r in ordered if r["destination"] == "field"]),
        ("Clarifications", tq),
    ]:
        cols = [
            ("item", "Inspection activity"),
            ("component", "Component / scenario"),
            ("condition", "Test condition"),
            ("method", "Test method"),
            ("requirement", "Specified requirement"),
            ("typical", "Typical value"),
            ("unit", "Unit"),
            ("frequency", "Sampling / frequency"),
            ("failure_action", "Failure disposition"),
            ("verbatim", "Customer wording"),
            ("source_pages", "PDF pages"),
        ]
        if name == "Clarifications":
            cols += extras
        headers = [v for _, v in cols] + ["Disposition"] + MANUAL

        def form_rows():
            for r in batch:
                if name == "Clarifications" or r["value_role"] in {
                    "tba",
                    "by_vendor",
                    "by_agreement",
                    "dash_not_listed",
                }:
                    disposition = "HOLD — clarification"
                elif r["value_role"] in {
                    "typical_only",
                    "test_condition",
                    "conditional_exception",
                }:
                    disposition = "Reference only"
                else:
                    disposition = "Review specified requirement"

                def joined(values):
                    return "\n".join(dict.fromkeys(v for v in values if v))

                phases = [label + "  " + r[k] for k, label in PHASES[:3] if r.get(k)]
                notes = [n["text"] for n in r.get("notes", [])]
                view = dict(
                    r,
                    component=joined(
                        (r["component"], r["scenario"], r["interface"], r["stage"])
                    ),
                    condition=joined(
                        (r["condition"], r["test_temp"], r["conditioning"], *notes)
                    ),
                    frequency=joined((r["sampling_basis"], r["frequency"], *phases)),
                    source_pages=f"{r['doc_no']} ({r['doc_rev']}) · p. "
                    + ", ".join(map(str, r["source_pages"])),
                )
                yield _values(view, cols) + [disposition, None, None, None]

        worksheet(lab, name, headers, form_rows(), editable=MANUAL)


def export_directory(store, order, directory):
    snap = store.snapshot(order)
    parent = Path(directory).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    import hashlib

    tag = hashlib.sha256(order.encode()).hexdigest()[:16]
    dest = parent / f"order-{tag}-rev-{snap['confirmed_rev']}"
    temp = Path(tempfile.mkdtemp(prefix=".order-export-", dir=parent))
    try:
        _write_outputs(snap, temp)
        try:
            os.rename(temp, dest)
        except OSError:
            if (
                not dest.is_dir()
                or not (dest / "confirmed.json").is_file()
                or not filecmp.cmp(
                    dest / "confirmed.json", temp / "confirmed.json", shallow=False
                )
                or not all((dest / n).is_file() for n in OUTPUTS)
            ):
                raise
        return dest
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def bundle(snapshot):
    out = BytesIO()
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as z:
        for name, data in files_for(snapshot).items():
            z.writestr(name, data)
    return out.getvalue()
