"""“生成报告”页：报告信息、产品、检测项、签字与生成。界面一律中文，报告语言只影响成品。"""
import os
import tkinter as tk
from datetime import date
from tkinter import messagebox, simpledialog, ttk

from . import theme
from .. import service
from ..models import Report
from ..presets import CUSTOM_STD_ID
from .item_dialog import AddItemDialog
from .items_panel import ItemsPanel
from .products_panel import ProductsPanel
from .rounded import Button, Panel
from .segmented import Segmented
from .widgets import AutocompleteEntry, run_background

LANG_OPTIONS = [("zh", "中文"), ("en", "English"), ("ru", "Русский")]


def _field(master, text, row, col, **grid):
    ttk.Label(master, text=text, style="Field.TLabel").grid(row=row, column=col, sticky="e",
                                                            padx=(0 if col == 0 else 18, 8), pady=5, **grid)


class GenerateTab(tk.Frame):
    def __init__(self, master, ctx, on_generated):
        super().__init__(master, bg=theme.SHELL)
        self.ctx, self.on_generated = ctx, on_generated
        self.lib, self.db, self.settings = ctx.lib, ctx.db, ctx.settings
        self.display_var, self.tmax_var = tk.StringVar(), tk.StringVar()
        self.display_auto = True
        self._std_index = self._tpl_index = 0
        self._build_info()
        prod = Panel(self, pad=12)
        prod.pack(fill="x", pady=(0, 10))
        self.products = ProductsPanel(prod.inner, lambda: self.db.names("product"))
        self.products.pack(fill="x")
        items = Panel(self, pad=12)
        items.pack(fill="both", expand=True, pady=(0, 10))
        self.items = ItemsPanel(items.inner, self.add_items, self.save_template, self.reset_items)
        self.items.pack(fill="both", expand=True)
        self._build_bottom()
        self._init_standard()

    # ---------- 布局 ----------
    def _build_info(self):
        p = Panel(self, pad=14)
        p.pack(fill="x", pady=(0, 10))
        f = p.inner
        _field(f, "客户名称", 0, 0)
        self.customer = AutocompleteEntry(f, self.db.customers)
        self.customer.grid(row=0, column=1, columnspan=3, sticky="ew", pady=5)
        _field(f, "报告语言", 0, 4)
        self.lang = Segmented(f, LANG_OPTIONS, self.settings.get("last_lang", "zh"),
                              command=lambda v: self._lang_changed())
        self.lang.grid(row=0, column=5, columnspan=2, sticky="w")
        _field(f, "检测标准", 1, 0)
        self.std_box = ttk.Combobox(f, state="readonly", width=26)
        self.std_box.grid(row=1, column=1, sticky="ew", pady=5)
        self.std_box.bind("<<ComboboxSelected>>", lambda e: self._std_changed())
        _field(f, "产品类型", 1, 2)
        self.tpl_box = ttk.Combobox(f, state="readonly")
        self.tpl_box.grid(row=1, column=3, columnspan=4, sticky="ew", pady=5)
        self.tpl_box.bind("<<ComboboxSelected>>", lambda e: self._tpl_changed())
        _field(f, "Tmax（℃）", 2, 0)
        tm = ttk.Entry(f, textvariable=self.tmax_var, width=10)
        tm.grid(row=2, column=1, sticky="w", pady=5)
        tm.bind("<KeyRelease>", lambda e: self._tmax_changed())
        _field(f, "报告中标准写法", 2, 2)
        disp = ttk.Entry(f, textvariable=self.display_var)
        disp.grid(row=2, column=3, columnspan=3, sticky="ew", pady=5)
        disp.bind("<KeyRelease>", lambda e: setattr(self, "display_auto", False))
        Button(f, "恢复默认", self._reset_display, kind="ghost", icon="reset", padx=8,
               pady=3).grid(row=2, column=6, sticky="w", padx=(8, 0))
        f.columnconfigure(3, weight=1)

    def _build_bottom(self):
        p = Panel(self, pad=10)
        p.pack(fill="x")
        b = p.inner
        ttk.Label(b, text="检验员", style="Field.TLabel").pack(side="left", padx=(4, 6))
        self.inspector = ttk.Combobox(b, width=12, postcommand=lambda: self.inspector.configure(
            values=[""] + self.db.names("inspector")))
        self.inspector.set(self.settings.get("inspector", ""))
        self.inspector.pack(side="left")
        ttk.Label(b, text="审核", style="Field.TLabel").pack(side="left", padx=(16, 6))
        self.auditor = ttk.Combobox(b, width=12, postcommand=lambda: self.auditor.configure(
            values=[""] + self.db.names("auditor")))
        self.auditor.set(self.settings.get("auditor", ""))
        self.auditor.pack(side="left")
        ttk.Label(b, text="可留空", style="Muted.TLabel").pack(side="left", padx=6)
        ttk.Label(b, text="报告日期", style="Field.TLabel").pack(side="left", padx=(16, 6))
        self.date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(b, textvariable=self.date_var, width=12).pack(side="left")
        self.pdf_var = tk.BooleanVar(value=self.settings.get("make_pdf", True))
        ttk.Checkbutton(b, text="同时生成 PDF", variable=self.pdf_var).pack(side="left", padx=16)
        self.gen_btn = Button(b, "生成报告", self.generate, kind="accent", icon="doc", font=theme.TITLE,
                              padx=20, pady=7, radius=10)
        self.gen_btn.pack(side="right")
        self.status = ttk.Label(b, style="Muted.TLabel")
        self.status.pack(side="right", padx=12)

    # ---------- 标准与模板 ----------
    def _init_standard(self):
        self.std_box.configure(values=[s.name for s in self.lib.standards])
        ids = [s.id for s in self.lib.standards]
        sid = self.settings.get("last_standard")
        self.std_box.current(ids.index(sid) if sid in ids else 0)
        self._std_changed(preferred=self.settings.get("last_template"))

    def current_std(self):
        return self.lib.standards[self.std_box.current()]

    def current_tpl(self):
        std, i = self.current_std(), self.tpl_box.current()
        return std.templates[i] if 0 <= i < len(std.templates) else None

    def _fill_templates(self):
        std = self.current_std()
        self.tpl_box.configure(values=[t.label.get("zh") or t.label.get("en") for t in std.templates])
        return [t.id for t in std.templates]

    def _confirm_reset(self, what):
        return not self.items.has_results() or messagebox.askyesno(
            what, "检测项会换成默认项，已录入的实测值将清空。继续？", parent=self)

    def _std_changed(self, preferred=None):
        if preferred is None and not self._confirm_reset("切换标准"):
            self.std_box.current(self._std_index)
            return
        self._std_index = self.std_box.current()
        ids = self._fill_templates()
        self.tpl_box.current(ids.index(preferred) if preferred in ids else 0)
        self._tpl_changed(confirm=False)

    def _tpl_changed(self, confirm=True):
        if confirm and not self._confirm_reset("切换产品类型"):
            self.tpl_box.current(self._tpl_index)
            return
        self._tpl_index = self.tpl_box.current()
        tpl = self.current_tpl()
        self.tmax_var.set("" if tpl.tmax is None else str(tpl.tmax))
        self.reset_items(confirm=False)
        self._reset_display()

    def reset_items(self, confirm=True):
        if confirm and not self._confirm_reset("恢复默认检测项"):
            return
        self.items.set_items(self.lib.build_items(self.current_std(), self.current_tpl()))
        self.items.set_tmax(self._tmax_value())

    def _tmax_value(self):
        return Report(tmax=self.tmax_var.get()).tmax_value()

    def _reset_display(self):
        self.display_auto = True
        tpl = self.current_tpl()
        self.display_var.set(self.lib.display(tpl, self.lang.get(), self._tmax_value()) if tpl else "")

    def _lang_changed(self):
        if self.display_auto:
            self._reset_display()

    def _tmax_changed(self):
        self.items.set_tmax(self._tmax_value())
        if self.display_auto:
            self._reset_display()

    # ---------- 检测项操作 ----------
    def add_items(self):
        std, tpl = self.current_std(), self.current_tpl()
        base = tpl if not tpl.custom else (std.templates[0] if std.id != CUSTOM_STD_ID else None)
        pool = self.lib.build_items(std, base, include_opt=True) if base and not base.custom else []
        dlg = AddItemDialog(self, pool, self.items.existing_keys(), self._tmax_value())
        self.wait_window(dlg)
        if dlg.result:
            self.items.insert_items(dlg.result)

    def save_template(self):
        name = simpledialog.askstring("保存为自定义模板", "模板名称（例如：某客户 80℃热缩带）：", parent=self)
        if not name:
            return
        items = [i.copy() for i in self.items.get_items()]
        for i in items:
            i.result = ""
        std, tpl = self.current_std(), self.current_tpl()
        tid = self.lib.save_custom(std.id, name.strip(), self._tmax_value(), tpl.tc if tpl else "",
                                   self.display_var.get(), items)
        ids = self._fill_templates()          # 只刷新列表并选中新模板，保留已录入的实测值
        self._tpl_index = ids.index(tid)
        self.tpl_box.current(self._tpl_index)
        messagebox.showinfo("保存为自定义模板", f"已保存。以后在“{std.name}”的产品类型中选择“★ {name}”即可。",
                            parent=self)

    # ---------- 生成 ----------
    def collect(self) -> Report:
        try:
            d = date.fromisoformat(self.date_var.get().strip())
        except ValueError:
            raise ValueError("报告日期格式应为 年-月-日，例如 2026-09-01")
        tpl = self.current_tpl()
        return Report(customer=self.customer.get_text(), lang=self.lang.get(),
                      standard_id=self.current_std().id, template_id=tpl.id if tpl else "",
                      std_display=self.display_var.get().strip(), tmax=self.tmax_var.get().strip(),
                      tc=tpl.tc if tpl else "", products=self.products.get_products(),
                      items=self.items.get_items(), inspector=self.inspector.get().strip(),
                      auditor=self.auditor.get().strip(), report_date=d)

    def _confirm(self, report):
        problems = service.validate(report)
        if problems:
            messagebox.showwarning("生成报告", "\n".join(problems), parent=self)
            return False
        empty = sum(1 for i in report.items if i.kind == "item" and not i.result)
        if empty and not messagebox.askyesno(
                "生成报告", f"还有 {empty} 项没填实测值，报告中这些格子会留空。继续生成？", parent=self):
            return False
        names = service.untranslated(report)
        if names:
            lang = dict(LANG_OPTIONS)[report.lang]
            shown = "\n".join("· " + n for n in names[:8]) + ("\n……" if len(names) > 8 else "")
            if not messagebox.askyesno("生成报告", f"以下检测项在 {lang} 报告中仍会显示中文"
                                       f"（可双击该行补填英文/俄文名称）：\n\n{shown}\n\n继续生成？", parent=self):
                return False
        return True

    def generate(self):
        try:
            report = self.collect()
        except ValueError as e:
            messagebox.showwarning("生成报告", str(e), parent=self)
            return
        if not self._confirm(report):
            return
        self.settings.update(make_pdf=self.pdf_var.get(), last_lang=report.lang,
                             last_standard=report.standard_id, last_template=report.template_id,
                             inspector=report.inspector, auditor=report.auditor)
        self.settings.save()
        self.gen_btn.set_enabled(False, "正在生成…")
        self.status.configure(text="PDF 转换需要几秒钟")
        run_background(self, lambda: service.generate(report, self.settings, self.db), self._done)

    def _done(self, result, error):
        self.gen_btn.set_enabled(True, "生成报告")
        if error:
            self.status.configure(text="生成失败")
            messagebox.showerror("生成报告", f"生成失败：{error}", parent=self)
            return
        self.status.configure(text="已生成：" + os.path.basename(result.docx_path)[:40])
        self.on_generated()
        msg = f"报告已生成：\n{result.docx_path}"
        if result.pdf_path:
            msg += f"\n{result.pdf_path}"
        if result.pdf_error:
            msg += f"\n\nPDF 未生成：{result.pdf_error}"
        if messagebox.askyesno("生成报告", msg + "\n\n现在打开所在文件夹？", parent=self):
            self.ctx.reveal(result.docx_path)
