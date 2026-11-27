"""Install/uninstall the Claude Code SessionEnd hook and cvprism skills, without clobbering user settings."""
from __future__ import annotations

import json
import os
import shutil
from importlib import resources
from pathlib import Path

from .. import paths

MARKERS = ("cvprism-hook", "cvprism.capture.hookentry")
SKILLS = ("cv-log", "cv-build")


class InstallError(RuntimeError):
    pass


def claude_dir() -> Path:
    for var in ("CVPRISM_CLAUDE_DIR", "CLAUDE_CONFIG_DIR"):
        if os.environ.get(var):
            return Path(os.environ[var]).expanduser()
    return Path.home() / ".claude"


def _settings_path() -> Path:
    return claude_dir() / "settings.json"


def _state_path() -> Path:
    return paths.home() / "state" / "claude-install.json"


def _load_settings() -> tuple[dict, bool]:
    p = _settings_path()
    if not p.exists():
        return {}, False
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as e:
        raise InstallError(f"{p} is not valid JSON ({e}); fix it before installing the cvprism hook") from e
    if not isinstance(data, dict):
        raise InstallError(f"{p} must contain a JSON object")
    return data, True


def _write_settings(data: dict) -> None:
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.cvprism-tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _is_ours(hook: dict) -> bool:
    return any(m in str(hook.get("command", "")) for m in MARKERS)


def hook_command(hook: str | list[str]) -> str:
    parts = [hook] if isinstance(hook, str) else list(hook)
    parts[0] = Path(parts[0]).as_posix()
    return " ".join(f'"{a}"' if (" " in a or i == 0) else a for i, a in enumerate(parts)) + " claude-session-end"


def install_hook(hook_exe: str | list[str]) -> None:
    data, existed = _load_settings()
    state = _state_path()
    if not state.exists():
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"settings_existed": existed}), encoding="utf-8")
    groups = data.setdefault("hooks", {}).setdefault("SessionEnd", [])
    for g in groups:
        g["hooks"] = [h for h in g.get("hooks", []) if not _is_ours(h)]
    groups[:] = [g for g in groups if g.get("hooks")]
    groups.append({"hooks": [{"type": "command", "command": hook_command(hook_exe), "timeout": 10}]})
    _write_settings(data)


def uninstall_hook() -> None:
    data, existed = _load_settings()
    if existed:
        hooks = data.get("hooks", {})
        groups = hooks.get("SessionEnd", [])
        for g in groups:
            g["hooks"] = [h for h in g.get("hooks", []) if not _is_ours(h)]
        groups = [g for g in groups if g.get("hooks")]
        if groups:
            hooks["SessionEnd"] = groups
        else:
            hooks.pop("SessionEnd", None)
        if not hooks:
            data.pop("hooks", None)
        state = json.loads(_state_path().read_text(encoding="utf-8")) if _state_path().exists() else {}
        if not data and state.get("settings_existed") is False:
            _settings_path().unlink()
        else:
            _write_settings(data)
    _state_path().unlink(missing_ok=True)


def installed() -> bool:
    data, _ = _load_settings()
    return any(_is_ours(h) for g in data.get("hooks", {}).get("SessionEnd", []) for h in g.get("hooks", []))


def install_skills() -> list[Path]:
    out = []
    src_root = resources.files("cvprism.data").joinpath("skills")
    for name in SKILLS:
        dst = claude_dir() / "skills" / name / "SKILL.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src_root.joinpath(name, "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
        out.append(dst)
    return out


def uninstall_skills() -> None:
    for name in SKILLS:
        d = claude_dir() / "skills" / name
        if (d / "SKILL.md").exists() and "cvprism" in (d / "SKILL.md").read_text(encoding="utf-8"):
            shutil.rmtree(d)
