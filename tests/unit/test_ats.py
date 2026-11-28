"""ADR-016: ATS read-back and keyword match."""
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cvprism.cli import app
from cvprism.compile.ats import ats_checks, keyword_match, normalise
from tests.compile_fixtures import make_fixture_vault
from tests.conftest import FIXTURES

runner = CliRunner()

CV = {
    "person": {"name": "Asha Verma", "email": "asha@example.org"},
    "sections": [
        {"key": "experience", "title": "Experience", "entries": [
            {"kind": "experience", "title": "Scientist", "org": "Acme", "bullets": [
                {"text": "Built an MCP server for HEC-RAS", "link": "https://github.com/a/flood-copilot/commit/9fceb02"},
                {"text": "Designed a retrieval-augmented generation pipeline", "link": None}]}]},
        {"key": "skills", "title": "Skills", "entries": []},
    ],
}
GOOD = ("Asha Verma\nasha@example.org\nExperience\nScientist, Acme\nBuilt an MCP server for HEC-RAS "
        "(github.com/a/flood-\ncopilot/commit/9fceb02)\nDesigned a retrieval-augmented genera-\ntion pipeline\nSkills\nPython")


def by_name(checks):
    return {c.name: c for c in checks}


def test_normalise_survives_hyphenation_and_wrapping():
    assert normalise("retrieval-augmented genera-\ntion") == normalise("retrieval-augmented generation")


def test_good_text_passes_all_checks():
    checks = by_name(ats_checks(GOOD, CV, size_bytes=50_000))
    assert all(c.ok for c in checks.values()), [c for c in checks.values() if not c.ok]


def test_lost_bullet_and_hidden_link_are_reported():
    bad = "Asha Verma\nasha@example.org\nExperience\nBuilt an MCP server for HEC-RAS\nSkills"
    checks = by_name(ats_checks(bad, CV, size_bytes=50_000))
    assert not checks["bullets readable"].ok and "1 of 2" in checks["bullets readable"].detail
    assert not checks["links visible as text"].ok


def test_contact_must_be_near_top():
    late = ("x " * 400) + GOOD
    assert not by_name(ats_checks(late, CV, size_bytes=1))["contact details at the top"].ok


def test_large_file_flagged():
    assert not by_name(ats_checks(GOOD, CV, size_bytes=3_000_000))["file size under 2 MB"].ok


def test_keyword_match():
    km = keyword_match(GOOD, jd_skills={"python": "Python", "kubernetes": "Kubernetes", "hec-ras": "HEC-RAS",
                                        "docker": "Docker"},
                       evidence={"python", "hec-ras", "docker"})
    assert km["matched"] == ["HEC-RAS", "Python"]
    assert km["opportunities"] == ["Docker"]          # evidence exists, but not on this CV
    assert km["gaps"] == ["Kubernetes"]               # no evidence: never added
    assert km["score"] == 50


def test_build_writes_quality_and_ats_reports(home, tmp_path):
    make_fixture_vault(tmp_path)
    res = runner.invoke(app, ["build", "--jd", str(FIXTURES / "jd" / "ml_engineer.txt"), "--no-llm",
                              "--format", "md,docx"])
    assert res.exit_code == 0, res.output
    out = Path(re.search(r"output: (.+)", res.output).group(1).strip())
    assert "ATS check:" in res.output and "keyword match" in res.output
    ats = (out / "ats.md").read_text(encoding="utf-8")
    assert "bullets readable" in ats and "Keyword match" in ats
    assert (out / "quality.md").exists()


def test_real_pdf_reads_back_cleanly(home, tmp_path):
    pytest.importorskip("rendercv")
    pytest.importorskip("pypdf")
    make_fixture_vault(tmp_path)
    res = runner.invoke(app, ["build", "--role", "applied-ai", "--no-llm", "--format", "pdf"])
    assert res.exit_code == 0, res.output
    out = Path(re.search(r"output: (.+)", res.output).group(1).strip())
    ats = (out / "ats.md").read_text(encoding="utf-8")
    assert "Read from: cv.pdf" in ats
    assert "✗" not in ats, ats


def test_short_skill_names_need_whole_words():
    text = "Processed archives in Google Earth Engine. AWS Certified."
    km = keyword_match(text, jd_skills={"go": "Go", "r": "R", "aws": "Amazon Web Services"}, evidence=set())
    assert km["matched"] == ["Amazon Web Services"]
    assert set(km["gaps"]) == {"Go", "R"}
