"""M2 criteria 3 and 6: queued signals become sensible, redacted cards; no recursion; failures retry."""
import json

from cvprism import paths
from cvprism.capture.queue import Queue
from cvprism.capture.worker import run_once
from cvprism.sync.outbox import Outbox
from tests.conftest import FIXTURES

SESSION = FIXTURES / "sessions" / "mcp_build.jsonl"


def extraction(cards):
    return json.dumps({"type": "result", "is_error": False, "structured_output": {"cards": cards}})


GOOD = {
    "txt": "Built a Model Context Protocol server for Contoso exposing HEC-RAS 2D runs with an async job queue",
    "s": ["mcp-server-development", "hec-ras"], "d": 3, "meth": ["async job orchestration"],
    "tl": ["fastmcp", "python"], "dom": ["applied-ai", "hydrodynamics"],
    "r": {"m": "run time", "val": 25, "unit": "min", "dir": "down"},  # invented: digest says 40, not 25
    "needs_metric": False, "work": False, "conf": 0.8,
}


def setup_redact(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "redact.yaml").write_text("v: 1\ndeny_terms: [Contoso]\n", encoding="utf-8")


def cards(device):
    return list(Outbox(paths.outbox_dir(), device["device_id"]).iter_cards())


def test_session_job_yields_redacted_card_without_invented_metric(home, device, fake_claude):
    setup_redact(home)
    fake = fake_claude(extraction([GOOD]))
    Queue(paths.queue_dir()).enqueue("claude_session", key=str(SESSION),
                                     payload={"transcript_path": str(SESSION), "session_id": "s1"})
    stats = run_once(device)
    assert stats["cards"] == 1 and stats["done"] == 1
    c = cards(device)[0]
    assert "mcp-server-development" in c["s"] and c["d"] >= 3 and c["src"] == "claude_session"
    assert c["r"] is None and "needs_metric" in c["flags"]
    assert "contoso" not in json.dumps(c).lower()
    sent = fake.calls()[0]["stdin"]
    assert "AKIA" not in sent and "Contoso" not in sent and "SECRET DATA ROW" not in sent
    assert fake.calls()[0]["extracting"] == "1"
    assert Queue(paths.queue_dir()).pending() == []


def test_grounded_metric_is_kept(home, device, fake_claude):
    good = dict(GOOD, r={"m": "run time", "val": 40, "unit": "min", "dir": "abs"})
    fake_claude(extraction([good]))
    Queue(paths.queue_dir()).enqueue("claude_session", key="k", payload={"transcript_path": str(SESSION)})
    run_once(device)
    assert cards(device)[0]["r"]["val"] == 40


def test_repeat_session_creates_no_duplicate(home, device, fake_claude):
    fake_claude(extraction([GOOD]))
    q = Queue(paths.queue_dir())
    q.enqueue("claude_session", key="a", payload={"transcript_path": str(SESSION)})
    run_once(device)
    q.enqueue("claude_session", key="b", payload={"transcript_path": str(SESSION)})
    stats = run_once(device)
    assert stats["cards"] == 0 and len(cards(device)) == 1


def test_claude_unavailable_keeps_job_for_retry(home, device):
    q = Queue(paths.queue_dir())
    q.enqueue("claude_session", key="a", payload={"transcript_path": str(SESSION)})
    stats = run_once(device)
    assert stats["retry"] == 1
    assert q.pending()[0]["attempts"] == 1


def test_missing_transcript_is_dropped(home, device, fake_claude):
    fake_claude(extraction([GOOD]))
    q = Queue(paths.queue_dir())
    q.enqueue("claude_session", key="gone", payload={"transcript_path": str(home / "gone.jsonl")})
    stats = run_once(device)
    assert stats["dropped"] == 1 and q.pending() == []


def test_disabled_capture_source_is_dropped(home, device, fake_claude):
    fake = fake_claude(extraction([GOOD]))
    device["capture"]["claude_session"]["enabled"] = False
    Queue(paths.queue_dir()).enqueue("claude_session", key="a", payload={"transcript_path": str(SESSION)})
    stats = run_once(device)
    assert stats["dropped"] == 1 and fake.calls() == []


def test_excluded_cwd_is_dropped(home, device, fake_claude):
    fake = fake_claude(extraction([GOOD]))
    device["privacy"]["exclude_paths"] = ["D:/work/**"]
    Queue(paths.queue_dir()).enqueue("claude_session", key="a",
                                     payload={"transcript_path": str(SESSION), "cwd": "D:/work/contoso-flood"})
    stats = run_once(device)
    assert stats["dropped"] == 1 and fake.calls() == []


def test_extraction_produces_no_new_jobs(home, device, fake_claude):
    """M2 criterion 6: no recursion; the extractor's own session must not enqueue."""
    fake_claude(extraction([GOOD]))
    q = Queue(paths.queue_dir())
    q.enqueue("claude_session", key="a", payload={"transcript_path": str(SESSION)})
    run_once(device)
    assert q.pending() == []


def test_watcher_jobs_are_batched_into_one_call(home, device, fake_claude):
    fake = fake_claude(extraction([{**GOOD, "txt": "Adopted PyTorch for deep learning model training",
                                    "s": ["pytorch"], "d": 2, "r": None}]))
    device["capture"]["watcher"]["enabled"] = True
    q = Queue(paths.queue_dir())
    q.enqueue("watcher", key="1", payload={"file_kind": "requirements.txt", "added": ["torch"], "project": "p"})
    q.enqueue("watcher", key="2", payload={"file_kind": "package.json", "added": ["react"], "project": "p"})
    stats = run_once(device)
    assert len(fake.calls()) == 1 and stats["done"] == 2
    assert "torch" in fake.calls()[0]["stdin"] and "react" in fake.calls()[0]["stdin"]


def test_git_jobs_batched_per_repo(home, device, fake_claude, tmp_path):
    import shutil
    import subprocess

    if shutil.which("git") is None:
        return
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    shas = []
    for i, (fname, content) in enumerate([("requirements.txt", "torch\n"), ("model.py", "x=1\n")]):
        (repo / fname).write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"feat: step {i} of training pipeline"], cwd=repo, check=True)
        shas.append(subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip())
    fake = fake_claude(extraction([]))
    q = Queue(paths.queue_dir())
    for s in shas:
        q.enqueue("git_commit", key=f"{repo}@{s}", payload={"repo": str(repo), "sha": s})
    stats = run_once(device)
    assert len(fake.calls()) == 1 and stats["done"] == 2
    sent = fake.calls()[0]["stdin"]
    assert "step 0 of training pipeline" in sent and "torch" in sent and ".py" in sent
    assert "x=1" not in sent  # never diff contents beyond dependency names
