"""Signed builds (ADR-017) and the open manifest schema (docs/spec)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cvprism import yamlio
from cvprism.cli import app
from cvprism.compile.sign import allowed_signers_line, sign_file, verify_signature
from cvprism.schemas import validate
from tests.compile_fixtures import make_fixture_vault

runner = CliRunner()


def _ssh_sign_supported() -> bool:
    if not shutil.which("ssh-keygen"):
        return False
    r = subprocess.run(["ssh-keygen", "-Y", "sign"], capture_output=True, text=True)
    return "Too few arguments" in (r.stderr + r.stdout) or "usage" in (r.stderr + r.stdout).lower()


needs_ssh = pytest.mark.skipif(not _ssh_sign_supported(), reason="ssh-keygen -Y not available")


@pytest.fixture
def keypair(tmp_path):
    key = tmp_path / "id_test"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", str(key)], check=True)
    return key, (tmp_path / "id_test.pub").read_text().strip()


@needs_ssh
def test_sign_and_verify_roundtrip(tmp_path, keypair):
    key, pub = keypair
    f = tmp_path / "manifest.json"
    f.write_text('{"a": 1}\n', encoding="utf-8")
    sig = sign_file(f, key)
    assert sig.exists() and "BEGIN SSH SIGNATURE" in sig.read_text()
    assert verify_signature(f, sig, "asha", [pub]) is True
    f.write_text('{"a": 2}\n', encoding="utf-8")
    assert verify_signature(f, sig, "asha", [pub]) is False


@needs_ssh
def test_wrong_key_fails(tmp_path, keypair):
    key, _ = keypair
    other = tmp_path / "other"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)], check=True)
    f = tmp_path / "m.json"
    f.write_text("{}\n", encoding="utf-8")
    sig = sign_file(f, key)
    assert verify_signature(f, sig, "asha", [(tmp_path / "other.pub").read_text().strip()]) is False


def test_allowed_signers_line_rejects_garbage():
    assert allowed_signers_line("asha", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample") == \
        'asha namespaces="cvprism-cv" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample'
    with pytest.raises(ValueError):
        allowed_signers_line("asha", "not a key; rm -rf /")


@needs_ssh
def test_build_sign_and_cli_verify(home, tmp_path, keypair):
    key, pub = keypair
    make_fixture_vault(tmp_path)
    prof_file = tmp_path / "vault" / "profile.yaml"
    prof = yamlio.load(prof_file)
    prof["verify"] = {"repo": "unused", "url": "https://ashaverma.github.io/cv", "signing_key": str(key)}
    yamlio.dump(prof, prof_file)
    res = runner.invoke(app, ["build", "--role", "applied-ai", "--no-llm", "--format", "md", "--sign"])
    assert res.exit_code == 0, res.output
    assert "signed manifest" in res.output
    out = Path(re.search(r"output: (.+)", res.output).group(1).strip())
    assert (out / "manifest.json.sig").exists()
    keys = tmp_path / "keys.txt"
    keys.write_text(pub + "\n", encoding="utf-8")
    res = runner.invoke(app, ["verify", str(out / "cv.md"), "--manifest", str(out / "manifest.json"),
                              "--keys", str(keys)])
    assert res.exit_code == 0 and "signed by" in res.output.lower()


def test_manifest_matches_open_schema(home, tmp_path):
    make_fixture_vault(tmp_path)
    res = runner.invoke(app, ["build", "--role", "applied-ai", "--no-llm", "--format", "md"])
    out = Path(re.search(r"output: (.+)", res.output).group(1).strip())
    validate("manifest", json.loads((out / "manifest.json").read_text(encoding="utf-8")))
