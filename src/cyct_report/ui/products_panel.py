"""产品清单：品名规格、数量、单位、批号；可多行。"""
import itertools
from tkinter import ttk

from ..i18n import QTY_UNITS, qty_unit_key
from ..models import Product
from .widgets import TreeEditor

COLUMNS = ("name", "qty", "unit", "batch")
HEADINGS = {"name": "产品名称/规格（按报告语言填写）", "qty": "数量", "unit": "单位", "batch": "生产批号"}
WIDTHS = {"name": 520, "qty": 90, "unit": 80, "batch": 160}
UNIT_CHOICES = [v["zh"] for v in QTY_UNITS.values()]


class ProductsPanel(ttk.LabelFrame):
    def __init__(self, master, product_names):
        super().__init__(master, text="产品（同一 ISO 类型的多个规格可放在同一份报告）")
        self.product_names = product_names
        self.rows = {}
        self._ids = itertools.count()
        bar = ttk.Frame(self)
        bar.pack(side="right", fill="y", padx=4, pady=2)
        ttk.Button(bar, text="添加产品", command=self.add_row).pack(fill="x", pady=1)
        ttk.Button(bar, text="复制选中行", command=self.copy_row).pack(fill="x", pady=1)
        ttk.Button(bar, text="删除", command=self.delete_row).pack(fill="x", pady=1)
        self.tree = ttk.Treeview(self, columns=COLUMNS, show="headings", height=3)
        for c in COLUMNS:
            self.tree.heading(c, text=HEADINGS[c])
            self.tree.column(c, width=WIDTHS[c], stretch=c == "name",
                             anchor="w" if c == "name" else "center")
        self.tree.pack(fill="both", expand=True, padx=4, pady=2)
        self.editor = TreeEditor(self.tree, self._spec, self._get, self._commit, COLUMNS)
        self.tree.bind("<Button-1>", self._click)
        self.add_row()

    def _click(self, e):
        iid, col = self.tree.identify_row(e.y), self.tree.identify_column(e.x)
        if iid and col:
            c = COLUMNS[int(col[1:]) - 1]
            self.tree.after(10, lambda: self.editor.edit(iid, c))

    def _spec(self, iid, col):
        if col == "name":
            return ("auto", self.product_names)
        if col == "unit":
            return ("combo", UNIT_CHOICES)
        return "entry"

    def _get(self, iid, col):
        p = self.rows[iid]
        if col == "unit":
            return QTY_UNITS.get(p.unit, {}).get("zh", p.unit)
        return getattr(p, col)

    def _commit(self, iid, col, value):
        p = self.rows[iid]
        value = value.strip()
        setattr(p, col, qty_unit_key(value) if col == "unit" else value)
        self._render(iid)

    def _render(self, iid):
        p = self.rows[iid]
        self.tree.item(iid, values=(p.name, p.qty, QTY_UNITS.get(p.unit, {}).get("zh", p.unit), p.batch))

    def add_row(self, product=None):
        last = self.get_products(keep_empty=True)[-1:] if self.rows else []
        p = product or Product(unit=last[0].unit if last else "set", batch=last[0].batch if last else "")
        iid = f"p{next(self._ids)}"
        self.rows[iid] = p
        self.tree.insert("", "end", iid=iid)
        self._render(iid)
        self.tree.configure(height=min(max(3, len(self.rows)), 6))
        return iid

    def copy_row(self):
        sel = self.tree.selection()
        if sel:
            src = self.rows[sel[0]]
            self.add_row(Product(src.name, src.qty, src.unit, src.batch))

    def delete_row(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.rows.pop(iid, None)
        if not self.rows:
            self.add_row()

    def get_products(self, keep_empty=False):
        self.editor.close(save=True)
        out = [self.rows[i] for i in self.tree.get_children()]
        return out if keep_empty else [p for p in out if p.name.strip()]

    def set_products(self, products):
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        for p in products or [Product()]:
            self.add_row(Product(p.name, p.qty, p.unit, p.batch))
