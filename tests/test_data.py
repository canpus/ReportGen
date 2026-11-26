from datetime import date

import docx

from cyct_report import importer, paths
from cyct_report.db import Database
from cyct_report.docx_builder import build_docx
from cyct_report.models import Product, Report
from cyct_report.naming import report_stem, safe_name, unique_path
from cyct_report.presets import Library


def test_parse_lines_cn_and_en_layouts():
    cn = ["收货单位：合成星点测试设计工作室                   ",
          "产品规格：常温热缩带SIMQ137x410/2.1mm                     数   量： 30套   ",
          "执行标准：GB/T 23257-2017                                 生产批号：SIM001-39",
          "    检验员： 甲员       审  核： 乙员        日期：2032.05.14"]
    r = importer.parse_lines(cn)
    assert r["customer"] == "合成星点测试设计工作室"
    assert r["products"] == [["常温热缩带SIMQ137x410/2.1mm", "30套"]]
    assert (r["standard"], r["batch"], r["date"]) == ("GB/T 23257-2017", "SIM001-39", date(2032, 5, 14))
    en = ["Consignee：Mock Fixture",
          "Product Specifications：80℃ Heat Shrinkable sleeves SIMQΦ131x480x2.2mm Quantity： 173 sets",
          "Testing standards：ISO 21809-3 14B-2   Product batch：SIM001-41",
          "Inspector： Operator One      Auditor： Reviewer Two      Date： April 3,2032 "]
    r = importer.parse_lines(en)
    assert r["products"][0][1] == "173 sets" and r["date"] == date(2032, 4, 3)


def test_db_customers_ranked_and_report_query(tmp_path):
    db = Database(tmp_path / "t.db")
    for n in ["合成星点", "Mock Fixture", "合成星点", "星环样厂"]:
        db.touch_customer(n)
    assert db.customers()[0] == "合成星点"
    db.touch_customer("mock fixture")            # 不区分大小写，视为同一客户
    assert len(db.customers()) == 3
    db.add_report(customer="合成星点", products="热缩带", standard="GB/T 23257-2017", source="imported")
    db.add_report(customer="Mock Fixture", products="sleeve", standard="ISO 21809-3")
    assert [r["customer"] for r in db.query_reports("星")] == ["合成星点"]
    assert len(db.query_reports(source="imported")) == 1


def test_naming_is_safe_and_unique(tmp_path):
    stem = report_stem("A/B公司", [Product("SIMQ137x410/2.1mm")], "GB/T 23257", date(2032, 5, 14))
    assert "/" not in stem and stem.startswith("5.14A-B公司")
    p1 = unique_path(tmp_path, stem)
    p1.write_text("x")
    assert unique_path(tmp_path, stem).name.endswith("(2).docx")
    assert safe_name('  a:b*c?  ') == "a-b-c-"


def test_generated_docx_roundtrips_through_importer(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TEMPLATES_DIR", tmp_path)
    docx.Document().save(paths.template_file("en"))
    lib = Library()
    std, tpl = lib.standard("iso21809-3"), lib.template("iso21809-3", "14B-2")
    rep = Report(customer="Mock Fixture", lang="en", std_display="ISO 21809-3 14B-2", tmax="80",
                 products=[Product("Sleeve 6in", "10", "set", "T1"), Product("Sleeve 8in", "5", "set", "T1")],
                 items=lib.build_items(std, tpl), report_date=date(2032, 4, 3))
    out = build_docx(rep, tmp_path / "r.docx")
    assert len(docx.Document(str(out)).tables) == 1
    rec = importer.read_record(out)
    assert rec.customer == "Mock Fixture"
    assert [p[0] for p in rec.products] == ["Sleeve 6in", "Sleeve 8in"]
    assert rec.batch == "T1" and rec.content_date == date(2032, 4, 3)
