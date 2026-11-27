"""Device configuration (~/.cvprism/device.yaml); schema: cvprism/schemas/device.schema.json."""
from __future__ import annotations

import secrets
from typing import Any

from . import paths, yamlio
from .novelty.ids import slugify
from .schemas import validate


class NotInitialised(RuntimeError):
    pass


def make_device_id(name: str) -> str:
    base = slugify(name)[:35] or "device"
    return f"{base}-{secrets.token_hex(2)}"


def new_device_config(
    *,
    name: str,
    role: str,
    vault_id: str,
    vault_path: str,
    watch_paths: list[str] | None = None,
    claude_session: bool = True,
) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "v": 1,
        "device_id": make_device_id(name),
        "name": name,
        "role": role,
        "vault_id": vault_id,
    }
    if role == "hub":
        cfg["vault_path"] = vault_path
    cfg["capture"] = {
        "claude_session": {"enabled": claude_session},
        "git": {"enabled": True, "exclude_repos": []},
        "watcher": {
            "enabled": bool(watch_paths),
            "paths": list(watch_paths or []),
            "ignore": ["**/node_modules/**", "**/.venv/**", "**/.git/**", "**/data/**"],
            "debounce_s": 60,
        },
        "manual": {"enabled": True},
    }
    cfg["extraction"] = {"model": "haiku", "max_input_tokens": 6000, "timeout_s": 120}
    cfg["privacy"] = {"review_mode": False, "exclude_paths": []}
    cfg["adapters"] = [{"type": "local", "enabled": True, "name": "vault-folder", "path": vault_path}]
    validate("device", cfg)
    return cfg


def save_device(cfg: dict) -> None:
    validate("device", cfg)
    yamlio.dump(cfg, paths.device_file())


def load_device() -> dict:
    p = paths.device_file()
    if not p.exists():
        raise NotInitialised("This device is not set up yet. Run `cvprism init` first.")
    cfg = yamlio.load(p)
    validate("device", cfg)
    return cfg
