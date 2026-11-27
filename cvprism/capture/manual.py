"""Manual capture: `cvprism log` and the /cv-log skill (M1)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .. import llm, paths
from ..novelty.counters import Counters
from ..novelty.filter import Knowledge, decide
from ..novelty.ids import card_id, kind_for, normnum, slugify
from ..schemas import validate
from ..sync.outbox import Outbox
from .prompts import MANUAL_PROMPT, MANUAL_SCHEMA


class LogError(ValueError):
    pass


@dataclass
class LogResult:
    card: dict | None
    messages: list[str] = field(default_factory=list)


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_result(spec: str) -> dict:
    """'metric:value:unit[:dir]' -> result object. Negative values default to dir=down."""
    parts = spec.split(":")
    if len(parts) not in (3, 4):
        raise LogError("--result must look like 'metric:value:unit' or 'metric:value:unit:dir' (dir = up|down|abs)")
    m, val, unit = parts[0].strip(), parts[1].strip(), parts[2].strip()
    try:
        num = float(val)
    except ValueError as e:
        raise LogError(f"--result value {val!r} is not a number") from e
    num = int(num) if num.is_integer() else num
    direction = parts[3].strip() if len(parts) == 4 else ("down" if num < 0 else "abs")
    if direction not in ("up", "down", "abs"):
        raise LogError("--result dir must be up, down or abs")
    if not m:
        raise LogError("--result needs a metric name")
    return {"m": m, "val": num, "unit": unit, "dir": direction}


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(text: str) -> set[str]:
    return {normnum(n.replace(",", "")) for n in _NUM.findall(text)}


def metric_is_grounded(r: dict, source: str) -> bool:
    """A metric is allowed only if its value literally appears in what the user wrote (honesty rule)."""
    return normnum(abs(float(r["val"]))) in numbers_in(source)


def load_knowledge(device_id: str) -> Knowledge:
    reg = None
    rc = paths.registry_cache()
    if rc.is_file():
        reg = json.loads(rc.read_text(encoding="utf-8"))
    return Knowledge.from_registry(reg).add_cards(Outbox(paths.outbox_dir(), device_id).iter_cards())


def _normalise_skills(names: list[str], known: Knowledge) -> list[str]:
    out = sorted({known.resolve_alias(n) for n in names if slugify(n)})
    return out[:5]


def _llm_fields(text: str, known: Knowledge, cfg: dict, hints: list[str]) -> dict:
    vocab = sorted(known.skills)[:300]
    prompt = MANUAL_PROMPT.format(
        known=", ".join(vocab) or "(none yet)",
        hints=", ".join(hints) or "(none)",
        entry=text,
    )
    ext = cfg.get("extraction", {})
    return llm.run_json(prompt, MANUAL_SCHEMA, model=ext.get("model"), timeout=int(ext.get("timeout_s", 120)))


def log_entry(
    text: str,
    *,
    cfg: dict,
    skills: list[str] | None = None,
    depth: int | None = None,
    result: str | None = None,
    work: bool = False,
    ctx: str | None = None,
    raw: bool = False,
    now: str | None = None,
) -> LogResult:
    out = LogResult(card=None)
    if os.environ.get("CVPRISM_EXTRACTING"):
        out.messages.append("cvprism: skipped (running inside an extraction session)")
        return out

    text = " ".join(text.split())
    if len(text) < 8:
        raise LogError("Entry is too short; describe what you did in a sentence.")
    skills = skills or []
    known = load_knowledge(cfg["device_id"])
    r = parse_result(result) if result else None
    flags: list[str] = []
    fields: dict = {}

    if not raw:
        try:
            fields = _llm_fields(text, known, cfg, skills)
        except llm.LLMUnavailable as e:
            out.messages.append(f"warning: Claude unavailable ({e}); falling back to --raw")
            raw = True

    if raw:
        if not skills:
            raise LogError("Raw mode needs at least one --skill (e.g. --skill python).")
        flags.append("manual_raw")
        s = _normalise_skills(skills, known)
        d = depth or 2
        txt, meth, tl, dom, conf = text, [], [], [], 1.0
    else:
        s = _normalise_skills(list(fields.get("s") or []) + skills, known)
        if not s:
            raise LogError("Could not identify a skill; pass --skill.")
        d = depth or int(fields.get("d") or 2)
        txt = str(fields.get("txt") or text)
        meth = [str(x)[:80] for x in (fields.get("meth") or [])][:8]
        tl = [t for t in (slugify(x) for x in (fields.get("tl") or [])) if t][:12]
        dom = [t for t in (slugify(x) for x in (fields.get("dom") or [])) if t][:6]
        conf = float(fields.get("conf") or 0.7)
        work = work or bool(fields.get("work"))
        if r is None and fields.get("r"):
            cand = fields["r"]
            if metric_is_grounded(cand, text):
                r = {"m": str(cand["m"]), "val": cand["val"], "unit": str(cand.get("unit", "")),
                     "dir": cand.get("dir", "abs")}
                base = cand.get("base")
                if base is not None and normnum(abs(float(base))) in numbers_in(text):
                    r["base"] = base
            else:
                flags.append("needs_metric")
                out.messages.append("note: the model proposed a metric you did not state; it was dropped (honesty rule)")
        if r is None and fields.get("needs_metric") and "needs_metric" not in flags:
            flags.append("needs_metric")

    if len(txt) > 220:
        txt = txt[:217].rstrip() + "..."
    card = {
        "v": 1,
        "k": kind_for(work=work, r=r, flags=flags),
        "s": s,
        "d": max(1, min(5, d)),
        "r": r,
        "ctx": slugify(ctx) if ctx else None,
        "txt": txt,
        "meth": meth,
        "tl": tl,
        "dom": dom,
        "t": now or utcnow(),
        "dev": cfg["device_id"],
        "src": "manual",
        "conf": conf,
        "flags": flags,
        "lang": "en",
    }
    card["id"] = card_id(card)
    why = decide(card, known)
    if why is None:
        Counters(paths.counters_file()).bump(card["s"], card["t"])
        out.messages.append(f"Already known: {', '.join(card['s'])} (usage counter updated, no new card)")
        return out
    card["why"] = why
    card = {k: card[k] for k in ("v", "id", "k", "why", "s", "d", "r", "ctx", "txt", "meth", "tl", "dom",
                                 "t", "dev", "src", "conf", "flags", "lang")}
    validate("card", card)
    Outbox(paths.outbox_dir(), cfg["device_id"]).append(card)
    out.card = card
    out.messages.append(f"New card {card['id']} ({why.replace('_', ' ')}): {card['txt']}")
    if "needs_metric" in flags:
        out.messages.append("Flagged needs_metric: add the number later with `cvprism review` if you have one.")
    return out
