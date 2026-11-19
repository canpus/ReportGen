"""把预置标准库导出为 Excel 核对表，供 CYCT 质检逐项核对指标。

用法：python tools/export_checklist.py <输出.xlsx>
每个标准一页，按标准原表的形式排列（行 = 检测项，列 = 各产品类型的指标）。
"""
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import Workbook                                          # noqa: E402
from openpyxl.utils import get_column_letter                         # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation           # noqa: E402

from cyct_report.docx_text import display_width                        # noqa: E402
from cyct_report.i18n import localize_method                           # noqa: E402
from cyct_report.presets import CUSTOM_STD_ID, Library                 # noqa: E402

FONT = "Arial"
THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="D9E1F2")
GROUP_FILL = PatternFill("solid", fgColor="EDEDED")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
WRAP = Alignment(wrap_text=True, vertical="center")
CENTER = Alignment(wrap_text=True, vertical="center", horizontal="center")
VERDICTS = '"正确,需修改,不适用"'

SHEET_NAMES = {"iso21809-3": "ISO 21809-3", "en12068": "EN 12068", "din30672": "DIN 30672",
               "gbt23257": "GB-T 23257", "gost-r-51164": "GOST R 51164",
               "adnoc-ages-sp-07-006": "ADNOC", "pdo-sp-2389": "PDO SP-2389",
               "gasco-dgs-1470-006": "GASCO"}
TABLE_TITLES = {
    ("iso21809-3", "t10"): "Table 10  冷缠聚合物胶带（Type 12）",
    ("iso21809-3", "t12"): "Table 12  粘弹体（Type 13A / 13B）",
    ("iso21809-3", "t16"): "Table 16  无底漆PE热缩带（Type 14A）",
    ("iso21809-3", "t17"): "Table 17  配底漆热缩带（Type 14B / 14C / 14D）",
    ("iso21809-3", "primer"): "Table 18  液体底漆数据（随 14B/14C/14D 报告列出，只填实测值）",
    ("en12068", "t1"): "Table 1  涂层要求（A / B / C 级；C1–C3 为 C 级三组可选指标）",
    ("en12068", "t2"): "Table 2  涂层要求（各等级通用）",
    ("din30672", "extra"): "DIN 30672 第 5.2、6.2、6.3 条增加的要求",
    ("gbt23257", "hs"): "热收缩带（按 CYCT 现行 GB/T 23257-2017 报告）",
    ("gost-r-51164", "t2"): "Таблица 2（结构 14 热收缩材料；15/16 聚合物胶带；17 耐热聚合物胶带）",
    ("adnoc-ages-sp-07-006", "cd"): "Table C（PE 热缩带）/ Table D（PP 热缩带）",
    ("pdo-sp-2389", "t141"): "Table 14.1  热缩带（PE / PP 基材）",
    ("pdo-sp-2389", "t131"): "Table 13.1  粘弹体自愈合缠绕体系",
    ("gasco-dgs-1470-006", "t1045"): "第 10.4.5 条  PP 热缩带",
}
COND_TEXT = {"Tmax95": "Tmax（不超过95℃）", "Tmax+20/80": "Tmax+20（不低于80℃）",
             "Tc": "温度等级30：23℃；50/HT：Tmax"}
REFERENCES = {
    "din30672": "其余检测项沿用 EN 12068 Table 1（C 级只用 C3 列）和 Table 2，见“EN 12068”页。",
    "pdo-sp-2389": "冷缠聚合物胶带按 ISO 21809-3 Table 10，见“ISO 21809-3”页。",
}


def style(cell, fill=None, bold=False, align=WRAP):
    cell.font = Font(name=FONT, size=10, bold=bold)
    cell.alignment = align
    cell.border = BORDER
    if fill:
        cell.fill = fill


_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def pretty(v: str) -> str:
    """Excel 中显示：10^8 → 10⁸，R_S100 → RS100。"""
    v = re.sub(r"\^\{?(-?\d+)\}?", lambda m: m.group(1).translate(_SUP), v)
    return re.sub(r"_\{?([A-Za-z0-9]+)\}?", lambda m: m.group(1), v)


def text(lib, value, col, lang="zh"):
    v = lib.resolve(value, col, lang)
    return "—（不适用）" if v is None else pretty(v)


def note_for(opts):
    notes = []
    if opts.get("opt"):
        notes.append("可选项，默认不列入报告")
    if opts.get("tc"):
        notes.append("仅温度等级 " + "/".join(opts["tc"]))
    return "；".join(notes)


def write_table(ws, lib, std, key, table, row):
    cols = table.get("cols") or ["指标"]
    head = ["序号", "检测项目", "Property (English)", "条件", "单位"] + cols + ["测试方法", "说明", "核对结论", "正确值 / 意见"]
    ws.cell(row, 1, TABLE_TITLES.get((std.id, key), key)).font = Font(name=FONT, size=11, bold=True)
    row += 1
    for c, h in enumerate(head, 1):
        style(ws.cell(row, c, h), HEAD_FILL, bold=True, align=CENTER)
    ws.row_dimensions[row].height = 30
    row += 1
    n, first = 0, row
    for r in table["rows"]:
        if isinstance(r, dict):
            g = lib.resolve(r["g"], None, "zh")
            if r.get("only"):
                g += f"（仅 {'/'.join(r['only'])}）"
            ws.cell(row, 1, g)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(head))
            style(ws.cell(row, 1), GROUP_FILL, bold=True)
            row += 1
            continue
        n += 1
        opts = r[5] if len(r) > 5 else {}
        cond = r[1] if isinstance(r[1], str) else None
        values = [n, text(lib, r[0], 0), text(lib, r[0], 0, "en"),
                  COND_TEXT.get(cond, text(lib, r[1], 0)), text(lib, r[2], 0)]
        values += [text(lib, r[3], i) for i in range(len(cols))]
        values += [localize_method(text(lib, r[4], 0), "zh").replace("\n", " "), note_for(opts), "", ""]
        lines = 1
        for c, v in enumerate(values, 1):
            cell = ws.cell(row, c, v)
            is_input = c > len(head) - 2
            style(cell, INPUT_FILL if is_input else None,
                  align=WRAP if c in (2, 3, len(head)) else CENTER)
            col_w = ws.column_dimensions[get_column_letter(c)].width or 10
            lines = max(lines, math.ceil(display_width(str(v)) / max(col_w - 1, 1)))
        ws.row_dimensions[row].height = 14 * lines + 2   # openpyxl 不会自动撑高换行的行
        row += 1
    dv = DataValidation(type="list", formula1=VERDICTS, allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{ws.cell(first, len(head) - 1).coordinate}:{ws.cell(row - 1, len(head) - 1).coordinate}")
    return row + 1, len(head)


def write_standard(wb, lib, std):
    ws = wb.create_sheet(SHEET_NAMES.get(std.id, std.id)[:31])
    ws.cell(1, 1, f"{std.name}    依据：{std.source}").font = Font(name=FONT, size=12, bold=True)
    if std.id in REFERENCES:
        ws.cell(2, 1, REFERENCES[std.id]).font = Font(name=FONT, size=10, italic=True)
    # 先按最宽的表设列宽，写行时据此估算行高
    ncols = max(len(t.get("cols") or [0]) for t in std.tables.values())
    widths = [6, 32, 34, 14, 10] + [17] * ncols + [20, 16, 11, 26]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    row = 3
    for key, table in std.tables.items():
        row, _ = write_table(ws, lib, std, key, table, row)
    ws.freeze_panes = "C3"


def write_types(wb, lib):
    ws = wb.create_sheet("产品类型")
    head = ["标准", "类型代码", "类型说明", "默认 Tmax (℃)", "报告中标准写法", "核对结论", "正确值 / 意见"]
    for c, h in enumerate(head, 1):
        style(ws.cell(1, c, h), HEAD_FILL, bold=True, align=CENTER)
    ws.row_dimensions[1].height = 30
    row = 2
    for std in lib.standards:
        if std.id == CUSTOM_STD_ID:
            continue
        for t in std.templates:
            vals = [std.name, t.id, t.label.get("zh", ""), "" if t.tmax is None else t.tmax,
                    lib.display(t, "zh", t.tmax), "", ""]
            for c, v in enumerate(vals, 1):
                style(ws.cell(row, c, v), INPUT_FILL if c >= 6 else None,
                      align=WRAP if c in (3, 5, 7) else CENTER)
            if display_width(vals[2]) > 64 or display_width(vals[0]) > 26:
                ws.row_dimensions[row].height = 30
            row += 1
    dv = DataValidation(type="list", formula1=VERDICTS, allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"F2:F{row - 1}")
    for i, w in enumerate([28, 10, 66, 14, 40, 11, 30], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def write_guide(wb):
    ws = wb.active
    ws.title = "填写说明"
    lines = [
        ("出厂检测报告生成器 · 预置检测项核对表", True),
        ("本表列出软件中预置的全部检测项、指标和测试方法，请按贵司执行的标准版本逐项核对。", False),
        ("", False),
        ("填写方法", True),
        ("1. 只需填写黄色底色的两列：“核对结论”（下拉选择：正确 / 需修改 / 不适用）和“正确值 / 意见”。", False),
        ("2. “需修改”时，请在“正确值 / 意见”中写明正确的指标、条件、单位或测试方法。", False),
        ("3. 各标准页按标准原表排列：每行一个检测项，中间各列是不同产品类型的指标；“—（不适用）”表示该类型没有这一项。", False),
        ("4. “产品类型”页列出软件中可选的产品类型及其说明、默认 Tmax 和报告中的标准写法，也请一并核对。", False),
        ("5. 条件栏中的 Tmax 为产品最高使用温度，生成报告时按所填温度换算，例如 80℃ 热缩带的“Tmax”显示为 80℃。", False),
        ("6. 如需增加贵司常用而本表没有的检测项（例如补伤片、补伤棒、固定片、压敏带），请在对应页末尾另起一行写明。", False),
        ("", False),
        ("填写示例", True),
    ]
    for i, (t, bold) in enumerate(lines, 1):
        cell = ws.cell(i, 1, t)
        cell.font = Font(name=FONT, size=12 if i == 1 else 10, bold=bold)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=6)
        if len(t) > 50:
            ws.row_dimensions[i].height = 30
    head = ["检测项目", "条件", "单位", "指标", "核对结论", "正确值 / 意见"]
    example = ["阴极剥离（28 d）", "23℃", "mm", "≤5.0", "需修改", "我司按客户规格书执行 ≤4.0"]
    r = len(lines) + 1
    for c, (h, v) in enumerate(zip(head, example), 1):
        style(ws.cell(r, c, h), HEAD_FILL, bold=True, align=CENTER)
        style(ws.cell(r + 1, c, v), INPUT_FILL if c >= 5 else None, align=CENTER)
    for i, w in enumerate([30, 12, 10, 14, 12, 34], 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def main(out):
    lib = Library()
    wb = Workbook()
    write_guide(wb)
    write_types(wb, lib)
    for std in lib.standards:
        if std.id != CUSTOM_STD_ID:
            write_standard(wb, lib, std)
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
