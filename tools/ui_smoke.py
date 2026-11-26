"""开发用：驱动界面走一遍“填写 → 生成 → 查询 → 导入”，并截图。

用法：python tools/ui_smoke.py <截图目录>
弹窗被替换为自动应答；使用截图目录下的独立合成数据。
"""
import sys
import time
import tempfile
from pathlib import Path
from tkinter import messagebox

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image                                  # noqa: E402

from cyct_report import importer, paths                           # noqa: E402
from cyct_report.models import Product                     # noqa: E402
from cyct_report.ui import app as app_mod                  # noqa: E402

LOG = []
messagebox.askyesno = lambda *a, **k: LOG.append(("ask", a[:2])) or True
messagebox.showinfo = lambda *a, **k: LOG.append(("info", a[:2]))
messagebox.showwarning = lambda *a, **k: LOG.append(("warn", a[:2]))
messagebox.showerror = lambda *a, **k: LOG.append(("error", a[:2]))
app_mod.AppContext.reveal = staticmethod(lambda p: LOG.append(("reveal", str(p))))


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def shot(root, path):
    """用 PrintWindow 抓取窗口内容（屏幕锁定或窗口被遮挡时也可用）。"""
    import ctypes
    from ctypes import wintypes
    root.update()
    hwnd = int(root.wm_frame(), 16)
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    gdi, user = ctypes.windll.gdi32, ctypes.windll.user32
    hdc = user.GetWindowDC(hwnd)
    mdc = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, h)
    gdi.SelectObject(mdc, bmp)
    user.PrintWindow(hwnd, mdc, 2)
    buf = ctypes.create_string_buffer(w * h * 4)
    hdr = (ctypes.c_uint32 * 10)(40, w, (-h) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
    gdi.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(hdr), 0)
    Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).save(path)
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mdc)
    user.ReleaseDC(hwnd, hdc)


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths.APP_DIR = Path(tempfile.mkdtemp(prefix="synthetic-", dir=out))
    root = app_mod.tk.Tk()
    a = app_mod.App(root)
    g = a.generate
    pump(root, 1)
    std_ids = [s.id for s in a.ctx.lib.standards]
    # 英文报告：ISO 21809-3 / 14B-2（界面仍显示中文）
    g.std_box.current(std_ids.index("iso21809-3"))
    g._std_changed(preferred="14B-2")
    g.lang.select("en")
    g.customer.set_text("Mock Fixture")
    g.products.set_products([Product("80℃ Heat Shrinkable sleeves SIMQΦ131x480x2.2mm", "173", "set",
                                     "SIM001-41"), Product("80℃ Heat Shrinkable sleeves SIMQΦ227x480x2.2mm",
                                                            "800", "set", "SIM001-41")])
    rows = [r for r in g.items.rows if r.var is not None]
    for r, val in zip(rows, ["2.18", "无漏点", "＞9", "", "0.91", "3.11", "17", "12.01", "0.81"]):
        r.var.set(val)
    g.items.select_row(rows[3])
    pump(root, 0.8)
    shot(root, out / "1-generate.png")
    g.generate()
    pump(root, 15)
    # 中文 GB 报告，客户带“星”
    g.std_box.current(std_ids.index("gbt23257"))
    g._std_changed(preferred="hs")
    g.lang.select("zh")
    g.customer.set_text("合成星点测试设计工作室")
    g.products.set_products([Product("常温热缩带SIMQ137x410/2.1mm", "30", "set", "SIM001-39")])
    g.generate()
    pump(root, 15)
    samples = a.ctx.settings.reports_dir()
    if samples.exists():
        for rec in [importer.read_record(f) for f in importer.scan_folder(samples)]:
            if rec.customer:
                importer.import_record(rec, a.ctx.db, a.ctx.settings.reports_dir(), "content")
    a.show("history")
    pump(root, 0.8)
    shot(root, out / "2-history.png")
    a.history.customer.set_text("星")
    a.history.refresh()
    print("rows (星):", len(a.history.tree.get_children()))
    for entry in LOG:
        print(entry[0], str(entry[1])[:160])
    root.destroy()


if __name__ == "__main__":
    main(sys.argv[1])
