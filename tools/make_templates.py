"""由 CYCT 现有报告生成 templates/report_{zh,en,ru}.docx（开发时运行一次）。

用法：python tools/make_templates.py <中文样本.docx> <英文样本.docx>
英文样本若是 .doc，请先用 Word 另存为 .docx。
模板只保留页面设置、页眉（logo、公司名、表单号）和页脚页码，正文由程序生成。
"""
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn

OUT = Path(__file__).resolve().parents[1] / "templates"
RU_TITLE = "Протокол испытаний"


def strip_body(document):
    body = document.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def replace_header_text(document, old, new):
    for section in document.sections:
        for part in (section.header, section.first_page_header):
            for t in part._element.iter(qn("w:t")):
                if t.text and old in t.text:
                    t.text = t.text.replace(old, new)


def main(zh_src, en_src):
    OUT.mkdir(exist_ok=True)
    d = docx.Document(zh_src)
    strip_body(d)
    d.save(OUT / "report_zh.docx")
    for lang in ("en", "ru"):
        d = docx.Document(en_src)
        strip_body(d)
        if lang == "ru":
            replace_header_text(d, "Test Report", RU_TITLE)
        d.save(OUT / f"report_{lang}.docx")
    for f in sorted(OUT.glob("report_*.docx")):
        print(f, f.stat().st_size, "bytes")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
