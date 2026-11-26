"""Drive the shipping Tk desktop over a private Linux X display and sample its whole process tree."""

import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Event, Thread
import time
import tkinter as tk
from zipfile import ZipFile

import psutil
from PIL import ImageGrab
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tests.orders.desktop_fixture import desktop_order, SCAN_ROW, TOTAL_PAGES

LIMIT = 100_000_000


class Service(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/v1/chat/completions" and request["temperature"] == 0
        content = request["messages"][-1]["content"]
        if isinstance(content, str):
            assert content == "Reply OK."
            answer = "OK"
            self.server.tests += 1
        else:
            assert any(
                it.get("image_url", {})
                .get("url", "")
                .startswith("data:image/png;base64,")
                for it in content
            )
            answer = (
                chr(96) * 3
                + "json\n"
                + json.dumps({"rows": [SCAN_ROW]})
                + "\n"
                + chr(96) * 3
            )
            self.server.images += 1
        body = json.dumps({"choices": [{"message": {"content": answer}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TrayHost:
    """A real XEmbed host on the isolated X display, owned by the observer."""

    def __init__(self):
        from Xlib import X, display

        self.x = display.Display()
        self.root = self.x.screen().root
        selection = self.x.intern_atom(
            "_NET_SYSTEM_TRAY_S" + str(self.x.get_default_screen())
        )
        if self.x.get_selection_owner(selection):
            raise RuntimeError("Use a private display with no tray manager")
        self.window = self.root.create_window(
            1370, 20, 28, 28, 0, X.CopyFromParent, event_mask=X.StructureNotifyMask
        )
        self.window.set_selection_owner(selection, X.CurrentTime)
        self.window.map()
        self.x.sync()
        self.opcode = self.x.intern_atom("_NET_SYSTEM_TRAY_OPCODE")
        self.icon = None

    def docked(self):
        from Xlib import X

        while self.x.pending_events():
            ev = self.x.next_event()
            if (
                ev.type == X.ClientMessage
                and ev.client_type == self.opcode
                and ev.data[1][1] == 0
            ):
                self.icon = self.x.create_resource_object("window", ev.data[1][2])
                self.icon.reparent(self.window, 0, 0)
                self.icon.map()
                self.x.sync()
        return (
            self.icon is not None and self.icon.query_tree().parent.id == self.window.id
        )

    def taskbar_icon(self, wm_frame):
        from Xlib import X

        window = self.x.create_resource_object("window", int(str(wm_frame), 0))
        atom = self.x.intern_atom("_NET_WM_ICON")
        return any(
            (prop := w.get_full_property(atom, X.AnyPropertyType)) is not None
            and len(prop.value) > 100
            for w in (window, window.query_tree().parent)
        )

    def close(self):
        self.x.close()


class Driver:
    def __init__(self):
        self.tk = tk.Tk()
        self.tk.withdraw()
        self.app = "ReportGenDesk"

    def script(self, script):
        return self.tk.tk.call("send", self.app, script)

    def cmd(self, *args):
        return self.script(tk._join(args))

    def find(self, name, scope="."):
        return self.cmd("findByName", scope, name)

    def click(self, name, scope="."):
        widget = self.find(name, scope)
        assert widget, name
        self.cmd("update", "idletasks")
        self.wait(lambda: int(self.cmd("winfo", "ismapped", widget)), "map " + name)
        self.cmd("event", "generate", widget, "<ButtonRelease-1>", "-x", 8, "-y", 8)

    def fill(self, name, value, scope="."):
        widget = self.find(name, scope)
        assert widget, name
        self.cmd(widget, "delete", 0, "end")
        self.cmd(widget, "insert", 0, str(value))

    def wait(self, predicate, description, timeout=45):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.04)
        raise AssertionError(description)

    def modal_closed(self, dialog):
        self.wait(
            lambda: not int(self.cmd("winfo", "exists", "." + dialog)),
            dialog + " did not close",
        )

    def screenshot(self, path, window="."):
        self.cmd("update", "idletasks")
        time.sleep(0.12)
        x, y, w, h = [
            int(self.cmd("winfo", key, window))
            for key in ("rootx", "rooty", "width", "height")
        ]
        ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ["DISPLAY"]).save(
            path
        )

    def status(self, dialog, text):
        return bool(int(self.cmd("hasText", dialog, text)))


def verify_files(folder):
    [result] = folder.glob("*/confirmed.json")
    snap = json.loads(result.read_text())
    assert len(snap["excluded"]) == 2 and len(snap["clarifications"]) == 1
    assert len(snap["requirements"]) == 112 and snap["omitted_pending"] == 0
    assert any(a["action"] == "edit" for a in snap["audit"])
    for file in ["confirmed.xlsx", "laboratory.xlsx"]:
        with ZipFile(result.with_name(file)) as archive:
            assert archive.testzip() is None
            if file == "laboratory.xlsx":
                assert all(
                    b'TargetMode="External"' not in archive.read(n)
                    for n in archive.namelist()
                    if n.endswith(".rels")
                )
        book = load_workbook(result.with_name(file))
        if file == "laboratory.xlsx":
            for ws in book:
                headers = [c.value for c in ws[1]]
                for row in list(ws.rows)[1:]:
                    for field in (
                        "Actual Test Result",
                        "Lab Judgement",
                        "Test Specimen/Date",
                    ):
                        c = row[headers.index(field)]
                        assert c.value is None and not c.protection.locked
        book.close()
    return {
        "confirmed": len(snap["requirements"]),
        "excluded": len(snap["excluded"]),
        "clarifications": len(snap["clarifications"]),
    }


def run(python, out):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pdf = desktop_order(out / "schedule.pdf")
    api = ThreadingHTTPServer(("127.0.0.1", 0), Service)
    api.tests = api.images = 0
    Thread(target=api.serve_forever, daemon=True).start()
    d = Driver()
    tray = TrayHost()
    if d.app in d.tk.tk.call("winfo", "interps"):
        raise RuntimeError("Use a separate display for the acceptance run")
    phase = ["startup"]
    samples = []
    stopped = Event()
    start = time.monotonic()
    with (out / "desktop.stderr").open("w") as log:
        app = subprocess.Popen(
            [
                "prlimit",
                "--as=8000000000",
                "--",
                str(python),
                str(ROOT / "tools/order_desktop.py"),
                "--data-dir",
                str(out / "private"),
            ],
            stderr=log,
            stdout=log,
        )
        main = psutil.Process(app.pid)

        def sample():
            while not stopped.is_set():
                try:
                    processes = [main, *main.children(recursive=True)]
                    rss = sum(p.memory_info().rss for p in processes)
                    hwm = (
                        int(
                            next(
                                x.split()[1]
                                for x in Path(f"/proc/{app.pid}/status")
                                .read_text()
                                .splitlines()
                                if x.startswith("VmHWM:")
                            )
                        )
                        * 1024
                    )
                    samples.append(
                        (time.monotonic() - start, phase[0], rss, hwm, len(processes))
                    )
                except (StopIteration, FileNotFoundError, psutil.NoSuchProcess):
                    pass
                stopped.wait(0.005)

        sampler = Thread(target=sample)
        sampler.start()
        try:
            d.wait(lambda: d.app in d.tk.tk.call("winfo", "interps"), "desktop startup")
            d.script("""proc findByName {root name} {
              foreach w [winfo children $root] {if {[winfo name $w] eq $name} {return $w}
                set found [findByName $w $name]; if {$found ne ""} {return $found}}
              return "" }
              proc hasText {root value} {
                foreach w [winfo children $root] {
                  if {![catch {$w cget -text} v] && [string match "*$value*" $v]} {return 1}
                  if {[hasText $w $value]} {return 1}}; return 0 }""")
            d.wait(lambda: d.find("api_settings"), "main window")
            d.wait(tray.docked, "native tray dock")
            assert tray.taskbar_icon(d.cmd("wm", "frame", "."))
            time.sleep(0.24)
            phase[0] = "api"
            d.click("api_settings")
            d.cmd(d.find("enabled", ".api_dialog"), "invoke")
            d.fill("base_url", f"127.0.0.1:{api.server_port}", ".api_dialog")
            d.fill("model", "synthetic-vision", ".api_dialog")
            d.click("test_api")
            d.wait(lambda: d.status(".api_dialog", "连接成功"), "model ping")
            d.screenshot(out / "api.png", ".api_dialog")
            d.click("save_api")
            d.modal_closed("api_dialog")
            phase[0] = "import"
            d.click("import_pdf")
            d.click("browse", ".import_dialog")
            d.fill("location", pdf, ".path_dialog")
            d.click("select", ".path_dialog")
            d.modal_closed("path_dialog")
            for k, v in {
                "order": "DEMO-COUPON",
                "number": "QA-SYN-018",
                "revision": "B",
                "pages": TOTAL_PAGES,
            }.items():
                d.fill(k, v, ".import_dialog")
            d.click("preview_pdf")
            d.click("preview_next")
            d.click("submit_import")
            d.modal_closed("import_dialog")
            assert api.tests == 1 and api.images == 1
            phase[0] = "page"
            time.sleep(0.3)
            search = d.find("search")
            tree = d.find("records")
            paper = d.find("original")
            with sqlite3.connect(out / "private/orders.sqlite3") as db:
                rows = [
                    (rid, json.loads(raw))
                    for rid, raw in db.execute(
                        "select rid,current from requirements order by rid"
                    )
                ]

            def choose(rid):
                if not int(d.cmd(tree, "exists", rid)):
                    d.fill("search", rid)
                d.cmd(tree, "selection", "set", rid)
                d.cmd(tree, "see", rid)
                d.cmd("update", "idletasks")
                d.wait(lambda: d.status(".", rid), "selected row " + rid)

            choose(rows[2][0])
            time.sleep(0.15)
            assert len(d.tk.tk.splitlist(d.cmd(paper, "find", "all"))) >= 3
            d.click("next_page")
            time.sleep(0.2)
            d.click("previous_page")
            time.sleep(0.18)
            d.click("zoom")
            time.sleep(0.18)
            d.click("zoom")
            time.sleep(0.2)
            phase[0] = "review"
            for rid, r in rows:
                choose(rid)
                action = (
                    "exclude"
                    if r["channel"] == "prose"
                    else "clarify"
                    if r["requirement"] == "TBA"
                    else "confirm"
                )
                if (
                    r["item"] == "Field splice clearance"
                    and r["scenario"] == "Scenario Bay-01"
                ):
                    d.click("edit")
                    dlg = ".review_dialog"
                    field = d.find("edit_field", dlg)
                    d.cmd(field, "set", "阶段")
                    d.cmd("event", "generate", field, "<<ComboboxSelected>>")
                    d.fill("new_value", "Field", dlg)
                    d.fill("user", "Demo Engineer", dlg)
                    d.fill(
                        "note", "Field designation verified on the generated page.", dlg
                    )
                    d.click("save_review", dlg)
                    d.modal_closed("review_dialog")
                d.click(action)
                dialog = ".review_dialog"
                d.fill("user", "Demo Engineer", dialog)
                if action == "clarify":
                    d.fill("question", "What is the approved ridge height?", dialog)
                    d.fill("respondent", "Design team", dialog)
                elif action == "confirm":
                    d.cmd(d.find("checked", dialog), "invoke")
                    d.fill("note", "Verified on the synthetic source page.", dialog)
                else:
                    d.fill(
                        "note", "Document navigation or archive instruction.", dialog
                    )
                d.click("save_review")
                d.modal_closed("review_dialog")
            d.cmd(search, "delete", 0, "end")
            choose(rows[2][0])
            time.sleep(0.24)
            d.screenshot(out / "review.png")
            d.click("zoom")
            time.sleep(0.18)
            d.screenshot(out / "detail.png")
            d.click("zoom")
            time.sleep(0.18)
            d.click("audit")
            d.click("done", ".review_dialog")
            d.modal_closed("review_dialog")
            time.sleep(0.1)
            phase[0] = "export"
            d.click("export_order")
            d.wait(
                lambda: int(d.cmd("winfo", "exists", ".export_dialog")), "export dialog"
            )
            d.fill("directory", out / "exports", ".export_dialog")
            d.click("save_export")
            d.modal_closed("export_dialog")
            phase[0] = "idle"
            time.sleep(0.45)
            info = verify_files(out / "exports")
            d.script("after idle [wm protocol . WM_DELETE_WINDOW]")
            app.wait(timeout=10)
        finally:
            stopped.set()
            sampler.join()
            if app.poll() is None:
                app.terminate()
                app.wait(timeout=10)
            api.shutdown()
            api.server_close()
            d.tk.destroy()
            tray.close()
            with (out / "memory.csv").open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(
                    [
                        "elapsed_s",
                        "phase",
                        "rss_bytes",
                        "kernel_peak_bytes",
                        "processes",
                    ]
                )
                w.writerows((round(t, 4), p, r, h, n) for t, p, r, h, n in samples)
    phases = {
        p: {
            "peak": max(r for _, s, r, _, _ in samples if s == p),
            "last": next(r for _, s, r, _, _ in reversed(samples) if s == p and r),
        }
        for p in dict.fromkeys(s[1] for s in samples)
    }
    result = dict(
        address_space_limit=8000000000,
        tray_docked=True,
        window_icon=True,
        pages=TOTAL_PAGES,
        rows=len(rows),
        api_pings=api.tests,
        images_sent=api.images,
        **info,
        phases=phases,
        tree_peak=max(s[2] for s in samples),
        kernel_peak=max(s[3] for s in samples),
        max_processes=max(s[4] for s in samples),
        samples=len(samples),
    )
    (out / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    assert max(result["tree_peak"], result["kernel_peak"]) <= LIMIT, (
        "Desktop exceeded 100 MB"
    )
    assert "Traceback" not in (out / "desktop.stderr").read_text(), (
        "Desktop emitted a traceback"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        type=Path,
        required=True,
        help="Product interpreter with only requirements-orders.txt",
    )
    parser.add_argument(
        "output", type=Path, help="New directory for measurements and screenshots"
    )
    args = parser.parse_args()
    run(
        args.python.resolve()
        if not args.python.is_symlink()
        else args.python.absolute(),
        args.output,
    )
