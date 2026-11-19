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


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", text or ""))


def ml_set(d: dict, lang: str, text: str) -> dict:
    """修改某语言的文字。

    界面只改中文：新文字不含汉字（数值、符号，如 ≥5.0）时三语一起改；
    含汉字时，其他语言若原本就没有译文（与旧中文相同或为空）则跟着改，已有译文则保留。
    """
    old = d.get(lang, "")
    out = dict(d)
    out[lang] = text
    for other in LANGS:
        if other == lang:
            continue
        if (lang == "zh" and not has_cjk(text)) or d.get(other, "") in ("", old):
            out[other] = text
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
