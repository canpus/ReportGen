import hashlib
from io import BytesIO
from PIL import Image, ImageFilter
import re

import pymupdf as fitz

from .model import Fragment, Page


def preview(page, dpi=180):
    if not 160 <= dpi <= 200:
        raise ValueError("Preview DPI must be between 160 and 200")
    return page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")


def unit_box(page, box):
    r = fitz.Rect(box) * page.rotation_matrix
    w, h = page.rect.width, page.rect.height
    return [round(max(0.0, min(1.0, v / size)), 6) for v, size in zip(r, (w, h, w, h))]


def union(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def _native(page):
    textpage = page.get_textpage(flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    blocks = page.get_text("dict", textpage=textpage)["blocks"]
    glyph_blocks = None
    parts = []
    for bi, block in enumerate(blocks):
        for li, line in enumerate(block.get("lines", [])):
            spans = [s for s in line["spans"] if s["text"]]
            if not spans:
                continue
            base = max(spans, key=lambda s: (s["size"], len(s["text"])))
            for si, s in enumerate(line["spans"]):
                raw = s["text"]
                if not raw.strip():
                    continue
                box = unit_box(page, s["bbox"])
                offset = base["origin"][1] - s["origin"][1]
                small = s["size"] < base["size"] * 0.9
                raised = bool(s["flags"] & 1) or small and offset > base["size"] * 0.12
                lowered = small and offset < -base["size"] * 0.12
                note = (
                    raw.strip()
                    if raised and re.fullmatch(r"[a-z]", raw.strip())
                    else ""
                )
                notation = ("^" if raised else "_" if lowered else "") + raw
                # Long runs of real whitespace frequently encode separate table cells.
                matches = list(re.finditer(r"\S(?:.*?\S)?(?=\s{3,}|\s*$)", raw))
                if len(matches) > 1:
                    if glyph_blocks is None:
                        glyph_blocks = page.get_text("rawdict", textpage=textpage)[
                            "blocks"
                        ]
                    chars = glyph_blocks[bi]["lines"][li]["spans"][si]["chars"]
                    for m in matches:
                        boxes = [
                            unit_box(page, c["bbox"])
                            for c in chars[m.start() : m.end()]
                        ]
                        parts.append(
                            (
                                m.group(),
                                m.group(),
                                union(boxes) if boxes else box,
                                [],
                                s["size"],
                            )
                        )
                else:
                    parts.append(
                        (raw, notation, box, [note] if note else [], s["size"])
                    )
    return parts


def _rows(parts, w, h):
    # First align baselines, including small separately positioned note markers.
    parts.sort(key=lambda t: ((t[2][1] + t[2][3]) / 2, t[2][0]))
    bands = []
    for part in parts:
        box = part[2]
        center = (box[1] + box[3]) / 2
        height = max(1 / h, box[3] - box[1])
        assigned = None
        for band in reversed(bands[-3:]):
            if abs(center - band[0]) <= max(height, band[1]) * 0.43:
                assigned = band
                break
        if assigned is None:
            bands.append([center, height, [part]])
        else:
            assigned[2].append(part)
            if height > assigned[1]:
                assigned[0:2] = [center, height]
    result = []
    for row, (_, _, band) in enumerate(bands, 1):
        group = []
        for part in sorted(band, key=lambda t: t[2][0]):
            if group:
                prev = group[-1]
                gap = (part[2][0] - prev[2][2]) * w
                if gap > max(3.5, min(prev[4], part[4]) * 0.55) or gap < -max(
                    prev[4], part[4]
                ):
                    result.append((row, group))
                    group = []
            group.append(part)
        if group:
            result.append((row, group))
    return result


def fragments(parts, page_no, w, h, origin):
    out = []
    for row, group in _rows(parts, w, h):
        raw = ""
        notation = ""
        marks = []
        normal = max(group, key=lambda v: v[4])
        for i, (text, math_text, box, m, size) in enumerate(group):
            if i:
                gap = (box[0] - group[i - 1][2][2]) * w
                if (
                    gap > size * 0.15
                    and not raw.endswith(" ")
                    and not text.startswith(" ")
                ):
                    raw += " "
                    notation += " "
                # Some generators place superscripts in separate PDF text objects.
                raise_by = (normal[2][3] - box[3]) * h
                if (
                    re.fullmatch(r"[a-z]|[−+-]?\d{1,3}", text.strip())
                    and size < normal[4] * 0.89
                    and raise_by > normal[4] * 0.12
                    and not math_text.startswith("^")
                ):
                    math_text = "^" + text
                    if re.fullmatch(r"[a-z]", text.strip()):
                        m = [text.strip()]
                elif (
                    re.fullmatch(r"[a-z]|[−+-]?\d{1,3}", text.strip())
                    and size < normal[4] * 0.89
                    and raise_by < -normal[4] * 0.12
                    and not math_text.startswith("_")
                ):
                    math_text = "_" + text
            raw += text
            notation += math_text
            marks.extend(m)
        for char in re.findall(r"[ᵃᵇᶜᵈ]", raw):
            marks.append(char.translate(str.maketrans("ᵃᵇᶜᵈ", "abcd")))
        out.append(
            Fragment(
                f"{page_no}.{len(out) + 1}",
                page_no,
                union([a[2] for a in group]),
                raw,
                notation,
                list(dict.fromkeys(marks)),
                row,
                origin,
                [dict(text=v[0], notation=v[1], box=v[2]) for v in group],
            )
        )
    return out


def _rules(page):
    segments = set()
    for draw in page.get_drawings():
        for item in draw["items"]:
            if item[0] == "l":
                pairs = [(item[1], item[2])]
            elif item[0] == "re":
                r = item[1]
                pairs = [(r.tl, r.tr), (r.bl, r.br), (r.tl, r.bl), (r.tr, r.br)]
            else:
                continue
            for a, b in pairs:
                box = unit_box(
                    page, (min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))
                )
                if (
                    box[2] - box[0] > 0.09
                    and box[3] - box[1] < 0.002
                    or box[3] - box[1] > 0.012
                    and box[2] - box[0] < 0.002
                ):
                    segments.add(tuple(box))
    return sorted(segments)


def scan_rules(png):
    # A ruled scan retains its horizontal cell boundaries even with imperfect OCR.
    with Image.open(BytesIO(png)) as original:
        gray = original.convert("L")
    gray.thumbnail((1450, 1800))
    ink = gray.point(lambda v: 255 if v < 178 else 0).filter(ImageFilter.MaxFilter(3))
    segments = []
    for vertical, img in (
        (False, ink),
        (True, ink.transpose(Image.Transpose.TRANSPOSE)),
    ):
        w, h = img.size
        density = img.resize((1, h), Image.Resampling.BOX).tobytes()
        bitmap = img.tobytes()
        last = {}
        for y, density_at_y in enumerate(density):
            if density_at_y < (42 if vertical else 75):
                continue
            stripe = bitmap[y * w : (y + 1) * w]
            for run in re.finditer(rb"\xff+", stripe):
                x1, x2 = run.span()
                if (x2 - x1) / w < (0.16 if vertical else 0.37):
                    continue
                key = (round(x1 / w * 40), round(x2 / w * 40))
                if key in last and y - last[key][0] <= 3:
                    last[key] = (y, last[key][1])
                    continue
                last[key] = (y, len(segments))
                x, end, pos = x1 / w, x2 / w, y / h
                segments.append((pos, x, pos, end) if vertical else (x, pos, end, pos))
    return segments


def joined_rules(rules):
    # Vector PDFs often represent a horizontal rule as separate cell-wide segments.
    horizontal = sorted(
        (b for b in rules if b[3] - b[1] < 0.002), key=lambda b: (round(b[1], 3), b[0])
    )
    merged = []
    for b in horizontal:
        if (
            merged
            and abs(merged[-1][1] - b[1]) < 0.0015
            and merged[-1][2] + 0.003 >= b[0]
        ):
            merged[-1][2] = max(merged[-1][2], b[2])
        else:
            merged.append(list(b))
    return merged + [b for b in rules if b[3] - b[1] >= 0.002]


def inspect_pdf(path, ocr=None, vision=None):
    pages = []
    suggestions = {}
    content = hashlib.sha256()
    with fitz.open(path) as doc:
        if not doc.is_pdf or doc.needs_pass or not len(doc):
            raise ValueError("An unlocked, non-empty PDF is required")
        for n, p in enumerate(doc, 1):
            w, h = p.rect.width, p.rect.height
            if not w or not h:
                raise ValueError("Invalid PDF page size")
            pix = p.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
            content.update(f"{pix.width}x{pix.height}|".encode())
            content.update(pix.digest)
            parts = _native(p)
            content.update(hashlib.sha256(p.get_text().encode()).digest())
            carrier = "native" if parts else "scan"
            image = None
            issue = ""
            # A scanned body can coexist with a small selectable running header.
            if parts and sum(len(t[0].strip()) for t in parts) < 100:
                if any(
                    fitz.Rect(i["bbox"]).get_area() > 0.55 * w * h
                    for i in p.get_image_info()
                ):
                    carrier = "mixed"
            if carrier != "native":
                image = preview(p)
                recognized = ocr.recognize(image, n, w, h) if ocr else []
                if recognized:
                    parts = recognized
                else:
                    issue = (
                        "OCR produced no page transcription; inspect the physical page."
                    )
            source = "ocr" if carrier != "native" and not issue else "native"
            fs = fragments(parts, n, w, h, source)
            page = Page(
                n,
                w,
                h,
                carrier,
                fs,
                joined_rules(_rules(p) if carrier == "native" else scan_rules(image)),
                issue,
            )
            if vision:
                suggestions[n] = vision.extract(image or preview(p), page)
            pages.append(page)
    return pages, content.hexdigest(), suggestions
