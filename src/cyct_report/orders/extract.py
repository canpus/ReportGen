"""Four evidence channels over the same per-page reading order and coordinates."""

import re
from collections import Counter, defaultdict
from itertools import groupby
from statistics import median

from .model import (
    Requirement,
    field_text,
    normalized,
    pending_role,
    quantity,
    read_text,
)

NUM = r"[+-]?\d+(?:[.,]\d+)?"
TEMP = re.compile(r"(?:[−–-]?\d+(?:[.,]\d+)?\s*(?:°\s*C|℃)|T\s*max)", re.I)
TIME = re.compile(
    r"\b\d+\s*(?:days?|weeks?|months?|hours?|minutes?|years?|[dh])\b", re.I
)
METHOD = re.compile(
    r"\b(?:(?:DIN\s+)?EN|ISO|ASTM|NACE|IEC|SSPC|GOST|DIN)\s*[-:]?\s*(?:[A-Z]{1,3}\s*)?\d[\d.\-]*(?::\d{4})?(?:[, ]+Annex\s+[A-Z](?:\.\d+)?)?|\bAnnex\s+[A-Z](?:\.\d+)?",
    re.I,
)
NORM = re.compile(
    r"\b(shall|must|should|required|at least|not exceed|maximum|minimum|permitted|unless|each|every|by agreement|by vendor|TBA|reject|retest|warranty|shelf life|no holiday|pass|stop work)\b|[≥≤√<>±]",
    re.I,
)
TOPIC = re.compile(
    r"coating|temp(?:erature)?|wft|dft|thick|overlap|width|diameter|strength|adhesi|peel|pressure|load|surface|roughness|holiday|voltage|repair|batch|sample|stor(?:e|age)|warranty|curing|primer|sleeve|material|service life|manufacturer|reinspect|testing|inspection|failure|strip",
    re.I,
)
CAPTION = re.compile(r"^\s*(Table|Tab\.)\s+([A-Z]?\d+(?:[.\-]\d+)*|[A-Z]\.\d+)\b", re.I)
SECTION = re.compile(
    r"^\s*(?:(?:Clause|Section|§)\s*)?(\d+(?:\.\d+){1,5}|\d+\.(?=\s))\s*[.:)]?\s+(.*)",
    re.I,
)
REF = re.compile(
    r"\b(Table|Clause|Section)\s+([A-Z]?\d+(?:[.\-]\d+)*|[A-Z]\.\d+)\b", re.I
)
TYPE = re.compile(r"\b(?:type\s*)?(14[A-D](?:\s*-\s*[123])?|18[A-D])\b", re.I)
EDITION = re.compile(
    r"ISO\s*21809\s*[-–]\s*3\s*(?:[:(,]|[-–]\s*(?=20))\s*(\d{4})", re.I
)

UNITS = re.compile(
    r"(?<![A-Za-z])(?:N\s*/\s*(?:mm|cm|m)(?:²|\^?2)?|J(?:\s*/\s*mm)?|MPa|kV(?:\s*/\s*mm)?|µm|μm|mm|mV|Ohm|%)(?![a-z])"
)
BOUND = re.compile(
    r"(?:[≥≤]|[<>]=?)\s*[−+-]?\d+(?:[.,]\d+)?(?:\s*(?:N/(?:mm|cm)(?:²)?|MPa|kV/mm|kV|mm|µm|%|°C))?",
    re.I,
)
FAILURE = re.compile(
    r"\b(?:fail(?:s|ed|ure)?|reject(?:ion|ed)?|re-?test|re-?inspect|stop work|written (?:approval|permission)|double the sample)\b",
    re.I,
)
SAMPLE = re.compile(
    r"(?:[≥≤<>]\s*)?\d+(?:[.,]\d+)?\s*(?:%\s*(?:of\s+(?:the\s+)?)?(?:[\w-]+\s+){0,2}(?:strips?|joints?|coupons?|samples?)|(?:joints?|coupons?|samples?|pieces|specimens?))\b",
    re.I,
)
FREQUENCY = re.compile(
    r"\b(?:each|every|once (?:per|a)|twice (?:per|a)|\d+ times (?:per|a))\s+(?:\d+\s+)?(?:shifts?|joints?|lots?|batches|batch|days?|hours?|weeks?|months?)\b",
    re.I,
)

HEADS = {
    "num": r"(?:no|s/?n|sl no|sr no|#|number)\.?$",
    "item": r"(?:test(?: item| activity)?|test description|description|(?:pipe |outside )?diameter|pipe size|inspection activit(?:y|ies)|project|activities|activity|property|properties|parameter|performance parameter|characteristic|item|checks?|examination|tests? to be performed)(?:s| name)?$",
    "condition": r"(?:test )?(?:condition|temperature|temp|tem|conditioning|parameters of test)(?:s|\.)?$",
    "method": r"(?:(?:test|testing|inspection|reference) )?(?:methods?|standards?|procedures?|references?)(?: of test)?$",
    "unit": r"units?\.?$",
    "requirement": r"(?:dimensions?(?:\s*\(mm\)?)?|value|performance indicators?|requirements?|required(?: result| value)?s?|acceptance(?: criteria| limit)?|specified(?: value)?|results?|limits?|criterion|criteria|minimum value)s?$",
    "typical": r"(?:typical|ty[pml][i1l]cal)(?: value| result)?s?$",
    "pqt": r"(?:pqt|qualification(?: tests?)?)$",
    "ppt": r"(?:ppt|pre[- ]production(?: test)?)$",
    "production": r"(?:production(?: tests?| frequency)?|routine(?: tests?)?)$",
}


def header_key(t):
    t = normalized(t).replace("\n", " ").strip(" :().")
    return next((k for k, v in HEADS.items() if re.fullmatch(v, t, re.I)), None)


def heading(row):
    return [(header_key(f.text), f) for f in row if header_key(f.text)]


def is_header(pairs):
    keys = {k for k, _ in pairs}
    return len(keys) >= 2 and (
        "item" in keys or {"pqt", "ppt"} <= keys or "requirement" in keys
    )


SCENARIO = re.compile(
    r"\bScenario\s+[A-Za-z0-9][\w-]*|\bHDD\b|horizontal(?:ly)? directional|directional drill|open[- ](?:cut|trench)",
    re.I,
)


def contexts(text, context):
    match = re.search(r"\bScenario\s+([A-Za-z0-9][\w-]*)", text, re.I)
    scenario = match.group(0) if match else ""
    if re.search(
        r"\bHDD\b|horizontal(?:ly)? directional|directional drill", text, re.I
    ):
        scenario = "HDD"
    elif re.search(r"open[- ](?:cut|trench)", text, re.I):
        scenario = "Open Cut"
    if scenario and normalized(context["scenario"]) != normalized(scenario):
        context.update(scenario=scenario, coating_type="", component="", stage="")
    if m := TYPE.search(text):
        context["coating_type"] = re.sub(r"\s", "", m[1]).upper()
    if m := EDITION.search(text):
        context["standard"] = "ISO 21809-3:" + m[1]
    if m := re.search(r"\bComponent\s*[:=]\s*([\w -]+)", text, re.I):
        context["component"] = m[1].strip()
    elif len(text) < 100:
        if re.search(r"\bprimer\b", text, re.I):
            context["component"] = "primer"
        elif re.search(r"\b(backing|adhesive|sleeve|system|repair tape)\b", text, re.I):
            context["component"] = re.search(
                r"\b(backing|adhesive|sleeve|system|repair tape)\b", text, re.I
            )[1].lower()
    if m := re.search(
        r"\b(field inspection|field testing|storage|production tests?|qualification|laboratory)\b",
        text,
        re.I,
    ):
        context["stage"] = m[1]


def semantic(r):
    blob = " ".join((r.item, r.condition, r.requirement))
    r.test_temp = " / ".join(dict.fromkeys(TEMP.findall(blob)))
    r.conditioning = " / ".join(dict.fromkeys(TIME.findall(blob)))
    iface = re.findall(
        r"(?:pipe|steel|plant|factory|coating|substrate|layer)[ -]+(?:surface|coating|interface)|between layers",
        blob,
        re.I,
    )
    r.interface = " / ".join(dict.fromkeys(iface))
    r.quantity_kind = (
        quantity(r.unit)
        if r.unit and quantity(r.unit) != "qualitative"
        else quantity(r.requirement)
    )
    if r.channel == "frequency":
        r.quantity_kind = "frequency"
        r.stage = "PQT / PPT / Production"
        r.phase_roles = {
            k: pending_role(getattr(r, k))
            or ("frequency" if getattr(r, k) else "unreported")
            for k in ("pqt", "ppt", "production")
        }
    r.destination = (
        "field"
        if r.channel == "frequency"
        or re.search(
            r"field|site|shift|receipt|repair|storage|production|installation|batch",
            r.stage + " " + blob,
            re.I,
        )
        else "laboratory"
    )
    special = pending_role(r.requirement)
    if special:
        r.value_role = special
    elif not r.requirement and r.typical:
        r.value_role = "typical_only"
    elif r.requirement and r.typical:
        r.value_role = "typical_reference"
    elif re.search(
        r"\b(?:applied (?:load|pressure)|test (?:load|pressure)|pressure applied|conditioning pressure|indentation.*pressure)\b",
        r.item,
        re.I,
    ) or (normalized(r.item) in {"pressure", "load"}):
        r.value_role = "test_condition"
        if r.requirement:
            r.condition = "\n".join(filter(None, (r.condition, r.requirement)))
            r.bindings.setdefault("condition", []).extend(
                r.bindings.pop("requirement", [])
            )
            r.requirement = ""
    if r.channel == "footnote":
        r.value_role = "conditional_exception"


def schema(pairs, page, row):
    cols = {}
    for k, f in pairs:
        cols[k] = (f.box[0] + f.box[2]) / 2
    # A material or coating type often names the acceptance column instead of "Value".
    if (
        "item" in cols
        and "requirement" not in cols
        and not {"pqt", "ppt"} & cols.keys()
    ):
        unknown = [
            f
            for f in row
            if not header_key(f.text)
            and f.box[0] > cols["item"]
            and (
                re.search(
                    r"poly\w+|type\b|epoxy|coating|adhesive|indicator", f.text, re.I
                )
                or "unit" in cols
                and "method" not in cols
                and f.box[0] > cols["unit"] + 0.035
            )
        ]
        if unknown:
            cols["requirement"] = (
                min(f.box[0] for f in unknown) + max(f.box[2] for f in unknown)
            ) / 2
    ordered = sorted(cols, key=cols.get)
    # An unlabelled activity column can precede a stage-only frequency header.
    if "item" not in cols and cols[ordered[0]] > 0.22:
        cols["item"] = max(0.08, cols[ordered[0]] * 0.42)
        ordered = sorted(cols, key=cols.get)
    y = median(f.box[3] for _, f in pairs)
    vertical = [
        b[0]
        for b in page.rules
        if b[2] - b[0] < 0.002 and b[1] - 0.012 <= y <= b[3] + 0.012
    ]
    edges = []
    for a, b in zip(ordered, ordered[1:]):
        mid = (cols[a] + cols[b]) / 2
        separators = [x for x in vertical if cols[a] + 0.003 < x < cols[b] - 0.003]
        edges.append(min(separators, key=lambda x: abs(x - mid)) if separators else mid)
    return ordered, edges


def cells(row, layout):
    keys, edges = layout
    out = defaultdict(list)
    for f in row:
        # Use overlap for long wrapped cell text; a left-aligned value can extend past a midpoint.
        bounds = [0] + edges + [1]
        overlaps = [
            max(0, min(f.box[2], b) - max(f.box[0], a))
            for a, b in zip(bounds, bounds[1:])
        ]
        out[keys[overlaps.index(max(overlaps))]].append(f)
    return out


def _make(rows, channel, columns, context, caption=None):
    r = Requirement(f"R{len(rows) + 1:05}", channel, **context)
    body = sorted(
        (f for parts in columns.values() for f in parts),
        key=lambda f: (f.page, f.row, f.box[0]),
    )
    r.verbatim = read_text(body)
    r.notation = "\n".join(f.notation for f in body)
    for key, fs in columns.items():
        if hasattr(r, key) and key not in {"id", "channel"}:
            setattr(
                r,
                key,
                "\n".join(field_text(f) for f in fs)
                if key in {"requirement", "unit", "typical", "condition"}
                else read_text(fs),
            )
        r.bind(key, fs)
    if not r.unit and channel == "performance":
        for name in ("requirement", "item"):
            if match := UNITS.search(getattr(r, name)):
                r.unit = match[0]
                r.bind("unit", [f for f in columns.get(name, []) if match[0] in f.text])
                break
    if caption:
        r.bind(
            "caption",
            caption,
            primary=len(r.source_pages) == 1
            and r.source_pages[0] - caption[0].page in (0, 1),
        )
    r.field_sources = {k: "client_explicit" for k in columns}
    if not r.item:
        r.item = body[0].text if body else ""
        r.flag("missing_item", "RED", "The row label needs verification on the page.")
    semantic(r)
    if r.unit:
        r.field_sources["unit"] = "client_explicit"
    rows.append(r)
    return r


def table_requirements(rows, channel, columns, context, caption):
    labels = columns.get("item", [])
    values = columns.get("requirement", [])
    loads = [
        f
        for f in values
        if re.search(r"\d\s*(?:N/mm(?:²|\^?2)|MPa)", field_text(f), re.I)
    ]
    residuals = [
        f for f in values if re.search(r"[≥><≤]\s*[\d.]+\s*mm\b", field_text(f), re.I)
    ]
    if (
        channel == "performance"
        and len(loads) == len(residuals) == 1
        and re.search(r"residual", read_text(labels), re.I)
        and re.search(r"pressure|load", read_text(labels), re.I)
    ):
        common = {
            k: fs
            for k, fs in columns.items()
            if k not in {"item", "requirement", "unit", "typical"}
        }
        load_labels = [f for f in labels if re.search(r"pressure|load", f.text, re.I)]
        residual_labels = [
            f for f in labels if re.search(r"residual|thickness", f.text, re.I)
        ]
        _make(
            rows,
            channel,
            dict(common, item=load_labels, requirement=loads),
            dict(context),
            caption,
        )
        _make(
            rows,
            channel,
            dict(common, item=residual_labels, requirement=residuals),
            dict(context),
            caption,
        )
    else:
        r = _make(rows, channel, columns, dict(context), caption)
        if (
            channel == "performance"
            and len(loads) + len(residuals) > 1
            and re.search(r"pressure|load", read_text(labels), re.I)
        ):
            r.flag(
                "mixed_conditions",
                "RED",
                "Separate the applied load from the residual-thickness limit on the source row.",
            )


def _paragraph(rows, frags, context, kind="prose"):
    text = read_text(frags)
    if not text.strip() or not (
        NORM.search(text)
        or TOPIC.search(text)
        and re.search(r"\d|only|same", text, re.I)
        or kind == "footnote"
    ):
        return None
    r = _make(rows, kind, {"item": frags}, context)
    r.requirement = text
    r.bind("requirement", frags)
    if kind == "prose":
        for name, pattern in (("sampling_basis", SAMPLE), ("frequency", FREQUENCY)):
            if m := pattern.search(text):
                setattr(r, name, m[0])
                r.bind(name, frags)
                r.field_sources[name] = "client_explicit"
        if FAILURE.search(text):
            r.failure_action = text
            r.bind("failure_action", frags)
            r.field_sources["failure_action"] = "client_explicit"
        elif len(list(BOUND.finditer(text))) == 1 and not re.search(
            r"√|unless|formula|ratio|typical|TBA|By Vendor", text, re.I
        ):
            criterion = BOUND.search(text)
            # Keep compound conditions and formulae intact. Narrow only a simple stated bound.
            if re.search(
                r"shall|must|minimum|maximum", text[: criterion.start()], re.I
            ):
                r.requirement = criterion[0].rstrip()
                if unit := UNITS.search(r.requirement):
                    r.unit = unit[0]
                    r.bind("unit", frags)
        if m := TEMP.search(text):
            r.condition = m[0]
            r.bind("condition", frags)
    if m := METHOD.search(text):
        r.method = m[0]
        r.bind("method", [f for f in frags if METHOD.search(f.text)])
    if m := re.search(r"\b(?:TBA|By Vendor|By Agreement)\b", text, re.I):
        r.requirement = m[0]
    elif re.search(r"\btypical(?: value)?\b", text, re.I) and not re.search(
        r"\b(?:shall|minimum|required|limit)\b", text, re.I
    ):
        r.typical = text
        r.requirement = ""
        r.bind("typical", frags)
        r.bindings.pop("requirement", None)
    elif re.search(r"\b(if|unless|provided that)\b", text, re.I):
        r.condition = text
        r.bind("condition", frags)
    semantic(r)
    for k in ("condition", "requirement", "typical", "method", "unit"):
        if getattr(r, k):
            r.field_sources[k] = "client_explicit"
    return r


def note_label(text):
    m = re.match(r"^\s*(?:\(([a-z])\)|([a-z])[.)]|([a-z])(?=\s)|([ᵃᵇᶜᵈ]))\s*(.+)", text)
    if m:
        return next(v for v in m.groups()[:4] if v).translate(
            str.maketrans("ᵃᵇᶜᵈ", "abcd")
        )
    return ""


def grid_band(row, rules):
    center = median((f.box[1] + f.box[3]) / 2 for f in row)
    lines = sorted(
        {round(b[1], 3) for b in rules if b[2] - b[0] > 0.40 and b[3] - b[1] < 0.002}
    )
    above = [y for y in lines if y <= center]
    below = [y for y in lines if y > center]
    if above and below and 0.006 < below[0] - above[-1] < 0.13:
        return above[-1], below[0]
    return None


def _head_noise(f):
    return f.box[1] < 0.19 or f.box[3] > 0.92


def extract_pages(pages, suggestions=None):
    rows = []
    anchors = defaultdict(list)
    footnotes = []
    context = dict(
        scenario="",
        component="",
        stage="",
        coating_type="",
        standard="",
        table="",
        clause="",
    )
    # Repeated running furniture is removed at fragment level only.
    repeated = Counter()
    for page in pages:
        repeated.update({normalized(f.text) for f in page.fragments if _head_noise(f)})
    fixed_positions = Counter(
        (normalized(f.text), round(f.box[1], 2))
        for page in pages
        for f in page.fragments
        if f.box[3] < 0.135
        and len(f.text.strip()) >= 5
        and not header_key(f.text)
        and not (NORM.search(f.text) or CAPTION.match(f.text) or SECTION.match(f.text))
    )
    all_frag = {f.id: f for p in pages for f in p.fragments}
    page_contexts = {}
    scenario_clause = ""
    layout = None
    caption = []
    buffer = defaultdict(list)
    para = []
    prev_y = None
    last_page = 0
    headerbuf = []
    last_band = None

    def flush_row():
        nonlocal last_band
        last_band = None
        if buffer:
            channel = (
                "frequency"
                if layout and {"pqt", "ppt", "production"} <= set(layout[0])
                else "performance"
            )
            table_requirements(rows, channel, dict(buffer), context, caption)
            buffer.clear()

    def flush_para():
        if para:
            _paragraph(rows, list(para), dict(context))
            para.clear()

    for page in pages:
        grid = page.rules
        # A stable running title can sit below a variable revision/approval masthead.
        header_end = max(
            (
                f.box[3]
                for f in page.fragments
                if f.box[3] < 0.135
                and fixed_positions[normalized(f.text), round(f.box[1], 2)]
                >= max(3, len(pages) * 0.70)
            ),
            default=0,
        )
        for _, line in groupby(page.fragments, key=lambda f: f.row):
            full = list(line)
            if max(f.box[3] for f in full) <= header_end and not is_header(
                heading(full)
            ):
                continue
            if all(_head_noise(f) for f in full):
                furniture = " ".join(f.text for f in full)
                if re.search(
                    r"\b(?:doc(?:ument)?\.?\s*(?:no|number)\.?\s*:|page\s*\d+\s*(?:of|/)\s*\d+|rev(?:ision)?\.?\s*[:.]?\s*\d+\s+page)",
                    furniture,
                    re.I,
                ):
                    continue
                if (
                    len(full) > 1
                    and not heading(full)
                    and any(
                        repeated[normalized(f.text)] >= max(3, len(pages) * 0.65)
                        for f in full
                    )
                    and not NORM.search(furniture)
                ):
                    continue
            row = [
                f
                for f in full
                if not (
                    _head_noise(f)
                    and not header_key(f.text)
                    and (
                        repeated[normalized(f.text)] >= max(3, len(pages) * 0.6)
                        or re.match(
                            r"^(?:page\s+)?\d+\s+(?:of|/)\s*\d+$", f.text.strip(), re.I
                        )
                    )
                )
            ]
            if not row:
                continue
            text = " ".join(f.text.strip() for f in row)
            y = min(f.box[1] for f in row)
            across = bool(last_page and page.number != last_page)
            gap = y - prev_y if prev_y is not None and not across else 0
            pairs = heading(row)
            if (
                layout
                and headerbuf
                and len(pairs) == len(row) == 1
                and normalized(row[0].text) in {"value", "values", "result", "results"}
                and any(
                    key == "typical"
                    and abs((f.box[0] + f.box[2] - row[0].box[0] - row[0].box[2]) / 2)
                    < 0.035
                    for key, f in headerbuf
                )
            ):
                continue
            if (
                is_header(pairs)
                or pairs
                and headerbuf
                and is_header(headerbuf + pairs)
                and abs(gap) < 0.034
            ):
                flush_para()
                flush_row()
                if headerbuf and abs(gap) < 0.034:
                    pairs = headerbuf + pairs
                layout = schema(pairs, page, row)
                headerbuf = pairs
            elif (
                pairs
                and len(pairs) == len(row)
                and not is_header(pairs)
                and (not layout or not buffer)
            ):
                headerbuf = pairs
            elif (
                (cap := CAPTION.match(text))
                and not re.search(r"\b(shall|must|see|per)\b", text, re.I)
                and len(text) < 170
            ):
                flush_row()
                flush_para()
                layout = None
                headerbuf = []
                context["table"] = cap[0]
                contexts(text, context)
                caption = row
                anchors[("table", cap[2].lower())].append((context["scenario"], row))
            elif (
                (section := SECTION.match(text))
                and not re.match(r"[≥≤<>±=]", section[2])
                and (len(row) <= 2 or NORM.search(text))
                and not (
                    layout
                    and re.match(r"^\d+\.$", row[0].text.strip())
                    and len(row) > 1
                )
            ):
                flush_row()
                flush_para()
                layout = None
                caption = []
                headerbuf = []
                number = section[1].rstrip(".")
                if (
                    scenario_clause
                    and number != scenario_clause
                    and not number.startswith(scenario_clause + ".")
                ):
                    context.update(scenario="", component="", stage="", coating_type="")
                    scenario_clause = ""
                if SCENARIO.search(text) and not NORM.search(text):
                    scenario_clause = number
                context["clause"] = number
                context["table"] = ""
                contexts(text, context)
                anchors[("clause", context["clause"].lower())].append(
                    (context["scenario"], row)
                )
                if NORM.search(text) or TIME.search(text) or TEMP.search(text):
                    para.extend(row)
            elif (
                (label := note_label(text))
                and (layout or caption)
                and (len(row) <= 2 or row[0].text.strip() == label)
            ):
                flush_row()
                flush_para()
                note = _paragraph(rows, row, dict(context), "footnote")
                if note:
                    footnotes.append((label, note, row))
            elif re.match(r"^(?:notes?|remarks?)\s*[:.]", text, re.I):
                flush_row()
                flush_para()
                layout = None
                headerbuf = []
                r = _make(rows, "footnote", {"item": row}, dict(context), caption)
                r.requirement = text
                r.bind("requirement", row)
            elif (
                re.match(
                    r"^(?:Scenario\b|Component\s*[:=]|Test Programmes?\b|Minimum Frequency\b|Open[- ]Cut\b|HDD\b)",
                    text,
                    re.I,
                )
                and len(text) < 130
                and not NORM.search(text.replace("Minimum Frequency", ""))
                and len(row) <= 2
            ):
                flush_row()
                flush_para()
                layout = None
                caption = []
                headerbuf = []
                contexts(text, context)
                context["table"] = text
                caption = row
            elif layout:
                fields = cells(row, layout)
                headerbuf = []
                band = grid_band(row, grid)
                same_band = bool(band and last_band == (page.number, band))
                # A continuation in a value column can begin with an inequality or "By Agreement".
                leftmost = row[0].box[0]
                wide = max(f.box[2] for f in row) - leftmost > 0.50
                sentence = bool(
                    re.search(r"\b(?:shall|must|may|should|will)\b", text, re.I)
                )
                is_paragraph = not same_band and (
                    len(fields) == 1
                    and "item" in fields
                    and sentence
                    and len(text.split()) >= 5
                    or wide
                    and sentence
                    and len(text.split()) >= 7
                    and not band
                    or len(row) >= 6
                    and wide
                    and len(text.split()) >= 10
                    and not band
                    and not re.search(r"\d", text)
                )
                if is_paragraph:
                    flush_row()
                    flush_para()
                    layout = None
                    caption = []
                    context["table"] = ""
                    para.extend(row)
                else:
                    flush_para()
                    numbered = bool(fields.get("num")) and bool(
                        re.fullmatch(r"\s*\d+[.)]?\s*", read_text(fields["num"]))
                    )
                    has_item = bool(fields.get("item"))
                    has_data = bool(
                        fields.keys()
                        & {"requirement", "typical", "pqt", "ppt", "production"}
                    )
                    if same_band:
                        newrow = False
                    elif band and last_band and last_band[0] == page.number:
                        newrow = True
                    else:
                        newrow = (
                            numbered
                            and buffer.get("num")
                            or has_item
                            and has_data
                            or has_item
                            and (gap > 0.022 or across)
                        )
                    if buffer and newrow:
                        flush_row()
                    if band:
                        last_band = (page.number, band)
                    for k, v in fields.items():
                        buffer[k].extend(v)
            else:
                headerbuf = []
                if (
                    len(row) >= 2
                    and not NORM.search(row[0].text)
                    and any(header_key(f.text) for f in row)
                ):
                    flush_para()
                if para and (
                    gap > 0.015
                    or across
                    or (
                        para[-1].text.rstrip().endswith((".", ";"))
                        and (
                            not re.match(
                                r"^(?:if|unless|should|then|until|only|otherwise|upon|when)\b",
                                text,
                                re.I,
                            )
                            or not re.search(
                                r"fail|retest|reject|stop", para[-1].text, re.I
                            )
                        )
                    )
                ):
                    flush_para()
                if (
                    len(text) < 140
                    and not para
                    and (EDITION.search(text) or TYPE.search(text))
                ):
                    metadata = {}
                    if m := EDITION.search(text):
                        metadata["standard"] = "ISO 21809-3:" + m[1]
                    if m := TYPE.search(text):
                        metadata["coating_type"] = re.sub(r"\s", "", m[1]).upper()
                    context.update(metadata)
                para.extend(row)
            if suggestions and page.number in suggestions:
                page_contexts.setdefault(page.number, []).append(
                    (y, dict(context), list(caption or []))
                )
            last_page = page.number
            prev_y = max(f.box[3] for f in row)
        if (
            suggestions
            and page.number in suggestions
            and not page_contexts.get(page.number)
        ):
            page_contexts[page.number] = [(0, dict(context), list(caption or []))]
        if page.issue:
            flush_row()
            flush_para()
            r = Requirement(
                f"R{len(rows) + 1:05}",
                "coverage",
                item="Page review",
                source_pages=[page.number],
            )
            r.flag("missing_ocr", "RED", page.issue)
            rows.append(r)
    flush_row()
    flush_para()
    if suggestions:
        _vision_rows(
            rows,
            suggestions,
            all_frag,
            {p.number: p for p in pages},
            page_contexts,
            anchors,
            footnotes,
        )
    attached_notes = set()
    for r in rows:
        if r.channel not in {"performance", "vision", "frequency"}:
            continue
        for key, ids in list(r.bindings.items()):
            if key == "caption":
                continue
            for mark in {m for fid in ids for m in all_frag[fid].markers}:
                hits = [
                    (n, fs)
                    for label, n, fs in footnotes
                    if label == mark
                    and n.table == r.table
                    and n.scenario == r.scenario
                    and min(abs(p - q) for p in r.source_pages for q in n.source_pages)
                    <= 1
                ]
                if len(hits) == 1:
                    n, fs = hits[0]
                    attached_notes.add(n.id)
                    r.notes.append(
                        dict(
                            marker=mark,
                            field=key,
                            text=n.verbatim,
                            role="conditional_exception",
                            evidence=[f.id for f in fs],
                        )
                    )
                    r.bind("footnote", fs, primary=False)
                else:
                    r.flag(
                        "unresolved_footnote",
                        "RED",
                        "Verify the marked cell and its note.",
                    )
    for _, note, _ in footnotes:
        if note.id not in attached_notes:
            note.flag(
                "unbound_footnote",
                "RED",
                "Verify the marked cell before applying this standalone note.",
            )
    for r in rows:
        for match in REF.finditer(r.verbatim):
            typ, num = match.groups()
            nearby = r.verbatim[match.end() : match.end() + 60]
            before = r.verbatim[max(0, match.start() - 45) : match.start()]
            if re.match(
                r"\s+(?:of|in)\s+(?:the\s+)?(?:ISO|EN|IEC|ASTM)\s*\d", nearby, re.I
            ) or re.search(
                r"(?:ISO|EN|IEC|ASTM)\s*[\d:–-]+\s*[,/(]?\s*$", before, re.I
            ):
                r.links.append(
                    dict(
                        label=match[0],
                        tier="external_standard_ref",
                        evidence=list(r.bindings.get("item", [])),
                        pages=r.source_pages.copy(),
                    )
                )
                continue
            targets = anchors.get(
                ("table" if typ.lower() == "table" else "clause", num.lower()), []
            )
            targets = [
                t for t in targets if not (r.scenario and t[0] and r.scenario != t[0])
            ]
            if len(targets) == 1:
                _, fs = targets[0]

                def belongs(candidate):
                    if (
                        candidate is r
                        or candidate.scenario
                        and r.scenario
                        and candidate.scenario != r.scenario
                    ):
                        return False
                    if typ.lower() == "table":
                        return any(
                            f.id in candidate.bindings.get("caption", []) for f in fs
                        )
                    return candidate.clause.lower() == num.lower()

                body = [c for c in rows if belongs(c)]
                ids = list(
                    dict.fromkeys(
                        [f.id for f in fs] + [i for c in body for i in c.evidence]
                    )
                )
                r.links.append(
                    dict(
                        label=typ + " " + num,
                        tier="same_doc_cross_ref",
                        targets=[c.id for c in body],
                        resolved_fields=[
                            dict(
                                id=c.id,
                                item=c.item,
                                condition=c.condition,
                                requirement=c.requirement,
                                method=c.method,
                                unit=c.unit,
                                scenario=c.scenario,
                                value_role=c.value_role,
                                pages=c.source_pages,
                            )
                            for c in body
                        ],
                        evidence=ids,
                        pages=sorted({all_frag[i].page for i in ids}),
                    )
                )
                caption_text = " ".join(f.text for f in fs)
                if re.search(
                    r"\b(?:abbreviations?|definitions?|reference documents?|document register|terminology)\b",
                    caption_text,
                    re.I,
                ) and re.search(
                    r"shall|must|acceptance|limit|performance|properties",
                    r.verbatim,
                    re.I,
                ):
                    r.flag(
                        "reference_mismatch",
                        "RED",
                        "The target is a glossary or document register. Verify the intended technical requirement.",
                    )
                if not body and not set(f.id for f in fs) & set(r.evidence):
                    r.flag(
                        "unresolved_reference",
                        "YELLOW",
                        "The heading was found but its clause or table body needs checking.",
                    )
            else:
                r.flag(
                    "unresolved_reference",
                    "RED",
                    "Verify reference " + typ + " " + num + " and its scope.",
                )
    return rows


def _vision_rows(rows, suggestions, fragments, pages, locations, anchors, footnotes):
    from .model import Fragment
    from math import isfinite

    previous_number = None
    visual_context = {}
    visual_caption = []
    for number, drafts in sorted(suggestions.items()):
        page = pages[number]
        lines = locations.get(number, [])
        if previous_number != number - 1 or page.carrier == "native":
            visual_context = {}
            visual_caption = []
        previous_number = number
        accepted = 0
        for index, draft in enumerate(drafts):
            if not isinstance(draft, dict):
                continue
            box = draft.get("box")
            precise = (
                isinstance(box, (tuple, list))
                and len(box) == 4
                and all(
                    isinstance(v, (float, int)) and isfinite(v) and 0 <= v <= 1
                    for v in box
                )
                and box[0] < box[2]
                and box[1] < box[3]
            )
            box = list(box) if precise else [0, 0, 1, 1]
            field_keys = (
                "item",
                "condition",
                "requirement",
                "typical",
                "unit",
                "method",
                "pqt",
                "ppt",
                "production",
                "sampling_basis",
                "failure_action",
            )
            ids = [
                fid
                for key in field_keys
                if isinstance(draft.get(key), list)
                for fid in draft[key]
                if isinstance(fid, str)
                and fid in fragments
                and fragments[fid].page == number
            ]
            y = fragments[ids[0]].box[1] if ids else box[1]
            context, caption = next(
                ((c, cap) for top, c, cap in reversed(lines) if top <= y + 0.025),
                (lines[0][1], lines[0][2]) if lines else ({}, []),
            )
            context = dict(context, **visual_context)
            context.setdefault("scenario", "")
            quote = draft.get("quote", "")
            if not isinstance(quote, str):
                continue

            def add(text, label, markers=()):
                f = Fragment(
                    f"{number}.V{index + 1}_{label}",
                    number,
                    box,
                    text,
                    text,
                    list(markers),
                    index + 1,
                    "vision_region" if precise else "vision_page",
                )
                fragments[f.id] = f
                page.fragments.append(f)
                return f

            kind = draft.get("kind")
            if kind == "heading" and quote.strip():
                f = add(quote, "heading")
                old = dict(context)
                contexts(quote, context)
                if old.get("scenario") != context["scenario"]:
                    context.update(table="", clause="")
                    visual_caption = []
                if m := CAPTION.match(quote):
                    context["table"] = m[0]
                    visual_caption = [f]
                    target = anchors[("table", m[2].lower())]
                    existing = next(
                        (
                            fs
                            for sc, fs in target
                            if sc == context["scenario"]
                            and fs[0].page == number
                            and normalized(read_text(fs)) == normalized(quote)
                        ),
                        None,
                    )
                    if existing:
                        visual_caption = existing
                    else:
                        target.append((context["scenario"], [f]))
                elif m := SECTION.match(quote):
                    context["clause"] = m[1].rstrip(".")
                    context["table"] = ""
                    visual_caption = []
                    target = anchors[("clause", context["clause"].lower())]
                    if not any(
                        sc == context["scenario"] and fs[0].page == number
                        for sc, fs in target
                    ):
                        target.append((context["scenario"], [f]))
                visual_context.update(
                    {k: v for k, v in context.items() if old.get(k) != v}
                )
                continue
            if kind == "footnote" and quote.strip():
                label = note_label(quote)
                if label:
                    f = add(quote, "note")
                    note = _paragraph(rows, [f], context, "footnote")
                    if note:
                        footnotes.append((label, note, [f]))
                        note.flag(
                            "visual_transcription",
                            "CHECK",
                            "Verify the printed footnote on the image.",
                        )
                        accepted += 1
                continue
            fields = {}
            unverified = False
            for key in field_keys:
                value = draft.get(key)
                if (
                    isinstance(value, list)
                    and value
                    and all(
                        isinstance(i, str)
                        and i in fragments
                        and fragments[i].page == number
                        for i in value
                    )
                ):
                    fields[key] = [fragments[i] for i in value]
                elif isinstance(value, str) and value.strip():
                    if not quote or value not in quote:
                        unverified = True
                        continue
                    markers = draft.get("markers", {})
                    marker = markers.get(key, "") if isinstance(markers, dict) else ""
                    visible = (
                        isinstance(marker, str)
                        and bool(re.fullmatch("[a-z]", marker))
                        and bool(
                            re.search(
                                re.escape(value)
                                + r"\s*(?:\^|\()?"
                                + marker
                                + r"(?![a-z])",
                                quote.replace("ᵃ", "a")
                                .replace("ᵇ", "b")
                                .replace("ᶜ", "c"),
                                re.I,
                            )
                        )
                    )
                    if marker and not visible:
                        unverified = True
                    fields[key] = [add(value, key, [marker] if visible else [])]
            if "item" not in fields:
                continue
            if "requirement" in fields:
                req = read_text(fields["requirement"])
                typical_only = re.search(
                    r"\btypical(?: value)?\s*[:=]?\s*" + re.escape(req), quote, re.I
                )
                if typical_only and not re.search(
                    r"(?:requirement|minimum|maximum|limit)\s*[:=]?\s*"
                    + re.escape(req),
                    quote,
                    re.I,
                ):
                    fields["typical"] = fields.pop("requirement")
                elif re.search(r"\d", req):
                    placeholders = re.findall(
                        r"\b(?:TBA|TBD|By Vendor|By Agreement)\b|(?:(?<=\|)|^)\s*[-–—]\s*(?=\||$)",
                        quote,
                        re.I,
                    )
                    elsewhere = {
                        normalized(read_text(fs))
                        for k, fs in fields.items()
                        if k != "requirement"
                    }
                    if any(normalized(v) not in elsewhere for v in placeholders):
                        # A number elsewhere in this row is not evidence for an unspecified limit.
                        del fields["requirement"]
                        unverified = True
            ident = {f.id for v in fields.values() for f in v}
            if any(ident <= set(r.evidence) for r in rows):
                accepted += 1
                continue
            channel = (
                "frequency"
                if any(key in fields for key in ("pqt", "ppt", "production"))
                else "vision"
            )
            matches = []
            if precise and "item" in fields:
                for original in rows:
                    if (
                        original.channel not in {"performance", "frequency", "prose"}
                        or number not in original.source_pages
                    ):
                        continue
                    if normalized(original.item) != normalized(
                        read_text(fields["item"])
                    ):
                        continue
                    if any(
                        box[1] <= sum(fragments[i].box[1::2]) / 2 <= box[3]
                        for i in original.bindings.get("item", [])
                        if fragments[i].page == number
                    ):
                        matches.append(original)
            if len(matches) == 1 and all(
                getattr(matches[0], k) == read_text(fs) for k, fs in fields.items()
            ):
                accepted += 1
                continue
            r = _make(rows, channel, fields, context, visual_caption or caption)
            if len(matches) == 1:
                original = matches[0]
                for row, peer in ((original, r), (r, original)):
                    row.flag(
                        "visual_alternative",
                        "RED",
                        "Readings differ on this printed row. Compare "
                        + peer.id
                        + " and record the supported reading.",
                    )
            if quote:
                r.verbatim = quote
                r.notation = quote
                r.bind("image_transcription", [add(quote, "source")])
            r.flag(
                "visual_transcription",
                "CHECK",
                "Verify the visual transcription against the original page.",
            )
            if unverified:
                r.flag(
                    "unverified_field",
                    "RED",
                    "Fields outside the quoted image transcription were omitted.",
                )
            if (
                ids
                and max(fragments[k].row for k in ids)
                - min(fragments[k].row for k in ids)
                > 1
            ):
                r.flag(
                    "row_alignment", "RED", "Model fields span distinct source rows."
                )
            accepted += 1
        if not accepted and not page.issue and (drafts or page.carrier != "native"):
            r = Requirement(
                f"R{len(rows) + 1:05}",
                "coverage",
                item="Visual page review",
                source_pages=[number],
            )
            r.flag(
                "visual_incomplete",
                "RED",
                "No usable visual rows. Inspect the original page.",
            )
            rows.append(r)
