import pytest

from cyct_report.checker import judge, parse_requirement
from cyct_report.search import filter_rank
from cyct_report.presets import Library, render_cond


@pytest.mark.parametrize("req,res,expected", [
    ("≥5.0", "21.01", True),
    ("≥5.0", "4.2", False),
    ("≤-65", "＜-65", True),
    ("≥7", "＞7", True),
    ("≥1×10^13", "2.12×10^14", True),
    ("≥10^8", "4.0x10^10", True),
    ("≥10^8", "4.0E7", False),
    ("1.25≥E₁₀₀/E₀≥0.75", "0.92", True),
    ("1.25≥E₁₀₀/E₀≥0.75", "1.30", False),
    ("0.75~1.25", "0,9", True),
    ("≥50/（内聚破坏）", "133内聚破坏", True),
    ("{text}", "", None),
    ("无漏点", "无漏点", True),
    ("no holiday", "pass", None),
    ("10.0", "10", None),          # 试验压力是条件，不判定
])
def test_judge(req, res, expected):
    assert judge(req, res) is expected


def test_parse_requirement_unbounded():
    assert parse_requirement("E₁₀₀/E₇₀≥0.8") == (0.8, None)


def test_fuzzy_search_multi_keyword_case_insensitive():
    names = ["四川盛创石油天然气工程勘察设计有限公司", "Petropipe FZE", "盛世管道", "Rigil Techno India"]
    assert filter_rank("盛", names) == ["盛世管道", "四川盛创石油天然气工程勘察设计有限公司"]
    assert filter_rank("四川 设计", names) == ["四川盛创石油天然气工程勘察设计有限公司"]
    assert filter_rank("PETRO fze", names) == ["Petropipe FZE"]
    assert filter_rank("四川 petro", names) == []


def test_render_cond_tokens():
    assert render_cond("23℃, Tmax", 80) == "23℃, 80℃"
    assert render_cond("Tmax95", 110) == "95℃"
    assert render_cond("Tmax+20/80", 50) == "80℃"
    assert render_cond("Tmax", None) == "Tmax"


def test_every_template_builds_without_unresolved_terms():
    lib = Library()
    for std in lib.standards:
        for tpl in std.templates:
            for it in lib.build_items(std, tpl, include_opt=True):
                for lang in ("zh", "en", "ru"):
                    for f in ("name", "cond", "unit", "req", "method", "note"):
                        assert "{" not in it.get(f, lang), (std.id, tpl.id, f, it.name)


def test_iso_14b2_values_match_table17():
    lib = Library()
    std = lib.standard("iso21809-3")
    items = lib.build_items(std, lib.template("iso21809-3", "14B-2"))
    reqs = {(i.get("name", "en"), i.get("cond", "en")): i.get("req", "en") for i in items}
    assert reqs[("Impact resistance (holiday detection at 5 kV/mm + 5 kV)", "23℃")] == "≥7"
    assert reqs[("Lap shear strength at 10 mm/min", "Tmax")] == "≥0.20"
    assert items[-1].kind == "item" and any(i.kind == "group" for i in items)


def test_en12068_class30_excludes_tmax_rows():
    lib = Library()
    std = lib.standard("en12068")
    items = lib.build_items(std, lib.template("en12068", "C3-30"))
    assert all(i.get("cond", "en") != "Tmax" for i in items)


def test_ml_set_chinese_edit_rules():
    from cyct_report.models import ml, ml_set
    preset = {"zh": "无漏点", "en": "No holiday", "ru": "Отсутствие пробоя"}
    assert ml_set(preset, "zh", "≥2.5") == ml("≥2.5")                     # 数值三语同步
    assert ml_set(preset, "zh", "无针孔")["en"] == "No holiday"            # 已有译文保留
    custom = ml("自定义项")
    assert ml_set(custom, "zh", "自定义项B")["en"] == "自定义项B"           # 无译文时跟随中文


def test_result_phrases_translated_and_untranslated_warning():
    from cyct_report.i18n import translate_result
    from cyct_report.models import Item, Report, ml
    from cyct_report.service import untranslated
    assert translate_result("133内聚破坏", "en") == "133 cohesive failure"
    assert translate_result("无漏点", "ru") == "Отсутствие пробоя"
    assert translate_result("无漏点", "zh") == "无漏点"
    known = Item(name={"zh": "厚度", "en": "Thickness", "ru": "Толщина"}, req=ml("≥2"), result="无漏点")
    custom = Item(name=ml("补伤片剥离强度"), req=ml("≥2"))
    rep = Report(lang="en", items=[known, custom])
    assert untranslated(rep) == ["补伤片剥离强度"]
