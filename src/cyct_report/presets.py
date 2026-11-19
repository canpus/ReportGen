"""预置标准库：读取 presets/*.json，按“标准 + 类型（模板）”生成检测项。

行格式见 presets/standards/*.json：
  {"g": 分组名, "note": 说明, "only": [适用列]}                 —— 分组行
  [名称, 条件, 单位, 指标, 方法, {"tc": [...], "opt": true}]      —— 检测项
字段可以是：含 {术语键} 的字符串 / 按列排列的列表（null 表示该列不适用）/ {zh,en,ru} 字典。
"""
import json
import re
import time
from dataclasses import dataclass, field

from . import paths
from .i18n import LANGS, localize_method, localize_unit, localize_standard_name
from .models import Item

CUSTOM_STD_ID = "custom"
_TERM = re.compile(r"\{([A-Za-z0-9_]+)\}")
_TMAX_TOKEN = re.compile(r"Tmax\+20/80|Tmax\+20|Tmax95|Tmax")


@dataclass
class Template:
    id: str
    label: dict
    parts: list = field(default_factory=list)
    tmax: object = None
    tc: str = ""
    display: object = ""
    custom: bool = False
    items: list = field(default_factory=list)   # 仅自定义模板使用（Item 字典）


@dataclass
class Standard:
    id: str
    name: str
    order: int = 100
    method_suffix: str = ""
    source: str = ""
    tables: dict = field(default_factory=dict)
    templates: list = field(default_factory=list)


def _fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def render_cond(cond: str, tmax) -> str:
    """把条件中的 Tmax 令牌替换为温度；未填 Tmax 时保留符号 Tmax。"""
    if tmax is None:
        return _TMAX_TOKEN.sub("Tmax", cond)

    def rep(m):
        tok = m.group()
        v = tmax
        if tok == "Tmax95":
            v = min(tmax, 95)
        elif tok == "Tmax+20":
            v = tmax + 20
        elif tok == "Tmax+20/80":
            v = max(tmax + 20, 80)
        return f"{_fmt_num(v)}℃"
    return _TMAX_TOKEN.sub(rep, cond)


class Library:
    def __init__(self):
        self.terms = {}
        self.standards = []
        self.reload()

    # ---------- 加载 ----------
    def reload(self):
        with open(paths.TERMS_FILE, encoding="utf-8") as f:
            self.terms = json.load(f)
        stds = []
        for p in sorted(paths.STANDARDS_DIR.glob("*.json")):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            tpls = [Template(id=t["id"], label=t["label"], parts=t.get("parts", []),
                             tmax=t.get("tmax"), tc=t.get("tc", ""),
                             display=t.get("display", d["name"]))
                    for t in d.get("templates", [])]
            stds.append(Standard(id=d["id"], name=d["name"], order=d.get("order", 100),
                                 method_suffix=d.get("method_suffix", ""),
                                 source=d.get("source", ""), tables=d.get("tables", {}),
                                 templates=tpls))
        stds.sort(key=lambda s: s.order)
        stds.append(Standard(id=CUSTOM_STD_ID, name="自定义 / Custom", order=999,
                             templates=[Template(id="blank", label={
                                 "zh": "空白模板（手动添加检测项）", "en": "Blank template",
                                 "ru": "Пустой шаблон"}, display="")]))
        self.standards = stds
        self._load_custom()

    def _custom_file(self):
        return paths.data_dir() / "custom_templates.json"

    def _load_custom(self):
        f = self._custom_file()
        if not f.exists():
            return
        data = json.loads(f.read_text(encoding="utf-8"))
        for t in data.get("templates", []):
            std = self.standard(t["standard_id"]) or self.standard(CUSTOM_STD_ID)
            std.templates.append(Template(id=t["id"], label=t["label"], tmax=t.get("tmax"),
                                          tc=t.get("tc", ""), display=t.get("display", ""),
                                          custom=True, items=t.get("items", [])))

    def save_custom(self, standard_id: str, name: str, tmax, tc: str, display, items):
        """把当前检测项保存为自定义模板，返回新模板 id。"""
        f = self._custom_file()
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"templates": []}
        tid = "custom-" + time.strftime("%Y%m%d%H%M%S")
        data["templates"].append({
            "standard_id": standard_id, "id": tid,
            "label": {lang: "★ " + name for lang in LANGS},
            "tmax": tmax, "tc": tc, "display": display,
            "items": [i.to_dict() for i in items]})
        f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        self.reload()
        return tid

    def delete_custom(self, tid: str):
        f = self._custom_file()
        if not f.exists():
            return
        data = json.loads(f.read_text(encoding="utf-8"))
        data["templates"] = [t for t in data["templates"] if t["id"] != tid]
        f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        self.reload()

    # ---------- 查询 ----------
    def standard(self, sid: str):
        return next((s for s in self.standards if s.id == sid), None)

    def template(self, sid: str, tid: str):
        std = self.standard(sid)
        return next((t for t in std.templates if t.id == tid), None) if std else None

    def display(self, tpl: Template, lang: str, tmax) -> str:
        d = tpl.display
        text = d.get(lang) or d.get("en", "") if isinstance(d, dict) else (d or "")
        text = text.replace("{tmax}", _fmt_num(tmax) if tmax is not None else "")
        return localize_standard_name(text, lang)

    # ---------- 文字解析 ----------
    def term(self, key: str, lang: str) -> str:
        t = self.terms.get(key)
        if not isinstance(t, dict):
            return "{" + key + "}"
        return t.get(lang) or t.get("en") or t.get("zh", "")

    def resolve(self, value, col, lang):
        """返回指定列、指定语言的文字；该列不适用时返回 None。"""
        if isinstance(value, list):
            value = value[col] if col is not None and col < len(value) else value[0]
        if value is None:
            return None
        if isinstance(value, dict):
            value = value.get(lang) or value.get("en") or value.get("zh", "")
        return _TERM.sub(lambda m: self.term(m.group(1), lang), str(value))

    # ---------- 生成检测项 ----------
    def build_items(self, std: Standard, tpl: Template, include_opt: bool = False) -> list:
        if tpl.custom:
            return [Item.from_dict(d) for d in tpl.items]
        items = []
        for table_ref, col_name in tpl.parts:
            owner, table = self._table(std, table_ref)
            items.extend(self._rows(std, owner, table, col_name, tpl.tc, include_opt))
        return _drop_empty_groups(items)

    def _table(self, std, ref):
        if ":" in ref:
            sid, tname = ref.split(":", 1)
            other = self.standard(sid)
            return other, other.tables[tname]
        return std, std.tables[ref]

    def _rows(self, std, owner, table, col_name, tc, include_opt):
        cols = table.get("cols", [])
        col = cols.index(col_name) if col_name in cols else None
        out = []
        for row in table["rows"]:
            if isinstance(row, dict):
                if "only" in row and col_name not in row["only"]:
                    continue
                g = Item(kind="group")
                g.name = {l: self.resolve(row["g"], col, l) for l in LANGS}
                g.note = {l: self.resolve(row.get("note", ""), col, l) for l in LANGS}
                out.append(g)
                continue
            opts = row[5] if len(row) > 5 else {}
            if opts.get("tc") and tc and tc not in opts["tc"]:
                continue
            if opts.get("opt") and not include_opt:
                continue
            if self.resolve(row[3], col, "en") is None:
                continue
            out.append(self._make_item(std, owner, row, col, tc, bool(opts.get("opt"))))
        return out

    def _make_item(self, std, owner, row, col, tc, opt):
        it = Item(opt=opt)
        # 引用他标准的表格时，本标准未设后缀则沿用被引用标准的后缀
        suffix = std.method_suffix or owner.method_suffix
        for lang in LANGS:
            name, cond, unit, req, method = (self.resolve(v, col, lang) or "" for v in row[:5])
            if cond == "Tc":
                cond = "23℃" if tc == "30" else "Tmax"
            raw_method = self.resolve(row[4], col, "en") or ""
            method = localize_method(method, lang)
            if suffix and raw_method.startswith("Annex"):
                method += "\n" + suffix
            it.name[lang], it.cond[lang], it.req[lang], it.method[lang] = name, cond, req, method
            it.unit[lang] = localize_unit(unit, lang)
        return it


def _drop_empty_groups(items):
    out = []
    for i, it in enumerate(items):
        if it.kind == "group":
            nxt = items[i + 1] if i + 1 < len(items) else None
            if nxt is None or nxt.kind == "group":
                continue
        out.append(it)
    return out
