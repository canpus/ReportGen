"""生成报告的完整流程：docx → PDF → 写入数据库与记忆项。"""
from dataclasses import dataclass

from . import naming, office
from .db import Database
from .docx_builder import build_docx
from .i18n import qty_unit_text, translate_result
from .models import Report, has_cjk
from .settings import Settings


@dataclass
class GenerateResult:
    docx_path: str
    pdf_path: str = ""
    pdf_error: str = ""
    report_id: int = 0


def summarize(report: Report) -> dict:
    """历史记录里显示的产品、数量、批号文字。"""
    prods = report.products
    return {
        "products": "；".join(p.name for p in prods),
        "quantities": "；".join(f"{p.qty}{qty_unit_text(p.unit, 'zh')}" for p in prods if p.qty),
        "batches": "；".join(dict.fromkeys(p.batch for p in prods if p.batch)),
    }


def validate(report: Report) -> list:
    problems = []
    if not report.customer.strip():
        problems.append("请填写客户名")
    if not any(p.name.strip() for p in report.products):
        problems.append("请至少填写一个产品名称/规格")
    if not any(i.kind == "item" for i in report.items):
        problems.append("检测项为空")
    return problems


def untranslated(report: Report) -> list:
    """英/俄报告中仍会出现汉字的检测项（手动新建或改过中文、未补译文的项目）。"""
    if report.lang == "zh":
        return []
    out = []
    for it in report.items:
        fields = [it.get(f, report.lang) for f in ("name", "cond", "unit", "req", "method", "note")]
        fields.append(translate_result(it.result, report.lang))
        if any(has_cjk(f) for f in fields):
            out.append(it.get("name", "zh"))
    return out


def generate(report: Report, settings: Settings, db: Database) -> GenerateResult:
    report.products = [p for p in report.products if p.name.strip()]
    folder = naming.report_dir(settings.reports_dir(), report.customer, report.report_date)
    stem = naming.report_stem(report.customer, report.products, report.std_display,
                              report.report_date)
    docx_path = naming.unique_path(folder, stem)
    build_docx(report, docx_path)
    result = GenerateResult(docx_path=str(docx_path))
    if settings.get("make_pdf", True):
        pdf_path = docx_path.with_suffix(".pdf")
        try:
            office.docx_to_pdf(docx_path, pdf_path, settings.get("pdf_engine", "auto"))
            result.pdf_path = str(pdf_path)
        except Exception as e:          # PDF 失败不影响 docx，提示用户即可
            result.pdf_error = str(e)
    result.report_id = db.add_report(
        customer=report.customer.strip(), standard=report.std_display,
        standard_id=report.standard_id, template_id=report.template_id, lang=report.lang,
        report_date=report.report_date.isoformat(), source="generated",
        docx_path=result.docx_path, pdf_path=result.pdf_path,
        data_json=report.to_dict(), **summarize(report))
    db.touch_customer(report.customer)
    for p in report.products:
        db.touch_name("product", p.name)
    db.touch_name("inspector", report.inspector)
    db.touch_name("auditor", report.auditor)
    return result
