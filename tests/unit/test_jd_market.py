"""M5: JD tailoring with gap report, and market-phrase intel."""
from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from cvprism.cli import app
from cvprism.compile.jd import extract_jd_deterministic, html_to_text, map_to_registry
from tests.compile_fixtures import make_fixture_vault
from tests.conftest import FIXTURES

runner = CliRunner()
JD = FIXTURES / "jd" / "ml_engineer.txt"


def cli(*args):
    res = runner.invoke(app, list(args))
    assert res.exit_code == 0, res.output
    return res.output


def registry(tmp_path):
    return json.loads((tmp_path / "vault" / "registry.json").read_text(encoding="utf-8"))


def test_deterministic_jd_extraction_finds_known_skills():
    jd = extract_jd_deterministic(JD.read_text(encoding="utf-8"))
    for slug in ["python", "pytorch", "docker", "kubernetes", "retrieval-augmented-generation",
                 "mcp-server-development", "llm-agents", "hec-ras", "aws", "google-earth-engine", "deep-learning"]:
        assert slug in jd["skills"], slug
    assert jd["title"].startswith("Senior Applied AI Engineer")


def test_map_to_registry_splits_covered_and_gaps(home, tmp_path):
    make_fixture_vault(tmp_path)
    covered, gaps = map_to_registry(["python", "kubernetes", "hec-ras", "aws", "rag"], registry(tmp_path))
    assert covered == ["python", "hec-ras", "retrieval-augmented-generation"]
    assert gaps == ["kubernetes", "aws"]


def test_build_for_jd_covers_jd_skills_and_reports_gaps(home, tmp_path):
    """M5 criteria 1 and 2."""
    make_fixture_vault(tmp_path)
    out = cli("build", "--jd", str(JD), "--no-llm", "--format", "md")
    d = Path(re.search(r"output: (.+)", out).group(1).strip())
    md = (d / "cv.md").read_text(encoding="utf-8")
    skills_block = md.split("## Skills", 1)[1].split("\n## ", 1)[0].lower()
    jd = extract_jd_deterministic(JD.read_text(encoding="utf-8"))
    reg = registry(tmp_path)
    covered, gaps = map_to_registry(jd["skills"], reg)
    names = {s: reg["skills"][s]["name"].lower() for s in covered}
    hit = [s for s in covered if names[s] in skills_block]
    assert len(hit) >= 0.8 * len(covered), (hit, covered)
    for g in gaps:                                                  # never claims a missing skill
        assert g.replace("-", " ") not in skills_block
    gap_md = (d / "gaps.md").read_text(encoding="utf-8")
    assert "Kubernetes" in gap_md and "AWS" in gap_md or "Amazon Web Services" in gap_md
    assert "Python" not in gap_md.split("## No evidence", 1)[1].split("##", 1)[0]


def test_market_extract_is_deterministic_with_cache(home, tmp_path, fake_claude):
    """M5 criterion 3."""
    make_fixture_vault(tmp_path)
    for p in sorted((FIXTURES / "market").glob("*.txt")):
        cli("market", "add", "applied-ai", str(p))
    fake = fake_claude(json.dumps({"type": "result", "structured_output": {"phrases": [
        "retrieval-augmented generation", "LLM agents", "evaluation harness", "MLOps", "Kubernetes"]}}))
    cli("market", "extract", "applied-ai")
    first = (tmp_path / "vault" / "market" / "applied-ai.json").read_text(encoding="utf-8")
    calls = len(fake.calls())
    assert calls == 3
    cli("market", "extract", "applied-ai")
    assert len(fake.calls()) == calls                               # cached: no new LLM calls
    second = (tmp_path / "vault" / "market" / "applied-ai.json").read_text(encoding="utf-8")
    assert json.loads(first)["phrases"] == json.loads(second)["phrases"]
    top = json.loads(first)["phrases"][0]
    assert top["count"] == 3 and top["share"] == 1.0


def test_market_phrases_feed_role_vocabulary(home, tmp_path):
    from cvprism.compile.market import vocabulary_for

    make_fixture_vault(tmp_path)
    m = tmp_path / "vault" / "market"
    (m / "applied-ai.json").write_text(json.dumps({"role": "applied-ai", "postings": 3, "phrases": [
        {"phrase": "evaluation harness", "count": 3, "share": 1.0},
        {"phrase": "rare thing", "count": 1, "share": 0.33}]}), encoding="utf-8")
    vocab = vocabulary_for("applied-ai", tmp_path / "vault", min_share=0.5)
    assert vocab == ["evaluation harness"]


def test_html_to_text_strips_markup():
    html = "<html><head><style>x{}</style><script>alert(1)</script></head><body><h1>ML Engineer</h1><p>Python &amp; RAG</p></body></html>"
    t = html_to_text(html)
    assert "ML Engineer" in t and "Python & RAG" in t and "alert" not in t and "x{}" not in t


def test_short_words_are_not_language_false_positives():
    jd = extract_jd_deterministic("You will go to market fast and r&d matters. We use Go and R daily.")
    assert "go" in jd["skills"] and "r" in jd["skills"]
    jd2 = extract_jd_deterministic("You will go to market fast.")
    assert "go" not in jd2["skills"] and "r" not in jd2["skills"]


def test_gap_report_points_to_related_evidence(home, tmp_path):
    from cvprism.compile.jd import gaps_md

    make_fixture_vault(tmp_path)
    text = gaps_md({"title": "T"}, ["hec-ras"], ["hydraulic-modelling"], registry(tmp_path))
    line = next(ln for ln in text.splitlines() if ln.startswith("- Hydraulic modelling"))
    assert "related evidence:" in line and "HEC-RAS" in line and "Flood modelling" in line
