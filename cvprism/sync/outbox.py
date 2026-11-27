"""Append-only per-device outbox (ADR-004): outbox/<device-id>/YYYY-MM.jsonl."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield complete lines only; an unterminated final line is a partial write (SYNC.md F2)."""
    data = Path(path).read_bytes()
    for line in data.split(b"\n")[:-1]:
        line = line.strip()
        if line:
            yield json.loads(line)


class Outbox:
    def __init__(self, root: Path, device_id: str):
        self.dir = Path(root) / device_id
        self.device_id = device_id

    def _file_for(self, t: str) -> Path:
        return self.dir / f"{t[:7]}.jsonl"

    def append(self, card: dict) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._file_for(card["t"])
        line = (json.dumps(card, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        # Ensure any partial tail from a crash cannot glue onto our line.
        if path.exists() and path.stat().st_size:
            with path.open("rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    line = b"\n" + line
        with path.open("ab") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        return path

    def files(self) -> list[Path]:
        return sorted(self.dir.glob("*.jsonl")) if self.dir.is_dir() else []

    def iter_cards(self) -> Iterator[dict]:
        for f in self.files():
            yield from iter_jsonl(f)
