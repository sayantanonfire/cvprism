"""Vault creation, device config, wizard guard rails, status and doctor (M1 criteria 1 and 6)."""
import json
import re

import pytest
from typer.testing import CliRunner

from cvprism import config, vault
from cvprism.cli import app
from cvprism.schemas import validate
from tests.conftest import ROOT

runner = CliRunner()


def test_device_id_format():
    did = config.make_device_id("Office PC #1")
    assert re.fullmatch(r"office-pc-1-[0-9a-f]{4}", did)


def test_init_vault_creates_template(tmp_path):
    v = tmp_path / "v"
    vid = vault.init_vault(v)
    assert json.loads((v / "vault.json").read_text())["vault_id"] == vid
    assert json.loads((v / "hub.json").read_text())["epoch"] == 1
    reg = json.loads((v / "registry.json").read_text())
    validate("registry", reg)
    assert "build/" in (v / ".gitignore").read_text()
    assert (v / "profile.yaml").exists() and (v / "roles").is_dir() and (v / "inbox").is_dir()


def test_init_vault_refuses_existing_vault(tmp_path):
    v = tmp_path / "v"
    vault.init_vault(v)
    with pytest.raises(vault.VaultError):
        vault.init_vault(v)


def test_vault_inside_code_checkout_is_refused():
    with pytest.raises(vault.VaultError, match="inside the cvprism code"):
        vault.check_vault_location(ROOT / "vault")


def test_device_config_round_trip_is_schema_valid(home, device):
    loaded = config.load_device()
    validate("device", loaded)
    assert loaded["device_id"] == device["device_id"]
    assert loaded["adapters"][0]["type"] == "local"


def test_noninteractive_init_hub(home, tmp_path):
    vpath = tmp_path / "vault-x"
    res = runner.invoke(app, ["init", "--name", "home-pc", "--role", "hub", "--vault", str(vpath), "--yes"])
    assert res.exit_code == 0, res.output
    assert (vpath / "vault.json").exists()
    assert config.load_device()["role"] == "hub"


def test_noninteractive_init_refuses_vault_in_checkout(home):
    res = runner.invoke(app, ["init", "--name", "x", "--role", "hub", "--vault", str(ROOT / "vault"), "--yes"])
    assert res.exit_code != 0
    assert "inside the cvprism code" in res.output


def test_interactive_wizard(home, tmp_path):
    vpath = tmp_path / "wiz-vault"
    answers = "\n".join(["lab-ws", "hub", str(vpath), "", str(tmp_path / "projects"), ""]) + "\n"
    res = runner.invoke(app, ["init"], input=answers)
    assert res.exit_code == 0, res.output
    cfg = config.load_device()
    assert cfg["name"] == "lab-ws"
    assert cfg["capture"]["watcher"]["paths"] == [str(tmp_path / "projects")]


def test_spoke_init_joins_existing_vault(home, tmp_path):
    vpath = tmp_path / "shared"
    vid = vault.init_vault(vpath)
    res = runner.invoke(app, ["init", "--name", "laptop", "--role", "spoke", "--vault", str(vpath), "--yes"])
    assert res.exit_code == 0, res.output
    cfg = config.load_device()
    assert cfg["role"] == "spoke" and cfg["vault_id"] == vid and "vault_path" not in cfg


def test_status_reports_counts(home, device):
    runner.invoke(app, ["log", "--raw", "Built a python tool", "--skill", "python", "--depth", "2"])
    res = runner.invoke(app, ["status"])
    assert res.exit_code == 0, res.output
    assert device["device_id"] in res.output
    assert re.search(r"cards in outbox:\s+1", res.output.lower())


def test_doctor_runs(home, device):
    res = runner.invoke(app, ["doctor"])
    assert "python" in res.output.lower()
    assert "claude cli" in res.output.lower()
