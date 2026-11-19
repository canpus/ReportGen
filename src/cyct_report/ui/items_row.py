"""检测项表格中的一行：只读文字 + “实测值”小输入框 + 判定标记。"""
import re
import tkinter as tk
from tkinter import ttk

from . import theme
from ..checker import judge
from ..presets import render_cond

# (标题, 最小宽度, 伸展权重)：宽屏时多出的宽度按权重分给项目、条件、标准值、方法
COLUMNS = [("序号", 46, 0), ("检测项目", 240, 5), ("条件 / 温度", 112, 1), ("单位", 74, 0),
           ("标准值", 160, 2), ("实测值", 136, 0), ("判定", 50, 0), ("测试方法", 160, 2)]
MIN_WIDTH = sum(w for _t, w, _wt in COLUMNS)
WEIGHTS = sum(wt for _t, _w, wt in COLUMNS)
_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def sup(text):
    """界面显示：10^14 → 10¹⁴，R_S100 → RS100（报告中输出真正的上下标）。"""
    text = re.sub(r"\^\{?(-?\d+)\}?", lambda m: m.group(1).translate(_SUP), text or "")
    return re.sub(r"_\{?([A-Za-z0-9]+)\}?", lambda m: m.group(1), text)


class ItemRow:
    def __init__(self, panel, item):
        self.panel, self.item = panel, item
        self.frame = tk.Frame(panel.table.body, bg=theme.CARD)
        panel.table.layout(self.frame)
        self.labels, self.entry, self.var = [], None, None
        self.selected = False
        if item.kind == "group":
            self._build_group()
        else:
            self._build_item()
        tk.Frame(self.frame, height=1, bg=theme.ROW_LINE).grid(
            row=1, column=0, columnspan=len(COLUMNS), sticky="ew")
        for w in [self.frame] + self.labels:
            w.bind("<Button-1>", self._click)
            w.bind("<Double-Button-1>", lambda e: panel.edit_row(self))

    def _label(self, col, text="", anchor="w", wrap=0, **kw):
        lbl = tk.Label(self.frame, text=text, bg=self.bg, fg=kw.pop("fg", theme.TEXT_BODY), anchor=anchor,
                       justify="left" if anchor == "w" else "center", wraplength=wrap,
                       font=kw.pop("font", theme.BASE), **kw)
        lbl.grid(row=0, column=col, sticky="nsew", padx=6, pady=5)
        self.labels.append(lbl)
        return lbl

    @property
    def bg(self):
        if self.selected:
            return theme.SELECTED
        return theme.GROUP_BG if self.item.kind == "group" else theme.CARD

    def _build_group(self):
        it = self.item
        text = it.get("name", "zh") + ("    " + it.get("note", "zh") if it.get("note", "zh") else "")
        lbl = tk.Label(self.frame, text=text, bg=self.bg, fg=theme.TEXT, anchor="w", justify="left",
                       font=theme.BOLD, wraplength=900)
        lbl.grid(row=0, column=0, columnspan=len(COLUMNS), sticky="nsew", padx=8, pady=6)
        self.labels.append(lbl)
        self.name_label = lbl

    def _build_item(self):
        it = self.item
        self.seq = self._label(0, "", anchor="center", fg=theme.FAINT, font=theme.SMALL)
        self.name_label = self._label(1, it.get("name", "zh"), wrap=COLUMNS[1][1])
        self.cond = self._label(2, "", anchor="center")
        self._label(3, it.get("unit", "zh"), anchor="center")
        self._label(4, sup(it.get("req", "zh")), anchor="center", wrap=COLUMNS[4][1] - 12)
        cell = tk.Frame(self.frame, bg=self.bg)
        cell.grid(row=0, column=5, sticky="nsew", padx=6, pady=3)
        self.cell = cell
        self.var = tk.StringVar(value=it.result)
        self.entry = ttk.Entry(cell, textvariable=self.var, width=12, justify="center")
        self.entry.pack(anchor="center", expand=True)
        self.var.trace_add("write", lambda *a: self._changed())
        self.entry.bind("<Return>", lambda e: self.panel.focus_next(self, 1) or "break")
        self.entry.bind("<Down>", lambda e: self.panel.focus_next(self, 1) or "break")
        self.entry.bind("<Up>", lambda e: self.panel.focus_next(self, -1) or "break")
        self.entry.bind("<FocusIn>", lambda e: self.panel.table.see(self.frame))
        self.mark = self._label(6, "", anchor="center", font=theme.BOLD)
        self._label(7, it.get("method", "zh").replace("\n", " "), anchor="center",
                    wrap=COLUMNS[7][1] - 12, fg=theme.MUTED, font=theme.SMALL)
        self._changed(notify=False)

    def _click(self, e):
        self.panel.select_row(self, additive=bool(e.state & 0x0004))

    def _changed(self, notify=True):
        self.item.result = self.var.get().strip()
        ok = judge(self.item.get("req", "zh"), self.item.result)
        self.mark.configure(text={True: "✓", False: "✗", None: ""}[ok],
                            fg=theme.OK if ok else theme.FAIL)
        self.entry.configure(style="Fail.TEntry" if ok is False else "TEntry")
        if notify:
            self.panel.update_summary()

    # ---------- 由面板调用 ----------
    def refresh(self, seq, tmax):
        if self.item.kind == "item":
            self.seq.configure(text=str(seq))
            self.cond.configure(text=render_cond(self.item.get("cond", "zh"), tmax))

    def set_selected(self, selected):
        self.selected = selected
        self.frame.configure(bg=self.bg)
        for w in self.labels:
            w.configure(bg=self.bg)
        if self.item.kind == "item":
            self.cell.configure(bg=self.bg)

    def set_name_width(self, width):
        self.name_label.configure(wraplength=max(width - 12, 120) if self.item.kind == "item" else 0)

    def judge(self):
        return judge(self.item.get("req", "zh"), self.item.result) if self.item.kind == "item" else None
