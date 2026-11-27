"""M2 criterion 4 and ADR-008: global dispatcher chains to repo-local and previous global hooks."""
import os
import shutil
import subprocess
import sys

import pytest

from cvprism import paths
from cvprism.capture.queue import Queue
from cvprism.install import githooks

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def hook_cmd():
    # run the hook entry with this interpreter so the test doesn't depend on an installed script
    return [sys.executable, "-m", "cvprism.capture.hookentry"]


def make_repo(tmp_path, name="repo"):
    r = tmp_path / name
    r.mkdir()
    git("init", "-q", cwd=r)
    return r


def write_hook(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)


def commit(repo, msg="c1"):
    (repo / "f.txt").write_text(msg, encoding="utf-8")
    git("add", ".", cwd=repo)
    return git("commit", "-q", "-m", msg, cwd=repo, check=False)


def test_install_sets_hooks_path_and_enqueues_commits(home, tmp_path):
    githooks.install(hook_cmd())
    assert git("config", "--global", "core.hooksPath").stdout.strip() == githooks.hooks_dir().as_posix()
    repo = make_repo(tmp_path)
    assert commit(repo).returncode == 0
    jobs = Queue(paths.queue_dir()).wait_for(1, timeout=10)
    assert jobs and jobs[0]["kind"] == "git_commit"
    assert jobs[0]["payload"]["sha"] == git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def test_repo_local_hook_still_runs_and_can_block(home, tmp_path):
    githooks.install(hook_cmd())
    repo = make_repo(tmp_path)
    marker = tmp_path / "local-ran.txt"
    write_hook(repo / ".git" / "hooks" / "post-commit", f'echo ran > "{marker.as_posix()}"')
    write_hook(repo / ".git" / "hooks" / "pre-commit", "echo blocked >&2; exit 1")
    assert commit(repo).returncode != 0            # blocking local hook still blocks
    (repo / ".git" / "hooks" / "pre-commit").unlink()
    assert commit(repo, "c2").returncode == 0
    assert marker.exists()                          # local post-commit chained


def test_previous_global_hooks_path_is_chained_and_restored(home, tmp_path):
    prev = tmp_path / "prev-hooks"
    marker = tmp_path / "prev-ran.txt"
    write_hook(prev / "post-commit", f'echo ran > "{marker.as_posix()}"')
    git("config", "--global", "core.hooksPath", prev.as_posix())
    githooks.install(hook_cmd())
    repo = make_repo(tmp_path)
    assert commit(repo).returncode == 0
    assert marker.exists()
    githooks.uninstall()
    assert git("config", "--global", "core.hooksPath").stdout.strip() == prev.as_posix()


def test_uninstall_without_previous_unsets(home, tmp_path):
    githooks.install(hook_cmd())
    githooks.uninstall()
    assert git("config", "--global", "core.hooksPath", check=False).returncode != 0


def test_repos_with_local_hooks_path_are_reported(home, tmp_path):
    repo = make_repo(tmp_path, "husky-repo")
    git("config", "core.hooksPath", ".husky", cwd=repo)
    assert githooks.repos_overriding_hooks([tmp_path]) == [repo]
