"""Device-side mapping of folders to project aliases, so captured work is tagged with its project.

Only the alias travels in cards; repository URLs and visibility live on the hub (ADR-015).
"""
from __future__ import annotations

from pathlib import Path


def _norm(p: str) -> str:
    return str(Path(p).expanduser()).replace("\\", "/").rstrip("/").lower()


def ctx_for_path(cfg: dict, path: str | None) -> str | None:
    if not path:
        return None
    target = _norm(path)
    best = None
    for m in cfg.get("projects") or []:
        root = _norm(m["path"])
        if target == root or target.startswith(root + "/"):
            if best is None or len(root) > len(_norm(best["path"])):
                best = m
    return best["ctx"] if best else None
