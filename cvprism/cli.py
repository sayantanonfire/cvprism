"""cvprism command-line interface."""
from __future__ import annotations

import json
import platform
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional

import typer

from . import __version__, config, llm, paths, vault
from .capture.manual import LogError, log_entry
from .novelty.counters import Counters
from .setup import wizard
from .sync.outbox import Outbox

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Turn everyday work across many computers into evidence-backed, role-specific CVs.",
)


def _fail(msg: str, code: int = 1) -> None:
    typer.echo(f"error: {msg}", err=False)
    raise typer.Exit(code)


def _cfg() -> dict:
    try:
        return config.load_device()
    except config.NotInitialised as e:
        _fail(str(e))


@app.callback(invoke_without_command=True)
def _main(version: bool = typer.Option(False, "--version", help="Show version and exit.")) -> None:
    if version:
        typer.echo(f"cvprism {__version__}")
        raise typer.Exit()


@app.command()
def init(
    name: Optional[str] = typer.Option(None, help="Device name, e.g. office-01."),
    role: Optional[str] = typer.Option(None, help="hub or spoke."),
    vault_path: Optional[Path] = typer.Option(None, "--vault", help="Vault folder (hub) or synced vault folder (spoke)."),
    watch: List[str] = typer.Option([], "--watch", help="Project folder to watch (repeatable)."),
    no_claude: bool = typer.Option(False, "--no-claude-capture", help="Disable Claude Code session capture."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive; requires --name, --role, --vault."),
    force: bool = typer.Option(False, help="Redo setup on an already configured device."),
) -> None:
    """First-run setup: device name, hub or spoke, vault location, watch paths."""
    try:
        if yes or (name and role and vault_path):
            if not (name and role and vault_path):
                _fail("--yes needs --name, --role and --vault")
            cfg = wizard.configure(name=name, role=role, vault_path=vault_path, watch_paths=watch,
                                   claude_session=not no_claude, force=force)
        else:
            if paths.device_file().exists() and not force:
                _fail(f"This device is already set up ({paths.device_file()}). Use --force to redo setup.")
            cfg = wizard.interactive()
    except wizard.SetupError as e:
        _fail(str(e))
    typer.echo(f"\nReady. Device {cfg['device_id']} is a {cfg['role']}.")
    typer.echo(f"Config: {paths.device_file()}")
    typer.echo('Try:  cvprism log --raw "Built X with Y" --skill y --depth 3')


@app.command()
def log(
    text: str = typer.Argument(..., help="One line describing what you did."),
    skill: List[str] = typer.Option([], "--skill", "-s", help="Skill name (repeatable)."),
    depth: Optional[int] = typer.Option(None, "--depth", "-d", min=1, max=5,
                                        help="1 used, 2 applied, 3 built, 4 led/production, 5 authored/taught."),
    result: Optional[str] = typer.Option(None, "--result", "-r", help="metric:value:unit[:up|down|abs]"),
    work: bool = typer.Option(False, "--work", help="Non-code achievement (paper, talk, field work, award)."),
    ctx: Optional[str] = typer.Option(None, "--project", help="Project alias (mapped to a display name in profile.yaml)."),
    raw: bool = typer.Option(False, "--raw", help="Skip Claude; store your words as-is."),
) -> None:
    """Record an achievement manually."""
    import os

    if os.environ.get("CVPRISM_EXTRACTING"):
        return  # never capture from inside an extraction session
    cfg = _cfg()
    try:
        res = log_entry(text, cfg=cfg, skills=skill, depth=depth, result=result, work=work, ctx=ctx, raw=raw)
    except LogError as e:
        _fail(str(e))
    for m in res.messages:
        typer.echo(m)


@app.command()
def status() -> None:
    """Show this device's capture and sync state."""
    cfg = _cfg()
    ob = Outbox(paths.outbox_dir(), cfg["device_id"])
    cards = list(ob.iter_cards())
    kinds = Counter(c["k"] for c in cards)
    flagged = sum(1 for c in cards if "needs_metric" in c.get("flags", []))
    counters = Counters(paths.counters_file()).data
    typer.echo(f"device:          {cfg['device_id']} ({cfg['role']})")
    typer.echo(f"vault id:        {cfg['vault_id']}")
    typer.echo(f"cards in outbox: {len(cards)}  " + "  ".join(f"{k}={n}" for k, n in sorted(kinds.items())))
    typer.echo(f"needs metric:    {flagged}")
    typer.echo(f"month files:     {', '.join(p.name for p in ob.files()) or '-'}")
    if counters:
        top = sorted(counters.items(), key=lambda kv: -kv[1]["n"])[:5]
        typer.echo("top repeats:     " + ", ".join(f"{k}×{v['n']}" for k, v in top))
    for a in cfg["adapters"]:
        state = "on" if a.get("enabled") else "off"
        typer.echo(f"adapter:         {a['type']} [{state}] {a.get('path') or a.get('remote') or ''}")


@app.command()
def doctor() -> None:
    """Check the environment and configuration."""
    ok = True

    def line(good: bool, label: str, detail: str = "") -> None:
        nonlocal ok
        ok = ok and good
        typer.echo(f"[{'ok' if good else '!!'}] {label}{': ' + detail if detail else ''}")

    py_ok = sys.version_info >= (3, 10)
    line(py_ok, "python", f"{platform.python_version()} ({sys.executable})")
    ver = llm.claude_version()
    line(ver is not None, "claude cli", ver or "not found; auto-extraction disabled, `cvprism log --raw` still works")
    line(shutil.which("git") is not None, "git", shutil.which("git") or "not found (git capture/adapter unavailable)")
    try:
        cfg = config.load_device()
        line(True, "device config", str(paths.device_file()))
    except Exception as e:  # noqa: BLE001 - doctor reports everything
        line(False, "device config", str(e))
        raise typer.Exit(1)
    for a in cfg["adapters"]:
        if a["type"] == "local":
            vid = vault.read_vault_id(Path(a["path"]))
            line(vid == cfg["vault_id"], f"adapter local:{a['path']}",
                 "vault reachable" if vid == cfg["vault_id"] else "vault missing or different vault_id")
    if not ok:
        raise typer.Exit(1)


@app.command()
def show(n: int = typer.Option(10, help="How many recent cards.")) -> None:
    """Pretty-print the most recent cards from this device."""
    cfg = _cfg()
    cards = sorted(Outbox(paths.outbox_dir(), cfg["device_id"]).iter_cards(), key=lambda c: c["t"])[-n:]
    for c in cards:
        r = c.get("r")
        rtxt = f"  [{r['m']}: {r['val']}{r['unit']}]" if r else ""
        typer.echo(f"{c['t'][:10]}  {c['id']}  d{c['d']}  {','.join(c['s'])}{rtxt}\n    {c['txt']}")


if __name__ == "__main__":  # pragma: no cover
    app()
