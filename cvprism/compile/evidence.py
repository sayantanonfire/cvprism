"""Evidence links and proof levels (ADR-015).

Visibility lives on the project (hub profile); links are resolved at build time so a project made
public later gains links for all its past cards. Private and local work always keeps its skills.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

LEVELS = ("public", "confirmed", "captured", "self-reported")
def no_link_text(level: str | None) -> str:
    """What the Evidence table says when a line has no public link and no private label."""
    return "no link yet" if level == "self-reported" else "local work"


LEVEL_LABEL = {"public": "Public proof", "confirmed": "Third-party confirmed", "captured": "Captured",
               "self-reported": "Self-reported"}
PRIVATE_LABEL = "private repository"
_HTTPS = re.compile(r"^https://[^\s]{4,500}$")


def is_https(url: str | None) -> bool:
    return bool(url) and bool(_HTTPS.match(url))


def normalise_repo_url(raw: str) -> str:
    u = raw.strip()
    m = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.+)$", u)
    if m:
        u = f"https://{m.group(1)}/{m.group(2)}"
    u = re.sub(r"^http://", "https://", u)
    u = u.rstrip("/")
    return u[:-4] if u.endswith(".git") else u


def commit_url(repo_url: str, sha: str) -> str | None:
    repo = normalise_repo_url(repo_url)
    host = re.sub(r"^https://", "", repo).split("/")[0].lower()
    if host == "github.com":
        return f"{repo}/commit/{sha}"
    if host == "gitlab.com":
        return f"{repo}/-/commit/{sha}"
    if host == "bitbucket.org":
        return f"{repo}/commits/{sha}"
    return None


def short_url(url: str, limit: int = 60) -> str:
    s = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
    if len(s) <= limit:
        return s
    head, tail = s[: limit - 18], s[-15:]
    return f"{head}…{tail}"


class LinkIndex:
    """Manual links from vault/links.jsonl (hub-owned, append-only)."""

    def __init__(self, links: dict[str, list[str]] | None = None):
        self.links = {k: list(v) for k, v in (links or {}).items()}

    @classmethod
    def load(cls, vault: Path) -> "LinkIndex":
        f = Path(vault) / "links.jsonl"
        idx: dict[str, list[str]] = {}
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if is_https(row.get("url")):
                    idx.setdefault(row["id"], [])
                    if row["url"] not in idx[row["id"]]:
                        idx[row["id"]].append(row["url"])
        return cls(idx)

    def get(self, card_id: str) -> list[str]:
        return self.links.get(card_id, [])


@dataclass
class Proof:
    level: str
    links: list[str] = field(default_factory=list)
    label: str | None = None


def _project(profile: dict, ctx: str | None) -> dict | None:
    if not ctx:
        return None
    return next((p for p in profile.get("projects") or [] if p.get("ctx") == ctx), None)


def card_proof(card: dict, profile: dict, index: LinkIndex) -> Proof:
    links: list[str] = []
    for u in list(card.get("lnk") or []) + index.get(card["id"]):
        if is_https(u) and u not in links:
            links.append(u)
    proj = _project(profile, card.get("ctx"))
    vis = (proj or {}).get("visibility")
    label = None
    if vis == "public" and is_https((proj or {}).get("url")):
        m = re.match(r"^git:[^@]+@([0-9a-f]{7,40})$", card.get("ref") or "")
        url = commit_url(proj["url"], m.group(1)) if m else None
        url = url or normalise_repo_url(proj["url"])
        if url not in links:
            links.append(url)
    elif vis == "private":
        label = PRIVATE_LABEL
    if links:
        level = "public"
    elif card.get("src") in ("claude_session", "git_commit", "watcher"):
        level = "captured"
    else:
        level = "self-reported"
    return Proof(level=level, links=links, label=None if links else label)


def bullet_proof(cites: Iterable[str], cards_by_id: dict, profile: dict, index: LinkIndex) -> Proof:
    proofs = [card_proof(cards_by_id[c], profile, index) for c in cites if c in cards_by_id]
    if not proofs:
        return Proof(level="self-reported")
    best = min(proofs, key=lambda p: LEVELS.index(p.level))
    links = [u for p in proofs for u in p.links]
    links = list(dict.fromkeys(links))
    label = None if links else next((p.label for p in proofs if p.label), None)
    return Proof(level=best.level, links=links, label=label)


def _fetch_status(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "cvprism-linkcheck"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        if e.code in (403, 405):  # some sites refuse HEAD; retry with GET
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "cvprism-linkcheck"}),
                                            timeout=15) as r:
                    return r.status
            except Exception:  # noqa: BLE001
                return e.code
        return e.code
    except Exception:  # noqa: BLE001
        return 0


def check_links(urls: Iterable[str], fetch: Callable[[str], int] = _fetch_status) -> list[str]:
    """Return the links that do not open (status not 2xx/3xx)."""
    dead = []
    for u in dict.fromkeys(urls):
        status = fetch(u)
        if not (200 <= int(status or 0) < 400):
            dead.append(u)
    return dead
