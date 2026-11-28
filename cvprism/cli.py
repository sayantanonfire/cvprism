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

from . import __version__, config, llm, paths, vault, yamlio
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
    adapter: List[str] = typer.Option([], "--adapter", "-a",
                                      help="Sync transport (repeatable): git:<url>, gdrive:<folder>, usb, "
                                           "syncthing:<folder>, local:<folder>."),
    watch: List[str] = typer.Option([], "--watch", help="Project folder to watch (repeatable)."),
    no_claude: bool = typer.Option(False, "--no-claude-capture", help="Disable Claude Code session capture."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive; requires --name, --role, --vault."),
    force: bool = typer.Option(False, help="Redo setup on an already configured device."),
    web: bool = typer.Option(False, "--web", help="Use a setup page in your browser instead of the terminal."),
) -> None:
    """First-run setup: device name, hub or spoke, vault location, watch paths."""
    if web:
        from .setup import web as webwiz

        if paths.device_file().exists() and not force:
            _fail(f"This device is already set up ({paths.device_file()}). Use --force to redo setup.")
        cfg = webwiz.run(force=force)
        if not cfg:
            _fail("Setup was not completed.")
        typer.echo(f"Ready. Device {cfg['device_id']} is a {cfg['role']}.")
        return
    try:
        if yes:
            if not (name and role and (vault_path or adapter)):
                _fail("--yes needs --name, --role and --vault (hub) or --adapter (spoke)")
            cfg = wizard.configure(name=name, role=role, vault_path=vault_path, adapters=adapter, watch_paths=watch,
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
    link: List[str] = typer.Option([], "--link", help="Public proof URL, e.g. a DOI, PyPI page or video (repeatable)."),
) -> None:
    """Record an achievement manually."""
    import os

    if os.environ.get("CVPRISM_EXTRACTING"):
        return  # never capture from inside an extraction session
    cfg = _cfg()
    try:
        res = log_entry(text, cfg=cfg, skills=skill, depth=depth, result=result, work=work, ctx=ctx, raw=raw,
                        links=link)
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
    from .sync.engine import adapters_for

    for a in adapters_for(cfg, include_disabled=True):
        on = next((s.get("enabled") for s in cfg["adapters"] if (s.get("name") or s["type"]) == a.name), False)
        try:
            reach = "reachable" if a.available() else "unreachable"
        except Exception:  # noqa: BLE001
            reach = "unreachable"
        backlog = a.backlog(ob)
        where = a.spec.get("path") or a.spec.get("remote") or a.spec.get("volume_marker") or ""
        typer.echo(f"adapter:         {a.name} [{'on' if on else 'off'}, {reach}, backlog {backlog} file(s)] {where}")
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


def _usb_mount_events(cfg: dict, seen: dict) -> bool:
    """True when a configured USB drop-box has just appeared (SYNC.md scheduling: flush on mount)."""
    from .sync.adapters import make_adapter

    fired = False
    for spec in cfg.get("adapters", []):
        if spec["type"] != "usb" or not spec.get("enabled"):
            continue
        a = make_adapter(spec, device_id=cfg["device_id"], vault_id=cfg["vault_id"],
                         state_dir=paths.home() / "state" / "transports")
        try:
            now = a.available()
        except Exception:  # noqa: BLE001
            now = False
        if now and not seen.get(a.name):
            fired = True
        seen[a.name] = now
    return fired


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
            import time as _time

            from .sync.engine import sync as _sync

            n = 0
            usb_seen: dict = {}
            last_sync = 0.0
            try:
                while True:
                    try:
                        cur = config.load_device()
                        run_once(cur)
                        every = min([int(a.get("interval_s", 900)) for a in cur["adapters"]] or [900])
                        if _usb_mount_events(cur, usb_seen) or _time.monotonic() - last_sync >= every:
                            _sync(cur)
                            last_sync = _time.monotonic()
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
    from .sync.engine import adapters_for

    for a in adapters_for(cfg):
        try:
            ok_a = a.available()
            detail = "reachable, vault matches" if ok_a else "not reachable now (cards wait in the outbox)"
        except Exception as e:  # noqa: BLE001
            ok_a, detail = False, str(e)
        line(ok_a, f"adapter {a.name} ({a.kind})", detail)
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


@app.command()
def build(
    role: Optional[str] = typer.Option(None, "--role", "-r", help="Role profile id (vault/roles or a starter)."),
    jd: Optional[str] = typer.Option(None, "--jd", help="Job description file or URL to tailor to."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Use card text directly; no Claude call."),
    fmt: Optional[str] = typer.Option(None, "--format", "-f", help="Comma list: pdf,docx,md (default: role outputs)."),
    out: Optional[Path] = typer.Option(None, "--out", help="Output root (default: vault/build/<role>/)."),
    check_links: bool = typer.Option(False, "--check-links", help="Open every proof link; drop dead ones."),
    publish: bool = typer.Option(False, "--publish", help="Publish the verify page (profile.yaml `verify:`)."),
    sign: bool = typer.Option(False, "--sign", help="Sign the manifest with your SSH key (profile `verify.signing_key`)."),
) -> None:
    """Build a tailored CV on the hub. Every bullet cites evidence; unsupported numbers are rejected."""
    from .compile.build import BuildError, build_cv
    from .compile.roles import RoleError, starter_roles

    cfg = _cfg()
    formats = [f.strip() for f in fmt.split(",")] if fmt else None
    try:
        if jd:
            from .compile.jd import build_for_jd

            res = build_for_jd(cfg, jd, use_llm=not no_llm, formats=formats, out_root=out, base_role=role,
                               check_links=check_links, publish=publish, sign=sign)
        else:
            if not role:
                _fail("Pass --role <id> or --jd <file-or-url>. Starter roles: " + ", ".join(starter_roles()))
            res = build_cv(cfg, role, use_llm=not no_llm, formats=formats, out_root=out, check_links=check_links,
                           publish=publish, sign=sign)
    except (BuildError, RoleError) as e:
        _fail(str(e))
    for line in res.log:
        typer.echo(line)
    typer.echo(f"formats: {', '.join(res.meta['formats'])}")
    typer.echo(f"output: {res.out_dir}")


def _import_report(rep) -> None:
    for n in rep.notes:
        typer.echo(f"note: {n}")
    typer.echo(f"{rep.cards} new card(s), {rep.known} already known; {rep.positions} position(s), "
               f"{rep.education} education entr(y/ies), {rep.certifications} certification(s) added to profile")
    if rep.cards:
        typer.echo("Imported cards are flagged needs_review (self-reported). Check them with `cvprism show`.")


@app.command("import-linkedin")
def import_linkedin_cmd(
    src: Path = typer.Argument(..., help="LinkedIn data export (.zip or unzipped folder)."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Keyword matching only."),
) -> None:
    """Bootstrap profile facts and evidence cards from a LinkedIn data export."""
    from .capture.importers import import_linkedin

    try:
        rep = import_linkedin(src, _cfg(), use_llm=not no_llm)
    except (OSError, ValueError) as e:
        _fail(str(e))
    _import_report(rep)


@app.command("import-cv")
def import_cv_cmd(
    path: Path = typer.Argument(..., help="Existing CV: .md, .txt, .docx (or .pdf with pypdf installed)."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Keyword matching on bullet points only."),
) -> None:
    """Turn an existing CV into evidence cards (flagged for review)."""
    from .capture.importers import import_cv

    try:
        rep = import_cv(path, _cfg(), use_llm=not no_llm)
    except (OSError, ValueError) as e:
        _fail(str(e))
    _import_report(rep)


@app.command("import-orcid")
def import_orcid(orcid: str = typer.Argument(..., help="Your ORCID iD, e.g. 0000-0002-1825-0097.")) -> None:
    """Fetch your public ORCID works and add new ones to the vault's BibTeX file (hub only)."""
    from .compile.orcid import fetch_bulk, merge_into_bib, works_to_entries

    cfg = _hub_cfg()
    vault_dir = Path(cfg["vault_path"])
    prof_file = vault_dir / "profile.yaml"
    prof = yamlio.load(prof_file) if prof_file.is_file() else {}
    bib_name = ((prof or {}).get("publications") or {}).get("bibtex") or "pubs.bib"
    bib = vault_dir / bib_name
    try:
        entries = works_to_entries(fetch_bulk(orcid))
    except Exception as e:  # noqa: BLE001
        _fail(f"ORCID import failed: {e}")
    text, added = merge_into_bib(bib.read_text(encoding="utf-8") if bib.is_file() else "", entries)
    bib.write_text(text, encoding="utf-8")
    typer.echo(f"{added} new publication(s) added to {bib} ({len(entries)} found on ORCID)")
    if not ((prof or {}).get("publications") or {}).get("bibtex"):
        typer.echo(f"Add `publications: {{bibtex: {bib_name}, orcid: \"{orcid}\"}}` to profile.yaml to use them.")


market_app = typer.Typer(help="Market intel: recurring phrases from job postings you saved (hub only).",
                         no_args_is_help=True)
app.add_typer(market_app, name="market")


@market_app.command("add")
def market_add(role: str = typer.Argument(..., help="Role id, e.g. applied-ai."),
               src: str = typer.Argument(..., help="Posting file or URL.")) -> None:
    """Save a job posting under vault/market/raw/<role>/."""
    from .compile.market import add_posting

    cfg = _hub_cfg()
    try:
        dest = add_posting(Path(cfg["vault_path"]), role, src)
    except (OSError, ValueError) as e:
        _fail(str(e))
    typer.echo(f"saved {dest}")


@market_app.command("extract")
def market_extract(role: str = typer.Argument(..., help="Role id."),
                   no_llm: bool = typer.Option(False, "--no-llm", help="Keyword matching only.")) -> None:
    """Aggregate recurring phrases into vault/market/<role>.json (used as role vocabulary in builds)."""
    from .compile.market import extract

    cfg = _hub_cfg()
    out = extract(Path(cfg["vault_path"]), role, use_llm=not no_llm)
    typer.echo(f"{out['postings']} posting(s), {len(out['phrases'])} phrase(s)")
    for p in out["phrases"][:15]:
        typer.echo(f"  {p['share']:>5.0%}  {p['phrase']}")


@app.command()
def demo(
    out: Path = typer.Option(Path("cvprism-demo"), "--out", help="Folder for the demo vault and CVs."),
    llm_: bool = typer.Option(False, "--llm", help="Draft bullets with Claude (default: offline, card text)."),
    fmt: Optional[str] = typer.Option(None, "--format", "-f", help="Comma list: pdf,docx,md."),
) -> None:
    """Build sample CVs (3 roles + a job posting) for a synthetic person. Needs no setup."""
    from .demo import run_demo

    formats = [f.strip() for f in fmt.split(",")] if fmt else None
    out = out.expanduser().resolve()
    typer.echo(f"Demo vault: {out / 'demo-vault'} (synthetic person, safe to delete)")
    for label, path, log in run_demo(out, use_llm=llm_, formats=formats):
        typer.echo(f"{label}: {log[-1] if log else ''}")
        typer.echo(f"  -> {path}")
    typer.echo("Open cv.pdf / cv.md, then evidence.md to see which card backs every bullet.")


project_app = typer.Typer(help="Projects: public (linked), private or local. Private work always keeps its skills.",
                          no_args_is_help=True)
app.add_typer(project_app, name="project")


@project_app.command("set")
def project_set(
    ctx: str = typer.Argument(..., help="Project alias, e.g. flood-copilot."),
    public: bool = typer.Option(False, "--public", help="Link proof to this project's public repo/page."),
    private: bool = typer.Option(False, "--private", help="Show '(private repository)' instead of links."),
    local: bool = typer.Option(False, "--local", help="Local-only work: no link, no label."),
    url: Optional[str] = typer.Option(None, "--url", help="Repository or project URL (https)."),
    display: Optional[str] = typer.Option(None, "--display", help="Public-safe name shown on CVs."),
) -> None:
    """Set a project's visibility on the hub (profile.yaml). Applies to all past and future cards."""
    from .compile.evidence import is_https, normalise_repo_url
    from .novelty.ids import slugify

    cfg = _hub_cfg()
    if sum([public, private, local]) > 1:
        _fail("Choose one of --public, --private, --local.")
    if url and not is_https(normalise_repo_url(url)):
        _fail("--url must be an https:// address (or a git@host:owner/repo remote).")
    if public and not url:
        _fail("A public project needs --url (its repository or project page).")
    pf = Path(cfg["vault_path"]) / "profile.yaml"
    prof = yamlio.load(pf) or {"v": 1, "person": {"name": "Your Name"}}
    slug = slugify(ctx)
    projects = prof.setdefault("projects", [])
    p = next((x for x in projects if x.get("ctx") == slug), None)
    if p is None:
        p = {"ctx": slug, "display": display or slug.replace("-", " ").capitalize()}
        projects.append(p)
    if display:
        p["display"] = display
    if public or private or local:
        p["visibility"] = "public" if public else "private" if private else "local"
    if url:
        p["url"] = normalise_repo_url(url)
    from .schemas import errors as _errors

    errs = _errors("profile", prof)
    if errs:
        _fail("; ".join(errs[:3]))
    yamlio.dump(prof, pf)
    typer.echo(f"{slug}: {p.get('visibility', 'local')}{' ' + p['url'] if p.get('url') else ''}")


@project_app.command("map")
def project_map(ctx: str = typer.Argument(..., help="Project alias."),
                path: Path = typer.Argument(..., help="Folder whose work belongs to this project.")) -> None:
    """On this computer: tag work captured inside PATH with the project alias."""
    from .novelty.ids import slugify

    cfg = _cfg()
    entry = {"ctx": slugify(ctx), "path": str(path.expanduser().resolve())}
    maps = [m for m in cfg.get("projects") or [] if m["path"] != entry["path"]]
    cfg["projects"] = maps + [entry]
    config.save_device(cfg)
    typer.echo(f"work in {entry['path']} is now tagged as project '{entry['ctx']}'")


@project_app.command("list")
def project_list() -> None:
    """Show projects, their visibility and folder mappings on this computer."""
    cfg = _cfg()
    if cfg.get("vault_path"):
        prof = yamlio.load(Path(cfg["vault_path"]) / "profile.yaml") or {}
        for p in prof.get("projects") or []:
            typer.echo(f"{p['ctx']:<24} {p.get('visibility', 'local'):<8} {p.get('url', '')}  ({p.get('display', '')})")
    for m in cfg.get("projects") or []:
        typer.echo(f"mapped: {m['path']} -> {m['ctx']}")


@app.command("link")
def link_cmd(card_id: str = typer.Argument(..., help="Card ID (see `cvprism show` or evidence.md)."),
             url: str = typer.Argument(..., help="Public proof URL (https).")) -> None:
    """Attach a public proof link to an existing card (hub only)."""
    import json as _json

    from .compile.evidence import is_https
    from .hub.merge import read_cards
    from .vault import utcnow

    cfg = _hub_cfg()
    if not is_https(url):
        _fail("Links must be public https:// URLs.")
    vault_dir = Path(cfg["vault_path"])
    if card_id not in {c["id"] for c in read_cards(vault_dir)}:
        _fail(f"No card {card_id} in this vault.")
    with (vault_dir / "links.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(_json.dumps({"id": card_id, "url": url, "t": utcnow()}) + "\n")
    typer.echo(f"linked {card_id} -> {url}")


@app.command("verify")
def verify_cmd(
    file: Path = typer.Argument(..., help="The CV file you received (PDF, DOCX or MD)."),
    manifest: str = typer.Option(..., "--manifest", help="manifest.json path or URL from the verify page."),
    github: Optional[str] = typer.Option(None, "--github", help="Also check the signature against this GitHub "
                                                               "user's published SSH keys."),
    keys: Optional[Path] = typer.Option(None, "--keys", help="Also check the signature against SSH public keys "
                                                             "in this file."),
) -> None:
    """Check a CV file against its published fingerprint, and optionally who signed it."""
    import json as _json
    import tempfile
    import urllib.request

    from .compile.verify import verify_pdf

    try:
        if manifest.startswith("https://"):
            with urllib.request.urlopen(manifest, timeout=30) as r:
                raw = r.read()
        else:
            raw = Path(manifest).read_bytes()
        m = _json.loads(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        _fail(f"Could not read the manifest: {e}")
    if not verify_pdf(file, m):
        _fail(f"{file.name} does not match the published fingerprint: it was changed or is a different build.")
    typer.echo(f"OK: {file.name} matches the CV {m['name']} published on {m['built'][:10]}.")
    if github or keys:
        from .compile.sign import SignError, github_keys, verify_signature

        try:
            if manifest.startswith("https://"):
                with urllib.request.urlopen(manifest + ".sig", timeout=30) as r:
                    sig_bytes = r.read()
            else:
                sig_bytes = Path(manifest + ".sig").read_bytes()
            pubs = github_keys(github) if github else [
                ln.strip() for ln in keys.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except Exception as e:  # noqa: BLE001
            _fail(f"Could not load the signature or keys: {e}")
        with tempfile.TemporaryDirectory() as td:
            mf, sf = Path(td) / "manifest.json", Path(td) / "manifest.json.sig"
            mf.write_bytes(raw)
            sf.write_bytes(sig_bytes)
            try:
                ok = verify_signature(mf, sf, github or "signer", pubs)
            except SignError as e:
                _fail(str(e))
        if not ok:
            _fail("The signature does not match those keys: this CV was not signed by that person.")
        typer.echo(f"Signed by {'GitHub user ' + github if github else 'the key in ' + keys.name}.")
    typer.echo("This proves the file was not changed. Check the proof links for the claims themselves.")


@app.command("app")
def app_cmd(
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open the browser automatically."),
    port: int = typer.Option(0, "--port", help="Fixed port (default: any free port)."),
) -> None:
    """Open cvprism in your browser: add evidence, import, manage projects and build CVs without a terminal."""
    from .app.server import run

    _cfg()
    run(open_browser=not no_browser, port=port)


@app.command("roles")
def roles_cmd() -> None:
    """List starter roles and the roles in your vault."""
    from .compile.roles import starter_roles

    cfg = _cfg()
    typer.echo("starter roles: " + ", ".join(starter_roles()))
    if cfg.get("vault_path"):
        mine = sorted(p.stem for p in (Path(cfg["vault_path"]) / "roles").glob("*.yaml"))
        typer.echo("vault roles:   " + (", ".join(mine) or "(none; copy a starter from the cvprism repo roles/)"))


@app.command("sync")
def sync_cmd() -> None:
    """Push this device's cards to every transport; on the hub, merge and publish the registry."""
    from .sync.engine import sync

    for line in sync(_cfg()).lines:
        typer.echo(line)


hub_app = typer.Typer(help="Hub-only operations: merge, rebuild, promote.", no_args_is_help=True)
app.add_typer(hub_app, name="hub")


def _hub_cfg() -> dict:
    cfg = _cfg()
    if cfg.get("role") != "hub":
        _fail("This device is a spoke. Run this on the hub, or use `cvprism hub promote`.")
    return cfg


@hub_app.command("merge")
def hub_merge() -> None:
    """Pull every inbox from every transport and merge into cards.jsonl."""
    from .sync.engine import sync

    for line in sync(_hub_cfg()).lines:
        typer.echo(line)


@hub_app.command("rebuild")
def hub_rebuild() -> None:
    """Recreate cards.jsonl and registry.json from inboxes alone."""
    from .hub.merge import merge
    from .sync.engine import adapters_for

    cfg = _hub_cfg()
    rep = merge(cfg, [a for a in adapters_for(cfg) if a.available()], rebuild=True)
    typer.echo(f"rebuilt: {rep.new_cards} card(s), quarantined {rep.quarantined}, registry rev {rep.rev}")


@hub_app.command("promote")
def hub_promote(vault_path: Path = typer.Option(..., "--vault", help="Folder for this device's new hub vault.")) -> None:
    """Make this device the hub (epoch+1) and rebuild the vault from every transport's inboxes."""
    import json as _json

    from .hub.merge import merge
    from .sync.engine import adapters_for, highest_hub

    cfg = _cfg()
    if cfg.get("role") == "hub":
        _fail("This device is already the hub.")
    adapters = adapters_for(cfg)
    current = highest_hub(adapters) or {"epoch": 0}
    vault_path = vault_path.expanduser().resolve()
    try:
        vault.check_vault_location(vault_path)
        if not vault.read_vault_id(vault_path):
            vault.init_vault(vault_path, vault_id=cfg["vault_id"])
    except vault.VaultError as e:
        _fail(str(e))
    hub = {"v": 1, "hub_device_id": cfg["device_id"], "epoch": int(current.get("epoch", 0)) + 1}
    (vault_path / "hub.json").write_text(_json.dumps(hub, indent=2) + "\n", encoding="utf-8")
    cfg["role"] = "hub"
    cfg["vault_path"] = str(vault_path)
    cfg["adapters"] = [{"type": "local", "enabled": True, "name": "local-vault", "path": str(vault_path)}] + [
        a for a in cfg["adapters"] if not (a["type"] == "local" and a.get("path") == str(vault_path))]
    config.save_device(cfg)
    rep = merge(cfg, [a for a in adapters if a.available()], rebuild=True)
    from .sync.engine import sync

    lines = sync(cfg).lines
    typer.echo(f"promoted to hub at epoch {hub['epoch']}; rebuilt {rep.new_cards} card(s)")
    for line in lines:
        typer.echo(line)


@app.command()
def suppress(card_id: str = typer.Argument(..., help="Card ID to hide from CVs (history kept).")) -> None:
    """Hide a card from merge and compile without deleting it (hub only)."""
    from .hub.merge import merge

    cfg = _hub_cfg()
    f = Path(cfg["vault_path"]) / "suppressed.txt"
    have = set(f.read_text(encoding="utf-8").split()) if f.is_file() else set()
    f.write_text("".join(i + "\n" for i in sorted(have | {card_id})), encoding="utf-8")
    merge(cfg)
    typer.echo(f"suppressed {card_id}")


@app.command()
def purge(
    card_id: str = typer.Argument(..., help="Card ID to erase."),
    yes: bool = typer.Option(False, "--yes", help="Confirm the rewrite."),
) -> None:
    """Erase a card everywhere this device can reach (the one deliberate exception to append-only)."""
    from .sync.engine import purge_local

    if not yes:
        typer.confirm(f"Permanently rewrite files to remove {card_id} from this device and its transports?",
                      abort=True)
    for line in purge_local(_cfg(), {card_id}):
        typer.echo(line)


if __name__ == "__main__":  # pragma: no cover
    app()
