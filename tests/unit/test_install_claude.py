"""M2 criterion 1: SessionEnd hook install merges without clobbering; uninstall restores exactly."""
import json
import os

import pytest

from cvprism.install import claude as cc

FIXTURE_SETTINGS = [
    None,  # no settings.json at all
    {"theme": "dark", "enabledPlugins": {"x@y": True}},
    {"hooks": {"SessionEnd": [{"hooks": [{"type": "command", "command": "echo bye"}]}],
               "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "guard.sh"}]}]},
     "permissions": {"allow": ["Bash(ls:*)"]}},
]


def settings_path():
    return cc.claude_dir() / "settings.json"


@pytest.mark.parametrize("original", FIXTURE_SETTINGS)
def test_install_merges_and_uninstall_restores(home, original):
    p = settings_path()
    if original is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(original, indent=2), encoding="utf-8")
    before = p.read_text(encoding="utf-8") if p.exists() else None

    cc.install_hook("C:/venv/Scripts/cvprism-hook.exe")
    s = json.loads(p.read_text(encoding="utf-8"))
    cmds = [h["command"] for g in s["hooks"]["SessionEnd"] for h in g["hooks"]]
    assert any("cvprism-hook" in c and "claude-session-end" in c for c in cmds)
    if original and "hooks" in original:
        assert "echo bye" in cmds and s["hooks"]["PreToolUse"] == original["hooks"]["PreToolUse"]
        assert s["permissions"] == original["permissions"]

    cc.install_hook("C:/venv/Scripts/cvprism-hook.exe")  # idempotent
    s = json.loads(p.read_text(encoding="utf-8"))
    assert sum("cvprism-hook" in h["command"] for g in s["hooks"]["SessionEnd"] for h in g["hooks"]) == 1

    cc.uninstall_hook()
    after = p.read_text(encoding="utf-8") if p.exists() else None
    if before is None:
        assert after is None or json.loads(after) == {}
    else:
        assert json.loads(after) == json.loads(before)


def test_install_refuses_invalid_json(home):
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(cc.InstallError):
        cc.install_hook("cvprism-hook")
    assert p.read_text(encoding="utf-8") == "{ not json"


def test_install_skills_copies_skill_files(home):
    installed = cc.install_skills()
    assert {"cv-log", "cv-build"} <= {p.parent.name for p in installed}
    text = (cc.claude_dir() / "skills" / "cv-log" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---") and "name: cv-log" in text and "cvprism log" in text
    cc.uninstall_skills()
    assert not (cc.claude_dir() / "skills" / "cv-log").exists()


def test_hook_command_quotes_argv():
    assert cc.hook_command(["C:/Program Files/py/python.exe", "-m", "cvprism.capture.hookentry"]) == \
        '"C:/Program Files/py/python.exe" -m cvprism.capture.hookentry claude-session-end'
    assert cc.hook_command("/venv/bin/cvprism-hook") == '"/venv/bin/cvprism-hook" claude-session-end'
