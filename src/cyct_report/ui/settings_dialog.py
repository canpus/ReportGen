"""设置对话框：报告保存目录、PDF 转换程序。"""
import tkinter as tk
from tkinter import filedialog, ttk

from .. import office

ENGINES = {"auto": "自动（先 Word，后 WPS）", "word": "Microsoft Word", "wps": "WPS 文字"}


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings):
        super().__init__(master)
        self.settings = settings
        self.title("设置")
        self.transient(master)
        self.resizable(False, False)
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="报告保存目录").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        self.dir_var = tk.StringVar(value=str(settings.reports_dir()))
        ttk.Entry(f, textvariable=self.dir_var, width=60).grid(row=0, column=1, pady=6)
        ttk.Button(f, text="浏览…", command=self._browse).grid(row=0, column=2, padx=4)
        ttk.Label(f, text="PDF 转换程序").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.engine = ttk.Combobox(f, values=list(ENGINES.values()), state="readonly", width=30)
        self.engine.current(list(ENGINES).index(settings.get("pdf_engine", "auto")))
        self.engine.grid(row=1, column=1, sticky="w", pady=6)
        found = office.available_engines()
        names = "、".join(ENGINES[e] for e in found) if found else "未检测到 Word 或 WPS，只能生成 docx"
        ttk.Label(f, text=f"本机检测到：{names}", foreground="#555").grid(
            row=2, column=1, columnspan=2, sticky="w")
        bar = ttk.Frame(f)
        bar.grid(row=3, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(bar, text="保存", command=self._save).pack(side="right", padx=4)
        self.grab_set()

    def _browse(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _save(self):
        self.settings["reports_dir"] = self.dir_var.get().strip()
        self.settings["pdf_engine"] = list(ENGINES)[self.engine.current()]
        self.settings.save()
        self.destroy()
