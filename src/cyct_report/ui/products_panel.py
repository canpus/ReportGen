"""产品清单：每行“名称规格 / 数量 / 单位 / 批号”输入框，可增删多行。"""
import tkinter as tk
from tkinter import ttk

from . import theme
from ..i18n import QTY_UNITS, qty_unit_key
from ..models import Product
from .rounded import Button
from .widgets import AutocompleteEntry

UNIT_CHOICES = [v["zh"] for v in QTY_UNITS.values()]
HEAD = (("产品名称 / 规格（原样印在报告上）", 1), ("数量", 0), ("单位", 0), ("生产批号", 0), ("", 0))
WIDTHS = (300, 90, 90, 170, 40)


class _Row:
    def __init__(self, panel, product):
        f = tk.Frame(panel.body, bg=theme.LANE)
        self.frame = f
        for i, w in enumerate(WIDTHS):
            f.grid_columnconfigure(i, minsize=w, weight=HEAD[i][1])
        self.name = AutocompleteEntry(f, panel.product_names)
        self.name.set_text(product.name)
        self.name.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=3)
        self.qty = ttk.Entry(f, width=8, justify="center")
        self.qty.insert(0, product.qty)
        self.qty.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=3)
        self.unit = ttk.Combobox(f, values=UNIT_CHOICES, width=6, justify="center")
        self.unit.set(QTY_UNITS.get(product.unit, {}).get("zh", product.unit))
        self.unit.grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=3)
        self.batch = ttk.Entry(f, width=16, justify="center")
        self.batch.insert(0, product.batch)
        self.batch.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=3)
        Button(f, "", lambda: panel.remove(self), kind="danger", icon="delete", padx=6,
               pady=3).grid(row=0, column=4)

    def product(self):
        return Product(self.name.get_text(), self.qty.get().strip(),
                       qty_unit_key(self.unit.get().strip() or "套"), self.batch.get().strip())


class ProductsPanel(tk.Frame):
    def __init__(self, master, product_names):
        super().__init__(master, bg=theme.LANE)
        self.product_names = product_names
        top = tk.Frame(self, bg=theme.LANE)
        top.pack(fill="x", pady=(0, 6))
        tk.Label(top, text="产品", font=theme.TITLE, bg=theme.LANE, fg=theme.TEXT).pack(side="left")
        tk.Label(top, text="同一类型的多个规格放在同一份报告；不同类型请分开出报告",
                 font=theme.SMALL, bg=theme.LANE, fg=theme.MUTED).pack(side="left", padx=10)
        Button(top, "添加产品", self.add_row, kind="soft", icon="add", padx=8, pady=3).pack(side="right")
        head = tk.Frame(self, bg=theme.LANE)
        head.pack(fill="x")
        for i, ((text, weight), w) in enumerate(zip(HEAD, WIDTHS)):
            head.grid_columnconfigure(i, minsize=w, weight=weight)
            tk.Label(head, text=text, font=theme.SMALL, bg=theme.LANE, fg=theme.MUTED,
                     anchor="w" if i == 0 else "center").grid(row=0, column=i, sticky="ew", padx=(2, 8))
        self.body = tk.Frame(self, bg=theme.LANE)
        self.body.pack(fill="x")
        self.rows = []
        self.add_row()

    def add_row(self, product=None):
        last = self.rows[-1].product() if self.rows else None
        p = product or Product(unit=last.unit if last else "set", batch=last.batch if last else "")
        row = _Row(self, p)
        row.frame.pack(fill="x")
        self.rows.append(row)
        return row

    def remove(self, row):
        row.frame.destroy()
        self.rows.remove(row)
        if not self.rows:
            self.add_row()

    def get_products(self):
        return [p for p in (r.product() for r in self.rows) if p.name]

    def set_products(self, products):
        for r in self.rows:
            r.frame.destroy()
        self.rows = []
        for p in products or [Product()]:
            self.add_row(Product(p.name, p.qty, p.unit, p.batch))
