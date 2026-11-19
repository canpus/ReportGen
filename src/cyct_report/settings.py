"""用户设置：data/settings.json。"""
import json
from pathlib import Path

from . import paths

DEFAULTS = {
    "reports_dir": "",          # 空 = data/reports
    "pdf_engine": "auto",       # auto | word | wps
    "make_pdf": True,
    "last_lang": "zh",
    "last_standard": "iso21809-3",
    "last_template": "14B-2",
    "inspector": "",
    "auditor": "",
}


class Settings(dict):
    def __init__(self, file: Path = None):
        super().__init__(DEFAULTS)
        self.file = file or paths.data_dir() / "settings.json"
        if self.file.exists():
            try:
                self.update(json.loads(self.file.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                pass          # 设置文件损坏时按默认值运行

    def save(self):
        self.file.write_text(json.dumps(self, ensure_ascii=False, indent=1), encoding="utf-8")

    def reports_dir(self) -> Path:
        d = Path(self["reports_dir"]) if self["reports_dir"] else paths.data_dir() / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d
