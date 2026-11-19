"""打包发布：python tools/build.py

产物：dist/CYCT检测报告/（CYCTReport.exe + presets/ + templates/ + assets/）及同名 zip。
标准库和报告模板放在 exe 旁边，方便以后直接修改。
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP = DIST / "CYCT检测报告"
EXCLUDES = ["pymupdf", "fitz", "PIL", "pytest", "numpy", "unittest", "pydoc_data",
            "test", "distutils", "setuptools", "pip", "xmlrpc", "multiprocessing"]


def main():
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(APP, ignore_errors=True)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
           "--onedir", "--name", "CYCTReport", "--paths", str(ROOT / "src"),
           "--distpath", str(DIST / "_pyi"), "--workpath", str(ROOT / "build"),
           "--specpath", str(ROOT / "build"), "--hidden-import", "comtypes.client",
           "--collect-data", "sv_ttk", "--icon", str(ROOT / "assets" / "app.ico")]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    subprocess.run(cmd + [str(ROOT / "tools" / "launcher.py")], check=True)
    shutil.move(str(DIST / "_pyi" / "CYCTReport"), str(APP))
    shutil.rmtree(DIST / "_pyi", ignore_errors=True)
    for folder in ("presets", "templates", "assets"):
        shutil.copytree(ROOT / folder, APP / folder)
    shutil.copy2(ROOT / "使用说明.txt", APP / "使用说明.txt")
    archive = shutil.make_archive(str(APP), "zip", DIST, APP.name)
    size = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file())
    print(f"文件夹 {size / 1e6:.1f} MB，压缩包 {Path(archive).stat().st_size / 1e6:.1f} MB：{archive}")


if __name__ == "__main__":
    main()
