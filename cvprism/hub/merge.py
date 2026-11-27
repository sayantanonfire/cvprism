"""Hub merge (SYNC.md): union all inboxes by content-hash ID into cards.jsonl, quarantine the rest."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..novelty.filter import Knowledge, decide
from ..novelty.ids import card_id
from ..schemas import errors
from ..sync.adapters.base import atomic_write, complete_lines, line_id, union_lines


@dataclass
class MergeReport:
    new_cards: int = 0
    quarantined: int = 0
    purged: int = 0
    rev: int | None = None
    pulled_from: tuple = ()


def _read_ids(p: Path) -> set[str]:
    return set(p.read_text(encoding="utf-8").split()) if p.is_file() else set()


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def vault_of(cfg: dict) -> Path:
    return Path(cfg["vault_path"])


def read_cards(vault: Path) -> list[dict]:
    f = vault / "cards.jsonl"
    return [json.loads(ln) for ln in complete_lines(f.read_bytes())] if f.is_file() else []


def collect_from(adapter, vault: Path, purged: set[str]) -> int:
    """Copy (union) every inbox file of a transport into the hub vault's inbox."""
    n = 0
    for dev, f in adapter.inbox_files():
        dest = vault / "inbox" / dev / f.name
        if f.name == "purged.txt":
            have = _read_ids(dest)
            new = _read_ids(f)
            if not new <= have:
                atomic_write(dest, "".join(i + "\n" for i in sorted(have | new)))
            continue
        if dest.resolve() == f.resolve():
            continue
        have = complete_lines(dest.read_bytes()) if dest.is_file() else []
        merged = union_lines(have, complete_lines(f.read_bytes()), purged)
        if merged != have:
            atomic_write(dest, "".join(ln + "\n" for ln in merged))
            n += 1
    return n


def _validate(line: str, dev: str) -> tuple[dict | None, str | None]:
    try:
        c = json.loads(line)
    except json.JSONDecodeError:
        return None, "not json"
    if not isinstance(c, dict):
        return None, "not an object"
    errs = errors("card", c)
    if errs:
        return None, "schema: " + "; ".join(errs[:3])
    if card_id(c) != c["id"]:
        return None, "id does not match content"
    if c["dev"] != dev:
        return None, f"card from {c['dev']} found in inbox of {dev}"
    return c, None


def merge(cfg: dict, adapters: list | None = None, *, rebuild: bool = False) -> MergeReport:
    vault = vault_of(cfg)
    rep = MergeReport()
    inbox = vault / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    purged = _read_ids(vault / "purged.txt")
    for adapter in adapters or []:
        collect_from(adapter, vault, purged)
    for pf in inbox.glob("*/purged.txt"):
        purged |= _read_ids(pf)
    if purged - _read_ids(vault / "purged.txt"):
        atomic_write(vault / "purged.txt", "".join(i + "\n" for i in sorted(purged)))
    suppressed = _read_ids(vault / "suppressed.txt")
    hidden = purged | suppressed

    # purge: physically remove from hub copies (SECURITY_PRIVACY.md)
    for f in inbox.glob("*/*.jsonl"):
        lines = complete_lines(f.read_bytes())
        kept = [ln for ln in lines if line_id(ln) not in purged]
        if kept != lines:
            atomic_write(f, "".join(ln + "\n" for ln in kept))

    existing = [] if rebuild else read_cards(vault)
    kept_existing = [c for c in existing if c["id"] not in hidden]
    rewrite = len(kept_existing) != len(existing) or rebuild
    rep.purged = len(existing) - len(kept_existing)
    known_ids = {c["id"] for c in kept_existing}

    quarantine_dir = vault / "quarantine"
    candidates: dict[str, dict] = {}
    for dev_dir in sorted(p for p in inbox.iterdir() if p.is_dir()):
        qfile = quarantine_dir / f"{dev_dir.name}.jsonl"
        qseen = {json.loads(ln)["raw"] for ln in complete_lines(qfile.read_bytes())} if qfile.is_file() else set()
        qnew = []
        for f in sorted(dev_dir.glob("*.jsonl")):
            for ln in complete_lines(f.read_bytes()):
                c, why = _validate(ln, dev_dir.name)
                if c is None:
                    if ln not in qseen:
                        qseen.add(ln)
                        qnew.append(json.dumps({"raw": ln, "reason": why, "file": f.name}, ensure_ascii=False))
                        rep.quarantined += 1
                    continue
                if c["id"] in hidden or c["id"] in known_ids or c["id"] in candidates:
                    continue
                candidates[c["id"]] = c
        if qnew:
            quarantine_dir.mkdir(exist_ok=True)
            with qfile.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write("".join(q + "\n" for q in qnew))

    known = Knowledge().add_cards(kept_existing)
    new = []
    for c in sorted(candidates.values(), key=lambda c: (c["t"], c["id"])):
        if decide(c, known) is None:
            c = dict(c, x_late=True)  # valid evidence, but not novel at the hub (ADR-011)
        known.add_card(c)
        new.append(c)
    rep.new_cards = len(new)

    cards_file = vault / "cards.jsonl"
    if not cards_file.exists():
        cards_file.touch()
    if rewrite:
        all_cards = kept_existing + new
        atomic_write(cards_file, "".join(json.dumps(c, ensure_ascii=False, separators=(",", ":")) + "\n"
                                         for c in sorted(all_cards, key=lambda c: (c["t"], c["id"]))))
    elif new:
        with cards_file.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(json.dumps(c, ensure_ascii=False, separators=(",", ":")) + "\n" for c in new))

    reg_file = vault / "registry.json"
    reg = json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.is_file() else {"rev": 0}
    if new or rewrite or reg.get("rev", 0) == 0:
        from .registry import build_registry

        hub = json.loads((vault / "hub.json").read_text(encoding="utf-8"))
        rev = int(reg.get("rev", 0)) + 1 if int(reg.get("epoch", hub["epoch"])) == int(hub["epoch"]) else 1
        new_reg = build_registry(read_cards(vault), vault_id=cfg["vault_id"], epoch=hub["epoch"], rev=rev,
                                 generated=_now())
        atomic_write(reg_file, json.dumps(new_reg, indent=1, ensure_ascii=False) + "\n")
        rep.rev = rev
    else:
        rep.rev = reg.get("rev")
    return rep
