"""通用控件：联想输入框、表格单元格内联编辑、后台任务。"""
import queue
import threading
import tkinter as tk
from tkinter import ttk

from ..search import filter_rank

NAV_KEYS = {"Up", "Down", "Return", "Escape", "Tab", "Left", "Right", "Shift_L", "Shift_R",
            "Control_L", "Control_R", "Alt_L", "Alt_R"}


class AutocompleteEntry(ttk.Entry):
    """输入时弹出模糊匹配列表（空格分隔多关键词、不区分大小写）。source() 返回候选列表。"""

    def __init__(self, master, source, on_select=None, max_rows=10, **kw):
        self.var = kw.pop("textvariable", None) or tk.StringVar()
        super().__init__(master, textvariable=self.var, **kw)
        self.source, self.on_select, self.max_rows = source, on_select, max_rows
        self.popup = None
        self.listbox = None
        self.bind("<KeyRelease>", self._on_key)
        self.bind("<Down>", self._down)
        self.bind("<Up>", self._up)
        self.bind("<Return>", self._enter)
        self.bind("<Escape>", lambda e: self.hide())
        self.bind("<FocusOut>", lambda e: self.after(150, self._maybe_hide))
        self.bind("<Double-Button-1>", lambda e: self.show(force=True))

    def get_text(self):
        return self.var.get().strip()

    def set_text(self, text):
        self.var.set(text)
        self.icursor("end")

    def _on_key(self, e):
        if e.keysym not in NAV_KEYS:
            self.show()

    def show(self, force=False):
        text = self.var.get()
        cands = filter_rank(text, self.source(), limit=50)
        if not cands or (not text.strip() and not force) or cands == [text]:
            self.hide()
            return
        if self.popup is None:
            self.popup = tk.Toplevel(self)
            self.popup.wm_overrideredirect(True)
            self.popup.attributes("-topmost", True)
            self.listbox = tk.Listbox(self.popup, activestyle="dotbox", exportselection=False)
            sb = ttk.Scrollbar(self.popup, command=self.listbox.yview)
            self.listbox.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            self.listbox.pack(side="left", fill="both", expand=True)
            self.listbox.bind("<ButtonRelease-1>", lambda e: self._choose())
            self.listbox.bind("<Return>", lambda e: self._choose())
        self.listbox.delete(0, "end")
        for c in cands:
            self.listbox.insert("end", c)
        self.listbox.configure(height=min(len(cands), self.max_rows))
        x, y = self.winfo_rootx(), self.winfo_rooty() + self.winfo_height()
        width = max(self.winfo_width(), 320)
        self.popup.geometry(f"{width}x{min(len(cands), self.max_rows) * 20 + 6}+{x}+{y}")
        self.popup.deiconify()

    def hide(self):
        if self.popup is not None:
            self.popup.withdraw()

    def _visible(self):
        return self.popup is not None and self.popup.winfo_viewable()

    def _maybe_hide(self):
        focus = self.focus_get()
        if focus is not self.listbox:
            self.hide()

    def _down(self, e):
        if not self._visible():
            self.show(force=True)
            return "break"
        cur = self.listbox.curselection()
        i = min((cur[0] + 1) if cur else 0, self.listbox.size() - 1)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(i)
        self.listbox.see(i)
        return "break"

    def _up(self, e):
        if self._visible():
            cur = self.listbox.curselection()
            i = max((cur[0] - 1) if cur else 0, 0)
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(i)
            self.listbox.see(i)
        return "break"

    def _enter(self, e):
        if self._visible() and self.listbox.curselection():
            self._choose()
            return "break"
        self.hide()
        return None

    def _choose(self):
        cur = self.listbox.curselection()
        if cur:
            self.set_text(self.listbox.get(cur[0]))
        self.hide()
        self.focus_set()
        if self.on_select:
            self.on_select(self.get_text())


class TreeEditor:
    """Treeview 单元格编辑。

    spec(iid, col) 返回 None（不可编辑）/ "entry" / ("combo", 选项) / ("auto", 候选函数)；
    get(iid, col) 取原值；commit(iid, col, value) 写回。Enter/↓ 跳到下一行同一列，↑ 上一行，Tab 下一列。
    """

    def __init__(self, tree, spec, get, commit, columns):
        self.tree, self.spec, self.get, self.commit = tree, spec, get, commit
        self.columns = list(columns)
        self.widget = None
        self.cell = None

    def edit(self, iid, col):
        self.close(save=True)
        kind = self.spec(iid, col)
        if kind is None:
            return False
        self.tree.see(iid)
        self.tree.update_idletasks()
        bbox = self.tree.bbox(iid, col)
        if not bbox:
            return False
        x, y, w, h = bbox
        value = self.get(iid, col)
        if isinstance(kind, tuple) and kind[0] == "combo":
            wdg = ttk.Combobox(self.tree, values=kind[1])
            wdg.set(value)
        elif isinstance(kind, tuple) and kind[0] == "auto":
            wdg = AutocompleteEntry(self.tree, kind[1])
            wdg.set_text(value)
        else:
            wdg = ttk.Entry(self.tree)
            wdg.insert(0, value)
        wdg.place(x=x, y=y, width=max(w, 60), height=h)
        wdg.focus_set()
        wdg.select_range(0, "end")
        wdg.bind("<Return>", lambda e: self._move(1, 0) or "break", add="+")
        wdg.bind("<Down>", lambda e: None if self._popup_open() else (self._move(1, 0) or "break"), add="+")
        wdg.bind("<Up>", lambda e: None if self._popup_open() else (self._move(-1, 0) or "break"), add="+")
        wdg.bind("<Tab>", lambda e: self._move(0, 1) or "break")
        wdg.bind("<Escape>", lambda e: self.close(save=False))
        wdg.bind("<FocusOut>", lambda e: self.tree.after(200, self._focus_lost))
        self.widget, self.cell = wdg, (iid, col)
        return True

    def _popup_open(self):
        return isinstance(self.widget, AutocompleteEntry) and self.widget._visible()

    def _focus_lost(self):
        if self.widget is None:
            return
        focus = self.widget.focus_get()
        if isinstance(self.widget, AutocompleteEntry) and focus is self.widget.listbox:
            return
        if focus is not self.widget:
            self.close(save=True)

    def close(self, save=True):
        if self.widget is None:
            return
        wdg, (iid, col) = self.widget, self.cell
        self.widget = self.cell = None
        value = wdg.get()
        if isinstance(wdg, AutocompleteEntry):
            wdg.hide()
        wdg.destroy()
        if save and self.tree.exists(iid):
            self.commit(iid, col, value)

    def _move(self, drow, dcol):
        iid, col = self.cell
        self.close(save=True)
        rows = self.tree.get_children()
        if dcol:
            idx = self.columns.index(col)
            for c in self.columns[idx + 1:]:
                if self.spec(iid, c) is not None:
                    self.edit(iid, c)
                    return
            drow = 1
            col = next((c for c in self.columns if self.spec(iid, c) is not None), col)
        i = rows.index(iid) + drow
        while 0 <= i < len(rows):
            if self.spec(rows[i], col) is not None:
                self.tree.selection_set(rows[i])
                self.edit(rows[i], col)
                return
            i += drow


def run_background(root, func, on_done):
    """在线程中执行 func()，完成后在界面线程调用 on_done(result, error)。"""
    q = queue.Queue()

    def worker():
        try:
            q.put((func(), None))
        except Exception as e:      # 交给界面统一提示
            q.put((None, e))

    def poll():
        try:
            result, error = q.get_nowait()
        except queue.Empty:
            root.after(100, poll)
            return
        on_done(result, error)

    threading.Thread(target=worker, daemon=True).start()
    root.after(100, poll)
