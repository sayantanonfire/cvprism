"""M6: browser-based first-run wizard (localhost only, one-time token)."""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

import pytest

from cvprism import config
from cvprism.setup.web import WizardServer
from tests.conftest import ROOT


@pytest.fixture
def server(home):
    s = WizardServer()
    s.start()
    yield s
    s.stop()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def post(s, fields, token=None):
    data = urllib.parse.urlencode({"token": token or s.token, **fields}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{s.port}/setup", data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def test_form_requires_token(server):
    assert get(f"http://127.0.0.1:{server.port}/")[0] == 403
    code, body = get(server.url)
    assert code == 200 and "<form" in body and 'name="vault"' in body and server.token in body


def test_rejects_foreign_host_header(server):
    code, _ = get(server.url, headers={"Host": "evil.example.com"})
    assert code == 403


def test_successful_setup(server, tmp_path):
    code, body = post(server, {"name": "lab-ws", "role": "hub", "vault": str(tmp_path / "v"), "adapters": "",
                               "watch": str(tmp_path / "proj"), "claude": "on"})
    assert code == 200 and "lab-ws" in body
    cfg = config.load_device()
    assert cfg["name"] == "lab-ws" and cfg["capture"]["watcher"]["paths"] == [str(tmp_path / "proj")]
    assert server.done.is_set()


def test_validation_error_is_shown(server):
    code, body = post(server, {"name": "x", "role": "hub", "vault": str(ROOT / "vault")})
    assert code == 400 and "inside the cvprism code" in body
    assert not server.done.is_set()


def test_wrong_token_on_post(server, tmp_path):
    code, _ = post(server, {"name": "x", "role": "hub", "vault": str(tmp_path / "v")}, token="nope")
    assert code == 403


def test_output_is_escaped(server):
    code, body = post(server, {"name": "<script>alert(1)</script>", "role": "spoke", "adapters": "gdrive:/nowhere"})
    assert code == 400 and "<script>alert(1)</script>" not in body
