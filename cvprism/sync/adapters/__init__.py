"""Adapter registry. Third parties can add adapters via the `cvprism.adapters` entry-point group."""
from __future__ import annotations

from pathlib import Path

from .base import FolderAdapter
from .folders import GDriveAdapter, LocalAdapter, SyncthingAdapter, USBAdapter
from .git import GitAdapter

BUILTIN = {"local": LocalAdapter, "gdrive": GDriveAdapter, "usb": USBAdapter, "syncthing": SyncthingAdapter,
           "git": GitAdapter}


def _plugins() -> dict:
    try:
        from importlib.metadata import entry_points

        return {ep.name: ep.load() for ep in entry_points(group="cvprism.adapters")}
    except Exception:  # noqa: BLE001
        return {}


def make_adapter(spec: dict, *, device_id: str, vault_id: str | None, state_dir: Path) -> FolderAdapter:
    cls = BUILTIN.get(spec["type"]) or _plugins().get(spec["type"])
    if cls is None:
        raise ValueError(f"unknown adapter type {spec['type']!r}")
    return cls(spec, device_id=device_id, vault_id=vault_id, state_dir=state_dir)


def parse_spec(text: str) -> dict:
    """CLI form: git:<remote> | gdrive:<path> | local:<path> | syncthing:<path> | usb[:<marker>]."""
    kind, _, arg = text.partition(":")
    kind = kind.strip().lower()
    if kind not in BUILTIN:
        raise ValueError(f"unknown adapter {kind!r}; use git:, gdrive:, local:, syncthing: or usb")
    spec = {"type": kind, "enabled": True, "name": kind}
    if kind == "git":
        if not arg:
            raise ValueError("git adapter needs a remote: git:<url-or-path>")
        spec["remote"] = arg
    elif kind == "usb":
        if arg:
            spec["volume_marker"] = arg
    else:
        if not arg:
            raise ValueError(f"{kind} adapter needs a folder: {kind}:<path>")
        spec["path"] = str(Path(arg).expanduser())
    return spec
