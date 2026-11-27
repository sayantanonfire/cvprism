"""Folder watcher for opted-in paths only (ARCHITECTURE: capture). Emits dependency/tool *names*, never contents."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import threading
import time
from pathlib import Path, PurePath

from .. import paths
from .queue import Queue

_SIGNAL_NAMES = {"pyproject.toml", "package.json", "environment.yml", "environment.yaml", "Pipfile",
                 "Cargo.toml", "go.mod", ".mcp.json", "SKILL.md", "dvc.yaml", "MLproject"}
_REQ = re.compile(r"^requirements[\w.\-]*\.txt$", re.I)
_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)")
_IMPORT = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", re.M)


def is_signal_file(name: str) -> bool:
    return name in _SIGNAL_NAMES or bool(_REQ.match(name)) or name.endswith(".ipynb")


def file_kind(name: str) -> str:
    if _REQ.match(name):
        return "requirements.txt"
    if name.endswith(".ipynb"):
        return "notebook"
    return name


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pep508(spec: str) -> str | None:
    m = _PEP508_NAME.match(spec)
    return _norm(m.group(1)) if m else None


def _toml(text: str) -> dict:
    try:
        import tomllib  # py311+
    except ImportError:  # pragma: no cover - py310
        return {}
    try:
        return tomllib.loads(text)
    except Exception:  # noqa: BLE001
        return {}


def _pyproject(text: str) -> set[str]:
    data = _toml(text)
    specs: list[str] = []
    if data:
        proj = data.get("project", {})
        specs += proj.get("dependencies", []) or []
        for group in (proj.get("optional-dependencies") or {}).values():
            specs += group
        poetry = data.get("tool", {}).get("poetry", {})
        specs += [k for k in (poetry.get("dependencies") or {}) if k != "python"]
    else:  # fallback for Python 3.10: quoted specs inside dependency arrays
        for block in re.findall(r"dependencies\s*=\s*\[(.*?)\]", text, re.S) + \
                re.findall(r"^\w+\s*=\s*\[(.*?)\]", text.split("optional-dependencies", 1)[-1], re.S | re.M):
            specs += re.findall(r"[\"']([^\"']+)[\"']", block)
    return {n for n in (_pep508(s) for s in specs) if n}


def dependency_names(path: Path) -> set[str]:
    path = Path(path)
    name = path.name
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    if _REQ.match(name):
        out = set()
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            n = _pep508(line)
            if n:
                out.add(n)
        return out
    if name == "pyproject.toml":
        return _pyproject(text)
    if name == "package.json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return set()
        return {k.lower() for sec in ("dependencies", "devDependencies", "peerDependencies")
                for k in (data.get(sec) or {})}
    if name in ("environment.yml", "environment.yaml"):
        out = set()
        for line in text.splitlines():
            m = re.match(r"^\s*-\s*([A-Za-z0-9][A-Za-z0-9._\-]*)\s*(?:[=<>!~].*)?$", line)
            if m and m.group(1) not in ("pip", "python"):
                out.add(_norm(m.group(1)))
        return out
    if name == "Pipfile":
        data = _toml(text)
        return {_norm(k) for sec in ("packages", "dev-packages") for k in (data.get(sec) or {})}
    if name == "Cargo.toml":
        data = _toml(text)
        return {k.lower() for sec in ("dependencies", "dev-dependencies") for k in (data.get(sec) or {})}
    if name == "go.mod":
        return {m.lower() for m in re.findall(r"^\s*(?:require\s+)?([\w.\-]+/[\w.\-/]+)\s+v[\d.]+", text, re.M)}
    if name == ".mcp.json":
        try:
            return {f"mcp:{k}" for k in (json.loads(text).get("mcpServers") or {})}
        except json.JSONDecodeError:
            return set()
    if name == "SKILL.md":
        m = re.search(r"^---\s*\n.*?^name:\s*([^\n]+)$.*?^---", text, re.S | re.M)
        return {f"skill:{m.group(1).strip()}"} if m else set()
    if name == "dvc.yaml":
        return {"tool:dvc"}
    if name == "MLproject":
        return {"tool:mlflow"}
    if name.endswith(".ipynb"):
        try:
            nb = json.loads(text)
        except json.JSONDecodeError:
            return set()
        out = set()
        for cell in nb.get("cells", []):
            if cell.get("cell_type") == "code":
                src = cell.get("source", "")
                src = "".join(src) if isinstance(src, list) else str(src)
                out |= {m.lower() for m in _IMPORT.findall(src)}
        lang = ((nb.get("metadata") or {}).get("kernelspec") or {}).get("language")
        if lang:
            out.add(f"lang:{lang.lower()}")
        return out
    return set()


def _key(path: Path) -> str:
    return hashlib.sha256(Path(path).resolve().as_posix().encode("utf-8")).hexdigest()[:20]


class SignalScanner:
    def __init__(self, watch_paths: list[str], ignore: list[str]):
        self.roots = [Path(p).expanduser().resolve() for p in watch_paths]
        self.ignore = list(ignore)
        self.state_file = paths.home() / "state" / "watch.json"
        self.state: dict[str, list[str]] = (
            json.loads(self.state_file.read_text(encoding="utf-8")) if self.state_file.is_file() else {}
        )

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state), encoding="utf-8")

    def _root_of(self, p: Path) -> Path | None:
        for r in self.roots:
            try:
                p.relative_to(r)
                return r
            except ValueError:
                continue
        return None

    def _ignored(self, p: Path) -> bool:
        s = p.as_posix()
        return any(fnmatch.fnmatch(s, pat) for pat in self.ignore)

    def iter_signal_files(self):
        for r in self.roots:
            if not r.is_dir():
                continue
            for p in r.rglob("*"):
                if p.is_file() and is_signal_file(p.name) and not self._ignored(p):
                    yield p

    def baseline(self) -> int:
        """Record current state without emitting: existing deps are not news."""
        n = 0
        for p in self.iter_signal_files():
            self.state[_key(p)] = sorted(dependency_names(p))
            n += 1
        self._save()
        return n

    def handle(self, path: Path) -> bool:
        p = Path(path).resolve()
        root = self._root_of(p)
        if root is None or not is_signal_file(p.name) or self._ignored(p) or not p.is_file():
            return False
        names = dependency_names(p)
        k = _key(p)
        prev = set(self.state.get(k, []))
        added = sorted(names - prev)
        self.state[k] = sorted(names)
        self._save()
        if not added:
            return False
        rel = p.relative_to(root).parts
        project = rel[0] if len(rel) > 1 else root.name
        Queue(paths.queue_dir()).enqueue(
            "watcher",
            key=f"{k}:{hashlib.sha256(','.join(added).encode()).hexdigest()[:12]}",
            payload={"file_kind": file_kind(p.name), "added": added, "project": PurePath(project).name},
        )
        return True


def run_observer(scanner: SignalScanner, debounce_s: int, stop: threading.Event) -> None:
    """Watch with watchdog; debounce bursts of editor writes."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    pending: dict[str, float] = {}
    lock = threading.Lock()

    class H(FileSystemEventHandler):
        def on_any_event(self, event):  # noqa: N802
            if event.is_directory:
                return
            for attr in ("src_path", "dest_path"):
                pth = getattr(event, attr, None)
                if pth and is_signal_file(Path(pth).name):
                    with lock:
                        pending[pth] = time.monotonic()

    obs = Observer()
    for r in scanner.roots:
        if r.is_dir():
            obs.schedule(H(), str(r), recursive=True)
    obs.start()
    try:
        while not stop.is_set():
            now = time.monotonic()
            with lock:
                ready = [p for p, t in pending.items() if now - t >= debounce_s]
                for p in ready:
                    pending.pop(p)
            for p in ready:
                try:
                    scanner.handle(Path(p))
                except Exception:  # noqa: BLE001 - keep watching
                    pass
            stop.wait(1.0)
    finally:
        obs.stop()
        obs.join(timeout=5)
