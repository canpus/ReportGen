"""Private order database. Source PDFs are content-addressed; reviews are append-audited."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import re
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid

from .adapters import adapters
from .extract import extract_pages
from .model import EDITABLE, ROLES, normalized, pending_role, quantity
from .validation import validate


class Conflict(ValueError):
    pass


class ReviewRequired(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def default_root():
    home = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_DATA_HOME")
        or str(Path.home() / ".local" / "share")
    )
    return Path(home) / "ReportGen" / "orders"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), doc_no TEXT NOT NULL,
 doc_rev TEXT NOT NULL, sha256 TEXT NOT NULL, signature TEXT NOT NULL, alias_of TEXT,
 active INTEGER NOT NULL, created TEXT NOT NULL, UNIQUE(order_id,doc_no,doc_rev,sha256));
CREATE INDEX IF NOT EXISTS docs_content ON documents(order_id,signature);
CREATE TABLE IF NOT EXISTS pages (
 doc TEXT NOT NULL REFERENCES documents(id), n INTEGER NOT NULL, detail TEXT NOT NULL, PRIMARY KEY(doc,n));
CREATE TABLE IF NOT EXISTS requirements (
 doc TEXT NOT NULL REFERENCES documents(id), rid TEXT NOT NULL, original TEXT NOT NULL,
 current TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate', version INTEGER NOT NULL DEFAULT 0,
 checked INTEGER NOT NULL DEFAULT 0, question TEXT NOT NULL DEFAULT '', respondent TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(doc,rid));
CREATE TABLE IF NOT EXISTS audit (
 seq INTEGER PRIMARY KEY, doc TEXT NOT NULL, rid TEXT NOT NULL, user TEXT NOT NULL,
 stamp TEXT NOT NULL, version INTEGER NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (
 order_id TEXT NOT NULL, revision INTEGER NOT NULL, generation INTEGER NOT NULL, detail TEXT NOT NULL,
 PRIMARY KEY(order_id,revision), UNIQUE(order_id,generation));
"""


class Store:
    def __init__(self, root=None):
        self.root = Path(root or default_root()).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.files = self.root / "files"
        self.files.mkdir(exist_ok=True, mode=0o700)
        self.database = self.root / "orders.sqlite3"
        with self.connection() as db:
            db.executescript(_SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            if "reference_edition" not in {
                c[1] for c in db.execute("PRAGMA table_info(documents)")
            }:
                db.execute(
                    "ALTER TABLE documents ADD COLUMN reference_edition TEXT NOT NULL DEFAULT ''"
                )

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.database, timeout=40)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def list_documents(self):
        with self.connection() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM documents ORDER BY rowid DESC")
            ]

    def import_pdf(
        self,
        path,
        order_id,
        doc_no,
        doc_rev,
        *,
        config=None,
        providers=None,
        reference_edition=None,
        vision_pages=None,
    ):
        order_id, doc_no, doc_rev = (
            str(x or "").strip() for x in (order_id, doc_no, doc_rev)
        )
        if not all((order_id, doc_no, doc_rev)):
            raise ValueError("Order, document number and revision are required.")
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(
            dir=self.files, suffix=".pdf", delete=False
        ) as tmp:
            temp = Path(tmp.name)
            try:
                with open(path, "rb") as src:
                    for chunk in iter(lambda: src.read(1024 * 1024), b""):
                        digest.update(chunk)
                        tmp.write(chunk)
            except BaseException:
                tmp.close()
                temp.unlink(missing_ok=True)
                raise
        sha = digest.hexdigest()
        key = (order_id, doc_no, doc_rev, sha)
        lookup = "SELECT * FROM documents WHERE order_id=? AND doc_no=? AND doc_rev=? AND sha256=?"

        def duplicate(row):
            if reference_edition and row["reference_edition"] != reference_edition:
                raise Conflict(
                    "This file/revision was already imported with a different comparison edition."
                )
            return dict(row)

        try:
            with self.connection() as db:
                prior = db.execute(lookup, key).fetchone()
                if prior:
                    return duplicate(prior)
            from .pdf import inspect_pdf

            ocr, vision = providers if providers is not None else adapters(config)
            pages, signature, suggestions = inspect_pdf(
                temp, ocr, vision, vision_pages=vision_pages
            )
            rows = validate(extract_pages(pages, suggestions), pages, reference_edition)
            doc = uuid.uuid4().hex
            with self.connection(write=True) as db:
                prior = db.execute(lookup, key).fetchone()
                if prior:
                    return duplicate(prior)
                db.execute("INSERT OR IGNORE INTO orders(id) VALUES(?)", (order_id,))
                same = db.execute(
                    "SELECT id FROM documents WHERE order_id=? AND signature=? ORDER BY rowid LIMIT 1",
                    (order_id, signature),
                ).fetchone()
                db.execute(
                    "UPDATE documents SET active=0 WHERE order_id=? AND doc_no=?",
                    (order_id, doc_no),
                )
                db.execute(
                    "INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        doc,
                        *key,
                        signature,
                        same[0] if same else None,
                        1,
                        now(),
                        reference_edition or "",
                    ),
                )
                db.executemany(
                    "INSERT INTO pages VALUES(?,?,?)",
                    ((doc, p.number, dump(asdict(p))) for p in pages),
                )
                db.executemany(
                    "INSERT INTO requirements(doc,rid,original,current) VALUES(?,?,?,?)",
                    ((doc, r.id, dump(asdict(r)), dump(asdict(r))) for r in rows),
                )
                target = self.files / (sha + ".pdf")
                if not target.exists():
                    os.replace(temp, target)
                db.execute(
                    "UPDATE orders SET generation=generation+1 WHERE id=?", (order_id,)
                )
                return dict(db.execute(lookup, key).fetchone())
        finally:
            temp.unlink(missing_ok=True)

    def document(self, doc):
        with self.connection() as db:
            r = db.execute("SELECT * FROM documents WHERE id=?", (doc,)).fetchone()
            if not r:
                raise KeyError("Unknown document")
            return dict(r)

    def original_pdf(self, doc):
        return self.files / (self.document(doc)["sha256"] + ".pdf")

    @staticmethod
    def _review_doc(db, doc):
        # Share decisions only within an order and a revision with identical visible content.
        row = db.execute(
            """SELECT peer.id FROM documents source JOIN documents peer
            ON peer.order_id=source.order_id AND peer.doc_rev=source.doc_rev AND peer.signature=source.signature AND peer.reference_edition=source.reference_edition
            WHERE source.id=? ORDER BY peer.rowid LIMIT 1""",
            (doc,),
        ).fetchone()
        if not row:
            raise KeyError("Unknown document")
        return row[0]

    def audit(self, doc, rid):
        with self.connection() as db:
            rows = db.execute(
                "SELECT user,stamp,action,detail FROM audit WHERE doc=? AND rid=? ORDER BY seq",
                (self._review_doc(db, doc), rid),
            )
            return [
                dict(user=r[0], stamp=r[1], action=r[2], detail=json.loads(r[3]))
                for r in rows
            ]

    def page(self, doc, n):
        with self.connection() as db:
            doc = self._review_doc(db, doc)
            row = db.execute(
                "SELECT detail FROM pages WHERE doc=? AND n=?", (doc, n)
            ).fetchone()
            if not row:
                raise KeyError("Unknown page")
            return json.loads(row[0])

    @staticmethod
    def _records(db, doc):
        result = []
        for row in db.execute(
            "SELECT * FROM requirements WHERE doc=? ORDER BY rid", (doc,)
        ):
            data = json.loads(row["current"])
            data.update(
                doc=doc,
                status=row["status"],
                version=row["version"],
                checked=bool(row["checked"]),
                question=row["question"],
                respondent=row["respondent"],
            )
            result.append(data)
        return result

    def records(self, doc):
        with self.connection() as db:
            return self._records(db, self._review_doc(db, doc))

    def row_index(self, doc):
        with self.connection() as db:
            canonical = self._review_doc(db, doc)
            return [
                dict(r)
                for r in db.execute(
                    """SELECT rid,status,json_extract(current,'$.channel') AS channel,
                substr(json_extract(current,'$.item'),1,160) AS item,json_extract(current,'$.source_pages[0]') AS page,
                json_extract(current,'$.scenario') AS scenario,json_extract(current,'$.component') AS component,
                json_extract(current,'$.stage') AS stage FROM requirements WHERE doc=? ORDER BY rid""",
                    (canonical,),
                )
            ]

    def record(self, doc, rid):
        with self.connection() as db:
            canonical = self._review_doc(db, doc)
            row = db.execute(
                "SELECT current,status,version,checked,question,respondent FROM requirements WHERE doc=? AND rid=?",
                (canonical, rid),
            ).fetchone()
            if not row:
                raise KeyError("Unknown requirement")
            return dict(
                json.loads(row["current"]),
                **{k: row[k] for k in row.keys() if k != "current"},
            )

    def page_count(self, doc):
        with self.connection() as db:
            return db.execute(
                "SELECT count(*) FROM pages WHERE doc=?", (self._review_doc(db, doc),)
            ).fetchone()[0]

    def review(
        self,
        doc,
        rid,
        *,
        version,
        action,
        user,
        changes=None,
        checked=False,
        no_requirements=False,
        note="",
        question="",
        respondent="",
    ):
        if not isinstance(checked, bool) or not isinstance(no_requirements, bool):
            raise ValueError("Review decisions must be boolean values.")
        changes = changes or {}
        if not user.strip() or action not in {"confirm", "edit", "clarify", "exclude"}:
            raise ValueError("Choose an action and enter the reviewer's name.")
        if (
            not isinstance(changes, dict)
            or set(changes) - set(EDITABLE)
            or any(not isinstance(v, str) for v in changes.values())
        ):
            raise ValueError("Unknown or invalid review field")
        if action == "exclude" and (not note.strip() or changes):
            raise ValueError(
                "Exclusion needs a reason and the original candidate fields."
            )
        if action == "clarify" and not (question.strip() and respondent.strip()):
            raise ValueError(
                "A clarification needs a question and a responsible party."
            )
        with self.connection(write=True) as db:
            doc = self._review_doc(db, doc)
            rec = db.execute(
                "SELECT * FROM requirements WHERE doc=? AND rid=?", (doc, rid)
            ).fetchone()
            if not rec:
                raise KeyError("Unknown requirement")
            if version != rec["version"]:
                raise Conflict("This row changed. Reload before saving.")
            current = json.loads(rec["current"])
            raw = json.loads(rec["original"])
            changed = {k: v for k, v in changes.items() if v != current[k]}
            if changed and not note.strip():
                raise ValueError("Record the reason for the correction.")
            initial = {k: current[k] for k in changed}
            current.update(changed)
            if current["value_role"] not in ROLES or current["destination"] not in {
                "field",
                "laboratory",
            }:
                raise ValueError("Invalid value role or destination")
            if (
                raw["value_role"]
                in {"by_vendor", "tba", "by_agreement", "dash_not_listed"}
                and current["requirement"] != raw["requirement"]
            ):
                raise ValueError(
                    "Keep the supplied placeholder. Register a TQ and an approved document revision."
                )
            if raw["channel"] == "frequency":
                for stage in ("pqt", "ppt", "production"):
                    if pending_role(raw[stage]) and raw[stage] != current[stage]:
                        raise ValueError(
                            "Keep the original stage placeholder and request clarification."
                        )
                current["phase_roles"] = {
                    k: pending_role(current[k])
                    or ("frequency" if current[k] else "unreported")
                    for k in ("pqt", "ppt", "production")
                }
            if (
                current["value_role"] in {"typical_only", "test_condition"}
                and current["requirement"]
            ):
                raise ValueError("This role has no acceptance limit.")
            if raw["value_role"] == "typical_only" and current["requirement"]:
                raise ValueError("A typical-only source has no acceptance limit.")
            if "requirement" in changed or "unit" in changed:
                current["quantity_kind"] = quantity(
                    current["unit"] + " " + current["requirement"]
                )
            if "method" in changed:
                current["field_sources"]["method"] = "client_explicit"
            if changed and not any(
                a["code"] == "manual_correction" for a in current["alerts"]
            ):
                current["alerts"].append(
                    dict(
                        code="manual_correction",
                        level="CHECK",
                        message="Verify the edited fields against their source.",
                    )
                )
            evidence_fields = changed.keys() & {
                "condition",
                "requirement",
                "unit",
                "typical",
                "method",
                "pqt",
                "ppt",
                "production",
            }
            if evidence_fields:
                evidence_ids = {
                    i for k in evidence_fields for i in current["bindings"].get(k, [])
                }
                pages = {int(i.split(".")[0]) for i in evidence_ids}
                fragments = {}
                for n in pages:
                    p = db.execute(
                        "SELECT detail FROM pages WHERE doc=? AND n=?", (doc, n)
                    ).fetchone()
                    fragments.update(
                        {
                            f["id"]: f
                            for f in json.loads(p[0])["fragments"]
                            if f["id"] in evidence_ids
                        }
                    )
                for key in sorted(evidence_fields):
                    bound = [
                        fragments[i]
                        for i in current["bindings"].get(key, [])
                        if i in fragments
                    ]
                    matches = any(
                        normalized(current[key])
                        in normalized(" ".join(f.get(view, "") for f in bound))
                        for view in ("text", "notation")
                    )
                    code = "edited_evidence_" + key
                    current["alerts"] = [
                        a for a in current["alerts"] if a["code"] != code
                    ]
                    if current[key] and not matches:
                        current["alerts"].append(
                            dict(
                                code=code,
                                level="RED",
                                message="Edited "
                                + key
                                + " is outside its original source tokens. Verify the image and record the correction basis.",
                            )
                        )
            risky = any(a["level"] in {"RED", "CHECK"} for a in current["alerts"])
            if (
                action == "exclude"
                and current["channel"] == "coverage"
                and not (checked and no_requirements)
            ):
                raise ReviewRequired(
                    "Inspect the whole page and attest that it has no requirements."
                )
            if (
                current["channel"] == "coverage"
                and action == "confirm"
                and not no_requirements
                and not any(
                    r["channel"] == "manual"
                    and r["status"] == "confirmed"
                    and r["source_pages"] == current["source_pages"]
                    for r in self._records(db, doc)
                )
            ):
                raise ReviewRequired(
                    "Page has no extraction. Add its requirements or keep it in clarification."
                )
            if action == "confirm" and risky and not (checked and note.strip()):
                raise ReviewRequired(
                    "Explicit visual verification and a review note are required."
                )
            status = {
                "confirm": "confirmed",
                "edit": "candidate",
                "clarify": "clarify",
                "exclude": "excluded",
            }[action]
            verified = bool(checked and note.strip() and action == "confirm")
            v = version + 1
            detail = dict(
                before=initial,
                after=changed,
                previous_status=rec["status"],
                status=status,
                note=note,
                verified=verified,
                no_requirements=bool(
                    no_requirements and current["channel"] == "coverage"
                ),
                question=question,
                respondent=respondent,
                previous_question=rec["question"],
                previous_respondent=rec["respondent"],
            )
            db.execute(
                "UPDATE requirements SET current=?,status=?,version=?,checked=?,question=?,respondent=? WHERE doc=? AND rid=?",
                (
                    dump(current),
                    status,
                    v,
                    int(verified),
                    question if action == "clarify" else "",
                    respondent if action == "clarify" else "",
                    doc,
                    rid,
                ),
            )
            db.execute(
                "INSERT INTO audit(doc,rid,user,stamp,version,action,detail) VALUES(?,?,?,?,?,?,?)",
                (doc, rid, user.strip(), now(), v, action, dump(detail)),
            )
            db.execute(
                "UPDATE orders SET generation=generation+1 WHERE id=(SELECT order_id FROM documents WHERE id=?)",
                (doc,),
            )
            return dict(status=status, version=v)

    def add_manual(self, doc, *, page, box, text, user):
        if (
            not user.strip()
            or not text.strip()
            or len(box) != 4
            or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)
        ):
            raise ValueError(
                "A manual transcription needs a reviewer, exact text and a page region."
            )
        from .model import Fragment, Requirement

        with self.connection(write=True) as db:
            doc = self._review_doc(db, doc)
            source = db.execute(
                "SELECT detail FROM pages WHERE doc=? AND n=?", (doc, page)
            ).fetchone()
            if not source:
                raise KeyError("Unknown page")
            pg = json.loads(source[0])
            rid = "M" + uuid.uuid4().hex[:12]
            fid = f"{page}.{rid}"
            f = Fragment(fid, page, box, text, text, [], 0, "manual")
            r = Requirement(
                rid, "manual", item=text, requirement=text, verbatim=text, notation=text
            )
            placeholder = re.search(
                r"\b(?:TBA|TBD|By Vendor|By Agreement)\b", text, re.I
            )
            if placeholder or pending_role(text):
                r.requirement = placeholder[0] if placeholder else text
                r.value_role = pending_role(r.requirement)
            elif re.search(r"\btypical\b", text, re.I):
                r.typical = text
                r.requirement = ""
                r.value_role = "typical_only"
            for k in ("item", "requirement", "typical"):
                if getattr(r, k):
                    r.bind(k, [f])
                    r.field_sources[k] = "client_explicit"
            r.flag(
                "manual_source", "CHECK", "Verify the transcription and source area."
            )
            pg["fragments"].append(asdict(f))
            db.execute(
                "UPDATE pages SET detail=? WHERE doc=? AND n=?", (dump(pg), doc, page)
            )
            data = dump(asdict(r))
            db.execute(
                "INSERT INTO requirements(doc,rid,original,current) VALUES(?,?,?,?)",
                (doc, rid, data, data),
            )
            db.execute(
                "INSERT INTO audit(doc,rid,user,stamp,version,action,detail) VALUES(?,?,?,?,0,'add',?)",
                (doc, rid, user, now(), dump(dict(text=text, page=page, box=box))),
            )
            db.execute(
                "UPDATE orders SET generation=generation+1 WHERE id=(SELECT order_id FROM documents WHERE id=?)",
                (doc,),
            )
            return rid

    def snapshot(self, order):
        with self.connection(write=True) as db:
            state = db.execute(
                "SELECT generation FROM orders WHERE id=?", (order,)
            ).fetchone()
            if not state:
                raise KeyError("Unknown order")
            prior = db.execute(
                "SELECT detail FROM snapshots WHERE order_id=? AND generation=?",
                (order, state[0]),
            ).fetchone()
            if prior:
                return json.loads(prior[0])
            rev = db.execute(
                "SELECT COALESCE(MAX(revision),0)+1 FROM snapshots WHERE order_id=?",
                (order,),
            ).fetchone()[0]
            docs = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM documents WHERE order_id=? ORDER BY rowid", (order,)
                )
            ]
            excluded = []
            confirmed = []
            tqs = []
            audit = []
            seen = set()
            pending = 0
            for d in docs:
                if not d["active"]:
                    continue
                canonical = self._review_doc(db, d["id"])
                if canonical in seen:
                    continue
                seen.add(canonical)
                fragments = {}
                for p in db.execute(
                    "SELECT detail FROM pages WHERE doc=?", (canonical,)
                ):
                    for f in json.loads(p[0])["fragments"]:
                        fragments[f["id"]] = f
                for r in self._records(db, canonical):
                    if r["status"] == "excluded":
                        excluded.append(
                            dict(
                                doc=d["id"],
                                doc_no=d["doc_no"],
                                id=r["id"],
                                source_pages=r["source_pages"],
                            )
                        )
                        continue
                    risky = any(a["level"] in {"RED", "CHECK"} for a in r["alerts"])
                    if risky and r["status"] != "clarify" and not r["checked"]:
                        raise ReviewRequired(
                            f"{r['id']}: check the original and record a decision, or open a TQ."
                        )
                    if r["status"] == "candidate":
                        pending += 1
                        continue
                    r["regions"] = [
                        fragments[i]
                        for i in dict.fromkeys(
                            r["evidence"]
                            + [
                                f
                                for link in r["links"]
                                for f in link.get("evidence", [])
                            ]
                        )
                    ]
                    r["review_doc"] = canonical
                    r["doc"] = d["id"]
                    r.update(
                        order_id=order,
                        doc_no=d["doc_no"],
                        doc_rev=d["doc_rev"],
                        file_sha256=d["sha256"],
                        confirmed_rev=rev,
                    )
                    (tqs if r["status"] == "clarify" else confirmed).append(r)
                for event in db.execute(
                    "SELECT * FROM audit WHERE doc=? ORDER BY seq", (canonical,)
                ):
                    item = dict(event)
                    item["detail"] = json.loads(item["detail"])
                    audit.append(item)
            if not confirmed and not tqs and not excluded:
                raise ReviewRequired("Review at least one row before exporting.")
            snap = dict(
                order_id=order,
                confirmed_rev=rev,
                generation=state[0],
                created=now(),
                documents=docs,
                requirements=[
                    r
                    for r in confirmed
                    if r["channel"] not in {"frequency", "coverage"}
                ],
                reviewed_pages=[r for r in confirmed if r["channel"] == "coverage"],
                frequencies=[r for r in confirmed if r["channel"] == "frequency"],
                clarifications=tqs,
                omitted_pending=pending,
                excluded=excluded,
                audit=sorted(audit, key=lambda a: a["seq"]),
            )
            db.execute(
                "INSERT INTO snapshots VALUES(?,?,?,?)",
                (order, rev, state[0], dump(snap)),
            )
            return snap
