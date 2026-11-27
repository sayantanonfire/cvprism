"""Drains the capture queue: reduce -> extract (claude -p) -> redact -> novelty -> outbox (ADR-007)."""
from __future__ import annotations

import fnmatch
import hashlib
from collections import defaultdict
from pathlib import Path, PurePath

from .. import llm, paths
from ..novelty.ids import slugify
from .manual import load_knowledge, load_redactor
from .pipeline import build_and_emit
from .prompts import EXTRACT_PROMPT, EXTRACT_SCHEMA
from .queue import Queue
from .reduce import Digest, reduce_commits, reduce_transcript, reduce_watch

SRC = {"claude_session": "claude_session", "git_commit": "git_commit", "watcher": "watcher"}


def _enabled(cfg: dict, source: str) -> bool:
    cap = cfg.get("capture") or {}
    return bool((cap.get(source) or {}).get("enabled", False))


def _human_text(d: Digest) -> str:
    """Only the human-authored parts ground metrics, never counts the reducer computed."""
    return " ".join(d.prompts) + " " + d.final_summary


def _extract(d: Digest, cfg: dict, known) -> list[dict]:
    ext = cfg.get("extraction") or {}
    budget = int(ext.get("max_input_tokens", 6000)) * 4
    prompt = EXTRACT_PROMPT.format(known=", ".join(sorted(known.skills)[:300]) or "(none yet)",
                                   digest=d.render(budget))
    res = llm.run_json(prompt, EXTRACT_SCHEMA, model=ext.get("model"), timeout=int(ext.get("timeout_s", 120)))
    cards = res.get("cards", [])
    return cards if isinstance(cards, list) else []


def _log(msg: str) -> None:
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    with (paths.logs_dir() / "worker.log").open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def run_once(cfg: dict, queue: Queue | None = None) -> dict:
    q = queue or Queue(paths.queue_dir())
    stats = {"done": 0, "cards": 0, "retry": 0, "dropped": 0}
    jobs = q.due()
    if not jobs:
        return stats
    redactor = load_redactor(cfg)
    known = load_knowledge(cfg["device_id"])
    exclude_repos = ((cfg.get("capture") or {}).get("git") or {}).get("exclude_repos") or []

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for j in jobs:
        kind, p = j["kind"], j.get("payload") or {}
        source = kind if kind != "git_commit" else "git"
        if not _enabled(cfg, source):
            q.done(j)
            stats["dropped"] += 1
            continue
        if kind == "claude_session":
            if redactor.is_excluded_path(p.get("cwd")):
                q.done(j)
                stats["dropped"] += 1
                continue
            groups[("claude_session", j["key"])].append(j)
        elif kind == "git_commit":
            repo = str(p.get("repo", ""))
            if redactor.is_excluded_path(repo) or any(fnmatch.fnmatch(Path(repo).as_posix(), g) for g in exclude_repos):
                q.done(j)
                stats["dropped"] += 1
                continue
            groups[("git_commit", repo)].append(j)
        elif kind == "watcher":
            groups[("watcher", "all")].append(j)
        else:
            q.dead(j, f"unknown job kind {kind}")

    for (kind, gkey), gjobs in groups.items():
        try:
            if kind == "claude_session":
                p = gjobs[0]["payload"]
                digest = reduce_transcript(Path(p["transcript_path"]), redactor)
                ref = "cc:" + hashlib.sha256(str(p.get("session_id") or p["transcript_path"]).encode()).hexdigest()[:8]
            elif kind == "git_commit":
                shas = [j["payload"]["sha"] for j in gjobs]
                digest = reduce_commits(gkey, shas, redactor)
                ref = f"git:{slugify(PurePath(gkey).name) or 'repo'}@{shas[-1][:7]}"
            else:
                digest = reduce_watch([j["payload"] for j in gjobs], redactor)
                ref = "watch:" + hashlib.sha256(gkey.encode()).hexdigest()[:8]
        except FileNotFoundError:
            for j in gjobs:
                q.done(j)
            stats["dropped"] += len(gjobs)
            _log(f"dropped {kind}: source no longer exists")
            continue
        try:
            candidates = _extract(digest, cfg, known)
        except llm.LLMUnavailable as e:
            for j in gjobs:
                q.retry_later(j, str(e))
            stats["retry"] += len(gjobs)
            continue
        source_text = _human_text(digest)
        for cand in candidates:
            oc = build_and_emit(cand, cfg=cfg, known=known, src=SRC[kind], source_text=source_text,
                                redactor=redactor, ref=ref)
            if oc.card:
                stats["cards"] += 1
            elif oc.dropped:
                _log(f"candidate dropped ({kind}): {oc.dropped}")
        for j in gjobs:
            q.done(j)
        stats["done"] += len(gjobs)
    return stats
