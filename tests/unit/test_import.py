"""M6: bootstrap a vault from a LinkedIn export or an existing CV."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from cvprism import config, paths, yamlio
from cvprism.cli import app
from cvprism.sync.outbox import Outbox
from tests.conftest import FIXTURES

runner = CliRunner()


def cli(*args):
    res = runner.invoke(app, list(args))
    assert res.exit_code == 0, res.output
    return res.output


def cards(cfg):
    return list(Outbox(paths.outbox_dir(), cfg["device_id"]).iter_cards())


def test_linkedin_import_fills_profile_and_cards(home, device, tmp_path):
    out = cli("import-linkedin", str(FIXTURES / "linkedin"), "--no-llm")
    prof = yamlio.load(tmp_path / "my-vault" / "profile.yaml")
    assert prof["person"]["name"] == "Asha Verma"
    assert prof["person"]["location"] == "Kolkata, West Bengal, India"
    titles = [(p["title"], p["org"], p["start"], p.get("end")) for p in prof["positions"]]
    assert ("Senior Data Scientist", "Acme Water", "2024-03", None) in titles
    assert ("Research Fellow", "IIT Example", "2019-07", "2024-02") in titles
    assert prof["education"][0]["institution"] == "IIT Example"
    assert prof["certifications"][0]["issuer"] == "Amazon Web Services (AWS)"
    cs = cards(device)
    listed = [c for c in cs if c["d"] == 1]
    assert {s for c in listed for s in c["s"]} >= {"python", "pytorch", "hydraulic-modelling"}
    assert all(c["src"] == "import" and "needs_review" in c["flags"] for c in cs)
    work = [c for c in cs if c["d"] >= 2]
    acme = next(c for c in work if "hec-ras" in c["s"])
    assert acme["t"].startswith("2024-03") and "120 to 15 minutes" in acme["txt"]
    assert "position(s)" in out


def test_linkedin_import_is_idempotent(home, device, tmp_path):
    cli("import-linkedin", str(FIXTURES / "linkedin"), "--no-llm")
    n = len(cards(device))
    prof1 = (tmp_path / "my-vault" / "profile.yaml").read_text(encoding="utf-8")
    cli("import-linkedin", str(FIXTURES / "linkedin"), "--no-llm")
    assert len(cards(device)) == n
    assert (tmp_path / "my-vault" / "profile.yaml").read_text(encoding="utf-8") == prof1


def test_linkedin_zip_is_accepted(home, device, tmp_path):
    import zipfile

    z = tmp_path / "Basic_LinkedInDataExport.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in (FIXTURES / "linkedin").iterdir():
            zf.write(f, f.name)
    cli("import-linkedin", str(z), "--no-llm")
    assert len(cards(device)) > 0


def test_cv_import_creates_cards_from_bullets(home, device):
    out = cli("import-cv", str(FIXTURES / "old_cv.md"), "--no-llm")
    cs = cards(device)
    txts = [c["txt"] for c in cs]
    assert any("retrieval-augmented generation" in t for t in txts)
    assert any("87%" in t for t in txts)
    assert not any("weekly meetings" in t for t in txts)       # no recognisable skill -> skipped
    assert all(c["src"] == "import" and "needs_review" in c["flags"] for c in cs)
    assert "card(s)" in out


def test_cv_import_docx(home, device, tmp_path):
    import pytest

    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("Built Docker images for a FastAPI service", style="List Bullet")
    p = tmp_path / "cv.docx"
    d.save(str(p))
    cli("import-cv", str(p), "--no-llm")
    assert any("fastapi" in c["s"] for c in cards(device))
