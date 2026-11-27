"""Manual capture: `cvprism log` and the /cv-log skill (M1)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .. import llm, paths
from ..novelty.filter import Knowledge
from ..novelty.ids import slugify
from ..sync.outbox import Outbox
from .pipeline import build_and_emit, numbers_in  # noqa: F401  (numbers_in re-exported for callers)
from .prompts import MANUAL_PROMPT, MANUAL_SCHEMA
from .redact import Redactor


class LogError(ValueError):
    pass


@dataclass
class LogResult:
    card: dict | None
    messages: list[str] = field(default_factory=list)


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


def load_knowledge(device_id: str) -> Knowledge:
    reg = None
    rc = paths.registry_cache()
    if rc.is_file():
        reg = json.loads(rc.read_text(encoding="utf-8"))
    return Knowledge.from_registry(reg).add_cards(Outbox(paths.outbox_dir(), device_id).iter_cards())


def load_redactor(cfg: dict) -> Redactor:
    return Redactor.load(paths.home() / "redact.yaml",
                         extra_exclude=(cfg.get("privacy") or {}).get("exclude_paths") or [])


def _llm_fields(text: str, known: Knowledge, cfg: dict, hints: list[str]) -> dict:
    prompt = MANUAL_PROMPT.format(
        known=", ".join(sorted(known.skills)[:300]) or "(none yet)",
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
        fields = {"txt": text, "s": skills, "d": depth or 2, "conf": 1.0}
    else:
        fields = dict(fields)
        fields["s"] = list(fields.get("s") or []) + skills
        if depth:
            fields["d"] = depth
        if not [x for x in fields["s"] if slugify(str(x))]:
            raise LogError("Could not identify a skill; pass --skill.")
    # manual entries are the user's own words: deny-list scrubbing applies, but never drop silently
    oc = build_and_emit(fields, cfg=cfg, known=known, src="manual", source_text=text, redactor=load_redactor(cfg),
                        r=r, flags=flags, ctx=ctx, work=work, now=now)
    if oc.dropped:
        raise LogError(f"Card not saved: {oc.dropped}")
    out.messages += oc.messages
    out.card = oc.card
    if oc.card and "needs_metric" in oc.card["flags"]:
        out.messages.append("Flagged needs_metric: add the number later with `cvprism review` if you have one.")
    return out
