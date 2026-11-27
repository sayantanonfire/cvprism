"""Headless Claude Code backend (ADR-007).

All LLM calls go through `run_json`. The command can be overridden with
CVPRISM_CLAUDE_CMD (used by tests and by users with a non-standard install).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from typing import Any


class LLMUnavailable(RuntimeError):
    """claude CLI missing, not logged in, timed out, or returned unusable output."""


def claude_command() -> list[str] | None:
    env = os.environ.get("CVPRISM_CLAUDE_CMD")
    if env:
        parts = shlex.split(env, posix=(os.name != "nt"))
        parts = [p.strip('"') for p in parts]
        exe = shutil.which(parts[0]) or (parts[0] if os.path.isfile(parts[0]) else None)
        return [exe, *parts[1:]] if exe else None
    exe = shutil.which("claude")
    return [exe] if exe else None


def claude_version() -> str | None:
    cmd = claude_command()
    if not cmd:
        return None
    try:
        out = subprocess.run([*cmd, "--version"], capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


_JSON_OBJ = re.compile(r"\{.*\}", re.S)


def _extract(stdout: str) -> dict:
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"claude returned non-JSON output: {stdout[:200]!r}") from e
    if env.get("is_error"):
        raise LLMUnavailable(f"claude reported an error: {str(env.get('result'))[:200]}")
    if isinstance(env.get("structured_output"), dict):
        return env["structured_output"]
    result = env.get("result")
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        m = _JSON_OBJ.search(result)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMUnavailable("claude output did not contain a JSON object")


def run_json(prompt: str, schema: dict, *, model: str | None = None, timeout: int = 120) -> dict[str, Any]:
    cmd = claude_command()
    if not cmd:
        raise LLMUnavailable("claude CLI not found on PATH")
    args = [
        *cmd, "-p",
        "--output-format", "json",
        "--tools", "",
        "--no-session-persistence",
        "--json-schema", json.dumps(schema, separators=(",", ":")),
    ]
    if model:
        args += ["--model", model]
    env = {**os.environ, "CVPRISM_EXTRACTING": "1"}  # recursion guard (ARCHITECTURE F9)
    try:
        proc = subprocess.run(
            args, input=prompt, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise LLMUnavailable(str(e)) from e
    if proc.returncode != 0:
        raise LLMUnavailable(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[:200]}")
    return _extract(proc.stdout)
