"""Novelty filter (ADR-011): emit a card only for new skills, depth-ups, new results or new work."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .ids import result_fp, slugify


@dataclass
class _Skill:
    max_d: int = 0
    rh: set[str] = field(default_factory=set)


class Knowledge:
    """What this device knows: hub registry cache ∪ its own outbox."""

    def __init__(self) -> None:
        self.skills: dict[str, _Skill] = {}
        self.ids: set[str] = set()
        self.aliases: dict[str, str] = {}

    @classmethod
    def from_registry(cls, registry: dict | None) -> "Knowledge":
        k = cls()
        for slug, e in ((registry or {}).get("skills") or {}).items():
            k.skills[slug] = _Skill(max_d=int(e.get("max_d", 0)), rh=set(e.get("rh", [])))
            for a in e.get("aliases", []) + [e.get("name", "")]:
                if a:
                    k.aliases[slugify(a)] = slug
        return k

    def add_cards(self, cards: Iterable[dict]) -> "Knowledge":
        for c in cards:
            self.add_card(c)
        return self

    def add_card(self, card: dict) -> None:
        if card.get("id"):
            self.ids.add(card["id"])
        for s in card["s"]:
            sk = self.skills.setdefault(s, _Skill())
            sk.max_d = max(sk.max_d, int(card["d"]))
            if card.get("r"):
                sk.rh.add(result_fp(card["r"]))

    def resolve_alias(self, name: str) -> str:
        slug = slugify(name)
        return self.aliases.get(slug, slug)


def decide(card: dict, known: Knowledge) -> str | None:
    """Return the novelty reason (stored as card['why']) or None if nothing new."""
    if card.get("id") in known.ids:
        return None
    if card["k"] == "work":
        return "work"
    slugs = card["s"]
    if any(s not in known.skills for s in slugs):
        return "new_skill"
    if any(int(card["d"]) > known.skills[s].max_d for s in slugs):
        return "depth_up"
    if card.get("r") and any(result_fp(card["r"]) not in known.skills[s].rh for s in slugs):
        return "new_result"
    return None
