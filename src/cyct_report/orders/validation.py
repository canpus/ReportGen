"""Read-only comparisons. Reference values never enter execution fields."""

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import json
import re

from .. import paths
from .extract import METHOD, NUM, TYPE, EDITION
from .model import field_text, normalized, quantity

SENSITIVE = re.compile(
    r"√|[≥≤]|\^\s*[-+]?\d|[⁰¹²³⁴⁵⁶⁷⁸⁹]|(?<![<>=])[<>](?!=)|\b(?:TBA|By Vendor|By Agreement)\b",
    re.I,
)
STOP = {
    "the",
    "on",
    "of",
    "to",
    "shall",
    "from",
    "a",
    "an",
    "test",
    "testing",
    "using",
    "for",
    "with",
    "measure",
    "verify",
    "check",
    "inspection",
    "method",
    "is",
    "be",
    "per",
    "according",
    "at",
    "activity",
}


def metric(text):
    s = normalized(text).replace("peal", "peel")
    for pattern, key in [
        (
            r"roughness|surface profile|anchor profile|surface rough|surface.{0,10}profile",
            "roughness",
        ),
        (r"holiday|discontinuity", "holiday"),
        (r"impact", "impact"),
        (r"indentation|residual thickness", "indentation"),
        (r"disbondment", "disbondment"),
        (
            r"(?:hot.water|water immersion|immers).*peel|peel.*(?:water|immers)",
            "peel_wet",
        ),
        (r"(?:thermal ag[ei]|heat ag[ei]).*elong|elongation.*ag[ei]", "age_elong"),
        (r"(?:thermal ag[ei]|heat ag[ei]).*peel|peel.*ag[ei]", "age_peel"),
        (r"adhesion|pull.off", "adhesion"),
        (r"peel", "peel"),
        (r"shear", "shear"),
        (r"thickness", "thickness"),
        (r"hardness", "hardness"),
        (r"dust", "dust"),
        (r"salt|chloride", "salts"),
        (r"volume resist(?:ance|iv)", "volume_resistivity"),
        (r"insulation", "insulation_ratio"),
        (r"immersion", "immersion"),
        (
            r"appearance|visual inspection of (?:the )?(?:finished |joint )?coating",
            "appearance",
        ),
        (r"surface condition.*before|before.*surface preparation", "initial_surface"),
        (r"visual.*cleaned surface|surface cleanliness", "clean_surface"),
        (r"adjacent.*(?:surface|coating)|dulled plant", "adjacent_surface"),
        (r"surface temperature|temperature of (?:the )?surface", "surface_temperature"),
        (r"application criteria|process parameters", "process"),
        (r"curing|degree of cure", "cure"),
    ]:
        if re.search(pattern, s):
            return key
    before = METHOD.split(s, maxsplit=1)[0]
    return " ".join(w for w in re.findall(r"[a-z]+|\d+", before) if w not in STOP)[:100]


def scalar(s):
    m = re.search(NUM, s or "")
    return float(m[0].replace(",", ".")) if m else None


@lru_cache(maxsize=1)
def standards():
    with (paths.STANDARDS_DIR / "iso21809-3.json").open(encoding="utf8") as f:
        preset = json.load(f)
    extension = json.loads(
        Path(__file__).with_name("reference.json").read_text(encoding="utf8")
    )
    return preset, extension


def _standard_values(r, key, edition):
    preset, extension = standards()
    typ = r.coating_type
    if edition != extension["edition"] or not typ:
        return None
    if r.channel == "frequency":
        if not typ.startswith("14B"):
            return None
        suffix = "_max" if "max" in normalized(r.item) else "_ambient"
        k = key + suffix if key in {"peel", "shear", "disbondment"} else key
        vals = extension["annex_a_14b"].get(k)
        if vals:
            return dict(
                section="Annex A / Table A.1",
                **vals,
                note=extension["annex_a_notes"].get(k, ""),
            )
        return None
    if typ == "18A":
        k = key
        if (
            key == "insulation_ratio"
            and r.quantity_kind != "ratio"
            and "/" not in r.item
        ):
            k = "insulation_absolute"
        if key == "adhesion":
            wet = bool(re.search(r"water|immers", r.item, re.I))
            plant = bool(re.search(r"FBE|polyolefin|plant|PU", r.item, re.I))
            k = (
                ("adhesion_wet_plant" if plant else "adhesion_wet_steel")
                if wet
                else (
                    "adhesion_polyolefin"
                    if "polyolefin" in r.item.lower()
                    else "adhesion_epoxy"
                    if plant
                    else "adhesion_steel"
                )
            )
        v = extension["table30"].get(k)
        if not v:
            return None
        if isinstance(v[0], list):
            v = next(
                (
                    i
                    for i in v
                    if i[0]
                    in re.findall(
                        r"Tmax|[−–-]?\d+(?:[.,]\d+)?",
                        r.test_temp.replace("−", "-"),
                        re.I,
                    )
                ),
                None,
            )
        if v:
            return dict(
                section="Table 30",
                temp=v[0],
                unit=v[1],
                limit=v[2],
                method=v[3],
                days=28 if k.startswith("adhesion_wet") or k == "disbondment" else None,
                note=extension["notes"].get(k, ""),
            )
        return None
    tab = "t16" if typ.startswith("14A") else "t17"
    table = preset["tables"][tab]
    if typ not in table["cols"]:
        return None
    keys = {
        "peel_wet": "{peel_hw100}",
        "age_elong": "{ta14_elong}",
        "age_peel": "{ta14_peel}",
        "impact": "{impact_holiday}",
        "holiday": "{holiday_5kv}",
        "indentation": "{indent_residual}",
        "peel": "{peel_po_10}"
        if re.search(r"plant|polyolefin", r.interface, re.I)
        else "{peel_pipe_10}",
        "shear": "{lap_shear_10}",
        "disbondment": "{cd_28d}",
    }
    term = keys.get(key)
    if key == "indentation" and r.value_role == "test_condition":
        term = "{indent_pressure}"
    idx = table["cols"].index(typ)
    matches = [v for v in table["rows"] if isinstance(v, list) and v[0] == term]
    if key in {"age_peel", "age_elong"}:
        ratios = lambda v: (
            normalized(v)
            .translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
            .replace("_", "")
            .replace(" ", "")
        )
        ratio = re.search(
            r"[a-z]+[0-9]+/[a-z]+[0-9]+", ratios(r.unit + " " + r.requirement)
        )
        if ratio:
            matches = [v for v in matches if ratios(v[2]) == ratio[0]]
        elif len(matches) > 1:
            return None
    if len(matches) > 1:
        matches = [
            v for v in matches if ("Tmax" in v[1]) == ("max" in normalized(r.test_temp))
        ]
    if not matches:
        return None
    _, temp, unit, limit, method, *_ = matches[0]
    if isinstance(limit, list):
        limit = limit[idx]
    if limit is None:
        return None
    return dict(
        section="Table " + tab[1:],
        temp=temp,
        unit=unit,
        limit=limit,
        method=method,
        days=100 if key == "peel_wet" else 28 if key == "disbondment" else None,
    )


def _compare(r, key, reference_edition):
    edition = r.standard or reference_edition
    base = _standard_values(r, key, edition)
    if not base:
        return
    base.update(
        standard=edition,
        edition_source="document" if r.standard else "reviewer_selection",
        coating_type=r.coating_type,
        tier="external_standard_ref",
    )
    r.reference.append(base)
    if r.channel == "frequency":
        for k in ("pqt", "ppt", "production"):
            if normalized(getattr(r, k)) != normalized(base[k]):
                r.flag(
                    "frequency_difference",
                    "YELLOW",
                    "Review the project frequency for " + k + ".",
                )
        return
    days = re.search(r"(\d+)\s*(?:days?|d)\b", r.conditioning, re.I)
    if base.get("days") and days and int(days[1]) != base["days"]:
        r.flag(
            "duration_difference",
            "RED",
            "Confirm the specified duration against the typed reference.",
        )
    unit = base.get("unit", "")
    if unit and r.quantity_kind not in {"qualitative", "number"}:
        if quantity(unit) != r.quantity_kind:
            r.flag(
                "quantity_difference",
                "RED",
                "Reference and order measure different quantities. Seek clarification.",
            )
        elif (
            r.unit
            and normalized(r.unit) != normalized(unit)
            and quantity(unit) in {"force_per_length", "energy_per_length"}
        ):
            r.flag(
                "unit_scale",
                "YELLOW",
                "Check the written units and their scale before comparing values.",
            )
    if r.quantity_kind == "ratio":
        written = re.search(r"(?:≥|>|>=)\s*(" + NUM + ")", r.requirement)
        expected = re.search(r"(?:≥|>|>=)\s*(" + NUM + ")", base.get("limit", ""))
        if written and expected and scalar(written[1]) != scalar(expected[1]):
            r.flag(
                "typed_limit_difference",
                "YELLOW",
                "Retention limit differs for this exact type.",
            )
    if (
        base.get("limit")
        and re.match(r"^\s*[<>](?!=)", r.requirement)
        and re.match(r"^[≤≥]", base["limit"])
    ):
        r.flag(
            "strict_operator",
            "YELLOW",
            "Check the strict inequality against the reference.",
        )


def _interval(r):
    t = r.condition + " " + r.item
    m = re.search(
        r"(" + NUM + r")\s*(<=|≤|<)\s*[A-Za-zØ]+\s*(<=|≤|<)\s*(" + NUM + ")", t
    )
    if m:
        return scalar(m[1]), scalar(m[4]), m[2] != "<", m[3] != "<"
    m = re.search(
        r"(?:diameter|width|size|\bD)\s*(<=|>=|≤|≥|<|>)\s*(" + NUM + ")", t, re.I
    )
    if not m:
        m = re.match(
            r"\s*(<=|>=|≤|≥|<|>)\s*("
            + NUM
            + r")(?:\s*(?:[″“”\x22]|in(?:ch(?:es)?)?\b|mm\b)|\s*$)",
            r.item,
            re.I,
        )
    if m:
        v = scalar(m[2])
        return (
            (-float("inf"), v, False, m[1] != "<")
            if m[1] in ("<", "<=", "≤")
            else (v, float("inf"), m[1] != ">", False)
        )
    return None


def compatible_scope(left, right):
    dimensions = ["component", "interface", "test_temp", "conditioning", "coating_type"]
    if "frequency" not in (left.channel, right.channel):
        dimensions.append("stage")
    return all(
        not a or not b or normalized(a) == normalized(b)
        for key in dimensions
        for a, b in [(getattr(left, key), getattr(right, key))]
    )


def check_alignment(r, frags, pages_by_number):
    if r.channel not in {"performance", "frequency", "vision"}:
        return
    body = [
        frags[i]
        for field, ids in r.bindings.items()
        if field not in {"caption", "footnote"}
        for i in ids
        if i in frags
    ]
    if not body:
        return
    positions = sorted({(f.page, f.row) for f in body})
    if any(
        b[0] - a[0] > 1 or (a[0] == b[0] and b[1] - a[1] > 2)
        for a, b in zip(positions, positions[1:])
    ):
        r.flag(
            "row_alignment",
            "RED",
            "Fields are separated by intervening source rows. Check the physical row.",
        )
    for n in {f.page for f in body}:
        here = [f for f in body if f.page == n]
        centers = [(f.box[1] + f.box[3]) / 2 for f in here]
        left = min(f.box[0] for f in here)
        right = max(f.box[2] for f in here)
        if any(
            y2 - y1 < 0.002
            and x2 - x1 > 0.4
            and x1 <= left + 0.015
            and x2 >= right - 0.015
            and min(centers) + 0.003 < y1 < max(centers) - 0.003
            for x1, y1, x2, y2 in pages_by_number[n].rules
        ):
            r.flag(
                "row_alignment",
                "RED",
                "A horizontal table rule separates the bound values.",
            )
    if r.channel == "vision" and len(positions) > 1:
        r.flag("row_alignment", "RED", "Verify row-local model evidence.")


def validate(rows, pages, reference_edition=None):
    if reference_edition and reference_edition != standards()[1]["edition"]:
        raise ValueError("Unsupported coating reference edition")
    pages_by_number = {p.number: p for p in pages}
    frags = {f.id: f for page in pages for f in page.fragments}
    editions = {m[1] for f in frags.values() for m in EDITION.finditer(f.text)}
    doc_types = {
        m[1].replace(" ", "").upper()
        for f in frags.values()
        for m in TYPE.finditer(f.text)
    }
    methods = defaultdict(list)
    ranges = defaultdict(list)
    grouped = defaultdict(list)
    for r in rows:
        if not r.standard and len(editions) == 1:
            r.standard = "ISO 21809-3:" + next(iter(editions))
        if not r.coating_type and len(doc_types) == 1:
            r.coating_type = next(iter(doc_types))
        if r.channel == "coverage":
            continue
        key = metric(r.item + " " + r.condition if r.channel != "frequency" else r.item)
        if (
            r.channel == "performance"
            and r.value_role == "acceptance_limit"
            and not r.requirement
        ):
            r.flag(
                "missing_limit",
                "YELLOW",
                "No acceptance criterion was located in this row.",
            )
        if r.typical and r.requirement:
            low, typ = scalar(r.requirement), scalar(r.typical)
            if (
                low is not None
                and typ is not None
                and (
                    bool(re.search(r"≥|>=|(?<!<)>|\bmin", r.requirement, re.I))
                    and typ < low
                    or bool(re.search(r"≤|<=|(?<!>)<|\bmax", r.requirement, re.I))
                    and typ > low
                    or re.fullmatch(NUM, r.requirement.strip())
                    and typ < low
                )
            ):
                r.flag(
                    "typical_outside",
                    "RED",
                    "Verify the typical value against the specified requirement and its comparison direction.",
                )
        if r.value_role in {"by_vendor", "tba", "by_agreement"}:
            r.flag(
                "unspecified",
                "RED",
                "A numeric acceptance decision needs a documented clarification.",
            )
        if SENSITIVE.search(r.notation) or any(
            frags[i].origin == "ocr" for i in r.evidence if i in frags
        ):
            r.flag(
                "visual_check",
                "CHECK",
                "Verify transcription, mathematical signs and column placement on the page.",
            )
        if r.value_role == "conditional_exception":
            r.flag("exception_scope", "YELLOW", "Verify the condition and its scope.")
        if (
            r.channel in {"performance", "frequency"}
            and r.standard
            and "21809" in r.standard
            and not r.coating_type
        ):
            r.flag(
                "reference_type",
                "YELLOW",
                "Select the applicable coating type before using a baseline.",
            )
        if (
            r.channel in {"performance", "frequency"}
            and r.coating_type
            and not r.standard
        ):
            r.flag(
                "reference_edition",
                "YELLOW",
                "Verify the referenced edition before comparing the standard.",
            )
        if r.channel in {"performance", "vision"}:
            if (
                key
                in {
                    "peel",
                    "peel_wet",
                    "impact",
                    "adhesion",
                    "shear",
                    "age_peel",
                    "age_elong",
                }
                and not r.test_temp
            ):
                r.flag(
                    "missing_temperature",
                    "YELLOW",
                    "Test temperature needs verification.",
                )
            if key in {"peel", "peel_wet"} and r.quantity_kind == "length":
                r.flag(
                    "suspect_unit",
                    "RED",
                    "Length was printed for a strength test; preserve and clarify the unit.",
                )
            if key == "volume_resistivity":
                if not re.search(r"[ΩΩ]|ohm", r.unit + " " + r.requirement, re.I):
                    r.flag(
                        "missing_quantity_unit",
                        "RED",
                        "Verify the resistivity unit on the original page.",
                    )
                if re.search(r"IEC\s*60243", r.method, re.I):
                    r.flag(
                        "method_dimension",
                        "RED",
                        "Verify the cited electric-strength method for a resistivity measurement.",
                    )
            _compare(r, key, reference_edition if len(editions) <= 1 else None)
        if r.channel == "frequency":
            _compare(r, key, reference_edition if len(editions) <= 1 else None)
            if not all((r.pqt, r.ppt, r.production)):
                r.flag(
                    "missing_frequency",
                    "YELLOW",
                    "At least one stage is blank. Check the column boundaries.",
                )
        if r.method:
            methods[(r.scenario, key)].append(
                (r, r.method, r.bindings.get("method", []))
            )
        if r.channel == "prose":
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", r.verbatim):
                if not re.search(r"\b(?:shall|must)\b", sentence, re.I):
                    continue
                topic = metric(sentence)
                for m in METHOD.finditer(sentence):
                    ids = [
                        i
                        for i in r.bindings["item"]
                        if any(
                            token in frags[i].text
                            for token in re.findall(r"\d[\d.-]*", m[0])
                        )
                    ]
                    if ids:
                        methods[(r.scenario, topic)].append((r, m[0], ids))
        scope = (
            r.component,
            r.scenario,
            r.interface,
            r.stage,
            r.test_temp,
            r.conditioning,
            key,
            r.table if not (r.component or r.scenario) else "",
        )
        if r.channel == "performance":
            grouped[scope].append(r)
            interval = _interval(r)
            if interval:
                axis = "size" if re.match(r"\s*[><≥≤]", r.item) else metric(r.item)
                ranges[(r.component, r.scenario, r.stage, axis, r.table)].append(
                    (interval, r)
                )
        for field in (
            "requirement",
            "typical",
            "pqt",
            "ppt",
            "production",
            "method",
            "unit",
            "condition",
            "sampling_basis",
            "failure_action",
            "frequency",
        ):
            value = getattr(r, field)
            bound = [frags[i] for i in r.bindings.get(field, []) if i in frags]
            corpora = [
                normalized(" ".join(render(f) for f in bound))
                for render in (lambda f: f.text, field_text)
            ]
            if value and (
                not bound or not any(normalized(value) in c for c in corpora)
            ):
                r.flag(
                    "unverified_field",
                    "RED",
                    "Check the geometry and source tokens for " + field + ".",
                )
        check_alignment(r, frags, pages_by_number)
    for r in rows:
        if r.channel not in {"performance", "frequency"}:
            continue
        key = metric(r.item)
        linked = [
            entry
            for entry in methods[(r.scenario, key)]
            if entry[0] is not r
            and entry[0].channel != r.channel
            and compatible_scope(r, entry[0])
        ]
        if r.scenario and not linked:
            linked = [
                entry
                for entry in methods[("", key)]
                if entry[0].channel == "prose"
                and compatible_scope(r, entry[0])
                and re.search(r"\b(?:shall|must)\b", entry[0].verbatim, re.I)
            ]
        known = {normalized(value).rstrip(".") for other, value, ids in linked}
        if r.method and known and normalized(r.method).rstrip(".") not in known:
            r.flag(
                "method_conflict",
                "RED",
                "Method differs from the same activity in this scenario; clarify both clauses.",
            )
            for other, value, ids in linked:
                link = dict(
                    label="method conflict",
                    target=other.id,
                    tier="same_doc_cross_ref",
                    method=value,
                    evidence=ids,
                    pages=other.source_pages.copy(),
                )
                if link not in r.links:
                    r.links.append(link)
        elif not r.method and len(known) == 1:
            other, value, ids = linked[0]
            r.method = value
            r.field_sources["method"] = "same_doc_cross_ref"
            r.bind("method", [frags[i] for i in ids], primary=False)
            r.links.append(
                dict(
                    label="method",
                    target=other.id,
                    tier="same_doc_cross_ref",
                    pages=other.source_pages.copy(),
                    evidence=ids,
                )
            )
        elif not r.method and len(known) > 1:
            r.flag(
                "ambiguous_method", "YELLOW", "Several methods exist in this scenario."
            )
    for group in grouped.values():
        seen = {}
        for r in group:
            k = (
                normalized(r.item),
                normalized(r.condition),
                normalized(r.unit),
                r.value_role,
            )
            if k in seen:
                other = seen[k]
                code = (
                    "duplicate_row"
                    if normalized(r.requirement) == normalized(other.requirement)
                    else "scope_conflict"
                )
                for row in (r, other):
                    row.flag(
                        code,
                        "YELLOW" if code == "duplicate_row" else "RED",
                        "Compare rows " + r.id + " and " + other.id + " in this scope.",
                    )
            seen[k] = r
    for group in ranges.values():
        ordered = sorted(group, key=lambda x: x[0])
        for (prev, one), (nxt, two) in zip(ordered, ordered[1:]):
            if prev[1] < nxt[0] or prev[1] == nxt[0] and not (prev[3] or nxt[2]):
                code = "range_gap"
            elif prev[1] > nxt[0] or prev[1] == nxt[0] and prev[3] and nxt[2]:
                code = "range_overlap"
            else:
                continue
            for r in (one, two):
                r.flag(
                    code, "YELLOW", "Verify the boundaries of the adjacent size ranges."
                )
    for r in rows:
        codes = {a["code"] for a in r.alerts if a["level"] == "RED"}
        if {"duration_difference", "quantity_difference"} & codes:
            r.clarification_suggestions.append(
                "Please confirm the ordered conditioning period and measured quantity against the cited standard and coating type."
            )
        if "method_conflict" in codes:
            r.clarification_suggestions.append(
                "Which of the two cited methods applies to this activity and scenario?"
            )
        if "unspecified" in codes:
            r.clarification_suggestions.append(
                "Please supply the agreed criterion for this order, including its unit and applicability."
            )
    return rows
