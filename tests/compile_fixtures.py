"""A realistic multidisciplinary fixture vault for compile tests (synthetic person, no real data)."""
from __future__ import annotations

import json
from pathlib import Path

from cvprism import config, vault
from cvprism.hub.registry import build_registry
from cvprism.novelty.ids import card_id

PROFILE = """v: 1
person:
  name: Asha Verma
  email: asha@example.org
  location: Kolkata, India
  links:
    - {label: GitHub, url: "https://github.com/ashaverma"}
positions:
  - {id: acme, title: Senior Data Scientist, org: Acme Water, location: Pune, start: "2024-03", end: null,
     dom: [applied-ai, hydrodynamics]}
  - {id: iit, title: Research Fellow, org: IIT Example, start: "2019-07", end: "2024-02",
     dom: [academic, hydrodynamics, geospatial]}
projects:
  - {ctx: flood-copilot, display: "LLM copilot for flood forecasting", position: acme}
  - {ctx: client-x-dam, display: "Dam-break study for a utility client", position: acme, confidential: true}
  - {ctx: delta-sar, display: "SAR flood mapping of the Ganges delta", position: iit}
education:
  - {degree: PhD, field: Civil Engineering, institution: IIT Example, end: "2023", thesis: "Coupled 1D-2D flood modelling"}
publications: {bibtex: pubs.bib, highlight_name: "Verma, A."}
certifications:
  - {name: "AWS Certified Machine Learning - Specialty", issuer: AWS, date: "2025-06"}
facts:
  - {id: f_team, text: "Mentored 4 junior engineers"}
"""

BIB = r"""@article{verma2023coupled,
  title = {Coupled {1D-2D} hydrodynamic modelling of urban floods},
  author = {Verma, A. and Sen, R. and Gupta, K.},
  journal = {Journal of Hydrology},
  year = {2023},
  doi = {10.1016/j.jhydrol.2023.000001}
}

@inproceedings{sen2022sar,
  title = "Sentinel-1 SAR flood mapping with deep learning",
  author = "Sen, R. and Verma, A.",
  booktitle = {IGARSS 2022},
  year = 2022
}
"""


def _card(**kw) -> dict:
    c = {"v": 1, "k": "skill", "why": "new_skill", "r": None, "ctx": None, "meth": [], "tl": [], "dom": [],
         "dev": "lab-ws-3c1d", "src": "claude_session", "conf": 0.9, "flags": [], "lang": "en"}
    c.update(kw)
    if c["r"] is not None and c["k"] != "work":
        c["k"] = "result"
    c["id"] = card_id(c)
    return c


CARDS = [
    _card(s=["mcp-server-development"], d=3, ctx="flood-copilot", t="2025-09-02T10:00:00Z", dom=["applied-ai"],
          txt="Built a Model Context Protocol server exposing HEC-RAS 2D runs as tools for an LLM assistant",
          tl=["python", "fastmcp"]),
    _card(s=["retrieval-augmented-generation"], d=3, ctx="flood-copilot", t="2025-10-01T10:00:00Z",
          dom=["applied-ai"], txt="Designed a retrieval-augmented generation pipeline over flood bulletins"),
    _card(s=["hec-ras", "flood-modelling"], d=4, ctx="flood-copilot", t="2025-11-01T10:00:00Z",
          dom=["hydrodynamics"], txt="Cut scenario setup time for 2D flood simulations through automation",
          r={"m": "scenario setup time", "val": 15, "unit": "min", "base": 120, "dir": "down"}),
    _card(s=["hec-ras"], d=3, ctx="client-x-dam", t="2024-06-01T10:00:00Z", dom=["hydrodynamics"],
          txt="Ran a dam-break inundation analysis with unsteady 2D hydraulic modelling"),
    _card(s=["sentinel-1-sar", "deep-learning"], d=3, ctx="delta-sar", t="2022-03-01T10:00:00Z",
          dom=["geospatial", "academic"], txt="Trained a U-Net on Sentinel-1 SAR imagery to map flood extent",
          r={"m": "f1 score", "val": 0.91, "unit": "", "dir": "abs"}),
    _card(s=["google-earth-engine"], d=2, ctx="delta-sar", t="2021-05-01T10:00:00Z", dom=["geospatial"],
          txt="Processed multi-year SAR archives in Google Earth Engine"),
    _card(k="work", s=["science-communication"], d=5, t="2023-04-20T10:00:00Z", dom=["academic"],
          txt="Presented coupled flood modelling results at EGU General Assembly 2023", src="manual"),
    _card(k="work", s=["adcp-survey"], d=4, t="2020-01-15T10:00:00Z", dom=["hydrodynamics", "academic"],
          txt="Led a 10-day ADCP field survey of estuarine currents", src="manual"),
    _card(s=["python"], d=2, t="2019-08-01T10:00:00Z", dom=["applied-ai"], src="git_commit",
          txt="Wrote Python tooling for hydrological data pipelines"),
    _card(s=["docker"], d=1, t="2018-01-01T10:00:00Z", dom=["devops"], txt="Containerised a small web service"),
]


def make_fixture_vault(tmp_path: Path) -> dict:
    vp = tmp_path / "vault"
    vid = vault.init_vault(vp)
    cfg = config.new_device_config(name="hub", role="hub", vault_id=vid, vault_path=str(vp))
    config.save_device(cfg)
    (vp / "profile.yaml").write_text(PROFILE, encoding="utf-8")
    (vp / "pubs.bib").write_text(BIB, encoding="utf-8")
    (vp / "cards.jsonl").write_text("".join(json.dumps(c) + "\n" for c in CARDS), encoding="utf-8")
    reg = build_registry(CARDS, vault_id=vid, epoch=1, rev=1, generated="2026-11-27T00:00:00Z")
    (vp / "registry.json").write_text(json.dumps(reg), encoding="utf-8")
    return cfg
