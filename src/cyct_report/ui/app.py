"""主窗口：顶栏（品牌、页面切换、常用操作）+ 内容区。"""
import ctypes
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

from . import theme
from .. import __version__
from ..db import Database
from ..presets import Library
from ..settings import Settings
from .generate_tab import GenerateTab
from .history_tab import HistoryTab
from .import_dialog import ImportDialog
from .rounded import Button
from .segmented import Segmented
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
        root.geometry("1400x900")
        root.minsize(1180, 720)
        try:
            root.state("zoomed")          # 默认最大化，检测项能多显示几行
        except tk.TclError:
            pass
        theme.apply(root)
        try:
            self.ctx = AppContext()
        except Exception as e:     # 预置库或数据库无法读取时给出明确提示
            messagebox.showerror(TITLE, f"启动失败：{e}")
            raise
        self._topbar()
        self.content = tk.Frame(root, bg=theme.SHELL)
        self.content.pack(fill="both", expand=True, padx=18, pady=(4, 16))
        self.history = HistoryTab(self.content, self.ctx, on_import=self.open_import)
        self.generate = GenerateTab(self.content, self.ctx, on_generated=self.history.refresh)
        self.show("generate")

    def _topbar(self):
        bar = tk.Frame(self.root, bg=theme.SHELL)
        bar.pack(fill="x", padx=18, pady=(14, 8))
        logo = tk.Label(bar, text=theme.ICONS["doc"], font=theme.icon_font(16), bg=theme.SHELL, fg=theme.ACCENT)
        logo.pack(side="left")
        tk.Label(bar, text="出厂检测报告", font=theme.BRAND, bg=theme.SHELL, fg=theme.TEXT).pack(side="left", padx=(8, 4))
        tk.Label(bar, text=f"v{__version__}", font=theme.SMALL, bg=theme.SHELL, fg=theme.FAINT).pack(side="left")
        self.tabs = Segmented(bar, [("generate", "生成报告"), ("history", "历史报告")], "generate",
                              command=self.show, font=theme.BOLD, padx=16, pady=5)
        self.tabs.pack(side="left", padx=28)
        for text, icon, cmd in (("设置", "settings", self.open_settings),
                                ("报告文件夹", "folder", lambda: self.ctx.open_file(self.ctx.settings.reports_dir())),
                                ("导入旧报告", "import", self.open_import)):
            Button(bar, text, cmd, kind="ghost", icon=icon, padx=10, pady=5).pack(side="right", padx=(4, 0))

    def show(self, page):
        self.tabs.select(page, notify=False)
        for name, frame in (("generate", self.generate), ("history", self.history)):
            if name == page:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        if page == "history":
            self.history.refresh()

    def open_import(self):
        ImportDialog(self.root, self.ctx, on_done=self.history.refresh)

    def open_settings(self):
        SettingsDialog(self.root, self.ctx.settings, on_reload=self.reload_presets)

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
