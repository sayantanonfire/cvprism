import json

import pytest

from cvprism.sync.outbox import Outbox
from cvprism.novelty.counters import Counters


def test_append_writes_one_complete_line(home):
    ob = Outbox(home / "outbox", "office-01-7f3a")
    path = ob.append({"id": "c_0000000000000001", "t": "2026-11-27T10:00:00Z", "txt": "é ok"})
    raw = path.read_bytes()
    assert path.name == "2026-11.jsonl"
    assert path.parent.name == "office-01-7f3a"
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1 and b"\r" not in raw
    assert json.loads(raw)["txt"] == "é ok"


def test_iter_cards_skips_unterminated_tail(home):
    ob = Outbox(home / "outbox", "dev-0001")
    p = ob.append({"id": "c_1", "t": "2026-11-27T10:00:00Z"})
    with p.open("ab") as f:
        f.write(b'{"id": "c_2", "t": "2026-11')  # partial write
    assert [c["id"] for c in ob.iter_cards()] == ["c_1"]


def test_month_file_follows_capture_time(home):
    ob = Outbox(home / "outbox", "dev-0001")
    ob.append({"id": "c_1", "t": "2026-10-31T23:59:59Z"})
    ob.append({"id": "c_2", "t": "2026-11-01T00:00:00Z"})
    assert sorted(p.name for p in ob.files()) == ["2026-10.jsonl", "2026-11.jsonl"]


def test_counters_increment_and_persist(home):
    c = Counters(home / "counters.json")
    c.bump(["python", "pytorch"], "2026-11-27T10:00:00Z")
    c.bump(["python"], "2026-11-28T10:00:00Z")
    c2 = Counters(home / "counters.json")
    assert c2.get("python") == {"n": 2, "last": "2026-11-28T10:00:00Z"}
    assert c2.get("pytorch")["n"] == 1
