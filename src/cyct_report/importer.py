"""导入以前手工制作的报告（.docx / .doc）。

- 从正文段落中按标签（收货单位/Consignee、产品规格/Product Specifications…）解析信息；
- 报告时间默认取文件创建时间，可改用修改时间或正文日期；
- 导入时把文件（及同名 PDF）复制到报告库，并在数据库中标记 source = 'imported'。
"""
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import docx

from . import naming, office

LABELS = {
    "customer": r"收货单位|Consignee|Получатель",
    "product": r"产品规格|Product\s+Specifications?|Продукция",
    "qty": r"数\s*量|Quantity|Количество",
    "standard": r"执行标准|Testing\s+standards?|Стандарт\s+испытаний",
    "batch": r"生产批号|Product\s+batch|Номер\s+партии",
    "inspector": r"检验员|Inspector|Испытал",
    "auditor": r"审\s*核|Auditor|Проверил",
    "date": r"日\s*期|Date|Дата",
}
_LABEL_RE = re.compile("|".join(f"(?P<{k}>{v})\\s*[:：]" for k, v in LABELS.items()), re.I)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
TIME_SOURCES = ("ctime", "mtime", "content")


@dataclass
class ImportRecord:
    path: Path
    customer: str = ""
    products: list = field(default_factory=list)     # [(名称, 数量)]
    standard: str = ""
    batch: str = ""
    content_date: date = None
    ctime: datetime = None
    mtime: datetime = None
    lang: str = ""
    error: str = ""

    def report_time(self, source: str) -> datetime:
        if source == "content" and self.content_date:
            return datetime.combine(self.content_date, datetime.min.time())
        if source == "mtime":
            return self.mtime
        return self.ctime


def parse_date(text: str):
    t = text.strip()
    m = re.search(r"(\d{4})\s*[.\-/年]\s*(\d{1,2})\s*[.\-/月]\s*(\d{1,2})", t)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"([A-Za-z]{3,})\.?\s+(\d{1,2})\s*,\s*(\d{4})", t)
    if m and m.group(1)[:3].lower() in MONTHS:
        return _mk(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", t)
    if m:
        return _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _mk(y, mo, d):
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _clean(v: str) -> str:
    return re.sub(r"[\s_]+", " ", v).strip(" _\t")


def parse_lines(lines) -> dict:
    out = {"products": [], "customer": "", "standard": "", "batch": "", "date": None}
    for line in lines:
        hits = list(_LABEL_RE.finditer(line))
        for i, m in enumerate(hits):
            end = hits[i + 1].start() if i + 1 < len(hits) else len(line)
            key, val = m.lastgroup, _clean(line[m.end():end])
            if key == "product":
                out["products"].append([val, ""])
            elif key == "qty":
                if out["products"]:
                    out["products"][-1][1] = val
                else:
                    out["products"].append(["", val])
            elif key == "date":
                out["date"] = out["date"] or parse_date(val)
            elif key in ("customer", "standard", "batch") and not out[key]:
                out[key] = val
    return out


def _docx_lines(path: Path) -> list:
    d = docx.Document(str(path))
    return [p.text for p in d.paragraphs if p.text.strip()]


def read_record(path, engine: str = "auto") -> ImportRecord:
    path = Path(path)
    st = path.stat()
    rec = ImportRecord(path=path, ctime=datetime.fromtimestamp(st.st_ctime),
                       mtime=datetime.fromtimestamp(st.st_mtime))
    try:
        if path.suffix.lower() == ".doc":
            with tempfile.TemporaryDirectory() as tmp:
                conv = Path(tmp) / "conv.docx"
                office.doc_to_docx(path, conv, engine)
                lines = _docx_lines(conv)
        else:
            lines = _docx_lines(path)
    except Exception as e:
        rec.error = f"无法读取：{e}"
        return rec
    info = parse_lines(lines)
    rec.customer, rec.standard, rec.batch = info["customer"], info["standard"], info["batch"]
    rec.products = [tuple(p) for p in info["products"]]
    rec.content_date = info["date"]
    text = " ".join(lines)
    rec.lang = "zh" if re.search(r"[一-鿿]{4}", text) else (
        "ru" if re.search(r"[А-Яа-я]{4}", text) else "en")
    if not rec.customer:
        rec.error = "未识别到客户名，请手动填写"
    return rec


def import_record(rec: ImportRecord, db, reports_root: Path, time_source: str) -> int:
    when = rec.report_time(time_source)
    folder = naming.report_dir(reports_root, rec.customer, when.date())
    target = naming.unique_path(folder, naming.safe_name(rec.path.stem), rec.path.suffix.lower())
    shutil.copy2(rec.path, target)
    pdf_src, pdf_target = rec.path.with_suffix(".pdf"), ""
    if pdf_src.exists():
        pdf_target = target.with_suffix(".pdf")
        shutil.copy2(pdf_src, pdf_target)
    rid = db.add_report(
        customer=rec.customer, products="；".join(p[0] for p in rec.products),
        quantities="；".join(p[1] for p in rec.products if p[1]), batches=rec.batch,
        standard=rec.standard, lang=rec.lang, created_at=when.isoformat(timespec="seconds"),
        report_date=rec.content_date.isoformat() if rec.content_date else "",
        source="imported", docx_path=str(target), pdf_path=str(pdf_target),
        data_json={"original_path": str(rec.path), "time_source": time_source})
    db.touch_customer(rec.customer)
    return rid


def scan_folder(folder) -> list:
    """列出文件夹（含子文件夹）中的 .doc/.docx，跳过 Word 临时文件。"""
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith((".doc", ".docx")) and not f.startswith("~$"):
                out.append(Path(root) / f)
    return sorted(out)
