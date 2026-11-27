import io
import json
import subprocess
import sys
import time

from cvprism.capture import hookentry
from cvprism.capture.queue import Queue
from cvprism import paths


def test_enqueue_is_idempotent_per_key(home):
    q = Queue(paths.queue_dir())
    q.enqueue("claude_session", key="/t/a.jsonl", payload={"transcript_path": "/t/a.jsonl"})
    q.enqueue("claude_session", key="/t/a.jsonl", payload={"transcript_path": "/t/a.jsonl"})
    q.enqueue("claude_session", key="/t/b.jsonl", payload={"transcript_path": "/t/b.jsonl"})
    assert len(q.pending()) == 2


def test_job_lifecycle(home):
    q = Queue(paths.queue_dir())
    q.enqueue("git_commit", key="repo@abc", payload={"repo": "r", "sha": "abc"})
    job = q.pending()[0]
    q.retry_later(job, "claude unavailable")
    job = q.pending()[0]
    assert job["attempts"] == 1 and job["last_error"] == "claude unavailable"
    q.done(job)
    assert q.pending() == []


def test_expired_jobs_go_to_dead_letter(home):
    q = Queue(paths.queue_dir(), ttl_days=30)
    q.enqueue("watcher", key="k", payload={}, created="2020-01-01T00:00:00Z")
    assert q.pending() == []
    assert len(list((paths.queue_dir() / "dead").glob("*.json"))) == 1


def test_session_end_hook_enqueues_from_stdin(home, monkeypatch):
    payload = {"session_id": "s1", "transcript_path": "/x/s1.jsonl", "cwd": "/x", "hook_event_name": "SessionEnd",
               "reason": "exit"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert hookentry.main(["claude-session-end"]) == 0
    jobs = Queue(paths.queue_dir()).pending()
    assert jobs[0]["kind"] == "claude_session" and jobs[0]["payload"]["transcript_path"] == "/x/s1.jsonl"


def test_hook_is_noop_inside_extraction(home, monkeypatch):
    monkeypatch.setenv("CVPRISM_EXTRACTING", "1")
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"transcript_path": "/x/s1.jsonl"}'))
    assert hookentry.main(["claude-session-end"]) == 0
    assert Queue(paths.queue_dir()).pending() == []


def test_hook_never_fails_on_garbage(home, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert hookentry.main(["claude-session-end"]) == 0
    assert hookentry.main(["unknown-hook"]) == 0


def test_hook_process_is_fast(home):
    """M2 criterion 2: the real hook process returns quickly (generous bound for CI noise)."""
    payload = json.dumps({"transcript_path": "/x/s9.jsonl", "session_id": "s9"})
    t0 = time.perf_counter()
    subprocess.run([sys.executable, "-m", "cvprism.capture.hookentry", "claude-session-end"],
                   input=payload, text=True, check=True)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.5, elapsed
    assert len(Queue(paths.queue_dir()).pending()) == 1


def test_hook_does_not_import_heavy_modules():
    code = ("import sys, cvprism.capture.hookentry as h; "
            "bad=[m for m in ('typer','jsonschema','ruamel.yaml','watchdog') if m in sys.modules]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
