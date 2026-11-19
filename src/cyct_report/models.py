"""报告数据结构。文本字段一律保存为 {zh, en, ru} 三语字典。"""
from dataclasses import dataclass, field, asdict
from datetime import date
import re

from .i18n import LANGS

TEXT_FIELDS = ("name", "cond", "unit", "req", "method", "note")


def ml(text: str = "") -> dict:
    """同一文字填入三种语言。"""
    return {lang: text for lang in LANGS}


def ml_get(d: dict, lang: str) -> str:
    if not d:
        return ""
    for k in (lang, "en", "zh", "ru"):
        if d.get(k):
            return d[k]
    return ""


def ml_set(d: dict, lang: str, text: str) -> dict:
    """编辑某语言的文字：若该字段原本三语相同（与语言无关的数值、符号），三语一起改。"""
    if len(set(d.values())) <= 1:
        return ml(text)
    out = dict(d)
    out[lang] = text
    return out


@dataclass
class Item:
    kind: str = "item"            # item | group
    name: dict = field(default_factory=ml)
    cond: dict = field(default_factory=ml)
    unit: dict = field(default_factory=ml)
    req: dict = field(default_factory=ml)
    method: dict = field(default_factory=ml)
    note: dict = field(default_factory=ml)   # 分组行的说明文字
    result: str = ""
    opt: bool = False             # 标准中的可选项（默认不列出）

    def get(self, fld: str, lang: str) -> str:
        return ml_get(getattr(self, fld), lang)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    def copy(self) -> "Item":
        return Item.from_dict(self.to_dict())


@dataclass
class Product:
    name: str = ""
    qty: str = ""
    unit: str = "set"
    batch: str = ""


@dataclass
class Report:
    customer: str = ""
    lang: str = "zh"
    standard_id: str = ""
    template_id: str = ""
    std_display: str = ""
    tmax: str = ""
    tc: str = ""
    products: list = field(default_factory=list)   # list[Product]
    items: list = field(default_factory=list)      # list[Item]
    inspector: str = ""
    auditor: str = ""
    report_date: date = field(default_factory=date.today)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["report_date"] = self.report_date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Report":
        r = cls(**{k: d[k] for k in cls.__dataclass_fields__
                   if k in d and k not in ("products", "items", "report_date")})
        r.products = [Product(**p) for p in d.get("products", [])]
        r.items = [Item.from_dict(i) for i in d.get("items", [])]
        if d.get("report_date"):
            r.report_date = date.fromisoformat(d["report_date"])
        return r

    def tmax_value(self):
        m = re.search(r"-?\d+(?:\.\d+)?", str(self.tmax or ""))
        return float(m.group()) if m else None
