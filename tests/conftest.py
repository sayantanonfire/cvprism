import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolated cvprism state dir (CVPRISM_HOME) and no real claude CLI."""
    h = tmp_path / "cvprism-home"
    monkeypatch.setenv("CVPRISM_HOME", str(h))
    monkeypatch.setenv("CVPRISM_CLAUDE_CMD", str(tmp_path / "no-such-claude"))
    monkeypatch.delenv("CVPRISM_EXTRACTING", raising=False)
    return h


@pytest.fixture
def device(home, tmp_path):
    """An initialised hub device with a fresh vault outside the code checkout."""
    from cvprism import config, vault

    vpath = tmp_path / "my-vault"
    vault_id = vault.init_vault(vpath)
    cfg = config.new_device_config(name="office-01", role="hub", vault_id=vault_id, vault_path=str(vpath))
    config.save_device(cfg)
    return cfg


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Install a fake `claude` executable that prints a canned JSON response."""

    def _install(payload: str, exit_code: int = 0):
        script = tmp_path / "fake_claude.py"
        script.write_text(
            "import sys\n"
            f"sys.stdout.write({payload!r})\n"
            f"sys.exit({exit_code})\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("CVPRISM_CLAUDE_CMD", f"{sys.executable} {script}")
        return script

    return _install
