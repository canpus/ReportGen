"""Consistent review snapshots; textual Excel cells never execute as formulas."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import os
import tempfile
import shutil

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink

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


def worksheet(wb, name, headers, rows, *, editable=()):
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


def _values(r, columns):
    data = dict(r, id_note=[n["text"] for n in r["notes"]])
    return [data.get(k, "") for k, _ in columns]


def _bytes(book):
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def files_for(snapshot):
    full = Workbook()
    full.remove(full.active)
    lab = Workbook()
    lab.remove(lab.active)
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
    evidence = []
    anchors = {}
    for r in rows:
        anchors[(r["doc"], r["id"])] = 2 + len(evidence)
        for f in r["regions"]:
            roles = [k for k, ids in r["bindings"].items() if f["id"] in ids]
            evidence.append(
                [
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
            )
        if not r["regions"]:
            evidence.append(
                [
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
            )
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
        evidence,
    )
    extras = [("question", "Question"), ("respondent", "Responsible party")]
    for name, batch, cols in [
        ("Confirmed", req, COMMON),
        ("Frequencies", freq, COMMON + PHASES),
        ("Clarifications", tq, COMMON + PHASES + extras),
    ]:
        ws = worksheet(
            full, name, [v for _, v in cols], (_values(r, cols) for r in batch)
        )
        idx = next(i for i, (k, _) in enumerate(cols, 1) if k == "source_pages")
        for i, r in enumerate(batch, 2):
            cell = ws.cell(i, idx)
            cell.hyperlink = Hyperlink(
                ref=cell.coordinate,
                location=f"'Evidence'!A{anchors[(r['doc'], r['id'])]}",
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
        cols = COMMON + PHASES + (extras if name == "Clarifications" else [])
        headers = [v for _, v in cols] + ["Disposition"] + MANUAL

        def form_rows():
            for r in batch:
                disposition = (
                    "HOLD — clarification"
                    if name == "Clarifications"
                    or r["value_role"]
                    in {"tba", "by_vendor", "by_agreement", "dash_not_listed"}
                    else (
                        "Reference only"
                        if r["value_role"]
                        in {"typical_only", "test_condition", "conditional_exception"}
                        else "Review specified requirement"
                    )
                )
                yield _values(r, cols) + [disposition, None, None, None]

        ws = worksheet(lab, name, headers, form_rows(), editable=MANUAL)
        page_column = headers.index("PDF pages") + 1
        for i, r in enumerate(batch, 2):
            cell = ws.cell(i, page_column)
            cell.hyperlink = Hyperlink(
                ref=cell.coordinate,
                target="confirmed.xlsx",
                location=f"'Evidence'!A{anchors[(r['doc'], r['id'])]}",
            )

    return {
        "confirmed.json": json.dumps(snapshot, ensure_ascii=False, indent=2).encode(),
        "confirmed.xlsx": _bytes(full),
        "laboratory.xlsx": _bytes(lab),
    }


def export_directory(store, order, directory):
    snap = store.snapshot(order)
    parent = Path(directory).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    import hashlib

    tag = hashlib.sha256(order.encode()).hexdigest()[:16]
    dest = parent / f"order-{tag}-rev-{snap['confirmed_rev']}"
    results = files_for(snap)
    temp = Path(tempfile.mkdtemp(prefix=".order-export-", dir=parent))
    try:
        for name, data in results.items():
            (temp / name).write_bytes(data)
        try:
            os.rename(temp, dest)
        except OSError:
            if (
                not dest.is_dir()
                or not (dest / "confirmed.json").is_file()
                or (dest / "confirmed.json").read_bytes() != results["confirmed.json"]
                or not all((dest / n).is_file() for n in results)
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
