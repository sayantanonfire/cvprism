"""Filter and score cards in code so the LLM only sees a bounded, relevant subset (ARCHITECTURE: compile)."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..novelty.ids import slugify

RESEARCH_DOMS = {"academic", "research"}


def _years_ago(t: str, now: datetime) -> float:
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return 10.0
    return max(0.0, (now - dt).days / 365.25)


def eligible(card: dict, role: dict) -> bool:
    inc, exc = role.get("include") or {}, role.get("exclude") or {}
    doms, skills = set(card.get("dom") or []), set(card["s"])
    if exc.get("ctx") and card.get("ctx") in exc["ctx"]:
        return False
    if exc.get("dom") and doms & set(exc["dom"]):
        return False
    if exc.get("skills") and skills & set(exc["skills"]):
        return False
    if card.get("k") != "work" and int(card["d"]) < int(inc.get("min_depth", 2)):
        return False
    if inc.get("since") and card["t"][: len(str(inc["since"]))] < str(inc["since"]):
        return False
    want_dom, want_sk = set(inc.get("dom") or []), set(inc.get("skills_any") or [])
    if want_dom or want_sk:
        return bool(doms & want_dom) or bool(skills & want_sk)
    return True


def vocab_terms(role: dict) -> set[str]:
    return {slugify(v) for v in role.get("vocabulary") or [] if slugify(v)}


def score(card: dict, role: dict, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    w = {"depth": 0.8, "recency": 0.6, "results": 0.8, "delivery": 0.6, "research": 0.4, **(role.get("weights") or {})}
    depth = int(card["d"]) / 5
    recency = math.exp(-_years_ago(card["t"], now) / 3)
    results = 1.0 if card.get("r") else (0.3 if "needs_metric" in (card.get("flags") or []) else 0.0)
    delivery = 1.0 if card.get("k") != "work" and int(card["d"]) >= 3 else 0.4
    research = 1.0 if card.get("k") == "work" or set(card.get("dom") or []) & RESEARCH_DOMS else 0.0
    s = (w["depth"] * depth + w["recency"] * recency + w["results"] * results
         + w["delivery"] * delivery + w["research"] * research)
    terms = vocab_terms(role)
    if terms:
        hay = set(card["s"]) | {slugify(t) for t in card.get("tl") or []} | {slugify(card.get("txt", ""))}
        hits = sum(1 for t in terms if t in hay or any(t in h for h in hay))
        s += 0.5 * hits / len(terms) * 4
    if card.get("x_late"):
        s -= 0.2
    return s


def select_cards(cards: list[dict], role: dict, suppressed: set[str] = frozenset(),
                 now: datetime | None = None) -> list[dict]:
    pool = [c for c in cards if c["id"] not in suppressed and eligible(c, role)]
    pool.sort(key=lambda c: (-score(c, role, now), c["t"], c["id"]), reverse=False)
    limit = int((role.get("limits") or {}).get("cards_to_llm", 60))
    return pool[:limit]
