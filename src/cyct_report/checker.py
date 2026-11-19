"""实测值与指标的自动比对（仅用于界面提示，不写入报告）。

judge(req, result) 返回 True（合格）/ False（不合格）/ None（无法判断，例如文字类指标）。
"""
import re

_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
# “10^8”必须排在前面，否则会被当成数字 10
_NUM = r"10\^-?\d+|-?\d+(?:\.\d+)?(?:\s*[×xX*]\s*10\^-?\d+)?"


def _normalize(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("＞", ">").replace("＜", "<").replace("≧", "≥").replace("≦", "≤")
    s = s.replace(">=", "≥").replace("<=", "≤").replace("－", "-").replace("−", "-")
    s = s.replace("～", "~").replace("–", "~").replace("—", "—")
    # 10¹⁴ → 10^14
    s = re.sub(r"10([⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)", lambda m: "10^" + m.group(1).translate(_SUP), s)
    s = s.translate(_SUB)
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)          # 0,8 → 0.8
    s = re.sub(r"[eE]([+-]?\d+)", r"×10^\1", s)    # 2.1E14 → 2.1×10^14
    return s


def _to_float(tok: str) -> float:
    tok = tok.replace(" ", "")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)?[×xX*]?10\^(-?\d+)", tok)
    if m:
        mant = float(m.group(1)) if m.group(1) else 1.0
        return mant * 10 ** int(m.group(2))
    return float(tok)


def parse_requirement(req: str):
    """返回 (low, high) 区间（含端点，None 表示无界），无法解析时返回 None。"""
    s = _normalize(req)
    m = re.match(rf"^\s*({_NUM})\s*≥.*?≥\s*({_NUM})", s)        # 1.25≥E/E0≥0.75
    if m:
        return _to_float(m.group(2)), _to_float(m.group(1))
    m = re.match(rf"^\s*({_NUM})\s*~\s*({_NUM})\s*$", s)          # 0.75~1.25
    if m:
        return _to_float(m.group(1)), _to_float(m.group(2))
    m = re.search(rf"(≥|≤|>|<)\s*({_NUM})", s)
    if not m:
        return None
    v = _to_float(m.group(2))
    return (v, None) if m.group(1) in "≥>" else (None, v)


def parse_result(res: str):
    s = _normalize(res)
    m = re.search(_NUM, s)
    return _to_float(m.group()) if m else None


def judge(req: str, result: str):
    if not (result or "").strip():
        return None
    rng = parse_requirement(req)
    if rng is None:
        r, q = _normalize(result).casefold(), _normalize(req).casefold()
        return True if q and r == q else None
    v = parse_result(result)
    if v is None:
        return None
    low, high = rng
    if low is not None and v < low:
        return False
    if high is not None and v > high:
        return False
    return True
