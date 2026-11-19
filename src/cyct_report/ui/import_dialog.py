"""“导入旧报告”对话框：选择文件/文件夹 → 预览解析结果 → 导入。"""
import itertools
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import theme
from .. import importer
from .widgets import TreeEditor, run_background

COLUMNS = ("file", "customer", "products", "standard", "batch", "ctime", "mtime", "cdate", "state")
HEADINGS = {"file": "文件", "customer": "客户（可双击修改）", "products": "产品", "standard": "标准",
            "batch": "批号", "ctime": "创建时间", "mtime": "修改时间", "cdate": "报告内日期",
            "state": "状态"}
WIDTHS = {"file": 230, "customer": 220, "products": 220, "standard": 130, "batch": 90,
          "ctime": 120, "mtime": 120, "cdate": 85, "state": 160}
TIME_LABELS = {"ctime": "文件创建时间（默认）", "mtime": "文件修改时间", "content": "报告内的日期"}


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


class ImportDialog(tk.Toplevel):
    def __init__(self, master, ctx, on_done):
        super().__init__(master)
        self.ctx, self.on_done = ctx, on_done
        self.title("导入以前手工制作的报告")
        self.configure(bg=theme.LANE)
        self.geometry("1350x600")
        self.transient(master)
        self.records = {}
        self._ids = itertools.count()
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="选择报告文件…", command=self.pick_files).pack(side="left", padx=3)
        ttk.Button(top, text="选择文件夹（含子文件夹）…", command=self.pick_folder).pack(side="left", padx=3)
        ttk.Label(top, text="报告时间取自").pack(side="left", padx=(20, 4))
        self.time_source = tk.StringVar(value="ctime")
        for key, label in TIME_LABELS.items():
            ttk.Radiobutton(top, text=label, value=key, variable=self.time_source).pack(side="left", padx=3)
        ttk.Label(self, foreground="#555", padding=(8, 0), text=(
            "支持 .docx / .doc（.doc 需本机装有 Word 或 WPS，后台读取）。同名 PDF 会一并导入。"
            "提示：文件被拷贝过时，“创建时间”是拷贝那天，可改用修改时间或报告内日期；未识别到报告内日期的仍按创建时间。"
        ), wraplength=1300).pack(fill="x")

        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings", selectmode="extended")
        for c in COLUMNS:
            self.tree.heading(c, text=HEADINGS[c])
            self.tree.column(c, width=WIDTHS[c], stretch=c in ("file", "customer", "products"))
        sb = ttk.Scrollbar(frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("err", foreground="#c00000")
        self.editor = TreeEditor(self.tree, self._spec, self._get, self._commit, COLUMNS)
        self.tree.bind("<Double-Button-1>", self._dbl)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        self.status = ttk.Label(bar, foreground="#555")
        self.status.pack(side="left")
        ttk.Button(bar, text="关闭", command=self.destroy).pack(side="right", padx=4)
        self.import_btn = ttk.Button(bar, text="开始导入", command=self.do_import)
        self.import_btn.pack(side="right", padx=4)
        ttk.Button(bar, text="移除选中", command=self.remove_selected).pack(side="right", padx=4)

    # ---------- 选择与解析 ----------
    def pick_files(self):
        files = filedialog.askopenfilenames(parent=self, title="选择报告",
                                            filetypes=[("Word 报告", "*.docx *.doc")])
        self._load([Path(f) for f in files])

    def pick_folder(self):
        folder = filedialog.askdirectory(parent=self, title="选择存放旧报告的文件夹")
        if folder:
            self._load(importer.scan_folder(folder))

    def _load(self, files):
        known = {r.path for r in self.records.values()}
        files = [f for f in files if f not in known]
        if not files:
            return
        self.status.configure(text=f"正在读取 {len(files)} 个文件…（.doc 文件较慢）")
        self.import_btn.configure(state="disabled")
        engine = self.ctx.settings.get("pdf_engine", "auto")
        run_background(self, lambda: [importer.read_record(f, engine) for f in files], self._loaded)

    def _loaded(self, records, error):
        self.import_btn.configure(state="normal")
        if error:
            messagebox.showerror("导入", f"读取失败：{error}", parent=self)
            return
        for rec in records:
            iid = f"r{next(self._ids)}"
            self.records[iid] = rec
            self.tree.insert("", "end", iid=iid)
            self._render(iid)
        self.status.configure(text=f"已列出 {len(self.records)} 个文件。")

    def _render(self, iid, state=None):
        r = self.records[iid]
        state = state or (r.error or "待导入")
        self.tree.item(iid, tags=("err",) if r.error and not r.customer else (), values=(
            r.path.name, r.customer, "；".join(p[0] for p in r.products), r.standard, r.batch,
            _fmt(r.ctime), _fmt(r.mtime), r.content_date.isoformat() if r.content_date else "", state))

    # ---------- 编辑 ----------
    def _spec(self, iid, col):
        return "entry" if col in ("customer", "standard", "batch") else None

    def _get(self, iid, col):
        return getattr(self.records[iid], col)

    def _commit(self, iid, col, value):
        setattr(self.records[iid], col, value.strip())
        if col == "customer" and value.strip():
            self.records[iid].error = ""
        self._render(iid)

    def _dbl(self, e):
        iid, col = self.tree.identify_row(e.y), self.tree.identify_column(e.x)
        if iid and col:
            self.editor.edit(iid, COLUMNS[int(col[1:]) - 1])

    def remove_selected(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.records.pop(iid, None)

    # ---------- 导入 ----------
    def do_import(self):
        self.editor.close(save=True)
        todo = [i for i in self.tree.get_children() if self.records[i].customer]
        skipped = len(self.tree.get_children()) - len(todo)
        if not todo:
            messagebox.showinfo("导入", "没有可导入的文件（客户名为空的文件需先填写客户）。", parent=self)
            return
        src, root = self.time_source.get(), self.ctx.settings.reports_dir()
        done = 0
        for iid in todo:
            try:
                importer.import_record(self.records[iid], self.ctx.db, root, src)
                done += 1
                self.tree.delete(iid)
                self.records.pop(iid)
            except OSError as e:
                self._render(iid, state=f"失败：{e}")
        self.on_done()
        messagebox.showinfo("导入", f"已导入 {done} 份报告。" + (
            f"\n{skipped} 份因客户名为空未导入。" if skipped else ""), parent=self)
