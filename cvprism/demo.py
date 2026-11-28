"""`cvprism demo`: a self-contained showcase on a synthetic person. Touches no device config."""
from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

from . import vault
from .compile.build import build_cv
from .compile.jd import build_for_jd
from .hub.merge import read_cards
from .hub.registry import build_registry

ROLES = ("applied-ai", "academic", "hydrodynamics")


def make_demo_vault(root: Path) -> dict:
    vp = Path(root) / "demo-vault"
    if vp.exists():
        shutil.rmtree(vp)
    vid = vault.init_vault(vp)
    src = resources.files("cvprism.data").joinpath("demo")
    for name in ("profile.yaml", "pubs.bib", "cards.jsonl", "sample_jd.txt"):
        (vp / name).write_text(src.joinpath(name).read_text(encoding="utf-8"), encoding="utf-8")
    reg = build_registry(read_cards(vp), vault_id=vid, epoch=1, rev=1, generated=vault.utcnow())
    (vp / "registry.json").write_text(json.dumps(reg, indent=1), encoding="utf-8")
    return {"v": 1, "device_id": "demo-0000", "name": "demo", "role": "hub", "vault_id": vid,
            "vault_path": str(vp), "extraction": {}, "adapters": []}


def run_demo(out: Path, *, use_llm: bool = False, formats: list[str] | None = None) -> list[tuple[str, Path, list[str]]]:
    cfg = make_demo_vault(out)
    results = []
    for role in ROLES:
        r = build_cv(cfg, role, use_llm=use_llm, formats=formats)
        results.append((role, r.out_dir, r.log))
    jd = Path(cfg["vault_path"]) / "sample_jd.txt"
    r = build_for_jd(cfg, str(jd), use_llm=use_llm, formats=formats)
    results.append(("job posting (sample_jd.txt)", r.out_dir, r.log))
    return results
