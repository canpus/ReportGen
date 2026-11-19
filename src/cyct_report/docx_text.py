"""Word 段落文字输出：字体设置、上下标解析、下划线填空。

文本中可识别的上下标写法：
  ₀–₉ 等 Unicode 下标、⁰–⁹ Unicode 上标、^14 / ^{14} 上标、_S100 / _{S100} 下标、
  名称中的 “Tmax” 输出为 T + 下标 max。
"""
import re
import unicodedata

from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

_SUB = dict(zip("₀₁₂₃₄₅₆₇₈₉ₐₑₒₓₘₕₖₗₙₚₛₜ", "0123456789aeoxmhklnpst"))
_SUP = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-"))
_TOKEN = re.compile(
    r"(?P<tmax>Tmax)"
    r"|\^\{(?P<sup1>[^}]*)\}|\^(?P<sup2>-?\d+)"
    r"|_\{(?P<sub1>[^}]*)\}|_(?P<sub2>[A-Za-z0-9]+)"
    r"|(?P<usub>[" + "".join(_SUB) + "]+)"
    r"|(?P<usup>[" + "".join(_SUP) + "]+)"
    r"|(?P<br>\n)")


def segments(text: str):
    """把文字拆成 (片段, 'sub'|'sup'|None|'br')。"""
    pos = 0
    for m in _TOKEN.finditer(text):
        if m.start() > pos:
            yield text[pos:m.start()], None
        g = m.lastgroup
        if g == "tmax":
            yield "T", None
            yield "max", "sub"
        elif g in ("sup1", "sup2"):
            yield m.group(g), "sup"
        elif g in ("sub1", "sub2"):
            yield m.group(g), "sub"
        elif g == "usub":
            yield "".join(_SUB[c] for c in m.group(g)), "sub"
        elif g == "usup":
            yield "".join(_SUP[c] for c in m.group(g)), "sup"
        else:
            yield "", "br"
        pos = m.end()
    if pos < len(text):
        yield text[pos:], None


def set_run_font(run, ascii_font, east_font, size, bold=False, underline=False):
    run.font.name = ascii_font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.underline = underline
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        fonts.set(qn(attr), ascii_font)
    fonts.set(qn("w:eastAsia"), east_font)


def add_rich(paragraph, text, font, size, bold=False, underline=False):
    """按上下标规则写入文字；font = (西文字体, 中文字体)。"""
    for seg, kind in segments(text or ""):
        if kind == "br":
            paragraph.add_run().add_break(WD_BREAK.LINE)
            continue
        run = paragraph.add_run(seg)
        set_run_font(run, font[0], font[1], size, bold, underline)
        if kind == "sub":
            run.font.subscript = True
        elif kind == "sup":
            run.font.superscript = True


def add_plain(paragraph, text, font, size, bold=False, underline=False):
    run = paragraph.add_run(text)
    set_run_font(run, font[0], font[1], size, bold, underline)
    return run


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def pad(text: str, width: int) -> str:
    """下划线填空：左右各留一个空格，不足 width 时补空格。"""
    text = f" {text} "
    return text + " " * max(0, width - display_width(text))
