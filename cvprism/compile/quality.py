"""Code-enforced writing quality (ADR-016): no repeated openers, no near-duplicate lines, flagged weak phrasing.

Only meaning-preserving edits are made automatically (swapping an opening verb for a vetted synonym,
merging two lines that say the same thing). Everything else is reported, never rewritten silently.
"""
from __future__ import annotations

import re

VERB_GROUPS = [
    ["built", "developed", "engineered", "implemented", "created", "constructed"],
    ["designed", "architected", "devised"],
    ["led", "directed", "headed", "coordinated"],
    ["improved", "enhanced", "strengthened"],
    ["cut", "reduced", "lowered", "decreased"],
    ["increased", "raised", "boosted"],
    ["analysed", "analyzed", "examined", "evaluated", "assessed"],
    ["automated", "streamlined"],
    ["wrote", "authored", "drafted"],
    ["presented", "delivered"],
    ["deployed", "launched", "shipped", "released"],
    ["integrated", "connected"],
    ["ran", "conducted", "performed"],
    ["managed", "oversaw", "supervised"],
    ["processed", "prepared"],
    ["mapped", "charted"],
]
_GROUP_OF = {v: g for g in VERB_GROUPS for v in g}
LEVEL_RANK = {"public": 0, "confirmed": 1, "captured": 2, "self-reported": 3, None: 4}

WEAK_OPENERS = re.compile(r"^(responsible for|worked on|helped|assisted|involved in|participated in|tasked with|"
                          r"duties included|in charge of)\b", re.I)
BUZZWORDS = ["passionate", "results-driven", "results driven", "synergy", "go-getter", "team player",
             "hard-working", "hardworking", "detail-oriented", "self-starter", "rockstar", "ninja", "guru",
             "thought leader", "best-in-class", "world-class", "think outside the box", "dynamic"]
_STOP = {"the", "and", "for", "with", "from", "into", "over", "using", "that", "this", "its", "their", "our", "via"}
_PREFIX = re.compile(r"^\*\*[^*]+:\*\*\s*")


def first_verb(text: str) -> str:
    t = _PREFIX.sub("", text or "").strip()
    m = re.match(r"([A-Za-z]+)", t)
    return m.group(1).lower() if m else ""


def _swap_first_verb(text: str, new: str) -> str:
    m = re.match(r"(\*\*[^*]+:\*\*\s*)?([A-Za-z]+)", text)
    if not m:
        return text
    word = m.group(2)
    new = new.capitalize() if word[0].isupper() else new
    return text[: m.start(2)] + new + text[m.end(2):]


def vary_verbs(bullets: list[dict]) -> tuple[list[dict], int]:
    """Second and later uses of an opening verb are swapped for an unused synonym from its group."""
    used: set[str] = set()
    out, changed = [], 0
    for b in bullets:
        v = first_verb(b.get("text", ""))
        if v in used and v in _GROUP_OF:
            alt = next((s for s in _GROUP_OF[v] if s not in used), None)
            if alt:
                b = dict(b, text=_swap_first_verb(b["text"], alt))
                used.add(alt)
                changed += 1
                out.append(b)
                continue
        used.add(v)
        out.append(b)
    return out, changed


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP}


def _skills(b: dict, cards_by_id: dict) -> set[str]:
    return {s for c in b.get("cites") or [] for s in (cards_by_id.get(c) or {}).get("s", [])}


def merge_duplicates(bullets: list[dict], cards_by_id: dict, threshold: float = 0.6) -> tuple[list[dict], int]:
    """Merge lines that share a skill and mostly the same words; keep the one with stronger proof."""
    out: list[dict] = []
    merged = 0
    for b in bullets:
        wb, sb = _words(b.get("text", "")), _skills(b, cards_by_id)
        hit = None
        for i, o in enumerate(out):
            wo = _words(o.get("text", ""))
            if not (wb and wo) or not (sb & _skills(o, cards_by_id)):
                continue
            if len(wb & wo) / len(wb | wo) >= threshold:
                hit = i
                break
        if hit is None:
            out.append(b)
            continue
        o = out[hit]
        keep = min((o, b), key=lambda x: (LEVEL_RANK.get(x.get("level"), 4), -len(x.get("text", ""))))
        cites = list(dict.fromkeys((o.get("cites") or []) + (b.get("cites") or [])))
        links = list(dict.fromkeys((o.get("links") or []) + (b.get("links") or [])))
        out[hit] = dict(keep, cites=cites, links=links, link=keep.get("link") or (links[0] if links else None))
        merged += 1
    return out, merged


def review(bullets: list[dict]) -> list[dict]:
    issues = []
    for i, b in enumerate(bullets):
        t = _PREFIX.sub("", b.get("text", "")).strip()
        low = t.lower()
        if WEAK_OPENERS.match(low):
            issues.append({"index": i, "text": t, "issue": "weak opener",
                           "hint": "start with what you did: Built, Designed, Cut, Led…"})
        hits = [w for w in BUZZWORDS if re.search(r"\b" + re.escape(w) + r"\b", low)]
        if hits:
            issues.append({"index": i, "text": t, "issue": "buzzword",
                           "hint": f"replace '{hits[0]}' with evidence of what you did"})
        if len(t.split()) > 35:
            issues.append({"index": i, "text": t, "issue": "too long", "hint": "keep lines under ~30 words"})
    return issues


def quality_md(varied: int, merged: int, issues: list[dict]) -> str:
    out = ["# Writing quality", "",
           f"- Repeated opening verbs varied: **{varied}**",
           f"- Near-duplicate lines merged: **{merged}**",
           f"- Lines to improve: **{len(issues)}**", ""]
    if issues:
        out += ["| Line | Issue | Suggestion |", "| --- | --- | --- |"]
        out += [f"| {x['text'][:90].replace('|', '/')} | {x['issue']} | {x['hint']} |" for x in issues]
    else:
        out.append("No weak openers, buzzwords or over-long lines found.")
    return "\n".join(out) + "\n"
