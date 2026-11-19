"""检测项编辑 / 手动新建对话框。界面只填中文；英文、俄文名称可选，留空则报告沿用原译文或中文。"""
import tkinter as tk
from tkinter import messagebox, ttk

from . import theme
from ..models import Item, has_cjk, ml, ml_set

ITEM_FIELDS = (("name", "检测项目 *"), ("cond", "条件 / 温度"), ("unit", "单位"),
               ("req", "标准值（指标）"), ("method", "测试方法"))
GROUP_FIELDS = (("name", "分组名称 *"), ("note", "说明（可空）"))


def _flat(text):
    """单行输入框里显示：把换行换成空格。"""
    return (text or "").replace(chr(10), " ")


class ItemEditDialog(tk.Toplevel):
    def __init__(self, master, item=None, kind="item", title=None):
        super().__init__(master)
        self.item = item.copy() if item else Item(kind=kind, name=ml(""), note=ml(""))
        self.result = None
        group = self.item.kind == "group"
        self.title(title or ("编辑分组" if group else ("编辑检测项" if item else "新建检测项")))
        self.configure(bg=theme.LANE)
        self.transient(master)
        self.resizable(False, False)
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        self.vars = {}
        fields = GROUP_FIELDS if group else ITEM_FIELDS
        for r, (key, label) in enumerate(fields):
            ttk.Label(body, text=label, style="Field.TLabel").grid(row=r, column=0, sticky="e", padx=(0, 10), pady=5)
            var = tk.StringVar(value=_flat(self.item.get(key, "zh")))
            ttk.Entry(body, textvariable=var, width=58).grid(row=r, column=1, sticky="we", pady=5)
            self.vars[key] = var
        r = len(fields)
        ttk.Separator(body).grid(row=r, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Label(body, style="Muted.TLabel", text=(
            "以下两项只影响英文 / 俄文报告，可不填：不填时沿用已有译文；新建的项目会显示中文。")).grid(
            row=r + 1, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.trans = {}
        for i, (lang, label) in enumerate((("en", "英文名称"), ("ru", "俄文名称"))):
            cur = self.item.name.get(lang, "")
            var = tk.StringVar(value="" if cur == self.item.name.get("zh") or has_cjk(cur) else cur)
            ttk.Label(body, text=label, style="Field.TLabel").grid(row=r + 2 + i, column=0, sticky="e",
                                                                   padx=(0, 10), pady=5)
            ttk.Entry(body, textvariable=var, width=58).grid(row=r + 2 + i, column=1, sticky="we", pady=5)
            self.trans[lang] = var
        bar = ttk.Frame(body)
        bar.grid(row=r + 4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text="确定", style="Accent.TButton", command=self._ok).pack(side="right")
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def _ok(self):
        values = {k: v.get().strip() for k, v in self.vars.items()}
        if not values["name"]:
            messagebox.showinfo(self.title(), "请填写名称。", parent=self)
            return
        it = self.item
        for key, text in values.items():
            if text == _flat(self.item.get(key, "zh")).strip():
                continue          # 没改动的字段原样保留（含测试方法里的换行与译文）
            setattr(it, key, ml_set(getattr(it, key) or ml(""), "zh", text))
        for lang, var in self.trans.items():
            if var.get().strip():
                it.name[lang] = var.get().strip()
        self.result = it
        self.destroy()
