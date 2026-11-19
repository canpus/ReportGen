"""检测项表格：多列只读显示，只有“实测值”一列是输入框；界面一律显示中文。"""
import tkinter as tk
from tkinter import messagebox

from . import theme
from .item_edit_dialog import ItemEditDialog
from .items_row import COLUMNS, MIN_WIDTH, WEIGHTS, ItemRow
from .rounded import Button, Panel
from .scroll import ScrollTable


class ItemsPanel(tk.Frame):
    def __init__(self, master, on_add_items, on_save_template, on_reset):
        super().__init__(master, bg=theme.LANE)
        self.tmax = None
        self.rows = []
        bar = tk.Frame(self, bg=theme.LANE)
        bar.pack(fill="x", pady=(0, 8))
        tk.Label(bar, text="检测项", font=theme.TITLE, bg=theme.LANE, fg=theme.TEXT).pack(side="left")
        tk.Label(bar, text="在“实测值”列输入，回车跳到下一项；双击一行可修改该项",
                 font=theme.SMALL, bg=theme.LANE, fg=theme.MUTED).pack(side="left", padx=(10, 16))
        self.summary = tk.Label(bar, font=theme.SMALL, bg=theme.LANE, fg=theme.MUTED)
        self.summary.pack(side="right")
        tools = tk.Frame(self, bg=theme.LANE)
        tools.pack(fill="x", pady=(0, 8))
        for text, icon, cmd, kind in (
                ("添加检测项", "add", on_add_items, "ghost"), ("编辑", "edit", self.edit_selected, "ghost"),
                ("添加分组", "group", self.add_group, "ghost"), ("上移", "up", lambda: self.move(-1), "ghost"),
                ("下移", "down", lambda: self.move(1), "ghost"), ("删除", "delete", self.delete_selected, "danger"),
                ("清空实测值", "clear", self.clear_results, "ghost"), ("恢复默认", "reset", on_reset, "ghost")):
            Button(tools, text, cmd, kind=kind, icon=icon, padx=8, pady=4).pack(side="left", padx=(0, 2))
        Button(tools, "保存为自定义模板", on_save_template, kind="soft", icon="save", padx=10,
               pady=4).pack(side="right")

        card = Panel(self, fill=theme.CARD, outside=theme.LANE, radius=10, border=theme.LINE, pad=1)
        card.pack(fill="both", expand=True)
        self.table = ScrollTable(card.inner, COLUMNS, bg=theme.CARD, header_bg=theme.CARD)
        self.table.pack(fill="both", expand=True, padx=4, pady=(4, 6))
        for i, (title, _w, _wt) in enumerate(COLUMNS):
            tk.Label(self.table.header, text=title, bg=theme.CARD, fg=theme.MUTED, font=theme.BOLD,
                     anchor="w" if i == 1 else "center").grid(row=0, column=i, sticky="ew", padx=6, pady=(6, 4))
        tk.Frame(self.table.header, height=1, bg=theme.LINE).grid(row=1, column=0, columnspan=len(COLUMNS) + 1,
                                                                  sticky="ew")
        self.table.width_callbacks.append(self._on_width)
        self.name_width = COLUMNS[1][1]

    # ---------- 数据 ----------
    def set_items(self, items):
        for r in self.rows:
            r.frame.destroy()
        self.rows = [ItemRow(self, it) for it in items]
        self._relayout()
        self.table.to_top()

    def get_items(self):
        return [r.item for r in self.rows]

    def set_tmax(self, tmax):
        self.tmax = tmax
        self._refresh()

    def has_results(self):
        return any(r.item.result for r in self.rows if r.item.kind == "item")

    def existing_keys(self):
        return {(r.item.get("name", "en"), r.item.get("cond", "en")) for r in self.rows}

    # ---------- 布局 ----------
    def _relayout(self):
        for r in self.rows:
            r.frame.pack_forget()
        for r in self.rows:
            r.frame.pack(fill="x")
            r.set_name_width(self.name_width)
        self._refresh()

    def _refresh(self):
        seq = 0
        for r in self.rows:
            if r.item.kind == "item":
                seq += 1
            r.refresh(seq, self.tmax)
        self.update_summary()

    def _on_width(self, width):
        extra = max(width - MIN_WIDTH - 30, 0)
        self.name_width = COLUMNS[1][1] + extra * COLUMNS[1][2] // WEIGHTS
        for r in self.rows:
            r.set_name_width(self.name_width)

    def update_summary(self):
        items = [r for r in self.rows if r.item.kind == "item"]
        filled = sum(1 for r in items if r.item.result)
        fails = sum(1 for r in items if r.judge() is False)
        text = f"共 {len(items)} 项 · 已录入 {filled} 项"
        if fails:
            text += f" · {fails} 项不符合指标"
        self.summary.configure(text=text, fg=theme.FAIL if fails else theme.MUTED)

    # ---------- 选择与键盘 ----------
    def selected(self):
        return [r for r in self.rows if r.selected]

    def select_row(self, row, additive=False):
        for r in self.rows:
            if r is row:
                r.set_selected(not r.selected if additive else True)
            elif not additive:
                r.set_selected(False)

    def focus_next(self, row, step):
        i = self.rows.index(row) + step
        while 0 <= i < len(self.rows):
            if self.rows[i].entry is not None:
                self.rows[i].entry.focus_set()
                self.rows[i].entry.select_range(0, "end")
                return
            i += step

    # ---------- 操作 ----------
    def insert_items(self, items):
        sel = self.selected()
        index = self.rows.index(sel[-1]) + 1 if sel else len(self.rows)
        new = [ItemRow(self, it) for it in items]
        self.rows[index:index] = new
        self._relayout()
        for r in self.rows:
            r.set_selected(r in new)
        if new:
            self.after(50, lambda: self.table.see(new[-1].frame))

    def edit_row(self, row):
        self.select_row(row)
        dlg = ItemEditDialog(self, row.item)
        self.wait_window(dlg)
        if dlg.result:
            dlg.result.result = row.item.result
            i = self.rows.index(row)
            row.frame.destroy()
            self.rows[i] = ItemRow(self, dlg.result)
            self._relayout()
            self.rows[i].set_selected(True)

    def edit_selected(self):
        sel = self.selected()
        if sel:
            self.edit_row(sel[0])
        else:
            messagebox.showinfo("编辑", "请先单击选中要修改的一行。", parent=self)

    def add_group(self):
        dlg = ItemEditDialog(self, kind="group", title="添加分组")
        self.wait_window(dlg)
        if dlg.result:
            self.insert_items([dlg.result])

    def delete_selected(self):
        sel = self.selected()
        if not sel:
            messagebox.showinfo("删除", "请先单击选中要删除的行（按住 Ctrl 可多选）。", parent=self)
            return
        if not messagebox.askyesno("删除", f"删除选中的 {len(sel)} 行？", parent=self):
            return
        for r in sel:
            r.frame.destroy()
            self.rows.remove(r)
        self._refresh()

    def move(self, step):
        sel = self.selected()
        if not sel:
            return
        order = sel if step < 0 else list(reversed(sel))
        for r in order:
            i = self.rows.index(r)
            j = i + step
            if 0 <= j < len(self.rows) and not self.rows[j].selected:
                self.rows[i], self.rows[j] = self.rows[j], self.rows[i]
        self._relayout()
        self.table.see(sel[0].frame)

    def clear_results(self):
        if self.has_results() and messagebox.askyesno("清空实测值", "清空全部实测值？", parent=self):
            for r in self.rows:
                if r.var is not None:
                    r.var.set("")
