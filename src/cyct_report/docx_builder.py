"""按语言模板生成报告 docx：表头信息、检测项表格、签字行。"""
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.shared import Pt, Twips

from . import paths
from .docx_table import build_table
from .docx_text import add_plain, display_width, pad
from .i18n import LABELS, format_date, qty_unit_text
from .models import Report

# 各语言字体与字号：(西文, 中文)
INFO_FONT = {"zh": ("仿宋", "仿宋"), "en": ("Times New Roman", "宋体"), "ru": ("Times New Roman", "宋体")}
TABLE_FONT = {"zh": ("Times New Roman", "宋体"), "en": ("Times New Roman", "宋体"),
              "ru": ("Times New Roman", "宋体")}
TABLE_SIZE = {"zh": 10.5, "en": 10, "ru": 9.5}
RIGHT_TAB = {"zh": 6060, "en": 6200, "ru": 6000}


def _info_paragraph(doc, lang, space_before=0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    fmt = p.paragraph_format
    fmt.space_before = Pt(space_before)
    fmt.space_after = Pt(0)
    fmt.line_spacing = 1.5
    fmt.tab_stops.add_tab_stop(Twips(RIGHT_TAB[lang]), WD_TAB_ALIGNMENT.LEFT)
    return p


def _field(p, lang, label_key, value, width, size):
    lab = LABELS[lang]
    add_plain(p, lab[label_key] + lab["colon"], INFO_FONT[lang], size)
    add_plain(p, pad(value, width), INFO_FONT[lang], size, underline=True)


def _batches(report: Report) -> str:
    seen = []
    for prod in report.products:
        b = prod.batch.strip()
        if b and b not in seen:
            seen.append(b)
    return "、".join(seen) if report.lang == "zh" else ", ".join(seen)


def _left_width(lang, label_key, size):
    """制表位左侧可容纳的半角字符数（扣除标签），用于决定填空长度与是否换行。"""
    lab = LABELS[lang]
    half_char = size * 10                      # 1 个半角字符约 size*10 twips
    return RIGHT_TAB[lang] // half_char - display_width(lab[label_key] + lab["colon"]) - 1


def _pair_line(doc, lang, size, left, right):
    """左右两栏：左栏放不下时，右栏另起一行（与原英文报告一致）。"""
    (lkey, lval), (rkey, rval) = left, right
    room = _left_width(lang, lkey, size)
    p = _info_paragraph(doc, lang)
    if display_width(lval) + 2 <= room:
        _field(p, lang, lkey, lval, room, size)
    else:
        _field(p, lang, lkey, lval, 0, size)
        p = _info_paragraph(doc, lang)
    p.add_run("\t")
    _field(p, lang, rkey, rval, 12, size)


def _write_header_info(doc, report: Report):
    lang, size = report.lang, 12
    p = _info_paragraph(doc, lang, space_before=12)
    _field(p, lang, "consignee", report.customer, 44, 14 if lang == "zh" else 13)
    for prod in report.products:
        qty = f"{prod.qty} {qty_unit_text(prod.unit, lang)}".strip() if prod.qty else ""
        _pair_line(doc, lang, size, ("product", prod.name), ("qty", qty))
    _pair_line(doc, lang, size, ("standard", report.std_display), ("batch", _batches(report)))


def _write_signatures(doc, report: Report):
    lang = report.lang
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(24)
    p.paragraph_format.left_indent = Twips(420)
    font, size = INFO_FONT[lang], 12
    lab = LABELS[lang]
    for i, (key, value) in enumerate((("inspector", report.inspector),
                                      ("auditor", report.auditor),
                                      ("date", format_date(report.report_date, lang)))):
        if i:
            add_plain(p, "      ", font, size)
        add_plain(p, lab[key] + lab["colon"], font, size)
        add_plain(p, pad(value, 12), font, size, underline=True)


def build_docx(report: Report, out_path: Path, template: Path = None) -> Path:
    template = template or paths.template_file(report.lang)
    doc = docx.Document(str(template))
    _write_header_info(doc, report)
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(0)
    spacer.paragraph_format.line_spacing = Pt(4)
    build_table(doc, report.items, report.lang, report.tmax_value(),
                TABLE_FONT[report.lang], TABLE_SIZE[report.lang])
    _write_signatures(doc, report)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
