"""带固定表头的纵向滚动表格容器：表头与每一行共用同一套列宽，保证对齐。"""
import tkinter as tk
from tkinter import ttk


class ScrollTable(tk.Frame):
    def __init__(self, master, columns, bg, header_bg):
        """columns: [(标题, 最小宽度px, 伸展权重)]"""
        super().__init__(master, bg=bg)
        self.columns = columns
        self.header = tk.Frame(self, bg=header_bg)
        self.header.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=bg)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.vbar.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.layout(self.header)
        self.header.grid_columnconfigure(len(columns), minsize=18)   # 让出滚动条宽度
        self.body.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.width_callbacks = []

    def layout(self, frame):
        for i, (_t, width, weight) in enumerate(self.columns):
            frame.grid_columnconfigure(i, minsize=width, weight=weight)

    def _on_resize(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        for cb in self.width_callbacks:
            cb(e.width)

    def _wheel(self, e):
        if self.body.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")

    def see(self, widget):
        self.update_idletasks()
        total = max(self.body.winfo_height(), 1)
        y, h = widget.winfo_y(), widget.winfo_height()
        top, view = self.canvas.canvasy(0), self.canvas.winfo_height()
        if y < top:
            self.canvas.yview_moveto(y / total)
        elif y + h > top + view:
            self.canvas.yview_moveto((y + h - view) / total)

    def to_top(self):
        self.canvas.yview_moveto(0)
