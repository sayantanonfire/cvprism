"""One sync tick for any device (SYNC.md: scheduling): epoch check, push, merge (hub), registry back-flow."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import config, paths
from .adapters import make_adapter
from .adapters.base import FolderAdapter, Unavailable, VaultMismatch, atomic_write, complete_lines, line_id
from .outbox import Outbox


@dataclass
class SyncReport:
    lines: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.lines.append(msg)


def adapters_for(cfg: dict, include_disabled: bool = False) -> list[FolderAdapter]:
    out = []
    for spec in cfg.get("adapters", []):
        if spec.get("enabled") or include_disabled:
            out.append(make_adapter(spec, device_id=cfg["device_id"], vault_id=cfg["vault_id"],
                                    state_dir=paths.home() / "state" / "transports"))
    return out


def local_purged() -> set[str]:
    f = paths.home() / "state" / "purged.txt"
    return set(f.read_text(encoding="utf-8").split()) if f.is_file() else set()


def accept_registry(reg: dict) -> bool:
    cache = paths.registry_cache()
    if cache.is_file():
        cur = json.loads(cache.read_text(encoding="utf-8"))
        if (int(reg["epoch"]), int(reg["rev"])) <= (int(cur.get("epoch", 0)), int(cur.get("rev", -1))):
            return False
    atomic_write(cache, json.dumps(reg, ensure_ascii=False) + "\n")
    return True


def _is_own_vault(a: FolderAdapter, cfg: dict) -> bool:
    if cfg.get("role") != "hub" or not cfg.get("vault_path") or a.kind == "git":
        return False
    r = a.root()
    try:
        return r is not None and r.resolve() == Path(cfg["vault_path"]).resolve()
    except OSError:
        return False


def _hub_key(h: dict | None) -> tuple:
    if not h:
        return (0, "")
    return (int(h.get("epoch", 0)), str(h.get("hub_device_id") or ""))


def highest_hub(adapters: list[FolderAdapter]) -> dict | None:
    best = None
    for a in adapters:
        try:
            if not a.available():
                continue
        except (Unavailable, VaultMismatch):
            continue
        h = a.read_json("hub.json")
        if h and _hub_key(h) > _hub_key(best):
            best = h
    return best


def demote(cfg: dict) -> dict:
    cfg = dict(cfg, role="spoke")
    cfg.pop("vault_path", None)
    config.save_device(cfg)
    return cfg


def sync(cfg: dict) -> SyncReport:
    rep = SyncReport()
    adapters = adapters_for(cfg)
    if not adapters:
        rep.add("no adapters configured")
        return rep
    is_hub = cfg.get("role") == "hub"

    if is_hub:
        own = json.loads((Path(cfg["vault_path"]) / "hub.json").read_text(encoding="utf-8"))
        other = highest_hub([a for a in adapters if not _is_own_vault(a, cfg)])
        if other and other.get("hub_device_id") != cfg["device_id"] and _hub_key(other) > _hub_key(own):
            cfg = demote(cfg)
            is_hub = False
            rep.add(f"demoted to spoke: {other['hub_device_id']} is hub at epoch {other['epoch']}")

    ob = Outbox(paths.outbox_dir(), cfg["device_id"])
    purged = local_purged()
    for a in adapters:
        try:
            if is_hub and not _is_own_vault(a, cfg):
                a.init_transport()
            r = a.push(ob, purged)
            rep.add(f"{a.name}: pushed {r.lines} card(s)" if r.files else f"{a.name}: up to date")
        except VaultMismatch as e:
            rep.add(f"{a.name}: REFUSED ({e})")
        except Unavailable as e:
            rep.add(f"{a.name}: unavailable ({e}); cards stay queued in the outbox")

    if is_hub:
        from ..hub.merge import merge

        reachable = []
        for a in adapters:
            try:
                if a.available():
                    reachable.append(a)
            except (Unavailable, VaultMismatch):
                pass
        m = merge(cfg, [a for a in reachable if not _is_own_vault(a, cfg)])
        rep.add(f"hub: merged {m.new_cards} new card(s), quarantined {m.quarantined}, registry rev {m.rev}")
        vault = Path(cfg["vault_path"])
        files = {n: (vault / n).read_text(encoding="utf-8") for n in ("registry.json", "hub.json", "vault.json")}
        for a in reachable:
            if _is_own_vault(a, cfg):
                continue
            try:
                a.publish(files)
            except (Unavailable, VaultMismatch) as e:
                rep.add(f"{a.name}: publish failed ({e})")
        accept_registry(json.loads(files["registry.json"]))
    else:
        best = None
        for a in adapters:
            try:
                if not a.available():
                    continue
                reg = a.pull()
            except (Unavailable, VaultMismatch):
                continue
            if reg and reg.get("vault_id") == cfg["vault_id"] and (
                    best is None or (reg["epoch"], reg["rev"]) > (best["epoch"], best["rev"])):
                best = reg
        if best and accept_registry(best):
            rep.add(f"registry updated to epoch {best['epoch']} rev {best['rev']} ({len(best['skills'])} skills)")
    return rep


def purge_local(cfg: dict, ids: set[str]) -> list[str]:
    """Purge ids from this device's outbox and its inbox copies on every reachable transport."""
    msgs = []
    pf = paths.home() / "state" / "purged.txt"
    pf.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(pf, "".join(i + "\n" for i in sorted(local_purged() | ids)))
    ob = Outbox(paths.outbox_dir(), cfg["device_id"])
    for f in ob.files():
        lines = complete_lines(f.read_bytes())
        kept = [ln for ln in lines if line_id(ln) not in ids]
        if kept != lines:
            atomic_write(f, "".join(ln + "\n" for ln in kept))
            msgs.append(f"outbox: rewrote {f.name}")
    for a in adapters_for(cfg):
        try:
            n = a.purge_own(ids)
            a.push(ob, local_purged())
            msgs.append(f"{a.name}: rewrote {n} file(s)")
            if a.kind == "git":
                msgs.append(f"{a.name}: history still contains the card; to erase it run "
                            "`git filter-repo` on the vault repository yourself (cvprism never force-pushes)")
        except (Unavailable, VaultMismatch) as e:
            msgs.append(f"{a.name}: unavailable ({e}); will be purged on next sync")
    if cfg.get("role") == "hub":
        from ..hub.merge import merge

        vault = Path(cfg["vault_path"])
        have = set((vault / "purged.txt").read_text(encoding="utf-8").split()) if (vault / "purged.txt").is_file() else set()
        atomic_write(vault / "purged.txt", "".join(i + "\n" for i in sorted(have | ids)))
        merge(cfg)
        msgs.append("hub: removed from cards.jsonl and inbox copies")
    return msgs
