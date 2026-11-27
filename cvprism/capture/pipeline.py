"""Candidate fields -> grounded, redacted, validated, novelty-checked card in the outbox."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .. import paths
from ..novelty.counters import Counters
from ..novelty.filter import Knowledge, decide
from ..novelty.ids import card_id, kind_for, normnum, slugify
from ..schemas import errors
from ..sync.outbox import Outbox
from .redact import Redactor

ORDER = ("v", "id", "k", "why", "s", "d", "r", "ctx", "txt", "meth", "tl", "dom",
         "t", "dev", "src", "ref", "conf", "flags", "lang")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def numbers_in(text: str) -> set[str]:
    return {normnum(n.replace(",", "")) for n in _NUM.findall(text)}


def grounded(value, source: str) -> bool:
    """Honesty rule: a number is allowed only if it literally appears in the source text."""
    try:
        return normnum(abs(float(value))) in numbers_in(source)
    except (TypeError, ValueError):
        return False


@dataclass
class Outcome:
    card: dict | None = None
    why: str | None = None
    messages: list[str] = field(default_factory=list)
    dropped: str | None = None


def ground_result(cand: dict | None, source: str, flags: list[str], msgs: list[str]) -> dict | None:
    if not cand:
        return None
    if not grounded(cand.get("val"), source):
        if "needs_metric" not in flags:
            flags.append("needs_metric")
        msgs.append("note: a metric not stated in the source was dropped (honesty rule)")
        return None
    r = {"m": str(cand["m"])[:60], "val": cand["val"], "unit": str(cand.get("unit", ""))[:20],
         "dir": cand.get("dir") if cand.get("dir") in ("up", "down", "abs") else "abs"}
    if cand.get("base") is not None and grounded(cand["base"], source):
        r["base"] = cand["base"]
    return r


def normalise_skills(names, known: Knowledge) -> list[str]:
    return sorted({known.resolve_alias(str(n)) for n in names if slugify(str(n))})[:5]


def build_and_emit(
    fields: dict,
    *,
    cfg: dict,
    known: Knowledge,
    src: str,
    source_text: str,
    redactor: Redactor | None = None,
    ref: str | None = None,
    r: dict | None = None,
    flags: list[str] | None = None,
    ctx: str | None = None,
    work: bool = False,
    now: str | None = None,
) -> Outcome:
    """fields: txt, s, d, meth, tl, dom, r, needs_metric, work, conf (LLM-shaped)."""
    out = Outcome()
    flags = list(flags or [])
    s = normalise_skills(fields.get("s") or [], known)
    if not s:
        out.dropped = "no skill identified"
        return out
    if r is None:
        r = ground_result(fields.get("r"), source_text, flags, out.messages)
    if r is None and fields.get("needs_metric") and "needs_metric" not in flags:
        flags.append("needs_metric")
    conf = float(fields.get("conf") if fields.get("conf") is not None else 0.7)
    if conf < 0.5 and "low_confidence" not in flags:
        flags.append("low_confidence")
    txt = " ".join(str(fields.get("txt") or "").split())
    if len(txt) > 220:
        txt = txt[:217].rstrip() + "..."
    card = {
        "v": 1,
        "k": kind_for(work=work or bool(fields.get("work")), r=r, flags=flags),
        "s": s,
        "d": max(1, min(5, int(fields.get("d") or 2))),
        "r": r,
        "ctx": slugify(ctx) if ctx else None,
        "txt": txt,
        "meth": [str(x)[:80] for x in (fields.get("meth") or [])][:8],
        "tl": [t for t in (slugify(str(x)) for x in (fields.get("tl") or [])) if t][:12],
        "dom": [t for t in (slugify(str(x)) for x in (fields.get("dom") or [])) if t][:6],
        "t": now or utcnow(),
        "dev": cfg["device_id"],
        "src": src,
        "conf": max(0.0, min(1.0, conf)),
        "flags": sorted(set(flags)),
        "lang": "en",
    }
    if ref:
        card["ref"] = ref[:120]
    if redactor is not None:
        red = redactor.apply_card(card)
        if red is None:
            out.dropped = "redactor dropped the card (secret or plugin veto)"
            return out
        card = red
    card["id"] = card_id(card)
    why = decide(card, known)
    if why is None:
        Counters(paths.counters_file()).bump(card["s"], card["t"])
        out.messages.append(f"Already known: {', '.join(card['s'])} (usage counter updated, no new card)")
        return out
    card["why"] = why
    card = {k: card[k] for k in ORDER if k in card}
    errs = errors("card", card)
    if errs:
        out.dropped = "schema: " + "; ".join(errs)
        return out
    Outbox(paths.outbox_dir(), cfg["device_id"]).append(card)
    known.add_card(card)
    out.card, out.why = card, why
    out.messages.append(f"New card {card['id']} ({why.replace('_', ' ')}): {card['txt']}")
    return out
