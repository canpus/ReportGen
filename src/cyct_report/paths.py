"""程序目录与数据目录。

presets/ 与 templates/ 作为普通文件夹放在程序旁边（打包后也一样），
方便质检人员直接用 Word 修改页眉、或替换标准库文件，而不必重新打包。
"""
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_DIR = app_dir()
PRESETS_DIR = APP_DIR / "presets"
STANDARDS_DIR = PRESETS_DIR / "standards"
TERMS_FILE = PRESETS_DIR / "terms.json"
TEMPLATES_DIR = APP_DIR / "templates"
ASSETS_DIR = APP_DIR / "assets"


def data_dir() -> Path:
    d = APP_DIR / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def template_file(lang: str) -> Path:
    return TEMPLATES_DIR / f"report_{lang}.docx"
