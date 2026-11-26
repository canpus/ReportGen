"""Build and verify the standalone 64-bit Windows order review ZIP on Linux or Windows."""

import argparse
import compileall
import hashlib
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).with_name("orders-win64-lock.json")
LIMIT = 50_000_000


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def inputs(cache):
    cache.mkdir(parents=True, exist_ok=True)
    for entry in json.loads(LOCK.read_text()):
        dest = cache / entry["filename"]
        if not dest.is_file():
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as tmp:
                tmp_path = Path(tmp.name)
                try:
                    with urlopen(entry["url"], timeout=90) as response:
                        shutil.copyfileobj(response, tmp)
                    tmp.close()
                    if digest(tmp_path) != entry["sha256"]:
                        raise ValueError("Download digest mismatch: " + dest.name)
                    os.replace(tmp_path, dest)
                finally:
                    tmp_path.unlink(missing_ok=True)
        if digest(dest) != entry["sha256"]:
            raise ValueError("Cache digest mismatch: " + dest.name)
        yield dest


def tk_files(msi, runtime, extractor):
    with tempfile.TemporaryDirectory(dir=runtime.parent.parent) as temp:
        if os.name == "nt" and not extractor:
            subprocess.run(
                [
                    "msiexec",
                    "/a",
                    str(msi.resolve()),
                    "/qn",
                    "TARGETDIR=" + str(Path(temp).resolve()),
                ],
                check=True,
            )
        else:
            subprocess.run(
                [extractor or "msiextract", "-C", temp, str(msi.resolve())],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        source = next(Path(temp).rglob("_tkinter.pyd")).parents[1]
        shutil.copytree(source / "DLLs", runtime / "DLLs")
        skip = shutil.ignore_patterns("test", "tests", "demos", "__pycache__")
        shutil.copytree(source / "Lib/tkinter", runtime / "Lib/tkinter", ignore=skip)
        for folder in ("tcl8", "tcl8.6", "tk8.6"):
            shutil.copytree(
                source / "tcl" / folder, runtime / "tcl" / folder, ignore=skip
            )


def build(stage, cache, extractor):
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        raise RuntimeError(
            "Use CPython 3.12 to precompile the matching Windows runtime libraries."
        )
    root = stage / "ReportGen"
    runtime = root / "runtime"
    app = root / "app"
    runtime.mkdir(parents=True)
    app.mkdir()
    packages = runtime / "Lib/site-packages"
    for source in inputs(cache):
        if source.suffix == ".msi":
            tk_files(source, runtime, extractor)
        elif source.suffix == ".appx":
            with ZipFile(source) as z:
                z.extract("msvcp140.dll", runtime)
        else:
            with ZipFile(source) as z:
                z.extractall(packages if source.suffix == ".whl" else runtime)
    # Each file is explicitly public application code, a required asset, or a verified dependency.
    code = app / "src/cyct_report"
    orders = code / "orders"
    orders.mkdir(parents=True)
    for name in ("__init__.py", "paths.py"):
        shutil.copyfile(ROOT / "src/cyct_report" / name, code / name)
    src = ROOT / "src/cyct_report/orders"
    for path in [*src.glob("*.py"), src / "reference.json"]:
        shutil.copyfile(path, orders / path.name)
    for name in ("assets", "icons", "fonts"):
        shutil.copytree(src / name, orders / name)
    standards = app / "presets/standards"
    standards.mkdir(parents=True)
    shutil.copyfile(
        ROOT / "presets/standards/iso21809-3.json", standards / "iso21809-3.json"
    )
    (runtime / "python312._pth").write_bytes(
        b"python312.zip\r\n.\r\nDLLs\r\nLib\r\nLib/site-packages\r\n../app/src\r\n"
    )
    (app / "launch.pyw").write_text(
        'from pathlib import Path\nfrom cyct_report.orders.store import Store\nfrom cyct_report.orders.desktop import launch\nlaunch(Store(Path(__file__).resolve().parents[1] / "private"))\n'
    )
    bat = [
        "@echo off",
        "setlocal",
        'set "TCL_LIBRARY=%~dp0runtime\\tcl\\tcl8.6"',
        'set "TK_LIBRARY=%~dp0runtime\\tcl\\tk8.6"',
        'start "" "%~dp0runtime\\pythonw.exe" -B "%~dp0app\\launch.pyw"',
    ]
    (root / "Start-ReportGen.bat").write_bytes(
        ("\r\n".join(bat) + "\r\n").encode("ascii")
    )
    guide = (ROOT / "docs/order-review.md").read_text(encoding="utf-8")
    for report in ("order-review-validation.md", "order-desktop-validation.md"):
        guide = guide.replace(
            f"]({report})",
            f"](https://github.com/canpus/ReportGen/blob/work/docs/{report})",
        )
    (root / "使用说明.md").write_bytes(guide.encode("utf-8"))
    shutil.copyfile(
        ROOT / "docs/order-review.example.yaml", root / "order-review.example.yaml"
    )
    shutil.copyfile(LOCK, root / "sources.json")
    shutil.copyfile(ROOT / "docs/order-desktop-notices.txt", root / "NOTICE.txt")
    # Avoid first-run compilation of large binding modules on an 8 GB workstation.
    for path in (runtime / "Lib", app / "src"):
        ok = compileall.compile_dir(
            str(path),
            quiet=2,
            invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
            stripdir=str(root),
            prependdir="ReportGen",
            workers=1,
        )
        if not ok:
            raise RuntimeError("Bytecode compilation failed")
    return root


def verify(path):
    with ZipFile(path) as z:
        if z.testzip():
            raise ValueError("ZIP CRC failure")
        files = set(z.namelist())
        for name in (
            "Start-ReportGen.bat",
            "app/launch.pyw",
            "runtime/python312.zip",
            "runtime/DLLs/_tkinter.pyd",
            "runtime/tcl/tcl8.6/init.tcl",
            "runtime/tcl/tk8.6/tk.tcl",
            "runtime/Lib/tkinter/__init__.py",
            "app/src/cyct_report/orders/icons/application.ico",
            "app/src/cyct_report/orders/icons/application.png",
            "app/src/cyct_report/orders/tray.py",
            "app/presets/standards/iso21809-3.json",
        ):
            if "ReportGen/" + name not in files:
                raise ValueError("Missing " + name)
        for name in (
            "runtime/msvcp140.dll",
            "runtime/pythonw.exe",
            "runtime/_sqlite3.pyd",
            "runtime/DLLs/tk86t.dll",
        ):
            if not z.read("ReportGen/" + name).startswith(b"MZ"):
                raise ValueError("Invalid PE component")
        if any(n.lower().endswith((".pdf", ".sqlite3", "/api.json")) for n in files):
            raise ValueError("Unexpected private file type")
        if path.stat().st_size > LIMIT:
            raise ValueError("Archive exceeds 50 MB")
        return len(files), sum(i.file_size for i in z.infolist())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache", type=Path, default=ROOT / "work/desktop-build/downloads"
    )
    parser.add_argument("--msiextract", help="msitools extractor path (Linux)")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "work/delivery/ReportGen-Desktop-win64.zip",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as temp:
        root = build(Path(temp), args.cache, args.msiextract)
        target = Path(temp) / "portable.zip"
        with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=9) as z:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    info = ZipInfo(
                        path.relative_to(temp).as_posix(), (2026, 1, 1, 0, 0, 0)
                    )
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    z.writestr(
                        info,
                        path.read_bytes(),
                        compress_type=ZIP_DEFLATED,
                        compresslevel=9,
                    )
        count, expanded = verify(target)
        os.replace(target, args.output)
    print(
        f"{args.output}   {args.output.stat().st_size} bytes   {count} files   {expanded} expanded bytes   SHA-256 {digest(args.output)}"
    )


if __name__ == "__main__":
    main()
