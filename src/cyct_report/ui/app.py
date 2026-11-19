"""主窗口。"""
import ctypes
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .. import __version__
from ..db import Database
from ..presets import Library
from ..settings import Settings
from .generate_tab import GenerateTab
from .history_tab import HistoryTab
from .import_dialog import ImportDialog
from .settings_dialog import SettingsDialog

TITLE = "CYCT 出厂检测报告生成器"


class AppContext:
    def __init__(self):
        self.settings = Settings()
        self.db = Database()
        self.lib = Library()

    @staticmethod
    def open_file(path):
        os.startfile(str(path))

    @staticmethod
    def reveal(path):
        """打开资源管理器并选中文件。"""
        subprocess.Popen(["explorer", "/select,", os.path.normpath(str(path))])


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"{TITLE}  v{__version__}")
        root.geometry("1360x860")
        root.minsize(1100, 680)
        self._style()
        try:
            self.ctx = AppContext()
        except Exception as e:     # 预置库或数据库无法读取时给出明确提示
            messagebox.showerror(TITLE, f"启动失败：{e}")
            raise
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.history = HistoryTab(self.nb, self.ctx, on_import=self.open_import)
        self.generate = GenerateTab(self.nb, self.ctx, on_generated=self.history.refresh)
        self.nb.add(self.generate, text="  生成报告  ")
        self.nb.add(self.history, text="  历史报告  ")
        self.nb.bind("<<NotebookTabChanged>>", self._tab_changed)
        self._menu()

    def _style(self):
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        default = ("Microsoft YaHei UI", 9)
        self.root.option_add("*Font", default)
        for name in ("TLabel", "TButton", "TRadiobutton", "TCheckbutton", "TEntry", "TCombobox",
                     "TLabelframe.Label", "TNotebook.Tab"):
            style.configure(name, font=default)
        style.configure("Treeview", font=default, rowheight=24)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    def _menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=False)
        f.add_command(label="导入旧报告…", command=self.open_import)
        f.add_command(label="打开报告文件夹", command=lambda: self.ctx.open_file(
            self.ctx.settings.reports_dir()))
        f.add_separator()
        f.add_command(label="退出", command=self.root.destroy)
        m.add_cascade(label="文件", menu=f)
        s = tk.Menu(m, tearoff=False)
        s.add_command(label="设置…", command=lambda: SettingsDialog(self.root, self.ctx.settings))
        s.add_command(label="重新加载标准库", command=self.reload_presets)
        m.add_cascade(label="工具", menu=s)
        h = tk.Menu(m, tearoff=False)
        h.add_command(label="关于", command=lambda: messagebox.showinfo(
            "关于", f"{TITLE}\n版本 {__version__}\n\n标准库：presets 文件夹\n报告模板：templates 文件夹"))
        m.add_cascade(label="帮助", menu=h)
        self.root.configure(menu=m)

    def _tab_changed(self, _e):
        if self.nb.select() == str(self.history):
            self.history.refresh()

    def open_import(self):
        ImportDialog(self.root, self.ctx, on_done=self.history.refresh)

    def reload_presets(self):
        self.ctx.lib.reload()
        self.generate._init_standard()
        messagebox.showinfo("重新加载标准库", "已重新读取 presets 文件夹中的标准库。")


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # 高分屏下字体清晰
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
