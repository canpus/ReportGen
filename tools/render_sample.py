"""开发用：用虚构样例生成中/英/俄报告并转 PDF、PNG，用于检查版式。

用法：python tools/render_sample.py <输出目录>
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cyct_report.docx_builder import build_docx      # noqa: E402
from cyct_report.models import Product, Report        # noqa: E402
from cyct_report.office import docx_to_pdf            # noqa: E402
from cyct_report.presets import Library               # noqa: E402

GB_RESULTS = ["18.75", "4.25", "2.0", "9.10", "", "", "无漏点"]


def make(lib, sid, tid, lang, customer, products, results=None):
    std, tpl = lib.standard(sid), lib.template(sid, tid)
    items = lib.build_items(std, tpl)
    vals = iter(results or [])
    for it in items:
        if it.kind == "item":
            it.result = next(vals, "")
    return Report(customer=customer, lang=lang, standard_id=sid, template_id=tid,
                  std_display=lib.display(tpl, lang, tpl.tmax), tmax=str(tpl.tmax or ""),
                  tc=tpl.tc, products=products, items=items, inspector="甲员" if lang == "zh" else "Fixture Operator",
                  auditor="乙员" if lang == "zh" else "Fixture Reviewer", report_date=date(2032, 5, 14))


def main(out):
    out = Path(out)
    lib = Library()
    cases = [
        ("zh-gb", make(lib, "gbt23257", "hs", "zh", "合成星点测试设计工作室",
                       [Product("常温热缩带SIMQ137x410/2.1mm", "30", "set", "SIM001-39")], GB_RESULTS)),
        ("en-iso", make(lib, "iso21809-3", "14B-2", "en", "Mock Fixture",
                        [Product("80℃ Heat Shrinkable sleeves SIMQΦ131（6inch)x480x2.2mm", "173", "set",
                                 "SIM001-41")], ["2.18", "no holiday", "＞9", "", "0.91", "3.11", "7.12"])),
        ("ru-iso", make(lib, "iso21809-3", "14B-2", "ru", "ТОО «Пример»",
                        [Product("Термоусаживающаяся манжета SIMQ Φ131x480x2.2", "100", "set", "T1"),
                         Product("Термоусаживающаяся манжета SIMQ Φ227x480x2.2", "50", "set", "T2")])),
        ("en-en12068", make(lib, "en12068", "C3-HT", "en", "Synthetic Fixture West",
                            [Product(f"80℃SIMQ heat shrink sleeve {d}inchx430x2.7mm", "300", "set", "SIM002-1")
                             for d in (4, 6, 8)])),
    ]
    for name, rep in cases:
        d = build_docx(rep, out / f"{name}.docx")
        pdf = out / f"{name}.pdf"
        print(name, "via", docx_to_pdf(d, pdf))
        try:
            import pymupdf
            doc = pymupdf.open(pdf)
            for i in range(doc.page_count):
                doc[i].get_pixmap(dpi=75).save(out / f"{name}-{i}.png")
        except ImportError:
            pass


if __name__ == "__main__":
    main(sys.argv[1])
