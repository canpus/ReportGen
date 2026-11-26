import argparse
import json
import sys

from .export import export_directory
from .store import Store
from .web import serve


def main(argv=None):
    for output in (sys.stdout, sys.stderr):
        if hasattr(output, "reconfigure"):
            output.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Local order specification review")
    p.add_argument("--data-dir", help="private database and PDF directory")
    p.add_argument("--config", help="optional local YAML parser configuration")
    sub = p.add_subparsers(dest="command", required=True)
    web = sub.add_parser("serve")
    web.add_argument("--port", type=int, default=0)
    web.add_argument("--open", action="store_true")
    imp = sub.add_parser("import")
    imp.add_argument("pdf")
    imp.add_argument("--order", required=True)
    imp.add_argument("--number", required=True)
    imp.add_argument("--revision", required=True)
    imp.add_argument(
        "--reference-edition",
        choices=["ISO 21809-3:2016"],
        help="engineer-selected read-only comparison when the PDF omits an edition",
    )
    sub.add_parser("list")
    show = sub.add_parser("show")
    show.add_argument("document")
    review = sub.add_parser("review")
    review.add_argument("document")
    review.add_argument("row")
    review.add_argument("action", choices=["confirm", "edit", "clarify"])
    review.add_argument("--user", required=True)
    review.add_argument("--version", type=int, required=True)
    review.add_argument("--changes", default="{}")
    review.add_argument("--checked", action="store_true")
    review.add_argument(
        "--no-requirements",
        action="store_true",
        help="attest that a page without usable OCR contains no requirements",
    )
    review.add_argument("--note", default="")
    review.add_argument("--question", default="")
    review.add_argument("--respondent", default="")
    exp = sub.add_parser("export")
    exp.add_argument("order")
    exp.add_argument("directory")
    a = p.parse_args(argv)
    store = Store(a.data_dir)
    try:
        if a.command == "serve":
            serve(store, a.port, a.open, a.config)
            return 0
        if a.command == "import":
            result = store.import_pdf(
                a.pdf,
                a.order,
                a.number,
                a.revision,
                config=a.config,
                reference_edition=a.reference_edition,
            )
        elif a.command == "list":
            result = store.list_documents()
        elif a.command == "show":
            result = store.records(a.document)
        elif a.command == "review":
            result = store.review(
                a.document,
                a.row,
                version=a.version,
                action=a.action,
                user=a.user,
                changes=json.loads(a.changes),
                checked=a.checked,
                no_requirements=a.no_requirements,
                note=a.note,
                question=a.question,
                respondent=a.respondent,
            )
        else:
            result = str(export_directory(store, a.order, a.directory))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
