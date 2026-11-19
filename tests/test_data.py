from datetime import date

import docx

from cyct_report import importer
from cyct_report.db import Database
from cyct_report.docx_builder import build_docx
from cyct_report.models import Product, Report
from cyct_report.naming import report_stem, safe_name, unique_path
from cyct_report.presets import Library


def test_parse_lines_cn_and_en_layouts():
    cn = ["收货单位：四川盛创石油天然气工程勘察设计有限公司                   ",
          "产品规格：常温热缩带FRDP406x520/2.5mm                     数   量： 30套   ",
          "执行标准：GB/T 23257-2017                                 生产批号：T260103-39",
          "    检验员： 杨浩斌       审  核： 左明龙        日期：2026.09.01"]
    r = importer.parse_lines(cn)
    assert r["customer"] == "四川盛创石油天然气工程勘察设计有限公司"
    assert r["products"] == [["常温热缩带FRDP406x520/2.5mm", "30套"]]
    assert (r["standard"], r["batch"], r["date"]) == ("GB/T 23257-2017", "T260103-39", date(2026, 9, 1))
    en = ["Consignee：Petropipe FZE",
          "Product Specifications：80℃ Heat Shrinkable sleeves FRDPΦ159x600x2.3mm Quantity： 2615 sets",
          "Testing standards：ISO 21809-3 14B-2   Product batch：T250103-41",
          "Inspector： Yanghaobin      Auditor： Minglong Zuo      Date： August 5,2026 "]
    r = importer.parse_lines(en)
    assert r["products"][0][1] == "2615 sets" and r["date"] == date(2026, 8, 5)


def test_db_customers_ranked_and_report_query(tmp_path):
    db = Database(tmp_path / "t.db")
    for n in ["四川盛创", "Petropipe FZE", "四川盛创", "盛世管道"]:
        db.touch_customer(n)
    assert db.customers()[0] == "四川盛创"
    db.touch_customer("petropipe fze")            # 不区分大小写，视为同一客户
    assert len(db.customers()) == 3
    db.add_report(customer="四川盛创", products="热缩带", standard="GB/T 23257-2017", source="imported")
    db.add_report(customer="Petropipe FZE", products="sleeve", standard="ISO 21809-3")
    assert [r["customer"] for r in db.query_reports("盛")] == ["四川盛创"]
    assert len(db.query_reports(source="imported")) == 1


def test_naming_is_safe_and_unique(tmp_path):
    stem = report_stem("A/B公司", [Product("FRDP406x520/2.5mm")], "GB/T 23257", date(2026, 9, 1))
    assert "/" not in stem and stem.startswith("9.1A-B公司")
    p1 = unique_path(tmp_path, stem)
    p1.write_text("x")
    assert unique_path(tmp_path, stem).name.endswith("(2).docx")
    assert safe_name('  a:b*c?  ') == "a-b-c-"


def test_generated_docx_roundtrips_through_importer(tmp_path):
    lib = Library()
    std, tpl = lib.standard("iso21809-3"), lib.template("iso21809-3", "14B-2")
    rep = Report(customer="Petropipe FZE", lang="en", std_display="ISO 21809-3 14B-2", tmax="80",
                 products=[Product("Sleeve 6in", "10", "set", "T1"), Product("Sleeve 8in", "5", "set", "T1")],
                 items=lib.build_items(std, tpl), report_date=date(2026, 8, 5))
    out = build_docx(rep, tmp_path / "r.docx")
    assert len(docx.Document(str(out)).tables) == 1
    rec = importer.read_record(out)
    assert rec.customer == "Petropipe FZE"
    assert [p[0] for p in rec.products] == ["Sleeve 6in", "Sleeve 8in"]
    assert rec.batch == "T1" and rec.content_date == date(2026, 8, 5)
