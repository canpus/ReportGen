"""Loopback-only review workstation. PDF data and document metadata are not logged."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit
import json
import secrets
import threading
import webbrowser

import pymupdf as fitz

from .export import bundle
from .pdf import preview
from .store import Conflict, ReviewRequired

ASSETS = Path(__file__).with_name("assets")


def server(store, port=0, config=None):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_bytes(self, status, data, mime, attachment=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            if attachment:
                self.send_header(
                    "Content-Disposition", 'attachment; filename="' + attachment + '"'
                )
            self.end_headers()
            self.wfile.write(data)

        def json_reply(self, data, status=200):
            self.send_bytes(
                status,
                json.dumps(data, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
            )

        def dispatch(self, post=False):
            host = self.headers.get("Host", "")
            if host not in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }:
                self.json_reply({"error": "Invalid local host"}, 403)
                return
            split = urlsplit(self.path)
            path = split.path
            args = {k: v[0] for k, v in parse_qs(split.query).items()}
            if post:
                if (
                    self.headers.get("X-Order-Session") != token
                    or self.headers.get("Origin", "http://" + host) != "http://" + host
                ):
                    self.json_reply({"error": "Refresh this local session"}, 403)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    raise ValueError("Empty request")
                if path == "/api/import":
                    with NamedTemporaryFile(
                        dir=store.root, suffix=".pdf", delete=False
                    ) as f:
                        temp = Path(f.name)
                    try:
                        with temp.open("wb") as f:
                            remaining = length
                            while remaining:
                                chunk = self.rfile.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    raise ValueError("Incomplete PDF")
                                f.write(chunk)
                                remaining -= len(chunk)
                        return self.json_reply(
                            store.import_pdf(
                                temp,
                                args.get("order", ""),
                                args.get("number", ""),
                                args.get("revision", ""),
                                config=config,
                                reference_edition=args.get("edition"),
                            )
                        )
                    finally:
                        temp.unlink(missing_ok=True)
                if length > 2_000_000:
                    raise ValueError("Review request too large")
                data = json.loads(self.rfile.read(length))
                if path == "/api/review":
                    return self.json_reply(store.review(**data))
                if path == "/api/manual":
                    return self.json_reply({"id": store.add_manual(**data)})
                if path == "/api/export":
                    snap = store.snapshot(data["order"])
                    return self.send_bytes(
                        200,
                        bundle(snap),
                        "application/zip",
                        f"order-review-r{snap['confirmed_rev']}.zip",
                    )
            else:
                if path in {"/", "/style.css", "/app.js"}:
                    name = {
                        "/": "index.html",
                        "/style.css": "style.css",
                        "/app.js": "app.js",
                    }[path]
                    content = (ASSETS / name).read_bytes()
                    if path == "/":
                        content = content.replace(b"__LOCAL_SESSION__", token.encode())
                    return self.send_bytes(
                        200,
                        content,
                        {
                            "/": "text/html",
                            "/style.css": "text/css",
                            "/app.js": "application/javascript",
                        }[path]
                        + "; charset=utf-8",
                    )
                if path == "/api/documents":
                    return self.json_reply(store.list_documents())
                if path == "/api/document":
                    doc = store.document(args["id"])
                    with store.connection() as db:
                        n = db.execute(
                            "SELECT count(*) FROM pages WHERE doc=?", (doc["id"],)
                        ).fetchone()[0]
                    return self.json_reply(
                        dict(document=doc, pages=n, rows=store.records(doc["id"]))
                    )
                if path == "/api/page":
                    return self.json_reply(store.page(args["id"], int(args["page"])))
                if path == "/api/image":
                    n = int(args["page"])
                    with fitz.open(store.original_pdf(args["id"])) as pdf:
                        if not 1 <= n <= len(pdf):
                            raise KeyError("Unknown page")
                        return self.send_bytes(200, preview(pdf[n - 1]), "image/png")
                if path == "/api/audit":
                    return self.json_reply(store.audit(args["id"], args["rid"]))
            self.json_reply({"error": "Unknown route"}, 404)

        def handle_api(self, post=False):
            try:
                self.dispatch(post)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (ReviewRequired, Conflict) as e:
                self.json_reply({"error": str(e)}, 409)
            except KeyError as e:
                self.json_reply({"error": str(e)}, 404)
            except (ValueError, TypeError, RuntimeError) as e:
                self.json_reply({"error": str(e)}, 400)
            except Exception:
                self.json_reply(
                    {
                        "error": "Operation failed. Check the local storage and configuration."
                    },
                    500,
                )

        def do_POST(self):
            self.handle_api(True)

        def do_GET(self):
            self.handle_api()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(store, port, open_browser=False, config=None):
    with server(store, port, config) as http:
        url = f"http://127.0.0.1:{http.server_port}/"
        print(url, flush=True)
        if open_browser:
            threading.Timer(0.15, webbrowser.open, args=(url,)).start()
        http.serve_forever()
