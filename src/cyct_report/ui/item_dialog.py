"""“添加检测项”对话框：从当前标准的全部检测项（含可选项）中挑选，或手动新建。"""
import tkinter as tk
from tkinter import messagebox, ttk

from . import theme
from ..presets import render_cond
from .item_edit_dialog import ItemEditDialog
from .items_row import sup


class AddItemDialog(tk.Toplevel):
    def __init__(self, master, pool, existing_keys, tmax):
        super().__init__(master)
        self.title("添加检测项")
        self.configure(bg=theme.LANE)
        self.transient(master)
        self.geometry("980x600")
        self.result = []
        self.pool = [it for it in pool if it.kind == "item"]
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="从标准中选择（可按住 Ctrl / Shift 多选，双击直接添加）", font=theme.TITLE,
                  foreground=theme.TEXT).pack(anchor="w")
        ttk.Label(body, style="Muted.TLabel", text="灰色字为标准中的可选项；“已在表中”表示当前报告里已有这一项。").pack(
            anchor="w", pady=(2, 8))
        frame = ttk.Frame(body)
        frame.pack(fill="both", expand=True)
        cols = ("name", "cond", "req", "state")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        for c, t, w in zip(cols, ("检测项目", "条件 / 温度", "标准值", ""), (520, 130, 200, 90)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, stretch=c == "name", anchor="w" if c == "name" else "center")
        self.tree.tag_configure("opt", foreground=theme.FAINT)
        for i, it in enumerate(self.pool):
            have = (it.get("name", "en"), it.get("cond", "en")) in existing_keys
            self.tree.insert("", "end", iid=str(i), tags=("opt",) if it.opt else (), values=(
                it.get("name", "zh"), render_cond(it.get("cond", "zh"), tmax), sup(it.get("req", "zh")),
                "已在表中" if have else ""))
        sb = ttk.Scrollbar(frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-Button-1>", lambda e: self._ok())
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text="手动新建检测项…", command=self._custom).pack(side="left")
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text="添加选中项", style="Accent.TButton", command=self._ok).pack(side="right")
        self.grab_set()

    def _ok(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("添加检测项", "请先选择要添加的检测项。", parent=self)
            return
        self.result = [self.pool[int(i)].copy() for i in sel]
        for it in self.result:
            it.opt = False
        self.destroy()

    def _custom(self):
        dlg = ItemEditDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self.result = [dlg.result]
            self.destroy()
