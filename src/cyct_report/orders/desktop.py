"""Native, portable order review workstation. All Tk calls stay on the UI thread."""

import ctypes
import os
from pathlib import Path
from queue import Empty, Queue
import sys
from threading import Thread
import tkinter as tk
from tkinter import ttk

from .api_config import desktop_config, load_settings, save_settings

ICONS = Path(__file__).with_name("icons")
PAPER = "#ffffff"
BACK = "#f3f5f3"
INK = "#18332f"
MUTE = "#596c66"
GREEN = "#16685d"
LINE = "#d9e1dc"
PALE = "#e4f2e9"
AMBER = "#865d1b"
DARK = "#163f39"
FACE = "ReportGen UI"
STATUS = {
    "candidate": "待核对",
    "confirmed": "已确认",
    "clarify": "待澄清",
    "excluded": "已排除",
}
LABELS = {
    "item": "检测项",
    "condition": "试验条件",
    "requirement": "合格判据",
    "typical": "典型值",
    "unit": "单位",
    "method": "检测方法",
    "component": "部件",
    "scenario": "工况",
    "interface": "界面",
    "stage": "阶段",
    "test_temp": "试验温度",
    "conditioning": "预处理",
    "sampling_basis": "抽样基数",
    "frequency": "频次",
    "failure_action": "失败处置",
    "pqt": "PQT",
    "ppt": "PPT",
    "production": "Production",
    "value_role": "数值角色",
    "destination": "检测地点",
}


def release_buffers():
    # Return discarded render / document buffers before starting another memory-intensive phase.
    import gc

    gc.collect()
    if sys.platform.startswith("linux"):
        trim = getattr(ctypes.CDLL(None), "malloc_trim", None)
        if trim:
            trim(0)


def label(parent, text, size=10, color=INK, bold=False, **kw):
    return tk.Label(
        parent,
        text=text,
        font=(FACE, size, "bold" if bold else "normal"),
        fg=color,
        bg=kw.pop("bg", parent.cget("bg")),
        anchor="w",
        padx=0,
        pady=0,
        **kw,
    )


class Button(tk.Canvas):
    """A focusable, keyboard-operable rounded action on both Tk window systems."""

    def __init__(
        self, parent, text, command, name, *, primary=False, width=92, compact=False
    ):
        h = 30 if compact else 37
        super().__init__(
            parent,
            name=name,
            width=width,
            height=h,
            bg=parent.cget("bg"),
            highlightthickness=0,
            takefocus=1,
            cursor="hand2",
        )
        self.command = command
        self.caption = text
        self.primary = primary
        self.w = width
        self.h = h
        self.enabled = True
        self.bind("<Enter>", lambda _: self.draw(True))
        self.bind("<Leave>", lambda _: self.draw())
        self.bind("<FocusIn>", lambda _: self.draw())
        self.bind("<FocusOut>", lambda _: self.draw())
        self.bind(
            "<ButtonRelease-1>",
            lambda e: (
                self.invoke() if 0 <= e.x <= self.w and 0 <= e.y <= self.h else None
            ),
        )
        for event in ("<Return>", "<space>"):
            self.bind(event, lambda _: self.invoke())
        self.draw()

    def invoke(self):
        if self.enabled:
            self.command()

    def draw(self, hover=False):
        self.delete("all")
        w, h = self.w - 1, self.h - 1
        r = 9
        fill = (
            ("#10584e" if hover else GREEN)
            if self.primary
            else ("#edf6ef" if hover else PAPER)
        )
        if not self.enabled:
            fill = "#e4e9e5"
        self.create_polygon(
            1,
            r,
            1,
            1,
            r,
            1,
            w - r,
            1,
            w,
            1,
            w,
            r,
            w,
            h - r,
            w,
            h,
            w - r,
            h,
            r,
            h,
            1,
            h,
            1,
            h - r,
            smooth=True,
            splinesteps=12,
            fill=fill,
            outline=(
                "#43897f"
                if self.tk.call("focus") == str(self)
                else GREEN
                if self.primary
                else "#c9d5cd"
            ),
        )
        self.create_text(
            w / 2,
            h / 2,
            text=self.caption,
            fill=PAPER
            if self.primary and self.enabled
            else INK
            if self.enabled
            else MUTE,
            font=(FACE, 10),
        )

    def enable(self, state):
        self.enabled = state
        self.draw()


def frame(parent, bg=None, **kw):
    return tk.Frame(parent, bg=bg or parent.cget("bg"), **kw)


class Dialog:
    def __init__(self, app, title, name, width=510):
        self.app = app
        self.top = tk.Toplevel(app.root, name=name)
        self.top.title(title)
        self.top.configure(bg=PAPER)
        self.top.transient(app.root)
        self.top.grab_set()
        self.top.minsize(width, 100)
        self.top.geometry(
            f"+{app.root.winfo_rootx() + 85}+{app.root.winfo_rooty() + 55}"
        )
        self.body = frame(self.top)
        self.body.pack(fill="both", expand=True, padx=24, pady=17)
        label(self.body, title, 16, bold=True).pack(fill="x", pady=(0, 10))
        self.values = {}
        self.msg = tk.StringVar()

    def field(self, k, title, value="", secret=False):
        label(self.body, title, 10, MUTE).pack(fill="x", pady=(5, 2))
        v = self.values[k] = tk.StringVar(value=value)
        entry = ttk.Entry(self.body, name=k, textvariable=v, show="•" if secret else "")
        entry.pack(fill="x", ipady=2)
        return entry

    def check(self, k, title, value=False):
        v = self.values[k] = tk.BooleanVar(value=value)
        ttk.Checkbutton(self.body, name=k, text=title, variable=v).pack(
            anchor="w", pady=4
        )

    def actions(self, buttons):
        label(self.body, "", 10, AMBER, textvariable=self.msg, wraplength=520).pack(
            fill="x", pady=4
        )
        bar = frame(self.body)
        bar.pack(fill="x", pady=(3, 0))
        for name, title, callback, primary in buttons:
            Button(
                bar,
                title,
                lambda cb=callback: self.run(cb),
                name,
                primary=primary,
                width=100,
            ).pack(side="right", padx=(6, 0))
        self.top.bind("<Escape>", lambda _: self.close())

    def run(self, cb):
        try:
            cb()
        except (ValueError, OSError, KeyError) as exc:
            self.msg.set(str(exc))

    def get(self):
        return {k: v.get() for k, v in self.values.items()}

    def close(self):
        if self.top.winfo_exists():
            self.top.destroy()


def choose_path(dialog, variable, *, directory=False, on_select=None):
    """Browse with the app's own controls; selected paths stay in the portable workspace."""
    pick = Dialog(
        dialog.app, "选择目录" if directory else "选择 PDF", "path_dialog", 550
    )
    pick.top.transient(dialog.top)
    initial = Path(variable.get() or Path.home()).expanduser()
    current = [initial if initial.is_dir() else initial.parent]
    entry = pick.field("location", "位置（可输入盘符或网络路径）", str(current[0]))
    listing = tk.Listbox(
        pick.body,
        name="files",
        height=13,
        font=(FACE, 10),
        selectmode="browse",
        relief="flat",
        bg=BACK,
        fg=INK,
        selectbackground=GREEN,
        selectforeground=PAPER,
    )
    listing.pack(fill="both", expand=True, pady=5)
    paths = []

    def show(folder):
        folder = folder.resolve()
        contents = sorted(
            (
                p
                for p in folder.iterdir()
                if p.is_dir() or not directory and p.suffix.lower() == ".pdf"
            ),
            key=lambda p: (not p.is_dir(), p.name.casefold()),
        )
        current[0] = folder
        paths[:] = contents
        pick.values["location"].set(str(folder))
        listing.delete(0, "end")
        for p in paths:
            listing.insert("end", p.name + os.sep if p.is_dir() else p.name)

    def done(p):
        variable.set(str(p))
        pick.close()
        dialog.top.grab_set()
        if on_select:
            on_select()

    def open_selected():
        sel = listing.curselection()
        if sel:
            path = paths[sel[0]]
        else:
            path = Path(entry.get()).expanduser()
        if path.is_dir():
            show(path)
        elif not directory and path.is_file() and path.suffix.lower() == ".pdf":
            done(path)
        else:
            raise ValueError("请选择有效的目录或 PDF。")

    def accept():
        if directory:
            sel = listing.curselection()
            path = paths[sel[0]] if sel else Path(entry.get()).expanduser()
            if not path.is_dir():
                raise ValueError("请选择目录。")
            done(path.resolve())
        else:
            open_selected()

    listing.bind("<Double-1>", lambda _: pick.run(open_selected))
    entry.bind(
        "<Return>", lambda _: pick.run(lambda: show(Path(entry.get()).expanduser()))
    )
    pick.top.bind(
        "<Destroy>",
        lambda e: (
            dialog.top.grab_set()
            if e.widget == pick.top and dialog.top.winfo_exists()
            else None
        ),
    )
    pick.actions(
        [
            ("select", "选择", accept, True),
            ("parent", "上一级", lambda: show(current[0].parent), False),
        ]
    )
    pick.run(lambda: show(current[0]))


class Desk:
    def __init__(self, root, store):
        self.root = root
        self.store = store
        self.settings_path = store.root / "api.json"
        try:
            self.settings = load_settings(self.settings_path)
            settings_issue = ""
        except (ValueError, OSError):
            self.settings = {}
            settings_issue = "无法读取本机 API 配置，可在 API 设置中重新保存。"
        self.events = Queue()
        self.busy = False
        self.tray = None
        self.image = None
        self.page = 1
        self.region = None
        self.doc = None
        self.row = None
        self.index = []
        self.docs = []
        self.count = 0
        self.offset = 0
        self.pan_start = None
        self.page_png = None
        self.timer = None
        self.render_key = None
        self.marking = False
        self.start = None
        self.last_reviewer = ""
        root.tk.call("tk", "appname", "ReportGenDesk")
        root.title("ReportGen · 订单规格书审校")
        root.geometry(
            f"{min(1330, root.winfo_screenwidth() - 42)}x{min(880, root.winfo_screenheight() - 75)}+18+20"
        )
        root.minsize(940, 650)
        root.configure(bg=BACK)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.icon = tk.PhotoImage(file=str(ICONS / "application.png"))
        root.iconphoto(True, self.icon)
        if sys.platform == "win32":
            root.iconbitmap(default=str(ICONS / "application.ico"))
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=(FACE, 10), background=PAPER, foreground=INK)
        style.configure(
            "TEntry",
            fieldbackground=PAPER,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            padding=3,
        )
        style.configure(
            "TCombobox",
            fieldbackground=PAPER,
            background=PAPER,
            bordercolor=LINE,
            arrowsize=13,
        )
        style.map("TCombobox", fieldbackground=[("readonly", PAPER)])
        style.configure(
            "Treeview",
            rowheight=29,
            background=PAPER,
            fieldbackground=PAPER,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            font=(FACE, 9),
            background="#eef3ef",
            foreground=MUTE,
            relief="flat",
            padding=4,
        )
        style.map(
            "Treeview",
            background=[("selected", "#d8ede2")],
            foreground=[("selected", INK)],
        )
        top = frame(root, PAPER)
        top.pack(fill="x")
        self.small_icon = self.icon.subsample(3)
        tk.Label(top, image=self.small_icon, bg=PAPER).pack(
            side="left", padx=(20, 9), pady=12
        )
        label(top, "ReportGen", 17, DARK, True).pack(side="left")
        label(top, "订单规格书审校", 13, MUTE).pack(side="left", padx=14)
        self.export_btn = Button(
            top, "导出订单", self.export_dialog, "export_order", primary=True
        )
        self.export_btn.pack(side="right", padx=(5, 18))
        Button(top, "导入 PDF", self.import_dialog, "import_pdf").pack(
            side="right", padx=5
        )
        Button(top, "API 设置", self.api_dialog, "api_settings").pack(
            side="right", padx=5
        )
        self.bar = frame(root, BACK)
        self.bar.pack(fill="x", padx=20, pady=10)
        label(self.bar, "订单文档", 10, MUTE).pack(side="left", padx=(0, 10))
        self.document = ttk.Combobox(
            self.bar, name="documents", state="readonly", width=44
        )
        self.document.pack(side="left")
        self.document.bind(
            "<<ComboboxSelected>>",
            lambda _: self.open_doc(self.docs[self.document.current()]["id"]),
        )
        self.badge = label(self.bar, "", 10, MUTE)
        self.badge.pack(side="right")
        self.main = frame(root, BACK)
        self.main.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        self.message = tk.StringVar(value=settings_issue or "就绪")
        footer = frame(root, "#e6ece7")
        footer.pack(fill="x", side="bottom")
        label(footer, "", 9, MUTE, textvariable=self.message).pack(
            side="left", padx=16, pady=4
        )
        self.empty = frame(self.main, PAPER)
        empty_inner = frame(self.empty)
        empty_inner.place(relx=0.5, rely=0.48, anchor="center")
        label(empty_inner, "导入客户技术规格书", 20, DARK, True).pack()
        label(
            empty_inner,
            "选择英文 PDF，按订单核对检测要求并生成实验室填报模板。",
            11,
            MUTE,
        ).pack(pady=12)
        Button(
            empty_inner,
            "选择规格书",
            self.import_dialog,
            "start",
            primary=True,
            width=128,
        ).pack()
        self.panes = tk.PanedWindow(
            self.main, orient="horizontal", bg=BACK, sashwidth=9, bd=0, showhandle=False
        )
        left = frame(self.panes, PAPER)
        right = frame(self.panes, PAPER)
        self.panes.add(left, minsize=340, stretch="always")
        self.panes.add(right, minsize=490, stretch="always")
        self.build_page(left)
        self.build_list(right)
        self.refresh_documents()
        self.root.after(50, self.poll)
        self.root.after(150, self.start_tray)

    def start_tray(self):
        if self.tray:
            return
        from .tray import install

        try:
            self.tray = install(
                self.root,
                self.icon,
                ICONS / "application.ico",
                self.restore,
                self.close,
            )
        except (OSError, tk.TclError):
            self.message.set("系统托盘暂不可用，窗口可继续审校。")

    def restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def close(self):
        if self.busy:
            self.message.set("正在保存或提取，完成后可关闭。")
            return
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def poll(self):
        try:
            while True:
                cb, args = self.events.get_nowait()
                cb(*args)
        except Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(40, self.poll)

    def work(self, description, task, success, failure=None):
        if self.busy:
            raise ValueError("另一个操作正在进行。")
        self.busy = True
        self.message.set(description)

        def finish(result, error):
            self.busy = False
            release_buffers()
            if error:
                self.message.set(error)
                if failure:
                    failure(error)
            else:
                success(result)

        def worker():
            try:
                self.events.put((finish, (task(), None)))
            except Exception as exc:
                self.events.put((finish, (None, str(exc) or "操作失败")))

        Thread(target=worker, daemon=True).start()

    def build_page(self, left):
        h = frame(left)
        h.pack(fill="x", padx=14, pady=(11, 6))
        label(h, "原页核查", 15, DARK, True).pack(side="left")
        self.pageinfo = label(h, "", 9, MUTE)
        self.pageinfo.pack(side="right")
        bar = frame(left)
        bar.pack(fill="x", padx=12, pady=(0, 8))
        for name, t, cb, w in [
            ("previous_page", "‹", lambda: self.goto(self.page - 1), 31),
            ("next_page", "›", lambda: self.goto(self.page + 1), 31),
            ("zoom", "放大 / 适宽", self.zoom, 99),
            ("manual", "框选补录", self.begin_manual, 86),
        ]:
            Button(bar, t, cb, name, width=w, compact=True).pack(side="left", padx=2)
        self.page_entry = ttk.Entry(bar, name="page_number", width=4)
        self.page_entry.pack(side="right", padx=2)
        self.page_entry.bind("<Return>", lambda _: self.goto(self.page_entry.get()))
        label(bar, "前往页", 9, MUTE).pack(side="right")
        self.paper = tk.Canvas(
            left, name="original", bg="#dfe6e1", bd=0, highlightthickness=0
        )
        self.paper.pack(fill="both", expand=True)
        self.paper.bind("<Configure>", lambda _: self.schedule_render())
        self.paper.bind("<ButtonPress-1>", self.pointer_down)
        self.paper.bind("<ButtonRelease-1>", self.pointer_up)
        self.paper.bind("<B1-Motion>", self.pointer_move)
        self.paper.bind("<Double-1>", lambda e: self.zoom(self.point(e)))

    def build_list(self, right):
        h = frame(right)
        h.pack(fill="x", padx=14, pady=(10, 5))
        label(h, "检测清单", 15, DARK, True).pack(side="left")
        self.counter = label(h, "", 9, MUTE)
        self.counter.pack(side="right")
        bar = frame(right)
        bar.pack(fill="x", padx=12, pady=(2, 6))
        self.filter = ttk.Combobox(
            bar,
            name="status_filter",
            values=["全部状态", *STATUS.values()],
            state="readonly",
            width=8,
        )
        self.filter.current(0)
        self.filter.pack(side="left")
        self.filter.bind("<<ComboboxSelected>>", lambda _: self.filter_rows())
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self.filter_rows())
        label(bar, "查找", 9, MUTE).pack(side="left", padx=(9, 4))
        ttk.Entry(bar, name="search", textvariable=self.query, width=18).pack(
            side="left", fill="x", expand=True
        )
        for name, t, delta in (("prev_list", "‹", -1), ("next_list", "›", 1)):
            Button(
                bar,
                t,
                lambda d=delta: self.draw_rows(self.offset + d * 80),
                name,
                width=28,
                compact=True,
            ).pack(side="left", padx=(3, 0))
        grid = frame(right)
        grid.pack(fill="both", expand=True, padx=10)
        self.tree = ttk.Treeview(
            grid,
            name="records",
            columns=("item", "page", "status"),
            show="headings",
            height=7,
            selectmode="browse",
        )
        for k, title, w in [
            ("item", "检测项 / 活动", 260),
            ("page", "物理页", 55),
            ("status", "状态", 73),
        ]:
            self.tree.heading(k, text=title)
            self.tree.column(k, width=w, minwidth=40, stretch=k == "item")
        scroll = ttk.Scrollbar(grid, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.select_row())
        detail = frame(right, "#f4f8f4")
        detail.pack(fill="both", expand=True, padx=11, pady=(9, 4))
        self.rowtitle = label(
            detail, "选择条款查看依据", 12, DARK, True, wraplength=450
        )
        self.rowtitle.pack(fill="x", padx=10, pady=(7, 2))
        self.details = tk.Text(
            detail,
            name="evidence",
            height=9,
            wrap="word",
            font=(FACE, 10),
            relief="flat",
            bg=detail.cget("bg"),
            fg=INK,
            padx=10,
            pady=3,
        )
        self.details.tag_configure("key", foreground=MUTE, font=(FACE, 9, "bold"))
        self.details.tag_configure("warn", foreground=AMBER)
        self.details.pack(fill="both", expand=True)
        actions = frame(right)
        actions.pack(fill="x", padx=9, pady=(4, 10))
        for key, title, w in (
            ("confirm", "确认", 64),
            ("edit", "修订", 64),
            ("clarify", "待澄清", 75),
            ("exclude", "排除非检测项", 120),
            ("audit", "审计", 65),
        ):
            Button(
                actions,
                title,
                lambda k=key: self.review_dialog(k),
                key,
                width=w,
                primary=key == "confirm",
            ).pack(side="left", padx=2)

    def refresh_documents(self, preferred=None):
        self.docs = self.store.list_documents()
        self.document["values"] = [
            f"{d['order_id']}   /   {d['doc_no']}   ·   {d['doc_rev']}"
            + ("" if d["active"] else "（历史）")
            for d in self.docs
        ]
        if not self.docs:
            self.empty.pack(fill="both", expand=True)
            self.export_btn.enable(False)
            return
        idx = next((i for i, d in enumerate(self.docs) if d["id"] == preferred), 0)
        self.document.current(idx)
        self.open_doc(self.docs[idx]["id"])

    def open_doc(self, doc):
        self.doc = self.store.document(doc)
        self.page = 1
        self.render_key = None
        self.region = None
        self.index = self.store.row_index(doc)
        self.count = self.store.page_count(doc)
        self.row = None
        self.empty.pack_forget()
        self.panes.pack(fill="both", expand=True)
        self.export_btn.enable(True)
        if not getattr(self, "split_initialized", False):
            self.root.update_idletasks()
            self.panes.sash_place(0, int(self.panes.winfo_width() * 0.51), 0)
            self.split_initialized = True
        self.image = None
        self.badge.configure(
            text=f"{self.count} 个物理页   ·   {self.doc['doc_no']}   /   {self.doc['doc_rev']}"
        )
        self.filter.current(0)
        self.query.set("")
        if not self.row:
            self.goto(1)

    def filter_rows(self):
        if not self.doc:
            return
        f = self.filter.get()
        q = self.query.get().strip().casefold()
        self.filtered = [
            r
            for r in self.index
            if (f == "全部状态" or STATUS.get(r["status"]) == f)
            and (
                not q
                or any(
                    q in str(r[k] or "").casefold()
                    for k in (
                        "item",
                        "scenario",
                        "component",
                        "stage",
                        "rid",
                        "channel",
                    )
                )
            )
        ]
        self.draw_rows(0)

    def draw_rows(self, start, preferred=None):
        self.offset = max(0, min(start, (max(1, len(self.filtered)) - 1) // 80 * 80))
        self.tree.delete(*self.tree.get_children())
        self.row = None
        for r in self.filtered[self.offset : self.offset + 80]:
            self.tree.insert(
                "",
                "end",
                iid=r["rid"],
                values=(
                    " ".join(r["item"].split()),
                    r["page"],
                    STATUS.get(r["status"], r["status"]),
                ),
            )
        batch = self.tree.get_children()
        self.counter.configure(
            text=f"{self.offset + 1 if batch else 0}–{self.offset + len(batch)} / {len(self.filtered)} 项"
        )
        if batch:
            rid = preferred if preferred in batch else batch[0]
            self.tree.selection_set(rid)
            self.tree.see(rid)
            self.select_row()
        else:
            self.rowtitle.configure(text="没有符合条件的条款")
            self.write_detail([])
            self.schedule_render()

    def write_detail(self, lines):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        for title, txt, tag in lines:
            if title:
                self.details.insert("end", title + "  ", "key")
            self.details.insert("end", txt + "\n", tag)
        self.details.configure(state="disabled")

    def select_row(self):
        sel = self.tree.selection()
        if not sel or not self.doc:
            return
        r = self.store.record(self.doc["id"], sel[0])
        self.row = r
        self.rowtitle.configure(text=f"{r['id']}   {' '.join(r['item'].split())[:78]}")
        lines = []
        for key in (
            "scenario",
            "condition",
            "requirement",
            "unit",
            "typical",
            "method",
            "frequency",
            "pqt",
            "ppt",
            "production",
            "failure_action",
        ):
            if r.get(key):
                lines.append((LABELS[key], r[key], ""))
        lines.append(("客户原文", r["verbatim"] or "请核对物理页。", ""))
        for a in r["alerts"]:
            lines.append((a["level"], a["message"], "warn"))
        for n in r["notes"]:
            lines.append(("脚注", n["text"], ""))
        for x in r["links"]:
            lines.append(
                ("引用", x.get("label", "") + " · " + str(x.get("pages", [])), "")
            )
        for x in r["reference"]:
            lines.append(
                (
                    "只读对照",
                    " · ".join(
                        str(x[k])
                        for k in (
                            "standard",
                            "coating_type",
                            "section",
                            "temp",
                            "limit",
                            "unit",
                        )
                        if x.get(k)
                    ),
                    "",
                )
            )
        if r["question"]:
            lines.append(("待澄清", r["question"] + " · " + r["respondent"], ""))
        self.write_detail(lines)
        ids = r["bindings"].get("item", [])
        n = int(ids[0].split(".")[0]) if ids else r["source_pages"][0]
        self.goto(n)

    def goto(self, n):
        if not self.doc:
            return
        try:
            n = max(1, min(int(n), self.count))
        except ValueError:
            return
        if n != self.page:
            self.region = None
            self.marking = False
            self.start = None
        self.page = n
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, str(n))
        self.pageinfo.configure(text=f"第 {n} / {self.count} 页")
        self.schedule_render()

    def schedule_render(self):
        if self.timer:
            self.root.after_cancel(self.timer)
        self.timer = self.root.after(45, self.render)

    def render(self):
        self.timer = None
        if not self.doc or self.busy:
            return
        w, h = self.paper.winfo_width() - 22, self.paper.winfo_height() - 22
        if min(w, h) < 20:
            return
        key = (self.doc["id"], self.page, w, h, self.region)
        if key != self.render_key or self.image is None:
            self.paper.delete("all")
            self.image = None
            if key != self.render_key:
                from .pdf import view_page

                self.page_png = view_page(
                    self.store.original_pdf(self.doc["id"]),
                    self.page,
                    w,
                    h,
                    self.region,
                )
                self.pg = self.store.page(self.doc["id"], self.page)
                self.render_key = key
            self.image = tk.PhotoImage(data=self.page_png, format="png")
        self.paper.delete("all")
        iw, ih = self.image.width(), self.image.height()
        self.ox = (w + 22 - iw) // 2
        self.oy = (h + 22 - ih) // 2
        self.paper.create_rectangle(
            self.ox + 2,
            self.oy + 3,
            self.ox + iw + 2,
            self.oy + ih + 3,
            fill="#c8d1c9",
            outline="",
        )
        self.paper.create_image(self.ox, self.oy, image=self.image, anchor="nw")
        wanted = set(self.row["evidence"]) if self.row else set()
        a, b, c, d = self.region or (0, 0, 1, 1)
        for f in self.pg["fragments"]:
            if f["id"] not in wanted:
                continue
            l, t, r, u = f["box"]
            l = max(l, a)
            t = max(t, b)
            r = min(r, c)
            u = min(u, d)
            if r <= l or u <= t:
                continue
            self.paper.create_rectangle(
                self.ox + (l - a) * iw / (c - a),
                self.oy + (t - b) * ih / (d - b),
                self.ox + (r - a) * iw / (c - a),
                self.oy + (u - b) * ih / (d - b),
                outline="#b97b15",
                width=2,
            )

    def point(self, e):
        a, b, c, d = self.region or (0, 0, 1, 1)
        return (
            a + max(0, min(1, (e.x - self.ox) / self.image.width())) * (c - a),
            b + max(0, min(1, (e.y - self.oy) / self.image.height())) * (d - b),
        )

    def zoom(self, point=None):
        if not self.image:
            return
        if self.region:
            self.region = None
        else:
            if point is None:
                bound = next(
                    (
                        f["box"]
                        for f in self.pg["fragments"]
                        if self.row and f["id"] in self.row["bindings"].get("item", [])
                    ),
                    [0.4, 0.4, 0.6, 0.6],
                )
                point = ((bound[0] + bound[2]) / 2, (bound[1] + bound[3]) / 2)
            x = max(0, min(0.55, point[0] - 0.225))
            y = max(0, min(0.55, point[1] - 0.225))
            self.region = (x, y, x + 0.45, y + 0.45)
        self.schedule_render()

    def begin_manual(self):
        self.marking = True
        self.message.set("在原页拖选要补录的区域。")

    def pointer_down(self, e):
        if self.marking and self.image:
            self.start = (e.x, e.y, self.point(e))
        elif self.region and self.image:
            self.pan_start = (e.x, e.y, self.region)

    def pointer_move(self, e):
        if self.start:
            self.paper.delete("drag")
            self.paper.create_rectangle(
                *self.start[:2], e.x, e.y, outline=GREEN, width=2, tags="drag"
            )

    def pointer_up(self, e):
        if self.pan_start and self.image:
            px, py, (a, b, c, d) = self.pan_start
            self.pan_start = None
            dx = (e.x - px) * (c - a) / self.image.width()
            dy = (e.y - py) * (d - b) / self.image.height()
            if abs(e.x - px) + abs(e.y - py) > 4:
                l = min(1 - (c - a), max(0, a - dx))
                t = min(1 - (d - b), max(0, b - dy))
                self.region = (l, t, l + (c - a), t + (d - b))
                self.schedule_render()
            return
        if not self.start:
            return
        x, y = self.start[2]
        r, b = self.point(e)
        self.marking = False
        self.start = None
        bounds = [min(x, r), min(y, b), max(x, r), max(y, b)]
        if bounds[2] - bounds[0] < 0.003 or bounds[3] - bounds[1] < 0.003:
            return
        d = Dialog(self, "原页补录", "manual_dialog")
        d.field("text", "框内客户英文原文")
        d.field("user", "审核人", self.last_reviewer)

        def save():
            v = d.get()
            rid = self.store.add_manual(
                self.doc["id"],
                page=self.page,
                box=bounds,
                text=v["text"],
                user=v["user"],
            )
            d.close()
            self.reload_row(rid)

        d.actions([("save_manual", "保存补录", save, True)])

    def reload_row(self, rid):
        self.index = self.store.row_index(self.doc["id"])
        self.filter_rows()
        i = next((i for i, r in enumerate(self.filtered) if r["rid"] == rid), None)
        if i is not None:
            self.draw_rows(i // 80 * 80, rid)

    def api_dialog(self):
        if self.busy:
            return
        d = Dialog(self, "视觉 API 设置", "api_dialog")
        cfg = self.settings
        d.check("enabled", "启用视觉解析", cfg.get("enabled", False))
        d.field(
            "base_url",
            "服务地址（主机:端口、内网 HTTP 或 HTTPS）",
            cfg.get("base_url", ""),
        )
        d.field("model", "模型名称", cfg.get("model", ""))
        d.field("api_key", "密钥（可留空）", cfg.get("api_key", ""), True)
        d.field("auth_header", "认证头", cfg.get("auth_header", "Authorization"))
        d.field(
            "auth_prefix",
            "认证前缀（自定义密钥头可留空）",
            cfg.get("auth_prefix", "Bearer"),
        )
        d.check(
            "allow_external_pages",
            "允许向此服务发送筛选后的规格书页",
            cfg.get("allow_external_pages", False),
        )

        def save():
            from .adapters import adapters

            vals = d.get()
            if vals["enabled"]:
                adapters(desktop_config(vals))
            save_settings(self.settings_path, vals)
            self.settings = vals
            d.close()
            self.message.set("API 配置已保存到本机私有目录。")

        def test():
            from .adapters import Vision

            client = Vision(d.get())
            d.msg.set("正在测试模型连接…")
            self.work(
                "测试模型连接…",
                client.test_connection,
                lambda _: (
                    d.msg.set("连接成功，模型已响应。")
                    if d.top.winfo_exists()
                    else None
                ),
                d.msg.set,
            )

        d.actions(
            [
                ("save_api", "保存配置", save, True),
                ("test_api", "测试连接", test, False),
            ]
        )

    def import_dialog(self):
        if self.busy:
            return
        d = Dialog(self, "导入订单规格书", "import_dialog", 560)
        path = d.field("file", "英文 PDF 文件")

        def choose():
            choose_path(d, d.values["file"], on_select=lambda: preview(0))

        options = frame(d.body)
        options.pack(fill="x", pady=(3, 1))
        Button(options, "选择 PDF", choose, "browse", width=86, compact=True).pack(
            side="left"
        )
        for key, title in (
            ("order", "订单号"),
            ("number", "文号"),
            ("revision", "版次"),
        ):
            d.field(key, title)
        d.field("pages", "视觉发送页范围（留空自动筛选可识别页，例如 3,5-8）")
        d.check("baseline", "合同另行指定 ISO 21809-3:2016 作为只读对照")
        local = frame(d.body, "#eef3ef")
        local.pack(fill="x", pady=4)
        state = {"page": 1, "total": 0}
        thumb = tk.Label(local, bg=local.cget("bg"))
        thumb.pack(side="left", padx=5)
        state_label = label(
            local, "可先预览纯扫描页，再选择允许发送的物理页。", 9, MUTE, wraplength=210
        )
        state_label.pack(side="left", fill="x", expand=True, padx=6)

        def preview(step):
            import pymupdf
            from .pdf import view_page

            name = d.values["file"].get()
            if not Path(name).is_file():
                raise ValueError("请选择 PDF 文件。")
            with pymupdf.open(name) as pdf:
                state["total"] = len(pdf)
            n = max(1, min(state["total"], state["page"] + step))
            state["page"] = n
            thumb.image = tk.PhotoImage(data=view_page(name, n, 125, 94), format="png")
            thumb.configure(image=thumb.image)
            state_label.configure(text=f"物理页 {n} / {state['total']}")

        for name, title, step in (
            ("preview_previous", "‹", -1),
            ("preview_next", "›", 1),
            ("preview_pdf", "预览", 0),
        ):
            Button(
                local,
                title,
                lambda s=step: d.run(lambda: preview(s)),
                name,
                width=46,
                compact=True,
            ).pack(side="right", padx=1)

        def submit():
            vals = d.get()
            if not Path(vals["file"]).is_file() or not all(
                vals[k].strip() for k in ("order", "number", "revision")
            ):
                raise ValueError("请选择文件并填全订单号、文号和版次。")
            cfg = desktop_config(self.settings)
            d.msg.set("正在逐页提取…")

            def done(doc):
                if d.top.winfo_exists():
                    d.close()
                self.refresh_documents(doc["id"])
                self.message.set("导入完成，可逐条核查候选项。")

            thumb.configure(image="")
            thumb.image = None
            release_buffers()
            self.work(
                "正在导入 PDF…",
                lambda: self.store.import_pdf(
                    vals["file"],
                    vals["order"],
                    vals["number"],
                    vals["revision"],
                    config=cfg,
                    vision_pages=vals["pages"],
                    reference_edition="ISO 21809-3:2016" if vals["baseline"] else None,
                ),
                done,
                d.msg.set,
            )

        d.actions(
            [
                ("submit_import", "导入并提取", submit, True),
                ("cancel", "取消", d.close, False),
            ]
        )
        path.focus_set()

    def review_dialog(self, action):
        if self.busy or not self.row:
            return
        r = self.row
        title = {
            "confirm": "确认检测项",
            "edit": "原位修订",
            "clarify": "登记待澄清",
            "exclude": "排除非检测项",
            "audit": "审计记录",
        }[action]
        d = Dialog(self, title, "review_dialog", 525)
        label(
            d.body,
            r["id"] + "  ·  " + " ".join(r["item"].split())[:110],
            10,
            MUTE,
            wraplength=460,
        ).pack(fill="x", pady=(0, 4))
        if action == "audit":
            events = self.store.audit(self.doc["id"], r["id"])
            audit = tk.Text(d.body, width=60, height=12, wrap="word", font=(FACE, 10))
            audit.pack()
            for event in events:
                audit.insert(
                    "end",
                    f"{event['stamp']}  {event['user']}  {event['action']}\n{event['detail']}\n",
                )
            audit.configure(state="disabled")
            d.actions([("done", "关闭", d.close, True)])
            return
        d.field("user", "审核人", self.last_reviewer)
        if action == "clarify":
            d.field(
                "question",
                "澄清问题",
                r["question"] or " ".join(r.get("clarification_suggestions", [])),
            )
            d.field("respondent", "待答方", r["respondent"])
        d.field("note", "排除原因（必填）" if action == "exclude" else "核查或修订依据")
        changes = {}
        edit_key = None
        if action == "edit":
            select = ttk.Combobox(
                d.body,
                name="edit_field",
                state="readonly",
                values=list(LABELS.values()),
            )
            select.pack(fill="x")
            select.current(0)
            entry = d.field("new_value", "字段值", r["item"])
            current = ["item"]

            def swap(_):
                changes[current[0]] = entry.get()
                current[0] = list(LABELS)[select.current()]
                d.values["new_value"].set(changes.get(current[0], r[current[0]]))

            select.bind("<<ComboboxSelected>>", swap)
            edit_key = current
        if action == "confirm" or r["channel"] == "coverage":
            d.check("checked", "已对照原图核实高风险符号与告警")
        if r["channel"] == "coverage":
            d.check("no_requirements", "已核实整页没有检测要求")

        def save():
            vals = d.get()
            if edit_key:
                changes[edit_key[0]] = vals.pop("new_value")
            self.store.review(
                self.doc["id"],
                r["id"],
                version=r["version"],
                action=action,
                changes=changes,
                **vals,
            )
            self.last_reviewer = vals["user"]
            d.close()
            self.reload_row(r["id"])
            self.message.set(r["id"] + " 已保存。")

        d.actions(
            [("save_review", "保存", save, True), ("cancel", "取消", d.close, False)]
        )

    def export_dialog(self):
        if self.busy or not self.doc:
            return
        d = Dialog(self, "导出订单", "export_dialog")
        d.field("directory", "导出目录", str(self.store.root.parent / "exports"))

        def choose():
            choose_path(d, d.values["directory"], directory=True)

        def save():
            release_buffers()
            from .export import export_directory

            dest = d.values["directory"].get().strip()
            if not dest:
                raise ValueError("请选择私有导出目录。")
            # The export worker has exclusive use of this order while writing. Drop the
            # decoded source raster and display a progress indicator until the workbook is closed.
            self.paper.delete("all")
            self.image = None
            self.paper.create_text(
                self.paper.winfo_width() / 2,
                self.paper.winfo_height() / 2,
                text="正在生成订单文件…",
                font=(FACE, 12),
                fill=MUTE,
            )
            release_buffers()

            def failed(message):
                d.msg.set(message)
                self.schedule_render()

            def done(path):
                self.schedule_render()
                if d.top.winfo_exists():
                    d.close()
                self.message.set("已导出 · " + str(path))

            self.work(
                "生成确认清单与实验室模板…",
                lambda: export_directory(self.store, self.doc["order_id"], dest),
                done,
                failed,
            )

        d.actions(
            [
                ("save_export", "导出文件", save, True),
                ("browse", "选择目录", choose, False),
            ]
        )


def register_fonts():
    fonts = Path(__file__).with_name("fonts")
    if sys.platform == "win32":
        for font in fonts.glob("*.otf"):
            ctypes.windll.gdi32.AddFontResourceExW(str(font), 0x10, None)
    elif sys.platform.startswith("linux"):
        try:
            fc = ctypes.CDLL("libfontconfig.so.1")
            fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            for font in fonts.glob("*.otf"):
                fc.FcConfigAppFontAddFile(None, os.fsencode(font))
        except OSError:
            pass


def launch(store):
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ReportGen.OrderReview.Desktop"
        )
        ctypes.windll.user32.SetProcessDPIAware()
    register_fonts()
    root = tk.Tk()
    Desk(root, store)
    root.mainloop()
