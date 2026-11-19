"""分段选择器：一排圆角按钮，选中的高亮（报告语言、页签）。"""
import tkinter as tk

from .rounded import Button


class Segmented(tk.Frame):
    def __init__(self, master, options, value, command=None, font=None, padx=12, pady=4):
        """options: [(值, 显示文字)]"""
        super().__init__(master, bg=master.cget("bg"))
        self.value, self.command = value, command
        self.buttons = {}
        for i, (val, text) in enumerate(options):
            b = Button(self, text, lambda v=val: self.select(v), kind="ghost", font=font,
                       padx=padx, pady=pady)
            b.pack(side="left", padx=(0 if i == 0 else 4, 0))
            self.buttons[val] = b
        self._refresh()

    def _refresh(self):
        for val, b in self.buttons.items():
            b.set_kind("accent" if val == self.value else "soft")

    def select(self, value, notify=True):
        if value == self.value:
            return
        self.value = value
        self._refresh()
        if notify and self.command:
            self.command(value)

    def get(self):
        return self.value
