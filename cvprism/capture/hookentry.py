"""`cvprism-hook`: the tiny process Claude Code and git call. It only enqueues (ADR-007).

Rules: stdlib + cvprism.paths only, never raise, always exit 0, never block the caller.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from .. import paths
from .queue import Queue


def _claude_session_end() -> None:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    tp = data.get("transcript_path")
    if not tp:
        return
    Queue(paths.queue_dir()).enqueue(
        "claude_session",
        key=str(tp),
        payload={"transcript_path": str(tp), "session_id": data.get("session_id"), "cwd": data.get("cwd"),
                 "reason": data.get("reason")},
    )


def _git_post_commit() -> None:
    out = subprocess.run(["git", "rev-parse", "HEAD", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    lines = out.stdout.split()
    if out.returncode != 0 or len(lines) < 2:
        return
    sha, repo = lines[0], lines[1]
    Queue(paths.queue_dir()).enqueue("git_commit", key=f"{repo}@{sha}", payload={"repo": repo, "sha": sha})


HANDLERS = {"claude-session-end": _claude_session_end, "git-post-commit": _git_post_commit}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if os.environ.get("CVPRISM_EXTRACTING"):
        return 0  # never capture the extractor's own sessions (ARCHITECTURE F9)
    try:
        handler = HANDLERS.get(argv[0] if argv else "")
        if handler:
            handler()
    except Exception as e:  # noqa: BLE001 - a hook must never break the caller
        try:
            paths.logs_dir().mkdir(parents=True, exist_ok=True)
            with (paths.logs_dir() / "hook-errors.log").open("a", encoding="utf-8") as f:
                f.write(f"{argv}: {type(e).__name__}: {e}\n")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
