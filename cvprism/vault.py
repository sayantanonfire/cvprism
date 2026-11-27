"""Vault scaffold and location guard rails (SECURITY_PRIVACY.md, F12)."""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path


class VaultError(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_cvprism_checkout(d: Path) -> bool:
    pp = d / "pyproject.toml"
    if not pp.is_file():
        return False
    try:
        text = pp.read_text(encoding="utf-8")
    except OSError:
        return False
    return 'name = "cvprism"' in text


def check_vault_location(path: Path) -> None:
    """Refuse vault paths inside a cvprism code checkout (public repo) or a USB copy of it."""
    p = Path(path).expanduser().resolve()
    for d in [p, *p.parents]:
        if _is_cvprism_checkout(d):
            raise VaultError(
                f"Refusing to put the vault inside the cvprism code checkout ({d}). "
                "Your vault is private career data; choose a separate folder."
            )


def read_vault_id(path: Path) -> str | None:
    f = Path(path) / "vault.json"
    if not f.is_file():
        return None
    return json.loads(f.read_text(encoding="utf-8"))["vault_id"]


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def init_vault(path: Path) -> str:
    """Create a new vault from the packaged template. Returns its vault_id."""
    path = Path(path).expanduser()
    check_vault_location(path)
    if read_vault_id(path):
        raise VaultError(f"{path} already contains a vault")
    path.mkdir(parents=True, exist_ok=True)
    vid = str(uuid.uuid4())
    now = utcnow()
    tpl = resources.files("cvprism.data").joinpath("vault_template")
    for item in tpl.iterdir():
        _copy_tree(item, path / item.name)
    for sub in ("inbox", "roles", "market"):
        (path / sub).mkdir(exist_ok=True)
    # written here, not shipped as package data: setuptools globs skip dotfiles
    (path / ".gitignore").write_text("build/\nstaging/\n*.tmp\n", encoding="utf-8", newline="\n")
    _write_json(path / "vault.json", {"v": 1, "vault_id": vid, "created": now})
    _write_json(path / "hub.json", {"v": 1, "hub_device_id": None, "epoch": 1})
    _write_json(path / "registry.json", {"v": 1, "vault_id": vid, "epoch": 1, "rev": 0, "generated": now, "skills": {}})
    return vid


def _copy_tree(src, dst: Path) -> None:
    if src.is_dir():
        dst.mkdir(exist_ok=True)
        for child in src.iterdir():
            _copy_tree(child, dst / child.name)
    elif not dst.exists():
        with src.open("rb") as fi, dst.open("wb") as fo:
            shutil.copyfileobj(fi, fo)
