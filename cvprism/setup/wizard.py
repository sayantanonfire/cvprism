"""First-run setup (TUI). Decision: TUI first, browser wizard in M6 (ARCHITECTURE open question 4)."""
from __future__ import annotations

from pathlib import Path

import typer

from .. import config, paths, vault


class SetupError(RuntimeError):
    pass


def default_vault_path() -> Path:
    return Path.home() / "cvprism-vault"


def configure(
    *,
    name: str,
    role: str,
    vault_path: Path,
    watch_paths: list[str],
    claude_session: bool = True,
    force: bool = False,
) -> dict:
    if role not in ("hub", "spoke"):
        raise SetupError("role must be 'hub' or 'spoke'")
    if paths.device_file().exists() and not force:
        raise SetupError(f"This device is already set up ({paths.device_file()}). Use --force to redo setup.")
    vault_path = Path(vault_path).expanduser().resolve()
    try:
        vault.check_vault_location(vault_path)
    except vault.VaultError as e:
        raise SetupError(str(e)) from e
    vid = vault.read_vault_id(vault_path)
    if vid is None:
        if role == "spoke":
            raise SetupError(
                f"No vault found at {vault_path}. Set up the hub first, then point this spoke at the "
                "folder the vault syncs through."
            )
        vid = vault.init_vault(vault_path)
    cfg = config.new_device_config(
        name=name, role=role, vault_id=vid, vault_path=str(vault_path),
        watch_paths=[str(Path(p).expanduser()) for p in watch_paths], claude_session=claude_session,
    )
    if role == "hub":
        _claim_hub(vault_path, cfg["device_id"])
    config.save_device(cfg)
    return cfg


def _claim_hub(vault_path: Path, device_id: str) -> None:
    import json

    hub_file = vault_path / "hub.json"
    hub = json.loads(hub_file.read_text(encoding="utf-8"))
    if hub.get("hub_device_id") and hub["hub_device_id"] != device_id:
        hub["epoch"] = int(hub.get("epoch", 1)) + 1  # promotion (ADR-012)
    hub["hub_device_id"] = device_id
    hub_file.write_text(json.dumps(hub, indent=2) + "\n", encoding="utf-8", newline="\n")


def interactive() -> dict:
    typer.echo("cvprism setup: about one minute. Press Enter to accept [defaults].\n")
    import socket

    name = typer.prompt("Device name (e.g. office-01)", default=socket.gethostname().lower()[:30])
    role = ""
    while role not in ("hub", "spoke"):
        role = typer.prompt("Is this the hub (where CVs are built) or a spoke? [hub/spoke]", default="hub").strip().lower()
    label = "Vault folder (private; NOT inside the code repo)" if role == "hub" else \
        "Folder where the vault syncs to this device"
    vpath = typer.prompt(label, default=str(default_vault_path()))
    watch = typer.prompt("Project folders to watch for new tech (comma-separated, blank = none)",
                         default="", show_default=False)
    claude = typer.confirm("Capture skills from Claude Code sessions?", default=True)
    return configure(name=name, role=role, vault_path=Path(vpath),
                     watch_paths=[w.strip() for w in watch.split(",") if w.strip()], claude_session=claude)
