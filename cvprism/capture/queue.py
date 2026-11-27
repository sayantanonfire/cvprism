"""Durable file-based job queue (ADR-007). Stdlib only: imported by the hook entry point."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class Queue:
    def __init__(self, root: Path, ttl_days: int = 30):
        self.root = Path(root)
        self.ttl = timedelta(days=ttl_days)

    def _path(self, kind: str, key: str) -> Path:
        h = hashlib.sha256(f"{kind}\0{key}".encode("utf-8")).hexdigest()[:20]
        return self.root / f"{kind}-{h}.json"

    def enqueue(self, kind: str, *, key: str, payload: dict, created: str | None = None) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(kind, key)
        if path.exists():
            return path  # idempotent per key (ARCHITECTURE F9)
        job = {"kind": kind, "key": key, "payload": payload, "created": created or utcnow(),
               "attempts": 0, "last_error": None, "next_try": None}
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return path

    def pending(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        now = datetime.now(timezone.utc)
        jobs = []
        for p in sorted(self.root.glob("*.json")):
            try:
                job = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            job["_path"] = str(p)
            if now - _parse(job["created"]) > self.ttl:
                self.dead(job, "expired")
                continue
            jobs.append(job)
        return sorted(jobs, key=lambda j: j["created"])

    def due(self) -> list[dict]:
        now = utcnow()
        return [j for j in self.pending() if not j.get("next_try") or j["next_try"] <= now]

    def _save(self, job: dict) -> None:
        path = Path(job["_path"])
        data = {k: v for k, v in job.items() if k != "_path"}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def retry_later(self, job: dict, error: str) -> None:
        job["attempts"] = int(job.get("attempts", 0)) + 1
        job["last_error"] = error[:300]
        backoff = min(3600 * 6, 60 * 2 ** job["attempts"])
        job["next_try"] = (datetime.now(timezone.utc) + timedelta(seconds=backoff)).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        self._save(job)

    def done(self, job: dict) -> None:
        Path(job["_path"]).unlink(missing_ok=True)

    def dead(self, job: dict, reason: str) -> None:
        dead = self.root / "dead"
        dead.mkdir(parents=True, exist_ok=True)
        job = dict(job, last_error=reason)
        src = Path(job.pop("_path"))
        (dead / src.name).write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        src.unlink(missing_ok=True)

    def wait_for(self, n: int, timeout: float = 10.0) -> list[dict]:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            jobs = self.pending()
            if len(jobs) >= n:
                return jobs
            time.sleep(0.1)
        return self.pending()
