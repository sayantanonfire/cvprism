"""Device-local usage counters for skills seen again without a new card (ADR-011)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class Counters:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, dict] = (
            json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}
        )

    def get(self, slug: str) -> dict | None:
        return self.data.get(slug)

    def bump(self, slugs: Iterable[str], when: str) -> None:
        for s in slugs:
            e = self.data.setdefault(s, {"n": 0, "last": when})
            e["n"] += 1
            e["last"] = max(e["last"], when)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        tmp.replace(self.path)
