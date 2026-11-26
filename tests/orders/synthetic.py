"""Entirely generated orders, with fictional activities and deliberately contradictory fields."""

from pathlib import Path
import pymupdf as fitz

FONT = fitz.Font("helv")
WIDTH, HEIGHT = 840, 620


def write(page, x, y, value, size=10):
    page.insert_font(fontname="FixtureFont", fontbuffer=FONT.buffer)
    page.insert_text((x, y), value, fontsize=size, fontname="FixtureFont")


def line(page, y, xs, values):
    for x, value in zip(xs, values):
        if value:
            write(page, x, y, value)


def page_in(doc):
    return doc.new_page(width=WIDTH, height=HEIGHT)


def store_file(doc, path):
    doc.save(path, garbage=4, deflate=True)
    doc.close()
    return Path(path)


def immersion(path):
    doc = fitz.open()
    page = page_in(doc)
    write(page, 40, 42, "Synthetic sleeve study / ISO 21809-3:2016 / Type 14B-2")
    write(page, 40, 87, "Table 2 Coupon evaluations")
    xs = [40, 218, 450, 575, 685]
    line(page, 120, xs, ["Property", "Test condition", "Requirement", "Unit", "Method"])
    line(
        page,
        148,
        xs,
        [
            "Peel after immersion",
            "28 days in water at 80°C; test at 23°C",
            "≥0.75",
            "N/mm",
            "Annex H",
        ],
    )
    line(
        page, 179, xs, ["Heat aged elongation", "23°C", "≥0.75", "E100/E70", "Annex M"]
    )
    return store_file(doc, path)


ESCALATION = (
    "If ≥10% of the trial strips fail, destructively retest the immediately preceding joint. "
    "If that joint also fails, stop work until written approval to restart."
)
SUPPLIER = "All coupon layers shall come from one manufacturer."


def matrix(path):
    doc = fitz.open()
    for scenario in ("A", "B"):
        page = page_in(doc)
        write(page, 40, 32, "Scenario " + scenario)
        if scenario == "A":
            write(
                page,
                40,
                57,
                "2.1 Surface roughness shall be inspected using ASTM D4417.",
            )
            write(page, 40, 79, ESCALATION.split(". ")[0] + ".")
            write(page, 40, 94, ESCALATION.split(". ")[1])
        write(page, 40, 124, "Test Programme")
        xs = [40, 245, 438, 568, 686]
        line(
            page, 145, xs, ["Activity", "Inspection Method", "PQT", "PPT", "Production"]
        )
        for i in range(1, 23):
            activity = "Surface roughness" if i == 3 else f"Coupon feature {i:02d}"
            method = (
                "ISO 8501-1"
                if scenario == "A" and i == 3
                else ("EN 12068" if scenario == "B" and i > 12 else "ISO 21809-3")
            )
            line(
                page,
                147 + i * 18,
                xs,
                [
                    activity,
                    method,
                    "4 coupons",
                    "By Agreement" if i % 2 else "-",
                    "Each lot",
                ],
            )
        if scenario == "B":
            write(page, 40, 585, SUPPLIER)
    return store_file(doc, path)


class ImagePageStub:
    """Known OCR transcription of the synthetic scan only; input must be a rendered PNG."""

    def __init__(self, words):
        self.words = words
        self.calls = []

    def recognize(self, png, number, width, height):
        assert png.startswith(b"\x89PNG")
        self.calls.append(number)
        return self.words[number]


def across_pages(path):
    doc = fitz.open()
    page = page_in(doc)
    write(page, 38, 555, "Table 7 Synthetic laminate checks")
    page = page_in(doc)
    xs = [38, 244, 431, 551, 677]
    line(page, 40, xs, ["Property", "Condition", "Requirement", "Typical", "Unit"])
    line(page, 70, xs, ["Coupon seal", "Dry", "≥12", "9", "MPa"])
    line(page, 103, xs, ["Elastic index", "Dry", "", "32", "mm"])
    line(page, 136, xs, ["Test load", "Indentation", "10 N/mm²", "", ""])
    line(page, 169, xs, ["Residual thickness", "After load release", "≥0.6", "", "mm"])
    line(page, 202, xs, ["Batch label", "Dry", "TBA", "", ""])
    line(page, 235, xs, ["Band width", "Dry", "By Vendor", "", "mm"])
    line(page, 268, xs, ["Adhesion pad one", "17°C", "≥11", "", "MPa"])
    write(page, xs[2] + FONT.text_length("≥11", fontsize=10) + 0.5, 264.5, "a", 7)
    line(page, 301, xs, ["Adhesion pad two", "17°C", "≥13", "", "MPa"])
    line(page, 334, xs, ["Insulator", "", "10", "", "Ohm"])
    write(page, xs[2] + FONT.text_length("10", fontsize=10), 330, "13", 7)
    line(page, 511, xs, ["Joint offset", "After conditioning", "", "", ""])
    # The next page has no hidden text layer. The deterministic adapter uses authored geometry.
    scan = fitz.open()
    layer = page_in(scan)
    line(layer, 48, xs, ["", "", "≥4.2", "", "mm"])
    write(layer, 38, 88, "(a) Only the first pad is conditioned in the amber bath.")
    write(
        layer, 38, 145, "3.1 The gauge voltage shall follow 2.2 √t on the trial strip."
    )
    from cyct_report.orders.pdf import _native

    words = {3: _native(layer)}
    pic = layer.get_pixmap(dpi=180).tobytes("png")
    page = page_in(doc)
    page.insert_image(page.rect, stream=pic)
    scan.close()
    return store_file(doc, path), ImagePageStub(words)


def workflow(path):
    doc = fitz.open()
    page = page_in(doc)
    write(page, 40, 50, "Table 4 Independent demonstration")
    xs = [40, 240, 420, 600]
    line(page, 92, xs, ["Item", "Condition", "Requirement", "Unit"])
    line(page, 128, xs, ["Sample width", "After cooling", "≥8", "mm"])
    line(page, 164, xs, ["Field seam check", "Each shift", "No visible gap", ""])
    line(page, 200, xs, ["Band pressure", "During assembly", "TBA", ""])
    return store_file(doc, path)


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    parser = argparse.ArgumentParser(
        description="Write four independently generated QA PDFs."
    )
    parser.add_argument("directory", type=Path)
    dest = parser.parse_args().directory
    dest.mkdir(parents=True, exist_ok=True)
    generators = (workflow, immersion, matrix, across_pages)
    if any((dest / (g.__name__ + ".pdf")).exists() for g in generators):
        parser.error("A generated file already exists in this directory.")
    for generate in generators:
        target = dest / (generate.__name__ + ".pdf")
        generate(target)
        print(target)
