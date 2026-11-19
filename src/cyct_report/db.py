"""SQLite 数据：客户名、常用名称（品名/检验员/审核人）、报告记录。"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from . import paths
from .search import matches

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    name TEXT PRIMARY KEY COLLATE NOCASE,
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS names (
    kind TEXT NOT NULL, value TEXT NOT NULL,
    use_count INTEGER NOT NULL DEFAULT 0, last_used TEXT,
    PRIMARY KEY (kind, value));
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT NOT NULL,
    products TEXT, quantities TEXT, batches TEXT,
    standard TEXT, standard_id TEXT, template_id TEXT, lang TEXT,
    created_at TEXT NOT NULL, report_date TEXT,
    source TEXT NOT NULL DEFAULT 'generated',
    docx_path TEXT, pdf_path TEXT, data_json TEXT);
CREATE INDEX IF NOT EXISTS ix_reports_customer ON reports(customer COLLATE NOCASE);
"""

REPORT_FIELDS = ("customer", "products", "quantities", "batches", "standard", "standard_id",
                 "template_id", "lang", "created_at", "report_date", "source",
                 "docx_path", "pdf_path", "data_json")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def to_stored_path(p) -> str:
    """程序目录内的文件存相对路径，整个程序文件夹搬家后仍能找到。"""
    if not p:
        return ""
    p = Path(p).resolve()
    try:
        return str(p.relative_to(paths.APP_DIR))
    except ValueError:
        return str(p)


def from_stored_path(s: str):
    if not s:
        return None
    p = Path(s)
    return p if p.is_absolute() else paths.APP_DIR / p


class Database:
    def __init__(self, file: Path = None):
        self.file = file or paths.data_dir() / "cyct.db"
        self.conn = sqlite3.connect(str(self.file), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- 客户 ----------
    def touch_customer(self, name: str):
        name = (name or "").strip()
        if not name:
            return
        now = _now()
        self.conn.execute(
            "INSERT INTO customers(name, use_count, last_used, created) VALUES (?, 1, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET use_count = use_count + 1, last_used = ?",
            (name, now, now, now))
        self.conn.commit()

    def customers(self) -> list:
        rows = self.conn.execute(
            "SELECT name FROM customers ORDER BY use_count DESC, last_used DESC").fetchall()
        return [r["name"] for r in rows]

    def delete_customer(self, name: str):
        self.conn.execute("DELETE FROM customers WHERE name = ?", (name,))
        self.conn.commit()

    # ---------- 常用名称 ----------
    def touch_name(self, kind: str, value: str):
        value = (value or "").strip()
        if not value:
            return
        self.conn.execute(
            "INSERT INTO names(kind, value, use_count, last_used) VALUES (?, ?, 1, ?) "
            "ON CONFLICT(kind, value) DO UPDATE SET use_count = use_count + 1, last_used = ?",
            (kind, value, _now(), _now()))
        self.conn.commit()

    def names(self, kind: str) -> list:
        rows = self.conn.execute(
            "SELECT value FROM names WHERE kind = ? ORDER BY use_count DESC, last_used DESC",
            (kind,)).fetchall()
        return [r["value"] for r in rows]

    # ---------- 报告 ----------
    def add_report(self, **rec) -> int:
        rec.setdefault("created_at", _now())
        for key in ("docx_path", "pdf_path"):
            rec[key] = to_stored_path(rec.get(key))
        if isinstance(rec.get("data_json"), dict):
            rec["data_json"] = json.dumps(rec["data_json"], ensure_ascii=False)
        cols = [k for k in REPORT_FIELDS if k in rec]
        cur = self.conn.execute(
            f"INSERT INTO reports({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [rec[k] for k in cols])
        self.conn.commit()
        return cur.lastrowid

    def query_reports(self, customer_query: str = "", keyword: str = "", source: str = "",
                      date_from: str = "", date_to: str = "") -> list:
        sql, args = "SELECT * FROM reports WHERE 1=1", []
        if source:
            sql += " AND source = ?"
            args.append(source)
        if date_from:
            sql += " AND substr(created_at, 1, 10) >= ?"
            args.append(date_from)
        if date_to:
            sql += " AND substr(created_at, 1, 10) <= ?"
            args.append(date_to)
        rows = [dict(r) for r in self.conn.execute(sql + " ORDER BY created_at DESC", args)]
        if customer_query:
            rows = [r for r in rows if matches(customer_query, r["customer"])]
        if keyword:
            rows = [r for r in rows if matches(keyword, " ".join(
                str(r[k] or "") for k in ("products", "batches", "standard", "quantities")))]
        return rows

    def get_report(self, rid: int):
        r = self.conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
        return dict(r) if r else None

    def delete_report(self, rid: int):
        self.conn.execute("DELETE FROM reports WHERE id = ?", (rid,))
        self.conn.commit()

    def has_report_file(self, stored_path: str) -> bool:
        r = self.conn.execute("SELECT 1 FROM reports WHERE docx_path = ?", (stored_path,)).fetchone()
        return r is not None
