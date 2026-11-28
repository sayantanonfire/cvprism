"""`cvprism app`: local browser app for non-developers (ADR-018)."""
from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

import pytest

from cvprism import config, paths, yamlio
from cvprism.app.server import AppServer
from cvprism.sync.outbox import Outbox
from tests.compile_fixtures import make_fixture_vault
from tests.conftest import FIXTURES


class Client:
    def __init__(self, server):
        self.s = server
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar),
                                              _NoRedirect())

    def url(self, path):
        return f"http://127.0.0.1:{self.s.port}{path}"

    def req(self, path, data=None, headers=None, method=None):
        r = urllib.request.Request(self.url(path), data=data, headers=headers or {}, method=method)
        try:
            with self.op.open(r, timeout=60) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def login(self):
        code, _, h = self.req(f"/k/{self.s.token}")
        assert code == 303, code
        return self

    def get(self, path):
        code, body, h = self.req(path)
        return code, body.decode("utf-8", "replace"), h

    def post(self, path, fields):
        data = urllib.parse.urlencode({"csrf": self.s.token, **fields}).encode()
        code, body, h = self.req(path, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
        return code, body.decode("utf-8", "replace"), h

    def upload(self, path, field, filename, content, extra=None):
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in {"csrf": self.s.token, **(extra or {})}.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
                     f"Content-Type: application/octet-stream\r\n\r\n".encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        code, body, h = self.req(path, data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return code, body.decode("utf-8", "replace"), h


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


@pytest.fixture
def hub(home, tmp_path):
    cfg = make_fixture_vault(tmp_path)
    s = AppServer()
    s.start()
    yield s, cfg, tmp_path
    s.stop()


# ---- access control -----------------------------------------------------------------------------------

def test_requires_key_then_sets_cookie(hub):
    s, _, _ = hub
    c = Client(s)
    assert c.get("/")[0] == 403
    assert c.req("/k/wrong")[0] == 403
    c.login()
    code, body, _ = c.get("/")
    assert code == 200 and "Asha Verma" in body


def test_foreign_host_rejected(hub):
    s, _, _ = hub
    c = Client(s).login()
    code, _, _ = c.req("/", headers={"Host": "evil.example"})
    assert code == 403


def test_post_without_csrf_rejected(hub):
    s, _, _ = hub
    c = Client(s).login()
    data = urllib.parse.urlencode({"what": "Built a thing well", "skill": "python"}).encode()
    code, _, _ = c.req("/add", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert code == 403


# ---- pages -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path, text", [("/", "Add evidence"), ("/add", "What did you do?"),
                                        ("/import", "LinkedIn"), ("/projects", "flood-copilot"),
                                        ("/build", "Applied AI Scientist"), ("/cards", "Proof")])
def test_pages_render(hub, path, text):
    s, _, _ = hub
    code, body, h = Client(s).login().get(path)
    assert code == 200 and text in body
    assert "default-src 'none'" in h.get("Content-Security-Policy", "")


# ---- actions ---------------------------------------------------------------------------------------------

def test_add_evidence_creates_card(hub):
    s, cfg, _ = hub
    code, body, _ = Client(s).login().post("/add", {
        "what": "Led a 10-day sediment sampling campaign on the Hooghly", "skill": "sediment sampling",
        "depth": "4", "work": "on", "link": "https://doi.org/10.5281/zenodo.123", "result": "", "use_ai": ""})
    assert code == 200 and "Saved" in body
    card = next(c for c in Outbox(paths.outbox_dir(), cfg["device_id"]).iter_cards() if "sediment" in c["txt"].lower())
    assert card["k"] == "work" and card["lnk"] == ["https://doi.org/10.5281/zenodo.123"]


def test_add_evidence_shows_errors_escaped(hub):
    s, _, _ = hub
    code, body, _ = Client(s).login().post("/add", {"what": "<b>x</b>", "skill": "", "depth": "2"})
    assert code == 400 and "<b>x</b>" not in body and "&lt;b&gt;x&lt;/b&gt;" in body


def test_project_visibility_form(hub):
    s, _, tmp = hub
    code, body, _ = Client(s).login().post("/projects", {"ctx": "client-x-dam", "visibility": "public",
                                                         "url": "https://github.com/acme/dam"})
    assert code == 200
    prof = yamlio.load(tmp / "vault" / "profile.yaml")
    p = next(p for p in prof["projects"] if p["ctx"] == "client-x-dam")
    assert p["visibility"] == "public" and p["url"] == "https://github.com/acme/dam"


def test_build_for_role_and_download(hub):
    s, _, _ = hub
    c = Client(s).login()
    code, body, _ = c.post("/build", {"role": "applied-ai", "jd": "", "use_ai": "", "formats": "md"})
    assert code == 200 and "Your CV is ready" in body and "ATS read-back" in body
    href = re.search(r'href="(/download/[^"]+/cv\.md)"', body).group(1)
    code, data, h = c.req(href)
    assert code == 200 and b"Asha Verma" in data and "attachment" in h.get("Content-Disposition", "")


def test_build_for_pasted_job_posting(hub):
    s, _, _ = hub
    jd = (FIXTURES / "jd" / "ml_engineer.txt").read_text(encoding="utf-8")
    code, body, _ = Client(s).login().post("/build", {"role": "", "jd": jd, "use_ai": "", "formats": "md"})
    assert code == 200 and "Keyword match" in body and "No evidence" in body


def test_download_cannot_escape_build_folder(hub):
    s, _, _ = hub
    c = Client(s).login()
    for bad in ["/download/..%2F..%2Fprofile.yaml", "/download/x/../../profile.yaml", "/download/%2e%2e/vault.json"]:
        assert c.req(bad)[0] in (400, 403, 404)


def test_import_linkedin_upload(hub, tmp_path):
    s, cfg, _ = hub
    z = tmp_path / "li.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in (FIXTURES / "linkedin").iterdir():
            zf.write(f, f.name)
    code, body, _ = Client(s).login().upload("/import", "file", "Basic_LinkedInDataExport.zip", z.read_bytes(),
                                             {"kind": "linkedin", "use_ai": ""})
    assert code == 200 and "new card" in body
    assert any(c["src"] == "import" for c in Outbox(paths.outbox_dir(), cfg["device_id"]).iter_cards())


def test_import_cv_upload(hub):
    s, cfg, _ = hub
    code, body, _ = Client(s).login().upload("/import", "file", "old_cv.md",
                                             (FIXTURES / "old_cv.md").read_bytes(), {"kind": "cv", "use_ai": ""})
    assert code == 200 and "new card" in body


def test_spoke_sees_add_but_not_build(home, device, tmp_path):
    cfg = config.load_device()
    cfg["role"] = "spoke"
    cfg.pop("vault_path", None)
    config.save_device(cfg)
    s = AppServer()
    s.start()
    try:
        c = Client(s).login()
        assert c.get("/add")[0] == 200
        code, body, _ = c.get("/build")
        assert code == 200 and "built on your main computer" in body
    finally:
        s.stop()
