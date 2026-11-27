"""Deterministic honesty gate (ADR-009): every bullet cites real cards; every number traces to evidence."""
from __future__ import annotations

import re

from ..hub.registry import seed
from ..novelty.ids import slugify

_NUM = re.compile(
    r"(?<![\w.\-/])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"         # 1,200 | 87.5 | 15
    r"(?:\s*(%|×|x|-fold|k|K|M|B|bn|million|billion|thousand))?"  # unit / magnitude
    r"(\+)?(?![\w])"
)
_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20}
_VAGUE = ("dozens", "hundreds", "thousands", "millions", "billions")
_WORD_RX = re.compile(r"(?<![\w-])(" + "|".join(list(_WORDS) + list(_VAGUE)) + r")(?![\w-])", re.I)
_MAG = {"k": 1e3, "K": 1e3, "thousand": 1e3, "M": 1e6, "million": 1e6, "B": 1e9, "bn": 1e9, "billion": 1e9}
_VERSIONED = {"python", "windows", "java", "sentinel", "landsat", "gpt", "claude", "version", "v", "phase", "level",
              "tier", "stage", "step", "ubuntu", "macos", "ios", "android", "dotnet", "net", "php", "web", "industry",
              "l", "llama", "qwen", "gemini", "html", "es", "s"}


def _known_names() -> set[str]:
    names = set(_VERSIONED)
    for slug, meta in seed().items():
        names |= set(slug.split("-"))
        names |= {w.lower() for w in re.findall(r"[A-Za-z]+", meta.get("name", ""))}
    return names


_KNOWN = None


def numbers(text: str) -> list[tuple[str, float | None, int]]:
    """(token, value or None for vague words, position) for every metric-like number in text."""
    global _KNOWN
    if _KNOWN is None:
        _KNOWN = _known_names()
    out = []
    for m in _NUM.finditer(text):
        raw, unit = m.group(1), m.group(2) or ""
        val = float(raw.replace(",", ""))
        if not unit and raw.isdigit() and 1950 <= val <= 2100:
            continue  # a year
        prev = re.findall(r"([A-Za-z]+)\s*$", text[: m.start()])
        if not unit and prev and prev[0].lower() in _KNOWN and val < 100 and raw.isdigit():
            continue  # version-like: "Python 3", "Sentinel 1"
        val *= _MAG.get(unit, 1)
        out.append((m.group(0), val, m.start()))
    for m in _WORD_RX.finditer(text):
        w = m.group(1).lower()
        out.append((m.group(0), float(_WORDS[w]) if w in _WORDS else None, m.start()))
    return out


def _plain_numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", text)]


def allowed_values(cards: list[dict], facts: list[dict]) -> set[float]:
    vals: set[float] = set()
    for c in cards:
        r = c.get("r")
        if r:
            v = float(r["val"])
            vals |= {v, abs(v)}
            b = r.get("base")
            if b not in (None, 0):
                b = float(b)
                vals |= {b, abs(b), abs(v - b), abs(v - b) / abs(b) * 100}
                if v:
                    vals |= {abs(b / v), abs(v / b)}
            if str(r.get("unit", "")).strip() in ("", "ratio") and abs(v) <= 1:
                vals.add(abs(v) * 100)  # 0.91 -> 91%
        vals |= set(_plain_numbers(c.get("txt", "")))
    for f in facts:
        vals |= set(_plain_numbers(f.get("text", "")))
    return vals


def _decimals(tok: str) -> int:
    m = re.search(r"\.(\d+)", tok)
    return len(m.group(1)) if m else 0


def _close(v: float, allowed: set[float], tok: str = "") -> bool:
    """Match within 1% or after rounding the evidence to the token's own precision (87.5 -> "88")."""
    dec = _decimals(tok)
    return any(abs(v - a) <= 0.01 * abs(a) or round(a, dec) == round(v, dec) for a in allowed)


def check_bullet(bullet: dict, cards_by_id: dict[str, dict], facts: list[dict]) -> tuple[bool, list[str]]:
    reasons = []
    cites = [c for c in bullet.get("cites") or [] if isinstance(c, str)]
    if not cites:
        reasons.append("no card cited")
    missing = [c for c in cites if c not in cards_by_id]
    if missing:
        reasons.append(f"cites unknown card(s): {', '.join(missing)}")
    cited = [cards_by_id[c] for c in cites if c in cards_by_id]
    allowed = allowed_values(cited, facts)
    fact_text = " ".join(f.get("text", "") for f in facts).lower()
    for tok, val, _ in numbers(bullet.get("text", "")):
        if val is None:
            if tok.lower() not in fact_text:
                reasons.append(f"vague quantity '{tok}' has no evidence")
        elif not _close(val, allowed, tok):
            reasons.append(f"number '{tok}' not found in cited evidence")
    return (not reasons), reasons


def skill_mentions_ok(text: str, cited: list[dict]) -> bool:
    """Soft check (warning only): bullet mentions at least one cited skill or tool."""
    hay = slugify(text)
    return any(s in hay for c in cited for s in list(c["s"]) + list(c.get("tl") or []))
