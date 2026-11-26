"""Generated engineering specification for the public desktop acceptance run."""

from .synthetic import line, page_in, store_file, write
import pymupdf as fitz

TOTAL_PAGES = 18
SCAN_ITEM = "Witness film curvature"
SCAN_QUOTE = "Witness film curvature | After release | ≥4.7 | mm"
SCAN_ROW = dict(
    kind="requirement",
    item=SCAN_ITEM,
    condition="After release",
    requirement="≥4.7",
    unit="mm",
    quote=SCAN_QUOTE,
    box=[0.045, 0.252, 0.92, 0.288],
)
NOISE = "The archive clerk shall print >1 copy of this index."
ROWS = [
    "Gauge pad width",
    "Coupon ridge height",
    "Witness radius",
    "Field splice clearance",
    "Marker separation",
    "Insert depth",
    "Edge allowance",
    "Trace length",
]


def desktop_order(path):
    pdf = fitz.open()
    for n in range(1, TOTAL_PAGES + 1):
        page = page_in(pdf)
        if n == 1:
            write(page, 50, 110, "COVER SHEET", 25)
            write(page, 50, 160, "Coupon assembly qualification", 17)
            write(page, 50, 205, "Independently generated demonstration specification.")
        elif n == 2:
            write(page, 50, 90, "Table of contents", 20)
            write(page, 50, 152, "Coupon inspection schedule .......... 4")
            write(page, 50, 180, "Witness film examination .......... 18")
        elif n == 3:
            write(page, 50, 80, "2.1 Archive handling", 16)
            write(page, 50, 130, NOISE)
        elif n == TOTAL_PAGES:
            with fitz.open() as layer:
                scan = page_in(layer)
                write(scan, 42, 65, "Film coupon / optical examination", 20)
                write(scan, 42, 115, "Test schedule", 14)
                write(scan, 42, 175, SCAN_QUOTE, 14)
                pic = scan.get_pixmap(dpi=140, colorspace=fitz.csGRAY).tobytes("png")
                page.insert_image(page.rect, stream=pic)
        else:
            x = [42, 277, 438, 584, 654]
            write(page, 42, 60, f"Scenario Bay-{n - 3:02}", 18)
            write(page, 42, 105, f"Table {n} Coupon inspection schedule", 15)
            line(
                page,
                145,
                x,
                ["Property", "Test condition", "Requirement", "Unit", "Method"],
            )
            for i, activity in enumerate(ROWS):
                criterion = (
                    "TBA"
                    if n == 4 and i == 1
                    else "≥8.4"
                    if n == 4 and i == 0
                    else f"{3 + (n + i) % 11}.5"
                )
                line(
                    page,
                    182 + i * 39,
                    x,
                    [activity, "Dry at 23°C", criterion, "mm", "Bench gauge"],
                )
            write(page, 42, 575, f"Inspection schedule   /   sheet {n - 3:02}", 9)
    return store_file(pdf, path)
