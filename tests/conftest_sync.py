"""Helpers for multi-device simulations: each device gets its own CVPRISM_HOME."""
from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def as_device(home: Path):
    old = os.environ.get("CVPRISM_HOME")
    os.environ["CVPRISM_HOME"] = str(home)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("CVPRISM_HOME", None)
        else:
            os.environ["CVPRISM_HOME"] = old


def bare_repo(path: Path) -> str:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return path.as_posix()


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
