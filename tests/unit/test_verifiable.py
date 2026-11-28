"""Verifiable CV (ADR-015): evidence links, proof levels, private work, verify page."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cvprism import config, paths, yamlio
from cvprism.cli import app
from cvprism.compile.evidence import (
    LinkIndex, bullet_proof, card_proof, check_links, commit_url, normalise_repo_url, short_url,
)
from tests.compile_fixtures import CARDS, PROFILE, make_fixture_vault
from tests.conftest_sync import bare_repo

runner = CliRunner()
PROF = yaml.safe_load(PROFILE)
MCP = next(c for c in CARDS if "mcp-server-development" in c["s"])
DAM = next(c for c in CARDS if c.get("ctx") == "client-x-dam")
SAR = next(c for c in CARDS if c.get("ctx") == "delta-sar" and c.get("r"))
TALK = next(c for c in CARDS if c["k"] == "work" and "science-communication" in c["s"])
PY = next(c for c in CARDS if c["s"] == ["python"])


def cli(*args):
    res = runner.invoke(app, list(args))
    assert res.exit_code == 0, res.output
    return res.output


# ---- URLs ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, norm", [
    ("https://github.com/you/repo.git", "https://github.com/you/repo"),
    ("git@github.com:you/repo.git", "https://github.com/you/repo"),
    ("https://gitlab.com/group/sub/repo/", "https://gitlab.com/group/sub/repo"),
    ("ssh://git@bitbucket.org/team/repo.git", "https://bitbucket.org/team/repo"),
])
def test_normalise_repo_url(raw, norm):
    assert normalise_repo_url(raw) == norm


@pytest.mark.parametrize("repo, url", [
    ("https://github.com/you/repo", "https://github.com/you/repo/commit/9fceb02"),
    ("https://gitlab.com/g/repo", "https://gitlab.com/g/repo/-/commit/9fceb02"),
    ("https://bitbucket.org/t/repo", "https://bitbucket.org/t/repo/commits/9fceb02"),
    ("https://git.example.org/x/repo", None),
])
def test_commit_url_per_host(repo, url):
    assert commit_url(repo, "9fceb02") == url


def test_short_url_is_readable():
    assert short_url("https://github.com/you/flood-copilot/commit/9fceb02") == "github.com/you/flood-copilot/commit/9fceb02"
    s = short_url("https://doi.org/10.1016/j.jhydrol.2023.000001/supplementary/data/very/long/path/x")
    assert len(s) <= 60 and s.startswith("doi.org/")


# ---- proof per card --------------------------------------------------------------------------------

def test_public_project_card_links_to_commit():
    p = card_proof(MCP, PROF, LinkIndex())
    assert p.level == "public" and p.links == ["https://github.com/ashaverma/flood-copilot/commit/9fceb02"]
    assert p.label is None


def test_private_project_keeps_skill_and_gets_label():
    p = card_proof(DAM, PROF, LinkIndex())
    assert p.links == [] and p.label == "private repository" and p.level == "captured"


def test_local_project_has_no_label():
    p = card_proof(SAR, PROF, LinkIndex())
    assert p.links == [] and p.label is None and p.level == "captured"


def test_manual_card_is_self_reported_until_linked():
    assert card_proof(TALK, PROF, LinkIndex()).level == "self-reported"
    idx = LinkIndex({TALK["id"]: ["https://www.youtube.com/watch?v=abc"]})
    p = card_proof(TALK, PROF, idx)
    assert p.level == "public" and p.links == ["https://www.youtube.com/watch?v=abc"]


def test_card_lnk_field_is_used():
    c = dict(PY, lnk=["https://pypi.org/project/hydrotools/"])
    assert card_proof(c, PROF, LinkIndex()).links == ["https://pypi.org/project/hydrotools/"]


def test_public_project_without_commit_ref_links_project():
    c = dict(MCP, ref=None)
    assert card_proof(c, PROF, LinkIndex()).links == ["https://github.com/ashaverma/flood-copilot"]


def test_bullet_proof_combines_cited_cards():
    by_id = {c["id"]: c for c in CARDS}
    b = bullet_proof([DAM["id"], MCP["id"]], by_id, PROF, LinkIndex())
    assert b.links and b.level == "public"                       # any public proof wins
    b = bullet_proof([DAM["id"]], by_id, PROF, LinkIndex())
    assert b.label == "private repository"


def test_check_links_reports_dead_ones():
    dead = check_links(["https://ok.example/a", "https://dead.example/b"],
                       fetch=lambda u: 200 if "ok." in u else 404)
    assert dead == ["https://dead.example/b"]


# ---- CLI: projects and links -----------------------------------------------------------------------

def test_project_set_updates_profile(home, tmp_path):
    make_fixture_vault(tmp_path)
    cli("project", "set", "client-x-dam", "--public", "--url", "https://github.com/acme/dam")
    prof = yamlio.load(tmp_path / "vault" / "profile.yaml")
    p = next(p for p in prof["projects"] if p["ctx"] == "client-x-dam")
    assert p["visibility"] == "public" and p["url"] == "https://github.com/acme/dam"
    cli("project", "set", "new-thing", "--private", "--display", "Internal tool")
    prof = yamlio.load(tmp_path / "vault" / "profile.yaml")
    assert any(p["ctx"] == "new-thing" and p["visibility"] == "private" for p in prof["projects"])
    out = cli("project", "list")
    assert "client-x-dam" in out and "public" in out


def test_project_set_refuses_non_https(home, tmp_path):
    make_fixture_vault(tmp_path)
    res = runner.invoke(app, ["project", "set", "x", "--public", "--url", "javascript:alert(1)"])
    assert res.exit_code != 0


def test_project_map_tags_captured_work(home, device, tmp_path):
    from cvprism.capture.projects import ctx_for_path

    work = tmp_path / "work" / "flood"
    work.mkdir(parents=True)
    cli("project", "map", "flood-copilot", str(work))
    cfg = config.load_device()
    assert ctx_for_path(cfg, str(work / "src" / "app.py")) == "flood-copilot"
    assert ctx_for_path(cfg, str(tmp_path / "elsewhere")) is None


def test_log_with_link_stores_lnk(home, device):
    cli("log", "--raw", "Released hydrotools on PyPI", "--skill", "python", "--depth", "4",
        "--link", "https://pypi.org/project/hydrotools/")
    from cvprism.sync.outbox import Outbox

    card = next(Outbox(paths.outbox_dir(), device["device_id"]).iter_cards())
    assert card["lnk"] == ["https://pypi.org/project/hydrotools/"]


def test_log_rejects_non_https_link(home, device):
    res = runner.invoke(app, ["log", "--raw", "Did a thing well", "--skill", "python", "--link", "file:///etc/passwd"])
    assert res.exit_code != 0


def test_link_command_appends_to_vault(home, tmp_path):
    make_fixture_vault(tmp_path)
    cli("link", TALK["id"], "https://www.youtube.com/watch?v=abc")
    rows = [json.loads(l) for l in (tmp_path / "vault" / "links.jsonl").read_text().splitlines()]
    assert rows[0]["id"] == TALK["id"] and rows[0]["url"].startswith("https://www.youtube.com")
    res = runner.invoke(app, ["link", "c_ffffffffffffffff", "https://x.org"])
    assert res.exit_code != 0                                     # unknown card


# ---- build output ----------------------------------------------------------------------------------

def build(*args):
    out = cli("build", *args)
    return Path(re.search(r"output: (.+)", out).group(1).strip()), out


def test_markdown_shows_links_labels_and_evidence(home, tmp_path):
    make_fixture_vault(tmp_path)
    out, _ = build("--role", "hydrodynamics", "--no-llm", "--format", "md")
    md = (out / "cv.md").read_text(encoding="utf-8")
    assert "[github.com/ashaverma/flood-copilot/commit/9fceb02](https://github.com/ashaverma/flood-copilot/commit/9fceb02)" in md
    dam_line = next(l for l in md.splitlines() if "dam-break" in l.lower())
    assert "*(private repository)*" in dam_line                  # private work still listed
    sar_line = next(l for l in md.splitlines() if "U-Net" in l)
    assert "private" not in sar_line and "](" not in sar_line    # local work: no label, no link
    ev = md.split("## Evidence", 1)[1]
    assert "Public proof" in ev and "Captured" in ev and "private repository" in ev


def test_manifest_lists_every_bullet(home, tmp_path):
    make_fixture_vault(tmp_path)
    out, _ = build("--role", "applied-ai", "--no-llm", "--format", "md")
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["name"] == "Asha Verma" and m["bullets"]
    assert all({"text", "cites", "level"} <= set(b) for b in m["bullets"])
    assert "client-x-dam" not in json.dumps(m)                   # no private slugs


def test_docx_has_blue_hyperlinks(home, tmp_path):
    pytest.importorskip("docx")
    make_fixture_vault(tmp_path)
    out, _ = build("--role", "applied-ai", "--no-llm", "--format", "docx")
    import zipfile

    xml = zipfile.ZipFile(out / "cv.docx").read("word/document.xml").decode("utf-8")
    rels = zipfile.ZipFile(out / "cv.docx").read("word/_rels/document.xml.rels").decode("utf-8")
    assert "<w:hyperlink" in xml and "github.com/ashaverma/flood-copilot/commit/9fceb02" in rels
    assert 'w:val="0052CC"' in xml                                # blue
    assert "private repository" in xml


def test_rendercv_model_has_blue_links_and_verify_connection(home, tmp_path):
    from cvprism.compile.render import to_rendercv

    cv = {"person": {"name": "X", "links": []}, "verify_url": "https://you.github.io/cv",
          "sections": [{"key": "experience", "title": "Experience", "entries": [
              {"kind": "experience", "title": "T", "org": "O", "bullets": [
                  {"text": "Did A", "link": "https://github.com/a/b/commit/1", "label": None},
                  {"text": "Did B", "link": None, "label": "private repository"}]}]}]}
    m = to_rendercv(cv, "classic")
    hl = m["cv"]["sections"]["Experience"][0]["highlights"]
    assert "[github.com/a/b/commit/1](https://github.com/a/b/commit/1)" in hl[0]
    assert hl[1].endswith("*(private repository)*")
    assert m["design"]["colors"]["links"].startswith("rgb(0, 82, 204)")
    assert m["cv"]["custom_connections"][0]["url"] == "https://you.github.io/cv"


# ---- publish + verify -------------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("git") is None, reason="git missing")
def test_publish_and_verify_roundtrip(home, tmp_path):
    from cvprism.compile.verify import verify_pdf

    make_fixture_vault(tmp_path)
    remote = bare_repo(tmp_path / "site.git")
    prof_file = tmp_path / "vault" / "profile.yaml"
    prof = yamlio.load(prof_file)
    prof["verify"] = {"repo": remote, "path": "cv", "url": "https://ashaverma.github.io/cv"}
    yamlio.dump(prof, prof_file)
    out, log = build("--role", "applied-ai", "--no-llm", "--format", "md", "--publish")
    assert "published" in log
    site = tmp_path / "site-check"
    import subprocess

    subprocess.run(["git", "clone", "-q", remote, str(site)], check=True)
    index = (site / "cv" / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((site / "cv" / "manifest.json").read_text(encoding="utf-8"))
    assert "Asha Verma" in index and "github.com/ashaverma/flood-copilot/commit/9fceb02" in index
    assert "proves this file was not changed" in index.lower()
    assert (site / "cv" / "qr.svg").exists()
    # the fingerprint covers the main CV file of the build
    target = out / manifest["file"]
    assert verify_pdf(target, manifest) is True
    tampered = tmp_path / "tampered"
    tampered.write_bytes(target.read_bytes() + b" ")
    assert verify_pdf(tampered, manifest) is False
    res = runner.invoke(app, ["verify", str(target), "--manifest", str(site / "cv" / "manifest.json")])
    assert res.exit_code == 0 and "matches" in res.output
    res = runner.invoke(app, ["verify", str(tampered), "--manifest", str(site / "cv" / "manifest.json")])
    assert res.exit_code != 0 and "does not match" in res.output


def test_publish_without_verify_config_explains(home, tmp_path):
    make_fixture_vault(tmp_path)
    res = runner.invoke(app, ["build", "--role", "applied-ai", "--no-llm", "--format", "md", "--publish"])
    assert res.exit_code != 0 and "verify:" in res.output


def test_evidence_wording_for_unlinked_lines(home, tmp_path):
    make_fixture_vault(tmp_path)
    out, _ = build("--role", "hydrodynamics", "--no-llm", "--format", "md")
    ev = (out / "cv.md").read_text(encoding="utf-8").split("## Evidence", 1)[1]
    survey = next(l for l in ev.splitlines() if "ADCP" in l)
    assert "Self-reported" in survey and "no link yet" in survey
    unet = next(l for l in ev.splitlines() if "U-Net" in l)
    assert "local work" in unet


def test_rendercv_puts_verify_qr_in_header():
    from cvprism.compile.render import to_rendercv

    cv = {"person": {"name": "X"}, "verify_url": "https://you.github.io/cv", "qr_file": "verify-qr.png",
          "sections": []}
    m = to_rendercv(cv, "classic")
    assert m["cv"]["photo"] == "verify-qr.png"
    assert m["design"]["header"]["photo_position"] == "right"
    assert to_rendercv(dict(cv, qr_file=None), "classic")["cv"].get("photo") is None


def test_pdf_with_verify_url_embeds_qr(home, tmp_path):
    pytest.importorskip("rendercv")
    make_fixture_vault(tmp_path)
    prof_file = tmp_path / "vault" / "profile.yaml"
    prof = yamlio.load(prof_file)
    prof["verify"] = {"repo": "unused", "url": "https://ashaverma.github.io/cv"}
    yamlio.dump(prof, prof_file)
    out, log = build("--role", "applied-ai", "--no-llm", "--format", "pdf")
    assert (out / "verify-qr.png").exists()
    import pypdf

    reader = pypdf.PdfReader(str(out / "cv.pdf"))
    assert any(page.images for page in reader.pages)        # the QR is an image on the page
    assert "5/5 passed" in log                              # still ATS-clean
