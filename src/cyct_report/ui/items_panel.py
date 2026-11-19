"""检测项表格：显示、实测值录入、增删改、上下移动、合格判定提示。"""
import itertools
import re
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ..checker import judge
from ..models import Item, ml, ml_set
from ..presets import render_cond
from .widgets import TreeEditor

COLUMNS = ("name", "cond", "unit", "req", "result", "judge", "method")
HEADINGS = {"name": "检测项目", "cond": "条件/温度", "unit": "单位", "req": "标准值（指标）",
            "result": "实测值", "judge": "判定", "method": "测试方法"}
WIDTHS = {"name": 300, "cond": 100, "unit": 70, "req": 170, "result": 120, "judge": 46, "method": 150}
_SUP_DIGITS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _sup(text):
    """界面显示用：10^14 → 10¹⁴（报告中由 docx_text 输出真正的上标）。"""
    return re.sub(r"\^\{?(-?\d+)\}?", lambda m: m.group(1).translate(_SUP_DIGITS), text or "")


class ItemsPanel(ttk.LabelFrame):
    def __init__(self, master, on_add_items, on_save_template, on_reset):
        super().__init__(master, text="检测项（单击“实测值”列直接录入，回车跳到下一项；双击其他列可修改）")
        self.lang, self.tmax = "zh", None
        self.items = {}                     # iid -> Item
        self._ids = itertools.count()
        self._build(on_add_items, on_save_template, on_reset)

    # ---------- 界面 ----------
    def _build(self, on_add_items, on_save_template, on_reset):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=4, pady=(2, 4))
        for text, cmd in (("添加检测项…", on_add_items), ("添加分组行", self.add_group),
                          ("删除", self.delete_selected), ("上移", lambda: self.move(-1)),
                          ("下移", lambda: self.move(1)), ("清空实测值", self.clear_results),
                          ("恢复默认检测项", on_reset), ("保存为自定义模板…", on_save_template)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)
        self.summary = ttk.Label(bar, foreground="#555")
        self.summary.pack(side="right", padx=6)

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings", selectmode="extended")
        for c in COLUMNS:
            self.tree.heading(c, text=HEADINGS[c])
            self.tree.column(c, width=WIDTHS[c], stretch=c in ("name", "req", "method"),
                             anchor="w" if c in ("name", "req", "method") else "center")
        sb = ttk.Scrollbar(frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("group", background="#e8eef7", font=("Microsoft YaHei UI", 9, "bold"))
        self.tree.tag_configure("fail", foreground="#c00000")
        self.tree.tag_configure("opt", foreground="#666666")
        self.editor = TreeEditor(self.tree, self._spec, self._get, self._commit, COLUMNS)
        self.tree.bind("<Button-1>", self._click)
        self.tree.bind("<Double-Button-1>", self._double_click)
        self.tree.bind("<Delete>", lambda e: self.delete_selected())

    def _col_at(self, x):
        col = self.tree.identify_column(x)
        return COLUMNS[int(col[1:]) - 1] if col else None

    def _click(self, e):
        iid, col = self.tree.identify_row(e.y), self._col_at(e.x)
        if iid and col == "result" and self.items[iid].kind == "item":
            self.tree.after(10, lambda: self.editor.edit(iid, "result"))

    def _double_click(self, e):
        iid, col = self.tree.identify_row(e.y), self._col_at(e.x)
        if iid and col and col != "result":
            self.editor.edit(iid, col)
            return "break"
        return None

    # ---------- 编辑 ----------
    def _spec(self, iid, col):
        it = self.items[iid]
        if col == "judge":
            return None
        if it.kind == "group":
            return "entry" if col == "name" else None
        return "entry"

    def _get(self, iid, col):
        it = self.items[iid]
        return it.result if col == "result" else it.get(col, self.lang)

    def _commit(self, iid, col, value):
        it = self.items[iid]
        if col == "result":
            it.result = value.strip()
        else:
            setattr(it, col, ml_set(getattr(it, col), self.lang, value))
        self._render_row(iid)
        self._update_summary()

    # ---------- 数据 ----------
    def set_items(self, items):
        self.editor.close(save=False)
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        for it in items:
            self._insert(it)
        self._update_summary()

    def get_items(self):
        self.editor.close(save=True)
        return [self.items[i] for i in self.tree.get_children()]

    def set_context(self, lang, tmax):
        self.lang, self.tmax = lang, tmax
        for iid in self.tree.get_children():
            self._render_row(iid)

    def _insert(self, it, index="end"):
        iid = f"i{next(self._ids)}"
        self.items[iid] = it
        self.tree.insert("", index, iid=iid)
        self._render_row(iid)
        return iid

    def _render_row(self, iid):
        it, lang = self.items[iid], self.lang
        if it.kind == "group":
            self.tree.item(iid, values=("【" + it.get("name", lang) + "】", "", "", "", "", "", ""),
                           tags=("group",))
            return
        ok = judge(it.get("req", lang), it.result)
        mark = {True: "✓", False: "✗", None: ""}[ok]
        values = (it.get("name", lang), render_cond(it.get("cond", lang), self.tmax),
                  it.get("unit", lang), _sup(it.get("req", lang)), _sup(it.result), mark,
                  it.get("method", lang).replace("\n", " "))
        tags = ("fail",) if ok is False else (("opt",) if it.opt else ())
        self.tree.item(iid, values=values, tags=tags)

    def _update_summary(self):
        items = [self.items[i] for i in self.tree.get_children() if self.items[i].kind == "item"]
        filled = sum(1 for i in items if i.result)
        fails = sum(1 for i in items if judge(i.get("req", self.lang), i.result) is False)
        text = f"共 {len(items)} 项，已录入 {filled} 项"
        if fails:
            text += f"，{fails} 项不符合指标"
        self.summary.configure(text=text, foreground="#c00000" if fails else "#555")

    def insert_items(self, items):
        sel = self.tree.selection()
        index = self.tree.index(sel[-1]) + 1 if sel else "end"
        new = []
        for it in items:
            new.append(self._insert(it, index))
            if index != "end":
                index += 1
        if new:
            self.tree.selection_set(new)
            self.tree.see(new[-1])
        self._update_summary()

    def add_group(self):
        name = simpledialog.askstring("添加分组行", "分组名称：", parent=self)
        if name:
            self.insert_items([Item(kind="group", name=ml(name), note=ml(""))])

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        if len(sel) > 1 and not messagebox.askyesno("删除", f"删除选中的 {len(sel)} 行？", parent=self):
            return
        for iid in sel:
            self.tree.delete(iid)
            self.items.pop(iid, None)
        self._update_summary()

    def move(self, step):
        sel = list(self.tree.selection())
        if not sel:
            return
        rows = self.tree.get_children()
        order = sel if step < 0 else reversed(sel)
        for iid in order:
            idx = rows.index(iid) + step
            if 0 <= idx < len(rows):
                self.tree.move(iid, "", idx)
                rows = self.tree.get_children()
        self.tree.see(sel[0])

    def clear_results(self):
        if messagebox.askyesno("清空实测值", "清空全部实测值？", parent=self):
            for iid, it in self.items.items():
                it.result = ""
                self._render_row(iid)
            self._update_summary()

    def has_results(self):
        return any(it.result for it in self.items.values())

    def existing_keys(self):
        return {(it.get("name", "en"), it.get("cond", "en")) for it in self.items.values()}
