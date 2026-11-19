"""检测项表格：六列（项目 | 条件 | 单位 | 指标 | 结果 | 方法）与合并规则。

合并规则（与 CYCT 现有报告一致）：
- 连续同名检测项，“项目”单元格纵向合并；
- 中文报告中条件为空时，“项目”横跨条件列；英俄报告条件为空写“—”；
- 同名检测项内，相同的单位、测试方法纵向合并；
- 分组行通栏，粗体组名 + 说明文字。
"""
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips

from .docx_text import add_rich
from .i18n import LABELS
from .presets import render_cond

COL_WIDTHS = [2420, 1100, 900, 1800, 1650, 1723]   # twips，合计 9593，与原报告表宽一致
NCOL = len(COL_WIDTHS)


def _cell_rows(items, lang, tmax):
    """把 Item 列表转成每行的文字；分组行为 ('group', 名称, 说明)。"""
    rows = []
    for it in items:
        if it.kind == "group":
            rows.append(("group", it.get("name", lang), it.get("note", lang)))
            continue
        cond = render_cond(it.get("cond", lang), tmax)
        if lang != "zh" and not cond.strip():
            cond = "—"
        rows.append(("item", it.get("name", lang), cond, it.get("unit", lang),
                     it.get("req", lang), it.result, it.get("method", lang)))
    return rows


def _runs(rows, start, key):
    """在 rows[start:] 内找“连续且 key 相同”的区段，返回 [(起, 止)]，不跨越分组行。"""
    out, i = [], start
    while i < len(rows):
        if rows[i][0] == "group":
            i += 1
            continue
        j = i
        while j + 1 < len(rows) and rows[j + 1][0] == "item" and key(rows[j + 1]) == key(rows[i]):
            j += 1
        out.append((i, j))
        i = j + 1
    return out


def _set_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tbl_pr.append(borders)


def _prepare_row(row, height):
    tr_pr = row._tr.get_or_add_trPr()
    cant = OxmlElement("w:cantSplit")
    tr_pr.append(cant)
    h = OxmlElement("w:trHeight")
    h.set(qn("w:val"), str(height))
    h.set(qn("w:hRule"), "atLeast")
    tr_pr.append(h)


def _write(cell, text, font, size, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER):
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    add_rich(p, text, font, size, bold)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def build_table(doc, items, lang, tmax, font, size):
    rows = _cell_rows(items, lang, tmax)
    table = doc.add_table(rows=len(rows) + 1, cols=NCOL)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_borders(table)
    for r in table.rows:
        _prepare_row(r, 400)
        for c, w in zip(r.cells, COL_WIDTHS):
            c.width = Twips(w)

    header = LABELS[lang]["header"]
    if lang == "zh":
        table.cell(0, 0).merge(table.cell(0, 1))
        header = [header[0], None] + header[2:]
    for c, text in enumerate(header):
        if text is not None:
            _write(table.cell(0, c), text, font, size, bold=True)

    merges, texts = [], {}
    for i, row in enumerate(rows):
        r = i + 1
        if row[0] == "group":
            merges.append(((r, 0), (r, NCOL - 1)))
            texts[(r, 0)] = ("group", row[1], row[2])
    for a, b in _runs(rows, 0, key=lambda x: x[1]):
        span_cond = lang == "zh" and all(not rows[k][2].strip() for k in range(a, b + 1))
        last_col = 1 if span_cond else 0
        if a != b or span_cond:
            merges.append(((a + 1, 0), (b + 1, last_col)))
        texts[(a + 1, 0)] = rows[a][1]
        for k in range(a, b + 1):
            if not span_cond:
                texts[(k + 1, 1)] = rows[k][2]
            texts[(k + 1, 3)] = rows[k][4]
            texts[(k + 1, 4)] = rows[k][5]
        # 单位、测试方法：只在同一检测项（同名区段）内合并
        for col, idx in ((2, 3), (5, 6)):
            for ua, ub in _runs(rows[:b + 1], a, key=lambda x, i=idx: x[i]):
                if ub > ua:
                    merges.append(((ua + 1, col), (ub + 1, col)))
                texts[(ua + 1, col)] = rows[ua][idx]

    for (r1, c1), (r2, c2) in merges:
        table.cell(r1, c1).merge(table.cell(r2, c2))
    for (r, c), text in texts.items():
        cell = table.cell(r, c)
        if isinstance(text, tuple):
            _write(cell, text[1], font, size, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)
            if text[2]:
                add_rich(cell.paragraphs[0], text[2], font, size - 1.5)
        else:
            _write(cell, text, font, size)
    return table
