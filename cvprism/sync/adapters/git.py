"""Private git repository transport (default). Paths are disjoint per device, so rebases never conflict."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .base import FolderAdapter, Unavailable

_ID = ["-c", "user.name=cvprism", "-c", "user.email=cvprism@localhost", "-c", "commit.gpgsign=false",
       "-c", "core.autocrlf=false"]


class GitAdapter(FolderAdapter):
    kind = "git"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._fresh = False

    def root(self) -> Path:
        return self.state_dir / f"git-{self.name}"

    @property
    def branch(self) -> str:
        return self.spec.get("branch") or "main"

    def _git(self, *args: str, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
        try:
            r = subprocess.run(["git", *_ID, "-C", str(self.root()), *args], capture_output=True, text=True,
                               timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Unavailable(f"git: {e}") from e
        if check and r.returncode != 0:
            raise Unavailable(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[:200]}")
        return r

    def _remote_has_branch(self) -> bool:
        r = subprocess.run(["git", "ls-remote", "--heads", self.spec["remote"], self.branch],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise Unavailable(f"git remote unreachable: {r.stderr.strip()[:200]}")
        return bool(r.stdout.strip())

    def _ensure_clone(self) -> None:
        d = self.root()
        if (d / ".git").is_dir():
            return
        d.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "-q", self.spec["remote"], str(d)], capture_output=True, text=True,
                           timeout=120)
        if r.returncode != 0:
            raise Unavailable(f"git clone failed: {r.stderr.strip()[:200]}")
        self._git("symbolic-ref", "HEAD", f"refs/heads/{self.branch}", check=False)
        attrs = d / ".gitattributes"
        if not attrs.exists():
            attrs.write_text("* -text\n", encoding="utf-8")

    def _before_read(self) -> None:
        if self._fresh:
            return
        self._ensure_clone()
        if self._remote_has_branch():
            self._git("pull", "-q", "--rebase", "origin", self.branch)
        self._fresh = True

    def _after_write(self, message: str) -> None:
        self._git("add", "-A")
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        self._git("commit", "-q", "-m", message)
        for _ in range(3):
            if self._git("push", "-q", "origin", f"HEAD:{self.branch}", check=False).returncode == 0:
                return
            self._git("pull", "-q", "--rebase", "origin", self.branch, check=False)
        raise Unavailable("git push failed after 3 attempts")

    def available(self) -> bool:
        self._fresh = False
        return super().available()

    def status(self):
        st = super().status()
        st.detail = self.spec.get("remote", "")
        return st
