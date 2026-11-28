"""Signed builds (ADR-017) with the SSH key people already use for GitHub.

`ssh-keygen -Y sign/verify` (OpenSSH >= 8.2) with namespace "cvprism-cv". Public keys can be fetched from
https://github.com/<user>.keys, so a recruiter needs nothing but OpenSSH to check who built a CV.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

NAMESPACE = "cvprism-cv"
_KEY = re.compile(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com)\s+[A-Za-z0-9+/=]{20,}"
                  r"(\s+[^\r\n;|&`$]*)?$")
_PRINCIPAL = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")


class SignError(RuntimeError):
    pass


def _ssh_keygen() -> str:
    exe = shutil.which("ssh-keygen")
    if not exe:
        raise SignError("ssh-keygen not found: install OpenSSH (Git for Windows includes it)")
    return exe


def sign_file(path: Path, key: Path) -> Path:
    """Write <path>.sig. `key` may be a private key, or a public key whose private half is in ssh-agent."""
    path, key = Path(path), Path(key).expanduser()
    if not key.exists():
        raise SignError(f"signing key not found: {key}")
    sig = path.with_name(path.name + ".sig")
    sig.unlink(missing_ok=True)
    r = subprocess.run([_ssh_keygen(), "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(path)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not sig.exists():
        raise SignError(f"signing failed: {(r.stderr or r.stdout).strip()[:300]}")
    return sig


def allowed_signers_line(principal: str, public_key: str) -> str:
    key = " ".join(public_key.split())
    if not _PRINCIPAL.match(principal) or not _KEY.match(key):
        raise ValueError("not a valid principal / SSH public key")
    return f'{principal} namespaces="{NAMESPACE}" {key}'


def verify_signature(path: Path, sig: Path, principal: str, public_keys: list[str]) -> bool:
    lines = []
    for k in public_keys:
        try:
            lines.append(allowed_signers_line(principal, k))
        except ValueError:
            continue
    if not lines or not Path(sig).exists():
        return False
    with tempfile.TemporaryDirectory() as td:
        allowed = Path(td) / "allowed_signers"
        allowed.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with Path(path).open("rb") as data:
            r = subprocess.run([_ssh_keygen(), "-Y", "verify", "-f", str(allowed), "-I", principal, "-n", NAMESPACE,
                                "-s", str(sig)], stdin=data, capture_output=True, timeout=60)
    return r.returncode == 0


def github_keys(user: str) -> list[str]:
    if not _PRINCIPAL.match(user):
        raise ValueError("invalid GitHub username")
    with urllib.request.urlopen(f"https://github.com/{user}.keys", timeout=20) as r:
        return [ln.strip() for ln in r.read().decode("utf-8").splitlines() if ln.strip()]
