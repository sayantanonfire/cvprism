"""Redaction hooks (SECURITY_PRIVACY.md): applied to digests before the LLM and to cards after it."""
from __future__ import annotations

import fnmatch
import importlib
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

SECRET_PATTERNS: dict[str, re.Pattern] = {
    "aws": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    "anthropic": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai": re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_\-]{20,}"),
    "gcp": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{6,}"),
}
_TOKEN = re.compile(r"[A-Za-z0-9+/=_\-]{20,}")
_URL = re.compile(r"\b(?:https?|ftp|s3|gs)://\S+", re.I)
_WIN_PATH = re.compile(r"\b[A-Za-z]:[\\/][^\s'\"<>|]*")
_NIX_PATH = re.compile(r"(?<![\w.])(?:~|/(?:home|Users|mnt|media|var|tmp|opt|srv|data|root|etc))/[^\s'\"<>|]*")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

REDACTED = "[redacted]"


def _entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def find_secrets(text: str, scanners: Iterable[str] | None = None) -> list[tuple[str, str]]:
    names = set(scanners) if scanners else set(SECRET_PATTERNS) | {"high_entropy"}
    hits = [(k, m.group(0)) for k, p in SECRET_PATTERNS.items() if k in names for m in p.finditer(text)]
    if "high_entropy" in names:
        for m in _TOKEN.finditer(text):
            tok = m.group(0)
            classes = sum(bool(re.search(p, tok)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]"))
            if classes >= 3 and _entropy(tok) >= 4.0 and not any(tok in h for _, h in hits):
                hits.append(("high_entropy", tok))
    return hits


def _expand(p: str) -> str:
    return os.path.expanduser(p).replace("\\", "/")


class Redactor:
    def __init__(
        self,
        deny_terms: list[str] | None = None,
        replace: list[dict] | None = None,
        exclude_paths: list[str] | None = None,
        secret_scanners: list[str] | None = None,
        on_secret: str = "drop",
        plugins: list[Callable[[dict], dict | None]] | None = None,
    ):
        self.deny_terms = list(deny_terms or [])
        self.replace = [(re.compile(r["pattern"]), r["with"]) for r in (replace or [])]
        self.exclude_paths = [_expand(p) for p in (exclude_paths or [])]
        self.scanners = secret_scanners
        self.on_secret = on_secret
        self.plugins = list(plugins or [])
        self._deny = [re.compile(r"(?i)" + re.escape(t)) for t in self.deny_terms if t.strip()]

    @classmethod
    def load(cls, path: Path, extra_exclude: list[str] | None = None) -> "Redactor":
        from .. import yamlio

        cfg = yamlio.load(path) if Path(path).is_file() else {}
        cfg = cfg or {}
        plugins = []
        for dotted in cfg.get("plugins", []) or []:
            mod, _, fn = dotted.rpartition(".")
            plugins.append(getattr(importlib.import_module(mod), fn))
        return cls(
            deny_terms=cfg.get("deny_terms"),
            replace=cfg.get("replace"),
            exclude_paths=(cfg.get("exclude_paths") or []) + list(extra_exclude or []),
            secret_scanners=cfg.get("secret_scanners"),
            on_secret=cfg.get("on_secret", "drop"),
            plugins=plugins,
        )

    # ---- paths -------------------------------------------------------------------------------
    def is_excluded_path(self, path: str | None) -> bool:
        if not path:
            return False
        p = _expand(str(path))
        return any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p + "/", pat) for pat in self.exclude_paths)

    # ---- text --------------------------------------------------------------------------------
    def _deny_and_replace(self, text: str) -> tuple[str, bool]:
        hit = False
        for rx in self._deny:
            text, n = rx.subn(REDACTED, text)
            hit = hit or n > 0
        for rx, rep in self.replace:
            text = rx.sub(rep, text)
        return text, hit

    def scrub_text(self, text: str) -> str:
        """For digests: remove secrets, URLs, emails, absolute paths and deny terms."""
        for _, s in find_secrets(text, self.scanners):
            text = text.replace(s, "[secret]")
        text = _URL.sub("[url]", text)
        text = _EMAIL.sub("[email]", text)
        text = _WIN_PATH.sub("[path]", text)
        text = _NIX_PATH.sub("[path]", text)
        text, _ = self._deny_and_replace(text)
        return text

    # ---- cards -------------------------------------------------------------------------------
    def apply_card(self, card: dict) -> dict | None:
        """Return a scrubbed card, or None if it must be dropped (secret found or a plugin vetoed)."""
        fields = [card.get("txt", "")] + list(card.get("meth", [])) + list(card.get("tl", []))
        if any(find_secrets(f, self.scanners) for f in fields) and self.on_secret in ("drop", "quarantine"):
            return None
        out = dict(card)
        flagged = False
        txt, h = self._deny_and_replace(_URL.sub("", out.get("txt", "")))
        flagged |= h
        out["txt"] = " ".join(txt.split())
        meth = []
        for m in out.get("meth", []):
            m2, h = self._deny_and_replace(m)
            flagged |= h
            meth.append(m2)
        out["meth"] = meth
        if flagged:
            out["flags"] = sorted(set(out.get("flags", [])) | {"needs_review"})
        for plugin in self.plugins:
            out = plugin(out)
            if out is None:
                return None
        return out
