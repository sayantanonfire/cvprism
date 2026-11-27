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
    from .capture.queue import Queue
    from .install import claude as cc
    from .install import githooks

    jobs = Queue(paths.queue_dir()).pending()
    waiting = [j for j in jobs if j.get("attempts")]
    typer.echo(f"queued jobs:     {len(jobs)}" + (f"  (retrying: {len(waiting)}, last error: "
                                                 f"{waiting[-1]['last_error']})" if waiting else ""))
    try:
        hook = "installed" if cc.installed() else "not installed"
    except cc.InstallError as e:
        hook = f"settings unreadable ({e})"
    typer.echo(f"claude hook:     {hook}")
    typer.echo(f"git hooks:       {'installed' if githooks.installed() else 'not installed'}")


def _hook_argv() -> list[str]:
    """argv for the hook entry point: the installed cvprism-hook script, else `python -m`."""
    exe_dir = Path(sys.executable).parent
    for name in ("cvprism-hook.exe", "cvprism-hook"):
        if (exe_dir / name).exists():
            return [str(exe_dir / name)]
    return [sys.executable, "-m", "cvprism.capture.hookentry"]


@app.command()
def install(
    no_claude: bool = typer.Option(False, "--no-claude", help="Skip the Claude Code SessionEnd hook."),
    no_git: bool = typer.Option(False, "--no-git", help="Skip the global git hook dispatcher."),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip installing /cv-log and /cv-build skills."),
    no_service: bool = typer.Option(False, "--no-service", help="Skip the background agent at login."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change, change nothing."),
) -> None:
    """Register capture hooks, skills and the background agent (all reversible with `cvprism uninstall`)."""
    from .install import claude as cc
    from .install import githooks, service

    cfg = _cfg()
    argv = _hook_argv()
    cap = cfg.get("capture") or {}
    steps = []
    if not no_claude and (cap.get("claude_session") or {}).get("enabled", True):
        steps.append(("Claude Code SessionEnd hook in " + str(cc.claude_dir() / "settings.json"),
                      lambda: cc.install_hook(argv)))
    if not no_skills:
        steps.append(("skills /cv-log and /cv-build in " + str(cc.claude_dir() / "skills"), cc.install_skills))
    if not no_git and (cap.get("git") or {}).get("enabled", True):
        steps.append((f"git: global core.hooksPath -> {githooks.hooks_dir()} (chains repo-local hooks)",
                      lambda: githooks.install(argv)))
    if not no_service:
        actions = service.plan(service.current_os(), service.default_argv())
        desc = "; ".join(f"write {a.path}" if a.kind == "write" else " ".join(a.cmd[:4]) for a in actions)
        steps.append((f"background agent at login: {desc}", lambda: typer.echo("\n".join(service.execute(actions)))))
    for label, fn in steps:
        if dry_run:
            typer.echo(f"would install: {label}")
            continue
        try:
            fn()
            typer.echo(f"installed: {label}")
        except Exception as e:  # noqa: BLE001
            typer.echo(f"FAILED: {label}: {e}")
    if not dry_run and not no_git:
        from .install import githooks as gh

        roots = ((cap.get("watcher") or {}).get("paths")) or []
        bypass = gh.repos_overriding_hooks([Path(r) for r in roots]) if roots else []
        for r in bypass:
            typer.echo(f"note: {r} sets its own core.hooksPath (e.g. husky); its commits are not captured")


@app.command()
def uninstall(
    no_service: bool = typer.Option(False, "--no-service", help="Leave the login agent registration alone."),
) -> None:
    """Remove hooks, skills and the login agent, restoring previous settings. Data is kept."""
    from .install import claude as cc
    from .install import githooks, service

    for label, fn in [("Claude Code hook", cc.uninstall_hook), ("skills", cc.uninstall_skills),
                      ("git hooks", githooks.uninstall)]:
        try:
            fn()
            typer.echo(f"removed: {label}")
        except Exception as e:  # noqa: BLE001
            typer.echo(f"FAILED: {label}: {e}")
    if not no_service:
        typer.echo("\n".join(service.execute(service.unplan(service.current_os()))))
    typer.echo(f"Your data is untouched in {paths.home()}")


@app.command()
def worker() -> None:
    """Process queued capture jobs once (the agent does this automatically)."""
    from .capture.worker import run_once

    stats = run_once(_cfg())
    typer.echo(" ".join(f"{k}={v}" for k, v in stats.items()))


@app.command()
def agent(
    interval: int = typer.Option(30, help="Seconds between queue drains."),
    iterations: int = typer.Option(0, help="Stop after N iterations (0 = run forever)."),
) -> None:
    """Background capture agent: folder watcher + queue worker. Started at login by `cvprism install`."""
    import threading

    from .capture.watcher import SignalScanner, run_observer
    from .capture.worker import run_once
    from .lock import AlreadyRunning, single_instance

    cfg = _cfg()
    try:
        with single_instance(paths.home() / "agent.lock"):
            stop = threading.Event()
            w = (cfg.get("capture") or {}).get("watcher") or {}
            t = None
            if w.get("enabled") and w.get("paths"):
                scanner = SignalScanner(w["paths"], w.get("ignore") or [])
                if not scanner.state:
                    scanner.baseline()
                t = threading.Thread(target=run_observer, args=(scanner, int(w.get("debounce_s", 60)), stop),
                                     daemon=True)
                t.start()
            n = 0
            try:
                while True:
                    try:
                        run_once(config.load_device())
                    except Exception as e:  # noqa: BLE001 - the agent must survive bad jobs
                        paths.logs_dir().mkdir(parents=True, exist_ok=True)
                        with (paths.logs_dir() / "agent.log").open("a", encoding="utf-8") as f:
                            f.write(f"{type(e).__name__}: {e}\n")
                    n += 1
                    if iterations and n >= iterations:
                        break
                    stop.wait(interval)
            finally:
                stop.set()
                if t:
                    t.join(timeout=5)
    except AlreadyRunning:
        typer.echo("cvprism agent is already running")


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
