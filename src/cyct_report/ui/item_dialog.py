"""“添加检测项”对话框：从当前标准的检测项（含可选项）中挑选，或手动新建。"""
import tkinter as tk
from tkinter import messagebox, ttk

from ..models import Item, ml
from ..presets import render_cond


class AddItemDialog(tk.Toplevel):
    def __init__(self, master, pool, existing_keys, lang, tmax):
        super().__init__(master)
        self.title("添加检测项")
        self.transient(master)
        self.geometry("900x560")
        self.result = []
        self.lang, self.tmax = lang, tmax
        self.pool = [it for it in pool if it.kind == "item"]
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        nb.add(self._pool_page(nb, existing_keys), text="从标准中选择")
        nb.add(self._custom_page(nb), text="手动新建")
        self.nb = nb
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(bar, text="添加", command=self._ok).pack(side="right", padx=4)
        self.grab_set()

    def _pool_page(self, nb, existing_keys):
        f = ttk.Frame(nb)
        ttk.Label(f, text="可多选（Ctrl/Shift）。灰色为标准中的可选项；已在表中的项目标注“已有”。").pack(
            anchor="w", pady=4)
        cols = ("name", "cond", "req", "state")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="extended")
        for c, t, w in zip(cols, ("检测项目", "条件", "指标", ""), (460, 110, 220, 50)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, stretch=c == "name")
        self.tree.tag_configure("opt", foreground="#777")
        for i, it in enumerate(self.pool):
            have = (it.get("name", "en"), it.get("cond", "en")) in existing_keys
            self.tree.insert("", "end", iid=str(i), tags=("opt",) if it.opt else (), values=(
                it.get("name", self.lang), render_cond(it.get("cond", self.lang), self.tmax),
                it.get("req", self.lang), "已有" if have else ""))
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-Button-1>", lambda e: self._ok())
        return f

    def _custom_page(self, nb):
        f = ttk.Frame(nb, padding=12)
        self.entries = {}
        for r, (key, label) in enumerate((("name", "检测项目 *"), ("cond", "条件/温度"), ("unit", "单位"),
                                          ("req", "标准值（指标）"), ("method", "测试方法"))):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="e", padx=6, pady=6)
            e = ttk.Entry(f, width=70)
            e.grid(row=r, column=1, sticky="we", pady=6)
            self.entries[key] = e
        ttk.Label(f, foreground="#555", text=(
            "说明：手动新建的文字会用于所有语言的报告；如需三语不同，可在添加后切换语言逐一修改。\n"
            "上下标写法：10^14 为上标，R_S100 为下标。")).grid(row=6, column=0, columnspan=2,
                                                       sticky="w", pady=10)
        f.columnconfigure(1, weight=1)
        return f

    def _ok(self):
        if self.nb.index("current") == 0:
            self.result = [self.pool[int(i)].copy() for i in self.tree.selection()]
            for it in self.result:
                it.opt = False
            if not self.result:
                messagebox.showinfo("添加检测项", "请先选择要添加的检测项。", parent=self)
                return
        else:
            vals = {k: e.get().strip() for k, e in self.entries.items()}
            if not vals["name"]:
                messagebox.showinfo("添加检测项", "请填写检测项目名称。", parent=self)
                return
            self.result = [Item(name=ml(vals["name"]), cond=ml(vals["cond"]), unit=ml(vals["unit"]),
                                req=ml(vals["req"]), method=ml(vals["method"]))]
        self.destroy()
