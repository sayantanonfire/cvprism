"""Canonical card identity (ADR-002).

The ID hashes only structured fields so the same achievement captured on two
devices, in different words, gets the same ID.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

_SLUG_SUBS = [("c++", "c-plus-plus"), ("c#", "c-sharp"), ("f#", "f-sharp"), ("+", " plus ")]
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = text.strip().lower()
    for a, b in _SLUG_SUBS:
        s = s.replace(a, b)
    return _NON_ALNUM.sub("-", s).strip("-")


def normnum(val: Any) -> str:
    """Render a number canonically: no trailing zeros, no exponent."""
    try:
        d = Decimal(str(val)).normalize()
    except InvalidOperation as e:
        raise ValueError(f"not a number: {val!r}") from e
    if d == 0:
        return "0"
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _norm_result(r: dict | None) -> dict | None:
    if r is None:
        return None
    return {
        "m": slugify(r["m"]),
        "val": normnum(r["val"]),
        "unit": str(r.get("unit", "")).strip().lower(),
        "dir": r["dir"],
    }


def canonical(card: dict) -> str:
    obj = {
        "k": card["k"],
        "s": sorted(set(card["s"])),
        "d": int(card["d"]),
        "r": _norm_result(card.get("r")),
        "ctx": card.get("ctx"),
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def card_id(card: dict) -> str:
    return "c_" + hashlib.sha256(canonical(card).encode("utf-8")).hexdigest()[:16]


def result_fp(r: dict) -> str:
    n = _norm_result(r)
    raw = f"{n['m']}|{n['val']}|{n['unit']}|{n['dir']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def kind_for(*, work: bool, r: dict | None, flags: Iterable[str]) -> str:
    """Kind is a pure function of content (ADR-002): work > result > skill."""
    if work:
        return "work"
    if r is not None or "needs_metric" in set(flags):
        return "result"
    return "skill"
