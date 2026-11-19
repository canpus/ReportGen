"""开发用：用样本报告的数据生成中/英/俄报告并转 PDF、PNG，便于与原报告对照版式。

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

GB_RESULTS = ["98.4", "6.7", "3.3", "4.0", "20.2", "587", "94.7", "＜-65", "28.2", "2.12×10^14",
              "＞1000", "97", "98", "94", "18.3", "513", "无裂纹、无流淌、无垂滴", "100", "3.02",
              "0.33", "2.77", "0.37", "＜-15", "＞15", "133内聚破坏", "6.5内聚破坏", "137内聚破坏",
              "5.9内聚破坏", "8.2", "86/内聚破坏", "87/内聚破坏", "无鼓泡、无剥离、膜下无水", "92", "92"]


def make(lib, sid, tid, lang, customer, products, results=None):
    std, tpl = lib.standard(sid), lib.template(sid, tid)
    items = lib.build_items(std, tpl)
    vals = iter(results or [])
    for it in items:
        if it.kind == "item":
            it.result = next(vals, "")
    return Report(customer=customer, lang=lang, standard_id=sid, template_id=tid,
                  std_display=lib.display(tpl, lang, tpl.tmax), tmax=str(tpl.tmax or ""),
                  tc=tpl.tc, products=products, items=items, inspector="杨浩斌" if lang == "zh" else "Yanghaobin",
                  auditor="左明龙" if lang == "zh" else "Minglong Zuo", report_date=date(2026, 9, 1))


def main(out):
    out = Path(out)
    lib = Library()
    cases = [
        ("zh-gb", make(lib, "gbt23257", "hs", "zh", "四川盛创石油天然气工程勘察设计有限公司",
                       [Product("常温热缩带FRDP406x520/2.5mm", "30", "set", "T260103-39")], GB_RESULTS)),
        ("en-iso", make(lib, "iso21809-3", "14B-2", "en", "Petropipe FZE",
                        [Product("80℃ Heat Shrinkable sleeves FRDPΦ159（6inch)x600x2.3mm", "2615", "set",
                                 "T250103-41")], ["2.3", "no holiday", "＞7", "10", "1.22", "3.2", "5.9"])),
        ("ru-iso", make(lib, "iso21809-3", "14B-2", "ru", "ТОО «Пример»",
                        [Product("Термоусаживающаяся манжета FRDP Φ159x600x2.3", "100", "set", "T1"),
                         Product("Термоусаживающаяся манжета FRDP Φ219x600x2.3", "50", "set", "T2")])),
        ("en-en12068", make(lib, "en12068", "C3-HT", "en", "Rigil Techno India Pvt. Ltd.",
                            [Product(f"80℃FRDP heat shrink sleeve {d}inchx430x2.7mm", "300", "set", "T260130-1")
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
