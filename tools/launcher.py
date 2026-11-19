"""打包入口。

CYCTReport.exe --selftest ：生成一份示例报告并转 PDF，结果写入 data/selftest/result.txt，
用于在新电脑上确认 Word/WPS 后台转换是否可用。
"""
import sys


def selftest():
    import traceback
    from cyct_report import office, paths
    from cyct_report.docx_builder import build_docx
    from cyct_report.models import Product, Report
    from cyct_report.presets import Library
    from cyct_report.settings import Settings

    out = paths.data_dir() / "selftest"
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    try:
        lib = Library()
        std, tpl = lib.standard("iso21809-3"), lib.template("iso21809-3", "14B-2")
        for lang in ("zh", "en", "ru"):
            rep = Report(customer="SELFTEST", lang=lang, std_display=lib.display(tpl, lang, 80),
                         tmax="80", products=[Product("FRDP 159x600x2.3", "1", "set", "T0")],
                         items=lib.build_items(std, tpl))
            d = build_docx(rep, out / f"selftest_{lang}.docx")
            used = office.docx_to_pdf(d, d.with_suffix(".pdf"), Settings().get("pdf_engine", "auto"))
            lines.append(f"{lang}: OK ({used})")
    except Exception:
        lines.append(traceback.format_exc())
    (out / "result.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        from cyct_report.ui.app import main
        main()
