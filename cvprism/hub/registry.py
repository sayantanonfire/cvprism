"""Deterministic registry build from merged cards plus the seed taxonomy (SCHEMA.md: skill registry)."""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from ..novelty.ids import result_fp


@lru_cache(maxsize=1)
def seed() -> dict:
    return json.loads(resources.files("cvprism.data").joinpath("seed_skills.json").read_text(encoding="utf-8"))


ACRONYMS = {"adcp", "ai", "api", "aws", "cfd", "cnn", "cv", "dem", "eo", "gis", "gpu", "hpc", "json", "llm", "ml",
            "mcp", "nlp", "ocr", "rag", "rest", "rnn", "sar", "sql", "uav", "gcp", "etl", "ci", "cd", "iot", "qa",
            "ui", "ux", "lidar", "insar", "ndvi", "swat", "hec", "ras", "dvc", "orcid"}
PROPER = {"bayesian", "python", "fourier", "monte", "carlo", "markov", "gaussian", "kalman", "sentinel", "landsat",
          "docker", "kubernetes", "linux", "windows", "excel", "matlab", "fortran", "julia", "rust", "java",
          "javascript", "typescript", "google", "azure", "github", "claude", "pytorch", "tensorflow", "keras"}


def display_name(slug: str) -> str:
    """Readable name for a slug with no seed entry: 'sentinel-1-sar' -> 'Sentinel-1 SAR'."""
    out: list[str] = []
    for i, w in enumerate(slug.split("-")):
        if w.isdigit() and out:
            out[-1] += "-" + w
            continue
        if w in ACRONYMS:
            out.append(w.upper())
        elif w in PROPER or (i == 0 and not out):
            out.append(w.capitalize())
        else:
            out.append(w)
    return " ".join(out)


_title = display_name


def build_registry(cards: list[dict], *, vault_id: str, epoch: int, rev: int, generated: str,
                   seed_skills: dict | None = None) -> dict:
    sd = seed() if seed_skills is None else seed_skills
    skills: dict[str, dict] = {}
    for c in sorted(cards, key=lambda c: (c["t"], c["id"])):
        for s in c["s"]:
            e = skills.get(s)
            if e is None:
                meta = sd.get(s, {})
                e = skills[s] = {
                    "name": meta.get("name") or _title(s),
                    "aliases": list(meta.get("aliases", [])),
                    "cat": meta.get("cat", "other"),
                    "dom": [],
                    "max_d": 0,
                    "first": c["t"],
                    "last": c["t"],
                    "n": 0,
                    "rh": [],
                    "parent": meta.get("parent"),
                }
            e["max_d"] = max(e["max_d"], int(c["d"]))
            e["first"] = min(e["first"], c["t"])
            e["last"] = max(e["last"], c["t"])
            e["n"] += 1
            for d in c.get("dom", []):
                if d not in e["dom"]:
                    e["dom"].append(d)
            if c.get("r"):
                fp = result_fp(c["r"])
                if fp not in e["rh"]:
                    e["rh"].append(fp)
    for e in skills.values():
        e["dom"].sort()
        e["rh"].sort()
        e["aliases"].sort()
    return {"v": 1, "vault_id": vault_id, "epoch": int(epoch), "rev": int(rev), "generated": generated,
            "skills": dict(sorted(skills.items()))}


def seed_knowledge_aliases() -> dict[str, str]:
    """alias -> slug for the seed taxonomy, so spokes normalise names even before any registry exists."""
    out = {}
    for slug, meta in seed().items():
        for a in meta.get("aliases", []) + [meta.get("name", "")]:
            if a:
                out[a] = slug
    return out
