import json
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
    # never touch the real ~/.claude or global git config from tests
    monkeypatch.setenv("CVPRISM_CLAUDE_DIR", str(tmp_path / "dot-claude"))
    gitcfg = tmp_path / "gitconfig-global"
    gitcfg.write_text("[user]\n\tname = cvprism-test\n\temail = test@example.invalid\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitcfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
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


class FakeClaude:
    def __init__(self, script, log):
        self.script, self.log = script, log

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Install a fake `claude` executable that prints a canned JSON response."""

    def _install(payload: str, exit_code: int = 0):
        script = tmp_path / "fake_claude.py"
        log = tmp_path / "claude_calls.jsonl"
        script.write_text(
            "import sys, json, os\n"
            "data = sys.stdin.read()\n"
            f"open({str(log)!r}, 'a', encoding='utf-8').write(json.dumps({{'argv': sys.argv[1:], 'stdin': data, "
            "'extracting': os.environ.get('CVPRISM_EXTRACTING')}) + '\\n')\n"
            f"sys.stdout.write({payload!r})\n"
            f"sys.exit({exit_code})\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("CVPRISM_CLAUDE_CMD", f"{sys.executable} {script}")
        return FakeClaude(script, log)

    return _install
