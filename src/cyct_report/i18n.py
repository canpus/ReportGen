"""报告用固定文字、单位、日期格式的三语映射。"""
import re
from datetime import date

LANGS = ("zh", "en", "ru")
LANG_NAMES = {"zh": "中文", "en": "English", "ru": "Русский"}

LABELS = {
    "zh": {
        "consignee": "收货单位", "product": "产品规格", "qty": "数    量",
        "standard": "执行标准", "batch": "生产批号",
        "inspector": "检验员", "auditor": "审  核", "date": "日期",
        "header": ["项 目", "", "单 位", "性能指标", "测试结果", "测试方法"],
        "colon": "：",
    },
    "en": {
        "consignee": "Consignee", "product": "Product Specifications", "qty": "Quantity",
        "standard": "Testing standards", "batch": "Product batch",
        "inspector": "Inspector", "auditor": "Auditor", "date": "Date",
        "header": ["Property", "Test temp.", "Unit", "Requirement", "Test result", "Test method"],
        "colon": ": ",
    },
    "ru": {
        "consignee": "Получатель", "product": "Продукция", "qty": "Количество",
        "standard": "Стандарт испытаний", "batch": "Номер партии",
        "inspector": "Испытал", "auditor": "Проверил", "date": "Дата",
        "header": ["Показатель", "Условия", "Ед. изм.", "Требование",
                   "Результат", "Метод испытания"],
        "colon": ": ",
    },
}

# 数量单位：键 → 三语显示
QTY_UNITS = {
    "set": {"zh": "套", "en": "sets", "ru": "компл."},
    "roll": {"zh": "卷", "en": "rolls", "ru": "рул."},
    "pc": {"zh": "片", "en": "pcs", "ru": "шт."},
    "stick": {"zh": "支", "en": "sticks", "ru": "шт."},
    "m2": {"zh": "m²", "en": "m²", "ru": "м²"},
    "m": {"zh": "m", "en": "m", "ru": "м"},
    "kg": {"zh": "kg", "en": "kg", "ru": "кг"},
}

# 俄文报告中的单位写法（单位字段整体匹配时替换）
RU_UNITS = {
    "mm": "мм", "J": "Дж", "J/mm": "Дж/мм", "N/mm": "Н/мм", "N/mm²": "Н/мм²",
    "N/cm": "Н/см", "N/cm²": "Н/см²", "N": "Н", "MPa": "МПа", "cm²": "см²",
    "Ω·m²": "Ом·м²", "Ω·m": "Ом·м", "kV/mm": "кВ/мм", "kV": "кВ", "h": "ч",
    "min": "мин", "g/cm³": "г/см³", "MV/m": "МВ/м", "mg KOH/g": "мг КОН/г",
}

MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]


# 实测值中常见的中文写法 → 英/俄（生成英俄报告时自动替换，长词在前）
RESULT_PHRASES = [
    ("无裂纹、无流淌、无垂滴", "No cracks, no flow, no dripping", "Без трещин, потёков и капель"),
    ("无鼓泡、无剥离、膜下无水", "No blistering, no disbondment, no water under film",
     "Без вздутий и отслаивания, без воды под плёнкой"),
    ("无分离、撕裂或裂纹", "No separation, tears or cracks", "Без отслаивания, разрывов и трещин"),
    ("不合格", "Fail", "Не выдержано"),
    ("合格", "Pass", "Выдержано"),
    ("无漏点", "No holiday", "Отсутствие пробоя"),
    ("无击穿", "No breakdown", "Без пробоя"),
    ("内聚破坏", "cohesive failure", "когезионный отрыв"),
    ("界面破坏", "adhesive failure", "адгезионный отрыв"),
    ("无裂纹", "No cracks", "Без трещин"),
    ("无滴落", "No dripping", "Без стекания"),
    ("无缺陷", "No defect", "Без дефектов"),
    ("无结晶", "No crystallization", "Без кристаллизации"),
]


def translate_result(text: str, lang: str) -> str:
    if lang == "zh" or not text:
        return text
    idx = 1 if lang == "en" else 2
    for phrase in RESULT_PHRASES:
        # 紧跟数字或字母时补一个空格：133内聚破坏 → 133 cohesive failure
        text = re.sub(r"(?<=[0-9A-Za-z.])" + re.escape(phrase[0]), " " + phrase[idx], text)
        text = text.replace(phrase[0], phrase[idx])
    return text


def qty_unit_text(key: str, lang: str) -> str:
    u = QTY_UNITS.get(key)
    return u[lang] if u else key


def qty_unit_key(text: str) -> str:
    """把任意语言的单位文字还原为键；不认识的原样返回。"""
    for k, v in QTY_UNITS.items():
        if text == k or text in v.values():
            return k
    return text


def format_date(d: date, lang: str) -> str:
    if lang == "zh":
        return f"{d.year}.{d.month:02d}.{d.day:02d}"
    if lang == "en":
        return f"{MONTHS_EN[d.month - 1]} {d.day}, {d.year}"
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def localize_unit(unit: str, lang: str) -> str:
    if lang == "ru":
        return RU_UNITS.get(unit, unit)
    return unit


_ANNEX = re.compile(r"\bAnnex\s+")
_SECTION = re.compile(r"\bSection\s+([\d.]+)")


def localize_method(method: str, lang: str) -> str:
    """标准方法列中“Annex X / Section x / ГОСТ”的本地化。"""
    if lang == "zh":
        method = _ANNEX.sub("附录", method)
        method = _SECTION.sub(r"第\1条", method)
        method = method.replace("Visual", "目视")
    elif lang == "ru":
        method = _ANNEX.sub("Приложение ", method)
        method = _SECTION.sub(r"Раздел \1", method)
        method = method.replace("Visual", "Визуально")
    if lang != "ru":
        method = method.replace("ГОСТ Р", "GOST R").replace("ГОСТ", "GOST")
    return method


def localize_standard_name(text: str, lang: str) -> str:
    if lang != "ru":
        return text.replace("ГОСТ Р", "GOST R").replace("ГОСТ", "GOST")
    return text
