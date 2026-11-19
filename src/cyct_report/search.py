"""模糊搜索：不区分大小写，空格（含全角空格）分隔多个关键词，全部命中才算匹配。"""


def keywords(query: str) -> list:
    return [k for k in (query or "").replace("　", " ").casefold().split() if k]


def matches(query: str, text: str) -> bool:
    t = (text or "").casefold()
    return all(k in t for k in keywords(query))


def filter_rank(query: str, candidates: list, limit: int = 50) -> list:
    """candidates 已按使用频率/最近使用排好序；以首个关键词开头的排在前面。"""
    kws = keywords(query)
    if not kws:
        return candidates[:limit]
    hit = [c for c in candidates if matches(query, c)]
    hit.sort(key=lambda c: 0 if c.casefold().startswith(kws[0]) else 1)
    return hit[:limit]
