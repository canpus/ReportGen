"""Run with the *unpacked* runtime/python.exe on Windows. Uses only synthetic in-memory input."""

import json
import os
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile


def verify_launcher(package):
    import ctypes
    import subprocess
    import time
    from ctypes import wintypes as w

    user = ctypes.windll.user32
    title = "ReportGen · 订单规格书审校"
    user.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
    user.FindWindowW.restype = w.HWND
    user.IsWindow.argtypes = [w.HWND]
    user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    if user.FindWindowW(None, title):
        raise RuntimeError("Use a clean Windows GUI session for the launcher check.")
    before = time.monotonic()
    subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "Start-ReportGen.bat"],
        cwd=package,
        check=True,
        timeout=30,
    )
    while time.monotonic() - before < 40:
        win = user.FindWindowW(None, title)
        if win and (package / "private/orders.sqlite3").is_file():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError(
            "Portable BAT did not start the desktop and portable database."
        )
    user.PostMessageW(win, 0x10, 0, 0)
    for _ in range(100):
        if not user.IsWindow(win):
            return
        time.sleep(0.1)
    raise RuntimeError("Desktop did not close cleanly.")


def main():
    if sys.platform != "win32":
        raise RuntimeError("Run this with the Windows ZIP's runtime/python.exe.")
    import ssl
    import tkinter as tk
    import pymupdf
    from cyct_report.orders.api_config import save_settings, load_settings
    from cyct_report.orders.desktop import Desk, register_fonts
    from cyct_report.orders.export import export_directory
    from cyct_report.orders.store import Store

    runtime = Path(sys.executable).resolve().parent
    package = runtime.parent
    for name, path in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        os.environ[name] = str(runtime / "tcl" / path)
    os.add_dll_directory(str(runtime / "DLLs"))
    assert (package / "Start-ReportGen.bat").is_file()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        store = Store(folder / "private")
        # Check dependency resolution into the extracted package, including the C++ runtime.
        assert Path(pymupdf.__file__).resolve().is_relative_to(runtime)
        assert ssl.OPENSSL_VERSION and (runtime / "msvcp140.dll").is_file()
        pdf_path = folder / "synthetic.pdf"
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((50, 95), "2.1 The witness coupon shall be 12 mm wide.")
            pdf.save(pdf_path)
        doc = store.import_pdf(
            pdf_path, "Synthetic", "Demo-Window", "R", providers=(None, None)
        )
        register_fonts()
        root = tk.Tk()
        app = Desk(root, store)
        root.update()
        root.update_idletasks()
        app.render()
        assert app.image and app.image.width() > 0 and app.count == 1
        app.api_dialog()
        root.update()
        assert root.nametowidget(".api_dialog").winfo_viewable()
        root.nametowidget(".api_dialog").destroy()
        app.start_tray()
        tray_available = bool(app.tray)
        if tray_available:
            assert app.tray.data.icon and app.tray.previous
            app.tray.stop()
            app.tray = None
        for row in store.records(doc["id"]):
            store.review(
                doc["id"],
                row["id"],
                version=0,
                action="confirm",
                user="Synthetic reviewer",
                checked=True,
                note="Verified synthetic original.",
            )
        dest = export_directory(store, "Synthetic", folder / "exports")
        assert json.loads((dest / "confirmed.json").read_text(encoding="utf-8"))[
            "requirements"
        ]
        for name in ("confirmed.xlsx", "laboratory.xlsx"):
            with ZipFile(dest / name) as archive:
                assert archive.testzip() is None
        settings = {
            "base_url": "127.0.0.1:8080",
            "model": "fixture",
            "api_key": "synthetic-check-only",
        }
        config = store.root / "api.json"
        save_settings(config, settings)
        assert (
            not settings["api_key"] in config.read_text()
            and load_settings(config)["api_key"] == settings["api_key"]
        )
        root.destroy()
    verify_launcher(package)
    print(
        f"Portable runtime {sys.version.split()[0]}; Tk {tk.TkVersion}; PyMuPDF {pymupdf.__version__}; BAT, GUI, DPAPI, export passed; tray={tray_available}."
    )


if __name__ == "__main__":
    main()
