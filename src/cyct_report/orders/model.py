"""Geometry uses the upright preview, normalized to [0, 1]; pages start at one."""

from dataclasses import dataclass, field

ROLES = (
    "acceptance_limit",
    "test_condition",
    "typical_only",
    "typical_reference",
    "by_vendor",
    "tba",
    "by_agreement",
    "dash_not_listed",
    "conditional_exception",
)
TIERS = ("client_explicit", "same_doc_cross_ref", "external_standard_ref")
DIMENSIONS = (
    "component",
    "scenario",
    "interface",
    "test_temp",
    "conditioning",
    "stage",
)
EDITABLE = (
    *DIMENSIONS,
    "item",
    "condition",
    "requirement",
    "typical",
    "unit",
    "method",
    "sampling_basis",
    "frequency",
    "failure_action",
    "value_role",
    "quantity_kind",
    "pqt",
    "ppt",
    "production",
    "destination",
)


@dataclass
class Fragment:
    id: str
    page: int
    box: list
    text: str
    notation: str = ""
    markers: list = field(default_factory=list)
    row: int = 0
    origin: str = "native"
    runs: list = field(default_factory=list)


@dataclass
class Page:
    number: int
    width: float
    height: float
    carrier: str
    fragments: list
    # horizontal/vertical vector segments, normalized to the same preview
    rules: list = field(default_factory=list)
    issue: str = ""


@dataclass
class Requirement:
    id: str
    channel: str
    item: str = ""
    condition: str = ""
    requirement: str = ""
    typical: str = ""
    unit: str = ""
    method: str = ""
    sampling_basis: str = ""
    frequency: str = ""
    failure_action: str = ""
    pqt: str = ""
    ppt: str = ""
    production: str = ""
    component: str = ""
    scenario: str = ""
    interface: str = ""
    test_temp: str = ""
    conditioning: str = ""
    stage: str = ""
    destination: str = "laboratory"
    value_role: str = "acceptance_limit"
    quantity_kind: str = "qualitative"
    source_tier: str = "client_explicit"
    field_sources: dict = field(default_factory=dict)
    phase_roles: dict = field(default_factory=dict)
    clarification_suggestions: list = field(default_factory=list)
    table: str = ""
    clause: str = ""
    standard: str = ""
    coating_type: str = ""
    source_pages: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    bindings: dict = field(default_factory=dict)
    verbatim: str = ""
    notation: str = ""
    notes: list = field(default_factory=list)
    links: list = field(default_factory=list)
    reference: list = field(default_factory=list)
    alerts: list = field(default_factory=list)

    def flag(self, code, level, message):
        if not any(a["code"] == code and a["message"] == message for a in self.alerts):
            self.alerts.append(dict(code=code, level=level, message=message))

    def bind(self, key, fragments, *, primary=True):
        ids = self.bindings.setdefault(key, [])
        for f in fragments:
            if f.id not in ids:
                ids.append(f.id)
            if f.id not in self.evidence:
                self.evidence.append(f.id)
            if primary and f.page not in self.source_pages:
                self.source_pages.append(f.page)
        self.source_pages.sort()


def read_text(fragments):
    return "\n".join(f.text for f in fragments)


def field_text(fragment):
    # Baseline markup keeps exponents distinct from digits and note markers from limits.
    text = fragment.notation or fragment.text
    for marker in fragment.markers:
        text = text.replace("^" + marker, "")
    return text


def normalized(text):
    return " ".join(text.casefold().split())


def pending_role(text):
    s = normalized(text)
    if s in {"-", "—", "–", "−"}:
        return "dash_not_listed"
    if s in {"tba", "tbd", "to be advised", "to be agreed"}:
        return "tba"
    if s in {"by vendor", "by manufacturer", "by supplier"}:
        return "by_vendor"
    if s in {"by agreement", "as agreed"}:
        return "by_agreement"
    return None


def quantity(text):
    import re

    t = (
        normalized(text)
        .replace(" ", "")
        .translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    )
    if re.search(r"[a-z]+_?\d+/[a-z]+_?\d+", t) or "ratio" in t:
        return "ratio"
    if re.search(r"n/(?:mm|cm)(?:²|2|\^2)|mpa|n/mm\*\*2", t):
        return "stress"
    if "n/mm" in t or "n/cm" in t or "n/m" in t:
        return "force_per_length"
    if "j/mm" in t:
        return "energy_per_length"
    if re.search(r"\d[j]\b|^j(?:$|[<>=≥≤+\-\d])", t):
        return "energy"
    if any(x in t for x in ("mm", "µm", "μm", "micron")):
        return "length"
    if "%" in t:
        return "percentage"
    if "°" in t or "℃" in t:
        return "temperature"
    if "ω" in t or "ohm" in t:
        return (
            "electrical_resistance_area"
            if "m²" in t or "m2" in t
            else "electrical_resistivity"
        )
    if "kv" in t or "volt" in t:
        return "voltage"
    if re.search(r"\d", t):
        return "number"
    return "qualitative"
