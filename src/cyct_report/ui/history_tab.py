"""“历史报告”页：按客户（模糊）、关键词、来源查询；双击打开报告。"""
import tkinter as tk
from tkinter import messagebox, ttk

from . import theme
from ..db import from_stored_path
from ..i18n import LANG_NAMES
from .rounded import Button, Panel
from .widgets import AutocompleteEntry

COLUMNS = ("created", "customer", "products", "qty", "batch", "standard", "lang", "source", "file")
HEADINGS = {"created": "报告时间", "customer": "客户", "products": "出货产品", "qty": "数量",
            "batch": "批号", "standard": "检测标准", "lang": "语言", "source": "来源", "file": "文件名"}
WIDTHS = {"created": 135, "customer": 220, "products": 300, "qty": 110, "batch": 110,
          "standard": 180, "lang": 60, "source": 80, "file": 260}
SOURCES = {"全部": "", "软件生成": "generated", "导入的旧报告": "imported"}


class HistoryTab(tk.Frame):
    def __init__(self, master, ctx, on_import):
        super().__init__(master, bg=theme.SHELL)
        self.ctx, self.db = ctx, ctx.db
        self.rows = {}
        top = Panel(self, pad=12)
        top.pack(fill="x", pady=(0, 10))
        f = top.inner
        ttk.Label(f, text="客户", style="Field.TLabel").pack(side="left", padx=(2, 8))
        self.customer = AutocompleteEntry(f, self.db.customers, on_select=lambda t: self.refresh(),
                                          width=36)
        self.customer.pack(side="left")
        self.customer.bind("<Return>", lambda e: self.refresh(), add="+")
        ttk.Label(f, text="关键词（产品 / 批号 / 标准）", style="Field.TLabel").pack(side="left", padx=(18, 8))
        self.keyword = ttk.Entry(f, width=22)
        self.keyword.pack(side="left")
        self.keyword.bind("<Return>", lambda e: self.refresh())
        ttk.Label(f, text="来源", style="Field.TLabel").pack(side="left", padx=(18, 8))
        self.source = ttk.Combobox(f, values=list(SOURCES), state="readonly", width=12)
        self.source.current(0)
        self.source.pack(side="left")
        self.source.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        Button(f, "查询", self.refresh, kind="accent", icon="search", padx=12, pady=4).pack(side="left", padx=(14, 4))
        Button(f, "清空条件", self.clear, kind="ghost", icon="clear", padx=8, pady=4).pack(side="left")

        body = Panel(self, pad=12)
        body.pack(fill="both", expand=True)
        card = Panel(body.inner, fill=theme.CARD, outside=theme.LANE, radius=10, border=theme.LINE, pad=6)
        card.pack(fill="both", expand=True)
        frame = card.inner
        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings")
        for c in COLUMNS:
            self.tree.heading(c, text=HEADINGS[c])
            self.tree.column(c, width=WIDTHS[c], stretch=c in ("products", "customer", "file"),
                             anchor="center" if c in ("lang", "source", "created") else "w")
        ys = ttk.Scrollbar(frame, command=self.tree.yview)
        xs = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree.tag_configure("imported", background="#FFF8E6")
        self.tree.tag_configure("missing", foreground=theme.FAINT)
        self.tree.bind("<Double-Button-1>", lambda e: self.open_selected("docx"))
        self.tree.bind("<Return>", lambda e: self.open_selected("docx"))
        self.tree.bind("<Button-3>", self._menu)
        self.status = ttk.Label(body.inner, style="Muted.TLabel")
        self.status.pack(fill="x", pady=(8, 0))
        self.menu = tk.Menu(self, tearoff=False, font=theme.BASE)
        self.menu.add_command(label="打开 Word 报告", command=lambda: self.open_selected("docx"))
        self.menu.add_command(label="打开 PDF 报告", command=lambda: self.open_selected("pdf"))
        self.menu.add_command(label="打开所在文件夹并选中", command=self.reveal_selected)
        self.menu.add_separator()
        self.menu.add_command(label="删除这条记录（不删除文件）", command=self.delete_selected)
        self.refresh()

    def clear(self):
        self.customer.set_text("")
        self.keyword.delete(0, "end")
        self.source.current(0)
        self.refresh()

    def refresh(self):
        rows = self.db.query_reports(customer_query=self.customer.get_text(),
                                     keyword=self.keyword.get().strip(),
                                     source=SOURCES[self.source.get()])
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for r in rows:
            path = from_stored_path(r["docx_path"])
            exists = bool(path and path.exists())
            tags = (("imported",) if r["source"] == "imported" else ()) + (() if exists else ("missing",))
            iid = str(r["id"])
            self.rows[iid] = r
            self.tree.insert("", "end", iid=iid, tags=tags, values=(
                r["created_at"].replace("T", " ")[:16], r["customer"], r["products"] or "",
                r["quantities"] or "", r["batches"] or "", r["standard"] or "",
                LANG_NAMES.get(r["lang"], r["lang"] or ""),
                "导入" if r["source"] == "imported" else "软件生成",
                (path.name if path else "") + ("" if exists else "（文件不存在）")))
        n_imp = sum(1 for r in rows if r["source"] == "imported")
        self.status.configure(text=f"共 {len(rows)} 份报告（其中导入的旧报告 {n_imp} 份，以浅黄底色标示）。"
                                   "双击打开报告，右键可打开 PDF 或所在文件夹。")

    def _selected(self):
        sel = self.tree.selection()
        return self.rows.get(sel[0]) if sel else None

    def _menu(self, e):
        iid = self.tree.identify_row(e.y)
        if iid:
            self.tree.selection_set(iid)
            self.menu.tk_popup(e.x_root, e.y_root)

    def open_selected(self, kind):
        r = self._selected()
        if not r:
            return
        path = from_stored_path(r["pdf_path"] if kind == "pdf" else r["docx_path"])
        if not path or not path.exists():
            alt = from_stored_path(r["docx_path"])
            if kind == "pdf" and alt and alt.exists():
                messagebox.showinfo("打开报告", "这份报告没有 PDF 版，将打开所在文件夹。", parent=self)
                self.ctx.reveal(alt)
            else:
                messagebox.showwarning("打开报告", f"找不到文件：\n{path}", parent=self)
            return
        self.ctx.open_file(path)

    def reveal_selected(self):
        r = self._selected()
        if r:
            path = from_stored_path(r["docx_path"])
            if path and path.exists():
                self.ctx.reveal(path)
            else:
                messagebox.showwarning("打开文件夹", f"找不到文件：\n{path}", parent=self)

    def delete_selected(self):
        r = self._selected()
        if r and messagebox.askyesno("删除记录", f"从历史记录中删除这份报告？\n{r['customer']}  {r['products']}\n"
                                               "（报告文件本身保留在磁盘上）", parent=self):
            self.db.delete_report(r["id"])
            self.refresh()
