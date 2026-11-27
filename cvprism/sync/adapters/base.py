"""Adapter interface and the folder-backed implementation shared by local/gdrive/usb/syncthing (ADR-005).

Invariants (docs/SYNC.md): a device writes only inbox/<own-id>/ (I1); inbox files are append-only
complete lines (I2); every transport root holds vault.json and mismatches are refused (I5).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


class VaultMismatch(RuntimeError):
    pass


class Unavailable(RuntimeError):
    pass


@dataclass
class PushReport:
    files: int = 0
    lines: int = 0


@dataclass
class AdapterStatus:
    kind: str
    name: str
    available: bool
    detail: str = ""
    backlog_files: int = 0


def complete_lines(data: bytes) -> list[str]:
    """Complete, non-empty lines only. An unterminated last line is a partial write (F2)."""
    parts = data.split(b"\n")[:-1]
    return [p.decode("utf-8", errors="replace").strip() for p in parts if p.strip()]


def line_id(line: str) -> str | None:
    try:
        return json.loads(line).get("id")
    except (json.JSONDecodeError, AttributeError):
        return None


def union_lines(base: list[str], extra: list[str], drop_ids: set[str] = frozenset()) -> list[str]:
    seen, out = set(), []
    for ln in base + extra:
        key = line_id(ln) or ln
        if key in seen or key in drop_ids:
            continue
        seen.add(key)
        out.append(ln)
    return out


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class FolderAdapter:
    kind = "local"

    def __init__(self, spec: dict, *, device_id: str, vault_id: str | None, state_dir: Path):
        self.spec = spec
        self.name = spec.get("name") or spec["type"]
        self.device_id = device_id
        self.vault_id = vault_id
        self.state_dir = Path(state_dir)

    # ---- location ----------------------------------------------------------------------------
    def root(self) -> Path | None:
        p = self.spec.get("path")
        return Path(p).expanduser() if p else None

    def _before_read(self) -> None:
        """Hook for transports that must refresh (git pull)."""

    def _after_write(self, message: str) -> None:
        """Hook for transports that must commit/upload (git push)."""

    def read_vault_id(self) -> str | None:
        r = self.root()
        if r is None or not (r / "vault.json").is_file():
            return None
        try:
            return json.loads((r / "vault.json").read_text(encoding="utf-8"))["vault_id"]
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def available(self) -> bool:
        try:
            self._before_read()
        except Unavailable:
            return False
        vid = self.read_vault_id()
        return vid is not None and (self.vault_id is None or vid == self.vault_id)

    def _check(self) -> Path:
        self._before_read()
        r = self.root()
        vid = self.read_vault_id()
        if r is None or vid is None:
            raise Unavailable(f"{self.name}: transport not reachable or not initialised")
        if self.vault_id and vid != self.vault_id:
            raise VaultMismatch(f"{self.name}: transport belongs to vault {vid}, not {self.vault_id}")
        return r

    def init_transport(self) -> None:
        """Hub only: create the transport layout with vault.json."""
        self._before_read()
        r = self.root()
        if r is None:
            raise Unavailable(f"{self.name}: no location")
        vid = self.read_vault_id()
        if vid and vid != self.vault_id:
            raise VaultMismatch(f"{self.name}: transport belongs to vault {vid}")
        if not vid:
            r.mkdir(parents=True, exist_ok=True)
            atomic_write(r / "vault.json", json.dumps({"v": 1, "vault_id": self.vault_id}) + "\n")
            (r / "inbox").mkdir(exist_ok=True)
            self._after_write("cvprism: initialise transport")

    # ---- cursors -----------------------------------------------------------------------------
    def _cursor_file(self) -> Path:
        return self.state_dir / f"cursor-{self.name}.json"

    def _cursors(self) -> dict:
        f = self._cursor_file()
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}

    def _save_cursors(self, c: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self._cursor_file(), json.dumps(c))

    @staticmethod
    def _sig(path: Path) -> list:
        data = path.read_bytes()
        return [len(data), hashlib.sha256(data).hexdigest()]

    def backlog(self, outbox) -> int:
        c = self._cursors()
        return sum(1 for f in outbox.files() if c.get(f.name) != self._sig(f))

    # ---- spoke side --------------------------------------------------------------------------
    def push(self, outbox, purged: set[str] = frozenset()) -> PushReport:
        root = self._check()
        rep = PushReport()
        cursors = self._cursors()
        dest = root / "inbox" / self.device_id
        for f in outbox.files():
            sig = self._sig(f)
            if cursors.get(f.name) == sig:
                continue
            remote = dest / f.name
            remote_lines = complete_lines(remote.read_bytes()) if remote.is_file() else []
            local_lines = complete_lines(f.read_bytes())
            merged = union_lines(remote_lines, local_lines, set(purged))
            if merged != remote_lines:
                atomic_write(remote, "".join(ln + "\n" for ln in merged))
                rep.files += 1
                rep.lines += len(merged) - len(remote_lines)
            cursors[f.name] = sig
        if purged:
            pf = dest / "purged.txt"
            have = set(pf.read_text(encoding="utf-8").split()) if pf.is_file() else set()
            if not set(purged) <= have:
                atomic_write(pf, "".join(i + "\n" for i in sorted(have | set(purged))))
                rep.files += 1
        if rep.files:
            self._after_write(f"cvprism: {self.device_id} +{rep.lines} cards")
        self._save_cursors(cursors)
        return rep

    def purge_own(self, ids: set[str]) -> int:
        """Deliberate exception to append-only (SECURITY_PRIVACY.md): rewrite own inbox without ids."""
        root = self._check()
        n = 0
        for f in sorted((root / "inbox" / self.device_id).glob("*.jsonl")):
            lines = complete_lines(f.read_bytes())
            kept = [ln for ln in lines if line_id(ln) not in ids]
            if kept != lines:
                atomic_write(f, "".join(ln + "\n" for ln in kept))
                n += 1
        self._save_cursors({})
        if n:
            self._after_write(f"cvprism: purge {len(ids)} card(s) from {self.device_id}")
        return n

    def read_json(self, name: str) -> dict | None:
        r = self.root()
        if r is None or not (r / name).is_file():
            return None
        try:
            return json.loads((r / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def pull(self) -> dict | None:
        self._check()
        return self.read_json("registry.json")

    # ---- hub side ----------------------------------------------------------------------------
    def inbox_files(self) -> Iterator[tuple[str, Path]]:
        root = self._check()
        inbox = root / "inbox"
        if not inbox.is_dir():
            return
        for d in sorted(p for p in inbox.iterdir() if p.is_dir()):
            for f in sorted(d.iterdir()):
                if f.is_file() and (f.suffix == ".jsonl" or f.name == "purged.txt") and not f.name.startswith("."):
                    yield d.name, f

    def iter_inbox_cards(self) -> Iterator[dict]:
        for _, f in self.inbox_files():
            if f.suffix == ".jsonl":
                for ln in complete_lines(f.read_bytes()):
                    try:
                        yield json.loads(ln)
                    except json.JSONDecodeError:
                        continue

    def publish(self, files: dict[str, str]) -> None:
        root = self._check()
        changed = False
        for name, text in files.items():
            p = root / name
            if p.is_file() and p.read_text(encoding="utf-8") == text:
                continue
            atomic_write(p, text)
            changed = True
        if changed:
            self._after_write("cvprism: hub publish " + ", ".join(sorted(files)))

    def list_files(self) -> list[str]:
        r = self.root()
        if r is None or not r.is_dir():
            return []
        return sorted(p.relative_to(r).as_posix() for p in r.rglob("*")
                      if p.is_file() and ".git" not in p.relative_to(r).parts)

    def status(self) -> AdapterStatus:
        ok = self.available()
        r = self.root()
        return AdapterStatus(kind=self.kind, name=self.name, available=ok, detail=str(r) if r else "not found")
