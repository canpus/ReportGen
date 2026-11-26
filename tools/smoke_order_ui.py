"""Exercise the local workstation in Chromium using only generated fixtures."""

import argparse
import json
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from openpyxl import load_workbook
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from orders.synthetic import workflow


def exercise(url, workspace, executable):
    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=executable)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}, accept_downloads=True
        )
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(url)
        page.locator("#start").click()
        intake = page.locator("#intake")
        for key, value in {
            "order": "Synthetic UI",
            "number": "Fixture",
            "revision": "A",
        }.items():
            intake.locator(f"[name={key}]").fill(value)
        intake.locator("[type=file]").set_input_files(
            workflow(workspace / "fabricated.pdf")
        )
        page.locator("#submitImport").click()
        rows = page.locator("#rows tr")
        expect(rows).to_have_count(3)
        expect(page.locator("#original")).to_be_visible()
        assert (
            page.locator("#original").evaluate(
                "img => img.decode().then(() => img.naturalWidth)"
            )
            == 2100
        )
        assert page.locator("#boxes i").count() >= 3
        page.locator("#export").click()
        expect(page.locator("#message")).to_contain_text("R00001")
        page.locator("#reviewer").fill("Synthetic UI reviewer")
        page.locator("#fieldsPanel summary").click()
        page.locator('[data-field="item"]').fill("Width after cooling")
        page.locator("#note").fill("Compared the original label and cooled state.")
        page.locator("#edit").click()
        expect(rows.first).to_contain_text("Width after cooling")
        page.locator("#checked").check()
        page.locator("#note").fill("Verified the sign and its row.")
        page.locator("#confirm").click()
        expect(rows.first).to_contain_text("已确认")
        page.locator("#auditPanel summary").click()
        expect(page.locator("#audit")).to_contain_text("Synthetic UI reviewer")
        rows.nth(1).click()
        page.locator("#confirm").click()
        expect(rows.nth(1)).to_contain_text("已确认")
        rows.nth(2).click()
        page.locator("#tq").click()
        page.locator("#question").fill("Which assembly pressure should be used?")
        page.locator("#respondent").fill("Fixture author")
        page.locator("#tqForm button.primary").click()
        expect(rows.nth(2)).to_contain_text("待澄清")
        page.locator("#status").select_option("clarify")
        expect(rows).to_have_count(1)
        page.locator("#frequencies").click()
        expect(rows).to_have_count(0)
        page.locator("#requirements").click()
        expect(rows).to_have_count(1)
        page.screenshot(path=str(workspace / "synthetic-workstation.png"))
        with page.expect_download() as download:
            page.locator("#export").click()
        dest = workspace / "ui-export.zip"
        download.value.save_as(dest)
        assert not errors, errors
        browser.close()
    with ZipFile(dest) as z:
        assert set(z.namelist()) == {
            "confirmed.json",
            "confirmed.xlsx",
            "laboratory.xlsx",
        }
        snap = json.loads(z.read("confirmed.json"))
        assert (
            len(snap["audit"]) == 4
            and len(snap["requirements"]) == 2
            and len(snap["clarifications"]) == 1
        )
        assert (
            load_workbook(BytesIO(z.read("confirmed.xlsx")))["Confirmed"].max_row == 3
        )
        lab = load_workbook(BytesIO(z.read("laboratory.xlsx")))
        for ws in lab:
            ix = [cell.value for cell in ws[1]].index("Actual Test Result") + 1
            assert (
                ws.max_row == 2 and ws.cell(2, ix).value is None and ws.protection.sheet
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-path", help="use an installed Chromium binary")
    parser.add_argument(
        "--server-python",
        default=sys.executable,
        help="Python with requirements-orders.txt installed",
    )
    parser.add_argument(
        "--work-dir", type=Path, help="parent for optional synthetic artifacts"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if args.work_dir:
            args.work_dir.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix="ui-", dir=args.work_dir))
        server = subprocess.Popen(
            [
                args.server_python,
                str(ROOT / "tools" / "order_review.py"),
                "--data-dir",
                str(root / "store"),
                "serve",
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            url = server.stdout.readline().strip()
            if not url.startswith("http://127.0.0.1:"):
                raise RuntimeError("The local review server did not start.")
            exercise(url, root, args.browser_path)
            print(
                "PASS: browser import, on-page evidence, edit, confirm, TQ, filter, export, blank result cells"
            )
        finally:
            server.terminate()
            server.wait(timeout=15)


if __name__ == "__main__":
    main()
