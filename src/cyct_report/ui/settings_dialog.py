"""设置对话框：报告保存目录、PDF 转换程序、重新加载标准库、版本信息。"""
import tkinter as tk
from tkinter import filedialog, ttk

from . import theme
from .. import __version__, office

ENGINES = {"auto": "自动（先 Word，后 WPS）", "word": "Microsoft Word", "wps": "WPS 文字"}


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings, on_reload=None):
        super().__init__(master)
        self.settings, self.on_reload = settings, on_reload
        self.title("设置")
        self.configure(bg=theme.LANE)
        self.transient(master)
        self.resizable(False, False)
        f = ttk.Frame(self, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="报告保存目录", style="Field.TLabel").grid(row=0, column=0, sticky="e", padx=(0, 10), pady=6)
        self.dir_var = tk.StringVar(value=str(settings.reports_dir()))
        ttk.Entry(f, textvariable=self.dir_var, width=56).grid(row=0, column=1, pady=6)
        ttk.Button(f, text="浏览…", command=self._browse).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(f, text="PDF 转换程序", style="Field.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 10), pady=6)
        self.engine = ttk.Combobox(f, values=list(ENGINES.values()), state="readonly", width=28)
        self.engine.current(list(ENGINES).index(settings.get("pdf_engine", "auto")))
        self.engine.grid(row=1, column=1, sticky="w", pady=6)
        found = office.available_engines()
        names = "、".join(ENGINES[e] for e in found) if found else "未检测到 Word 或 WPS，只能生成 docx"
        ttk.Label(f, text=f"本机检测到：{names}", style="Muted.TLabel").grid(row=2, column=1, columnspan=2, sticky="w")
        ttk.Separator(f).grid(row=3, column=0, columnspan=3, sticky="ew", pady=14)
        ttk.Label(f, text="标准库", style="Field.TLabel").grid(row=4, column=0, sticky="e", padx=(0, 10))
        ttk.Button(f, text="重新加载标准库", command=self._reload).grid(row=4, column=1, sticky="w")
        ttk.Label(f, style="Muted.TLabel", text=(
            f"修改 presets 文件夹中的标准文件后点此生效。版本 {__version__}；报告模板在 templates 文件夹。")).grid(
            row=5, column=1, columnspan=2, sticky="w", pady=(6, 0))
        bar = ttk.Frame(f)
        bar.grid(row=6, column=0, columnspan=3, sticky="e", pady=(18, 0))
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bar, text="保存", style="Accent.TButton", command=self._save).pack(side="right")
        self.grab_set()

    def _browse(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _reload(self):
        if self.on_reload:
            self.on_reload()

    def _save(self):
        self.settings["reports_dir"] = self.dir_var.get().strip()
        self.settings["pdf_engine"] = list(ENGINES)[self.engine.current()]
        self.settings.save()
        self.destroy()
