"""报告文件命名与存放：<报告目录>/<客户>/<年份>/<月.日客户 产品 标准>.docx"""
import re
from datetime import date
from pathlib import Path

_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]+')
MAX_STEM = 110


def safe_name(text: str) -> str:
    text = _ILLEGAL.sub("-", text or "").strip(" .")
    return re.sub(r"\s{2,}", " ", text) or "未命名"


def report_dir(root: Path, customer: str, d: date) -> Path:
    return Path(root) / safe_name(customer)[:60] / str(d.year)


def report_stem(customer: str, products: list, std_display: str, d: date) -> str:
    first = products[0].name if products else ""
    more = f" 等{len(products)}项" if len(products) > 1 else ""
    stem = f"{d.month}.{d.day}{customer} {first}{more} {std_display}"
    return safe_name(stem)[:MAX_STEM].strip()


def unique_path(folder: Path, stem: str, suffix: str = ".docx") -> Path:
    """同名文件已存在时追加 (2)、(3)…；同时检查同名 PDF。"""
    folder.mkdir(parents=True, exist_ok=True)
    n, candidate = 1, stem
    while (folder / (candidate + suffix)).exists() or (folder / (candidate + ".pdf")).exists():
        n += 1
        candidate = f"{stem} ({n})"
    return folder / (candidate + suffix)
