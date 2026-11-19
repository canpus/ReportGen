"""“生成报告”页：客户、语言、标准/类型、产品、检测项、签字与生成。"""
import os
import tkinter as tk
from datetime import date
from tkinter import messagebox, simpledialog, ttk

from .. import service
from ..i18n import LANG_NAMES, LANGS
from ..models import Report
from ..presets import CUSTOM_STD_ID
from .item_dialog import AddItemDialog
from .items_panel import ItemsPanel
from .products_panel import ProductsPanel
from .widgets import AutocompleteEntry, run_background


class GenerateTab(ttk.Frame):
    def __init__(self, master, ctx, on_generated):
        super().__init__(master, padding=6)
        self.ctx, self.on_generated = ctx, on_generated
        self.lib, self.db, self.settings = ctx.lib, ctx.db, ctx.settings
        self.lang = tk.StringVar(value=self.settings.get("last_lang", "zh"))
        self.display_var, self.tmax_var = tk.StringVar(), tk.StringVar()
        self.display_auto = True
        self._std_ids, self._std_index, self._tpl_index = [], 0, 0
        self._build_form()
        self.products = ProductsPanel(self, lambda: self.db.names("product"))
        self.products.pack(fill="x", pady=4)
        self.items = ItemsPanel(self, self.add_items, self.save_template, self.reset_items)
        self.items.pack(fill="both", expand=True, pady=4)
        self._build_bottom()
        self._init_standard()

    # ---------- 布局 ----------
    def _build_form(self):
        f = ttk.Frame(self)
        f.pack(fill="x")
        ttk.Label(f, text="客户名称").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        self.customer = AutocompleteEntry(f, self.db.customers, width=60)
        self.customer.grid(row=0, column=1, columnspan=3, sticky="we", pady=3)
        ttk.Label(f, text="（输入关键字联想，空格分隔多个关键字）", foreground="#666").grid(
            row=0, column=4, columnspan=2, sticky="w")
        lf = ttk.Frame(f)
        lf.grid(row=0, column=6, sticky="e", padx=8)
        ttk.Label(lf, text="报告语言").pack(side="left", padx=4)
        for lang in LANGS:
            ttk.Radiobutton(lf, text=LANG_NAMES[lang], value=lang, variable=self.lang,
                            command=self._lang_changed).pack(side="left", padx=3)

        ttk.Label(f, text="检测标准").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        self.std_box = ttk.Combobox(f, state="readonly", width=30)
        self.std_box.grid(row=1, column=1, sticky="w", pady=3)
        self.std_box.bind("<<ComboboxSelected>>", lambda e: self._std_changed())
        ttk.Label(f, text="产品类型").grid(row=1, column=2, sticky="e", padx=4)
        self.tpl_box = ttk.Combobox(f, state="readonly", width=70)
        self.tpl_box.grid(row=1, column=3, columnspan=4, sticky="we", pady=3)
        self.tpl_box.bind("<<ComboboxSelected>>", lambda e: self._tpl_changed())

        ttk.Label(f, text="Tmax (℃)").grid(row=2, column=0, sticky="e", padx=4, pady=3)
        tm = ttk.Entry(f, textvariable=self.tmax_var, width=8)
        tm.grid(row=2, column=1, sticky="w", pady=3)
        tm.bind("<KeyRelease>", lambda e: self._tmax_changed())
        ttk.Label(f, text="报告中标准写法").grid(row=2, column=2, sticky="e", padx=4)
        disp = ttk.Entry(f, textvariable=self.display_var, width=50)
        disp.grid(row=2, column=3, columnspan=2, sticky="we", pady=3)
        disp.bind("<KeyRelease>", lambda e: setattr(self, "display_auto", False))
        ttk.Button(f, text="恢复默认写法", command=self._reset_display).grid(row=2, column=5, sticky="w")
        f.columnconfigure(3, weight=1)

    def _build_bottom(self):
        b = ttk.Frame(self)
        b.pack(fill="x", pady=(2, 0))
        ttk.Label(b, text="检验员").pack(side="left", padx=4)
        self.inspector = ttk.Combobox(b, width=14, postcommand=lambda: self.inspector.configure(
            values=[""] + self.db.names("inspector")))
        self.inspector.set(self.settings.get("inspector", ""))
        self.inspector.pack(side="left")
        ttk.Label(b, text="审核").pack(side="left", padx=(12, 4))
        self.auditor = ttk.Combobox(b, width=14, postcommand=lambda: self.auditor.configure(
            values=[""] + self.db.names("auditor")))
        self.auditor.set(self.settings.get("auditor", ""))
        self.auditor.pack(side="left")
        ttk.Label(b, text="（可留空）", foreground="#666").pack(side="left", padx=2)
        ttk.Label(b, text="报告日期").pack(side="left", padx=(12, 4))
        self.date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(b, textvariable=self.date_var, width=12).pack(side="left")
        self.pdf_var = tk.BooleanVar(value=self.settings.get("make_pdf", True))
        ttk.Checkbutton(b, text="同时生成 PDF", variable=self.pdf_var).pack(side="left", padx=12)
        self.gen_btn = ttk.Button(b, text="生成报告（docx + PDF）", command=self.generate)
        self.gen_btn.pack(side="right", padx=4, ipadx=10, ipady=3)
        self.status = ttk.Label(b, foreground="#555")
        self.status.pack(side="right", padx=8)

    # ---------- 标准与模板 ----------
    def _init_standard(self):
        self._std_ids = [s.id for s in self.lib.standards]
        self.std_box.configure(values=[s.name for s in self.lib.standards])
        sid = self.settings.get("last_standard")
        idx = self._std_ids.index(sid) if sid in self._std_ids else 0
        self.std_box.current(idx)
        self._std_changed(preferred=self.settings.get("last_template"))

    def current_std(self):
        return self.lib.standards[self.std_box.current()]

    def current_tpl(self):
        std, i = self.current_std(), self.tpl_box.current()
        return std.templates[i] if 0 <= i < len(std.templates) else None

    def _std_changed(self, preferred=None):
        if preferred is None and self.items.has_results() and not messagebox.askyesno(
                "切换标准", "切换后检测项会换成新标准的默认项，已录入的实测值将清空。继续？", parent=self):
            self.std_box.current(self._std_index)
            return
        self._std_index = self.std_box.current()
        std = self.current_std()
        self.tpl_box.configure(values=[t.label.get("zh") or t.label.get("en") for t in std.templates])
        ids = [t.id for t in std.templates]
        self.tpl_box.current(ids.index(preferred) if preferred in ids else 0)
        self._tpl_changed(confirm=False)

    def _tpl_changed(self, confirm=True):
        if confirm and self.items.has_results() and not messagebox.askyesno(
                "切换类型", "切换后检测项会换成新类型的默认项，已录入的实测值将清空。继续？", parent=self):
            self.tpl_box.current(self._tpl_index)
            return
        self._tpl_index = self.tpl_box.current()
        tpl = self.current_tpl()
        self.tmax_var.set("" if tpl.tmax is None else str(tpl.tmax))
        self.reset_items(confirm=False)
        self.display_auto = True
        self._reset_display()

    def reset_items(self, confirm=True):
        if confirm and self.items.has_results() and not messagebox.askyesno(
                "恢复默认", "恢复为该类型的默认检测项？已录入的实测值将清空。", parent=self):
            return
        self.items.set_items(self.lib.build_items(self.current_std(), self.current_tpl()))
        self._apply_context()

    def _tmax_value(self):
        return Report(tmax=self.tmax_var.get()).tmax_value()

    def _apply_context(self):
        self.items.set_context(self.lang.get(), self._tmax_value())

    def _reset_display(self):
        self.display_auto = True
        tpl = self.current_tpl()
        self.display_var.set(self.lib.display(tpl, self.lang.get(), self._tmax_value()) if tpl else "")

    def _lang_changed(self):
        self._apply_context()
        if self.display_auto:
            self._reset_display()

    def _tmax_changed(self):
        self._apply_context()
        if self.display_auto:
            self._reset_display()

    # ---------- 检测项操作 ----------
    def add_items(self):
        std, tpl = self.current_std(), self.current_tpl()
        pool = self.lib.build_items(std, tpl, include_opt=True) if not tpl.custom else []
        if tpl.custom and std.id != CUSTOM_STD_ID:
            base = std.templates[0]
            pool = self.lib.build_items(std, base, include_opt=True)
        dlg = AddItemDialog(self, pool, self.items.existing_keys(), self.lang.get(), self._tmax_value())
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
        std = self.current_std()
        tpl = self.current_tpl()
        tid = self.lib.save_custom(std.id, name.strip(), self._tmax_value(), tpl.tc if tpl else "",
                                   self.display_var.get(), items)
        # 只刷新类型列表并选中新模板，保留表中已录入的实测值
        std = self.current_std()
        self.tpl_box.configure(values=[t.label.get("zh") or t.label.get("en") for t in std.templates])
        self._tpl_index = [t.id for t in std.templates].index(tid)
        self.tpl_box.current(self._tpl_index)
        messagebox.showinfo("保存为自定义模板", f"已保存，可在“{std.name}”的产品类型列表中选择“★ {name}”。",
                            parent=self)

    # ---------- 生成 ----------
    def collect(self) -> Report:
        try:
            d = date.fromisoformat(self.date_var.get().strip())
        except ValueError:
            raise ValueError("报告日期格式应为 YYYY-MM-DD，例如 2026-09-01")
        tpl = self.current_tpl()
        return Report(customer=self.customer.get_text(), lang=self.lang.get(),
                      standard_id=self.current_std().id, template_id=tpl.id if tpl else "",
                      std_display=self.display_var.get().strip(), tmax=self.tmax_var.get().strip(),
                      tc=tpl.tc if tpl else "", products=self.products.get_products(),
                      items=self.items.get_items(), inspector=self.inspector.get().strip(),
                      auditor=self.auditor.get().strip(), report_date=d)

    def generate(self):
        try:
            report = self.collect()
        except ValueError as e:
            messagebox.showwarning("生成报告", str(e), parent=self)
            return
        problems = service.validate(report)
        if problems:
            messagebox.showwarning("生成报告", "\n".join(problems), parent=self)
            return
        empty = sum(1 for i in report.items if i.kind == "item" and not i.result)
        if empty and not messagebox.askyesno(
                "生成报告", f"还有 {empty} 项未填实测值，这些格子将留空。继续生成？", parent=self):
            return
        self.settings.update(make_pdf=self.pdf_var.get(), last_lang=report.lang,
                             last_standard=report.standard_id, last_template=report.template_id,
                             inspector=report.inspector, auditor=report.auditor)
        self.settings.save()
        self.gen_btn.configure(state="disabled")
        self.status.configure(text="正在生成，PDF 转换需要几秒钟…")
        run_background(self, lambda: service.generate(report, self.settings, self.db), self._done)

    def _done(self, result, error):
        self.gen_btn.configure(state="normal")
        if error:
            self.status.configure(text="生成失败")
            messagebox.showerror("生成报告", f"生成失败：{error}", parent=self)
            return
        self.status.configure(text="已生成：" + os.path.basename(result.docx_path))
        self.on_generated()
        msg = f"报告已生成：\n{result.docx_path}"
        if result.pdf_path:
            msg += f"\n{result.pdf_path}"
        if result.pdf_error:
            msg += f"\n\nPDF 未生成：{result.pdf_error}"
        if messagebox.askyesno("生成报告", msg + "\n\n现在打开所在文件夹？", parent=self):
            self.ctx.reveal(result.docx_path)
