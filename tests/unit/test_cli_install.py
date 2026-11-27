import json
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from cvprism import paths
from cvprism.capture.queue import Queue
from cvprism.cli import app
from cvprism.install import claude as cc

runner = CliRunner()


def test_install_dry_run_changes_nothing(home, device):
    res = runner.invoke(app, ["install", "--dry-run"])
    assert res.exit_code == 0, res.output
    assert "SessionEnd" in res.output and "core.hooksPath" in res.output
    assert not (cc.claude_dir() / "settings.json").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git missing")
def test_install_and_uninstall_round_trip(home, device):
    res = runner.invoke(app, ["install", "--no-service"])
    assert res.exit_code == 0, res.output
    assert cc.installed()
    assert (cc.claude_dir() / "skills" / "cv-log" / "SKILL.md").exists()
    hp = subprocess.run(["git", "config", "--global", "core.hooksPath"], capture_output=True, text=True).stdout
    assert "git-hooks" in hp
    res = runner.invoke(app, ["uninstall", "--no-service"])
    assert res.exit_code == 0, res.output
    assert not cc.installed()
    assert not (cc.claude_dir() / "skills" / "cv-log").exists()
    assert subprocess.run(["git", "config", "--global", "core.hooksPath"], capture_output=True).returncode != 0


def test_worker_command_runs_once(home, device):
    Queue(paths.queue_dir()).enqueue("claude_session", key="x", payload={"transcript_path": "/nope.jsonl"})
    res = runner.invoke(app, ["worker"])
    assert res.exit_code == 0, res.output
    assert "dropped=1" in res.output


def test_status_shows_queue_and_hooks(home, device):
    Queue(paths.queue_dir()).enqueue("watcher", key="x", payload={"added": ["torch"]})
    res = runner.invoke(app, ["status"])
    assert "queued jobs:     1" in res.output
    assert "claude hook:" in res.output and "git hooks:" in res.output


def test_agent_single_iteration(home, device):
    res = runner.invoke(app, ["agent", "--iterations", "1", "--interval", "0"])
    assert res.exit_code == 0, res.output
