"""M4: role profiles, selection, honesty gate, rendering (acceptance criteria 1-6)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cvprism.cli import app
from cvprism.compile.bibtex import parse_bibtex
from cvprism.compile.gate import check_bullet
from cvprism.compile.roles import load_role, starter_roles
from cvprism.compile.select import select_cards
from cvprism.schemas import validate
from tests.compile_fixtures import BIB, CARDS, make_fixture_vault

runner = CliRunner()
BY_ID = {c["id"]: c for c in CARDS}
SETUP = next(c for c in CARDS if c["r"] and c["r"]["m"] == "scenario setup time")
F1 = next(c for c in CARDS if c["r"] and c["r"]["m"] == "f1 score")


# ---- honesty gate (ADR-009) ---------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Cut 2D flood scenario setup from 120 to 15 minutes by automating HEC-RAS",
    "Reduced scenario setup time by 87.5% through HEC-RAS automation",       # derived (120-15)/120
    "Made scenario setup 8x faster",                                            # derived ratio 120/15
    "Automated HEC-RAS 2D runs with Python 3 and Sentinel-1 inputs",            # numbers inside names
    "Automated flood scenarios in 2025",                                         # a year
])
def test_gate_accepts_traceable_numbers(text):
    ok, reasons = check_bullet({"text": text, "cites": [SETUP["id"]]}, BY_ID, facts=[])
    assert ok, reasons


@pytest.mark.parametrize("text", [
    "Cut scenario setup time by 73%",
    "Cut setup from 120 to 10 minutes",
    "Saved dozens of engineer-hours per week",
    "Served 2M+ requests",
])
def test_gate_rejects_untraceable_numbers(text):
    ok, reasons = check_bullet({"text": text, "cites": [SETUP["id"]]}, BY_ID, facts=[])
    assert not ok and reasons


def test_gate_requires_existing_citations():
    assert not check_bullet({"text": "Built things", "cites": []}, BY_ID, facts=[])[0]
    assert not check_bullet({"text": "Built things", "cites": ["c_ffffffffffffffff"]}, BY_ID, facts=[])[0]


def test_gate_accepts_numbers_from_profile_facts():
    ok, _ = check_bullet({"text": "Mentored 4 junior engineers", "cites": [SETUP["id"]]}, BY_ID,
                         facts=[{"id": "f_team", "text": "Mentored 4 junior engineers"}])
    assert ok


def test_gate_decimal_metric():
    assert check_bullet({"text": "Reached an F1 score of 0.91 on flood extent", "cites": [F1["id"]]}, BY_ID, [])[0]
    assert not check_bullet({"text": "Reached an F1 score of 0.95", "cites": [F1["id"]]}, BY_ID, [])[0]


# ---- roles and selection -----------------------------------------------------------------------

def test_starter_roles_are_valid():
    names = starter_roles()
    assert {"academic", "industry-ds", "applied-ai", "hydrodynamics", "geospatial"} <= set(names)
    for n in names:
        validate("role", load_role(n, vault=None))


def test_role_extends_and_vault_override(tmp_path):
    (tmp_path / "roles").mkdir()
    (tmp_path / "roles" / "my-ai.yaml").write_text(
        "v: 1\nid: my-ai\ntitle: ML Engineer\nextends: applied-ai\nlimits: {pages: 1}\n", encoding="utf-8")
    r = load_role("my-ai", vault=tmp_path)
    assert r["title"] == "ML Engineer" and r["limits"]["pages"] == 1
    assert r["sections"] == load_role("applied-ai", vault=None)["sections"]   # inherited
    assert r["limits"]["bullets_per_position"] == load_role("applied-ai", vault=None)["limits"]["bullets_per_position"]


def test_selection_respects_include_exclude_and_limit():
    role = {"v": 1, "id": "t", "title": "T", "sections": ["experience"],
            "include": {"dom": ["applied-ai", "hydrodynamics"], "min_depth": 2, "since": "2019"},
            "exclude": {"ctx": ["client-x-dam"]}, "limits": {"cards_to_llm": 3}}
    picked = select_cards(CARDS, role)
    assert len(picked) == 3                                     # criterion 4: bounded LLM input
    assert all(c["ctx"] != "client-x-dam" for c in picked)
    assert all(c["d"] >= 2 for c in picked)
    assert all(c["t"] >= "2019" for c in picked)
    assert all(set(c["dom"]) & {"applied-ai", "hydrodynamics"} for c in picked)


def test_selection_prefers_results_and_vocabulary():
    role = {"v": 1, "id": "t", "title": "T", "sections": ["experience"], "include": {"min_depth": 1},
            "weights": {"results": 1.0, "depth": 0.2, "recency": 0.2}, "vocabulary": ["hec-ras"],
            "limits": {"cards_to_llm": 2}}
    picked = select_cards(CARDS, role)
    assert SETUP in picked


def test_bibtex_parser():
    entries = parse_bibtex(BIB)
    assert entries[0]["title"] == "Coupled 1D-2D hydrodynamic modelling of urban floods"
    assert entries[0]["authors"] == ["Verma, A.", "Sen, R.", "Gupta, K."]
    assert entries[1]["venue"] == "IGARSS 2022" and entries[1]["year"] == "2022"


# ---- end-to-end builds ---------------------------------------------------------------------------

def build(*args):
    res = runner.invoke(app, ["build", *args])
    assert res.exit_code == 0, res.output
    m = re.search(r"output: (.+)", res.output)
    return Path(m.group(1).strip()), res.output


def test_deterministic_build_cites_every_bullet(home, tmp_path):
    make_fixture_vault(tmp_path)
    out, log = build("--role", "applied-ai", "--no-llm", "--format", "md")
    md = (out / "cv.md").read_text(encoding="utf-8")
    ev = (out / "evidence.md").read_text(encoding="utf-8")
    assert "Asha Verma" in md and "Senior Data Scientist" in md
    bullets = [ln for ln in md.splitlines() if ln.startswith("- ")]
    assert bullets
    cited = re.findall(r"c_[0-9a-f]{16}", ev)
    assert cited and set(cited) <= set(BY_ID)                    # criterion 2
    assert "c_" not in md                                        # citations live in evidence.md, not the CV


def test_confidential_projects_show_display_only(home, tmp_path):
    make_fixture_vault(tmp_path)
    out, _ = build("--role", "hydrodynamics", "--no-llm", "--format", "md")
    md = (out / "cv.md").read_text(encoding="utf-8")
    assert "client-x-dam" not in md and "flood-copilot" not in md   # criterion 6: no raw ctx slugs
    assert "Dam-break study for a utility client" in md


def test_publications_render_with_highlight(home, tmp_path):
    make_fixture_vault(tmp_path)
    out, _ = build("--role", "academic", "--no-llm", "--format", "md")
    md = (out / "cv.md").read_text(encoding="utf-8")
    assert "Coupled 1D-2D hydrodynamic modelling of urban floods" in md
    assert "**Verma, A.**" in md                                  # criterion 5


def test_llm_invented_metric_is_rejected_and_reported(home, tmp_path, fake_claude):
    make_fixture_vault(tmp_path)
    draft = {
        "summary": {"text": "Applied AI scientist bridging LLM tooling and flood modelling",
                    "cites": [SETUP["id"]]},
        "positions": [{"id": "acme", "bullets": [
            {"text": "Cut scenario setup from 120 to 15 minutes by automating HEC-RAS", "cites": [SETUP["id"]]},
            {"text": "Reduced flood forecast error by 42% with an LLM copilot", "cites": [SETUP["id"]]},
        ]}],
        "projects": [], "skills": [],
    }
    fake = fake_claude(json.dumps({"type": "result", "structured_output": draft}))
    out, log = build("--role", "applied-ai", "--format", "md")
    md = (out / "cv.md").read_text(encoding="utf-8")
    assert "120 to 15 minutes" in md
    assert "42%" not in md                                        # criterion 3
    assert "42%" in (out / "rejected.md").read_text(encoding="utf-8")
    assert "rejected 1" in log
    sent = fake.calls()[0]["stdin"]
    assert sent.count('"id": "c_') <= 60                          # criterion 4 at the LLM boundary


def test_docx_output(home, tmp_path):
    pytest.importorskip("docx")
    make_fixture_vault(tmp_path)
    out, _ = build("--role", "industry-ds", "--no-llm", "--format", "docx")
    import docx

    text = "\n".join(p.text for p in docx.Document(str(out / "cv.docx")).paragraphs)
    assert "Asha Verma" in text and "Senior Data Scientist" in text


def test_pdf_respects_page_limit(home, tmp_path):
    pytest.importorskip("rendercv")
    make_fixture_vault(tmp_path)
    out, log = build("--role", "applied-ai", "--no-llm", "--format", "pdf")
    assert (out / "cv.pdf").exists()
    meta = json.loads((out / "build.json").read_text(encoding="utf-8"))
    assert 1 <= meta["pages"] <= meta["page_limit"]               # criterion 1


def test_build_on_spoke_is_refused(home, tmp_path):
    from cvprism import config

    cfg = make_fixture_vault(tmp_path)
    cfg["role"] = "spoke"
    cfg.pop("vault_path")
    config.save_device(cfg)
    res = runner.invoke(app, ["build", "--role", "applied-ai"])
    assert res.exit_code != 0 and "hub" in res.output


@pytest.mark.parametrize("slug, name", [("adcp-survey", "ADCP survey"), ("sentinel-1-sar", "Sentinel-1 SAR"),
                                        ("gis-pipelines", "GIS pipelines"), ("llm-evaluation", "LLM evaluation"),
                                        ("bayesian-calibration", "Bayesian calibration")])
def test_display_names_for_unknown_slugs(slug, name):
    from cvprism.hub.registry import display_name

    assert display_name(slug) == name


def test_rendercv_year_only_dates_are_ints():
    from cvprism.compile.render import to_rendercv

    cv = {"person": {"name": "X"}, "sections": [{"key": "publications", "title": "Publications", "entries": [
        {"kind": "publication", "title": "T", "authors": ["A"], "year": "2023"}]}]}
    assert to_rendercv(cv, "classic")["cv"]["sections"]["Publications"][0]["date"] == 2023


def test_orcid_bulk_to_bibtex_dedupes_by_doi():
    from cvprism.compile.orcid import merge_into_bib, works_to_entries
    from tests.conftest import FIXTURES

    bulk = json.loads((FIXTURES / "orcid" / "bulk.json").read_text(encoding="utf-8"))
    entries = works_to_entries(bulk)
    assert [e["year"] for e in entries] == ["2023", "2024"]
    assert entries[1]["authors"] == ["Asha Verma"] and entries[1]["type"] == "inproceedings"
    merged, added = merge_into_bib(BIB, entries)
    assert added == 1                                    # the 2023 DOI already exists in pubs.bib
    titles = [e["title"] for e in parse_bibtex(merged)]
    assert "A brand-new SAR paper" in titles and len(titles) == 3
