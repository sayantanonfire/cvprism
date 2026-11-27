"""First-run setup (TUI). Decision: TUI first, browser wizard in M6 (ARCHITECTURE open question 4)."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from .. import config, paths, vault
from ..sync.adapters import make_adapter, parse_spec


class SetupError(RuntimeError):
    pass


def default_vault_path() -> Path:
    return Path.home() / "cvprism-vault"


def _name_adapters(specs: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    for s in specs:
        n = seen.get(s["type"], 0) + 1
        seen[s["type"]] = n
        s["name"] = s["type"] if n == 1 else f"{s['type']}-{n}"
    return specs


def discover_vault_id(specs: list[dict]) -> str | None:
    for s in specs:
        a = make_adapter(s, device_id="setup-0000", vault_id=None, state_dir=paths.home() / "state" / "transports")
        try:
            if a.available():
                return a.read_vault_id()
        except Exception:  # noqa: BLE001 - try the next transport
            continue
    return None


def configure(
    *,
    name: str,
    role: str,
    vault_path: Path | None = None,
    adapters: list[str] | None = None,
    watch_paths: list[str] | None = None,
    claude_session: bool = True,
    force: bool = False,
) -> dict:
    if role not in ("hub", "spoke"):
        raise SetupError("role must be 'hub' or 'spoke'")
    if paths.device_file().exists() and not force:
        raise SetupError(f"This device is already set up ({paths.device_file()}). Use --force to redo setup.")
    try:
        specs = [parse_spec(a) for a in (adapters or [])]
    except ValueError as e:
        raise SetupError(str(e)) from e
    if vault_path is not None:
        vault_path = Path(vault_path).expanduser().resolve()
        try:
            vault.check_vault_location(vault_path)
        except vault.VaultError as e:
            raise SetupError(str(e)) from e
        specs.insert(0, {"type": "local", "enabled": True, "name": "local", "path": str(vault_path)})
    specs = _name_adapters(specs)

    if role == "hub":
        if vault_path is None:
            raise SetupError("A hub needs --vault <folder> for its private vault.")
        vid = vault.read_vault_id(vault_path) or vault.init_vault(vault_path)
    else:
        if not specs:
            raise SetupError("A spoke needs at least one --adapter (e.g. git:<repo-url>, gdrive:<folder>, usb).")
        vid = discover_vault_id(specs)
        if vid is None:
            raise SetupError("No vault found on any adapter. Set up the hub and run `cvprism sync` there first, "
                             "then point this spoke at the same transport.")
    cfg = config.new_device_config(
        name=name, role=role, vault_id=vid, vault_path=str(vault_path) if vault_path else "",
        watch_paths=[str(Path(p).expanduser()) for p in (watch_paths or [])], claude_session=claude_session,
    )
    cfg["adapters"] = specs
    if role == "spoke":
        cfg.pop("vault_path", None)
    else:
        _claim_hub(vault_path, cfg["device_id"])
    config.save_device(cfg)
    return cfg


def _claim_hub(vault_path: Path, device_id: str) -> None:
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
    vpath = None
    if role == "hub":
        vpath = Path(typer.prompt("Vault folder (private; NOT inside the code repo)", default=str(default_vault_path())))
    typer.echo("Sync transports, comma-separated: git:<private-repo-url>, gdrive:<synced-folder>, usb, "
               "syncthing:<folder>, local:<folder>")
    adapters = typer.prompt("Adapters" + (" (blank = this machine only)" if role == "hub" else ""),
                            default="", show_default=False)
    watch = typer.prompt("Project folders to watch for new tech (comma-separated, blank = none)",
                         default="", show_default=False)
    claude = typer.confirm("Capture skills from Claude Code sessions?", default=True)
    return configure(name=name, role=role, vault_path=vpath,
                     adapters=[a.strip() for a in adapters.split(",") if a.strip()],
                     watch_paths=[w.strip() for w in watch.split(",") if w.strip()], claude_session=claude)
