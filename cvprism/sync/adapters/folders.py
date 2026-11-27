"""Folder-like transports: local, gdrive (any desktop-synced folder), usb drop-box, syncthing."""
from __future__ import annotations

import os
import platform
import string
import urllib.request
from pathlib import Path

from .base import AdapterStatus, FolderAdapter


class LocalAdapter(FolderAdapter):
    kind = "local"


class GDriveAdapter(FolderAdapter):
    """Google Drive / OneDrive / Dropbox desktop folders: plain file I/O, no API (SYNC.md)."""

    kind = "gdrive"

    def _before_read(self) -> None:
        # Force hydration of "online-only" placeholders by touching the inbox listing.
        r = self.root()
        if r is not None and (r / "inbox").is_dir():
            try:
                for _ in (r / "inbox").iterdir():
                    pass
            except OSError:
                pass


def usb_candidate_mounts() -> list[Path]:
    env = os.environ.get("CVPRISM_USB_ROOTS")
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p]
    system = platform.system()
    if system == "Windows":
        return [Path(f"{d}:/") for d in string.ascii_uppercase[3:] if os.path.exists(f"{d}:/")]
    if system == "Darwin":
        base = Path("/Volumes")
        return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    user = os.environ.get("USER", "")
    out = []
    for base in (Path("/media") / user, Path("/run/media") / user, Path("/mnt")):
        if base.is_dir():
            out += sorted(p for p in base.iterdir() if p.is_dir())
    return out


class USBAdapter(FolderAdapter):
    """A drop-box folder on removable media; available only while the right drive is mounted."""

    kind = "usb"

    def root(self) -> Path | None:
        marker = self.spec.get("volume_marker") or "cvprism-dropbox"
        fallback = foreign = None
        for m in usb_candidate_mounts():
            d = m / marker
            try:
                if not d.is_dir():
                    continue
            except OSError:
                continue
            vj = d / "vault.json"
            if vj.is_file():
                if self.vault_id is None:
                    return d
                try:
                    if self.vault_id in vj.read_text(encoding="utf-8"):
                        return d
                except OSError:
                    continue
                foreign = foreign or d  # another vault's stick: reported as a mismatch (SYNC.md S12)
            elif fallback is None:
                fallback = d  # empty drop-box: usable by the hub's init_transport
        return fallback or foreign

    def push(self, outbox, purged=frozenset()):
        rep = super().push(outbox, purged)
        try:  # flush directory entries before the user yanks the stick
            fd = os.open(str(self.root()), os.O_RDONLY)
            os.fsync(fd)
            os.close(fd)
        except (OSError, AttributeError, TypeError):
            pass
        return rep


class SyncthingAdapter(FolderAdapter):
    """Plain folder shared by Syncthing; cvprism never reimplements transport (ADR-006)."""

    kind = "syncthing"

    def status(self) -> AdapterStatus:
        st = super().status()
        try:
            with urllib.request.urlopen("http://127.0.0.1:8384/rest/noauth/health", timeout=1) as r:
                st.detail += " (syncthing running)" if r.status == 200 else " (syncthing not responding)"
        except OSError:
            st.detail += " (syncthing not running on this device)"
        return st
