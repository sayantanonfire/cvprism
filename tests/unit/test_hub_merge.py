"""Hub merge, registry, epochs, suppress/purge, and the M3 headline scenario."""
from __future__ import annotations

import json
import shutil

import pytest
from typer.testing import CliRunner

from cvprism import config, paths
from cvprism.cli import app
from cvprism.hub.merge import merge
from cvprism.hub.registry import build_registry
from cvprism.novelty.ids import card_id
from tests.conftest_sync import as_device, bare_repo, read_jsonl

runner = CliRunner()


def cli(*args):
    res = runner.invoke(app, list(args))
    assert res.exit_code == 0, res.output
    return res.output


def mk(**over):
    c = {"v": 1, "k": "skill", "why": "new_skill", "s": ["python"], "d": 2, "r": None, "ctx": None,
         "txt": "Built a python tool", "meth": [], "tl": [], "dom": ["applied-ai"], "t": "2026-11-27T10:00:00Z",
         "dev": "spoke-a-0001", "src": "manual", "conf": 1.0, "flags": [], "lang": "en"}
    c.update(over)
    c["id"] = card_id(c)
    return c


def test_registry_is_deterministic_and_valid():
    from cvprism.schemas import validate

    cards = [mk(), mk(s=["python", "pytorch"], d=3, t="2026-11-28T10:00:00Z"),
             mk(k="result", s=["pytorch"], d=3, r={"m": "latency", "val": 40, "unit": "ms", "dir": "down"})]
    r1 = build_registry(cards, vault_id="2b7c6f0e-8a8d-4f6a-9a51-0f3e5c8b1d22", epoch=1, rev=5, generated="x")
    r2 = build_registry(list(reversed(cards)), vault_id="2b7c6f0e-8a8d-4f6a-9a51-0f3e5c8b1d22", epoch=1, rev=5,
                        generated="x")
    assert r1 == r2
    r1["generated"] = "2026-11-27T10:00:00Z"
    validate("registry", r1)
    assert r1["skills"]["pytorch"]["max_d"] == 3 and r1["skills"]["pytorch"]["n"] == 2
    assert len(r1["skills"]["pytorch"]["rh"]) == 1
    assert r1["skills"]["python"]["first"] == "2026-11-27T10:00:00Z"
    assert "py" in r1["skills"]["python"]["aliases"]          # from the seed taxonomy


def setup_hub(tmp_path, adapters):
    hub_home = tmp_path / "hub-home"
    with as_device(hub_home):
        cli("init", "--name", "hub", "--role", "hub", "--vault", str(tmp_path / "vault"), "--yes", *adapters)
        cfg = config.load_device()
    return hub_home, cfg


@pytest.mark.skipif(shutil.which("git") is None, reason="git missing")
def test_headline_two_spokes_two_adapters_zero_duplicates(tmp_path, home):
    """M3 acceptance 1: A via git, B via a synced folder, a shared card captured on both."""
    remote = bare_repo(tmp_path / "vault-remote.git")
    drive = tmp_path / "GoogleDrive" / "cvprism"
    hub_home, hub_cfg = setup_hub(tmp_path, ["--adapter", f"git:{remote}", "--adapter", f"gdrive:{drive}"])
    with as_device(hub_home):
        cli("sync")                                   # publishes vault.json/registry to both transports
    a_home, b_home = tmp_path / "a-home", tmp_path / "b-home"
    with as_device(a_home):
        cli("init", "--name", "laptop-a", "--role", "spoke", "--adapter", f"git:{remote}", "--yes")
        cli("log", "--raw", "Built an MCP server for HEC-RAS", "--skill", "mcp-server-development", "--depth", "3")
        cli("log", "--raw", "Built a python flood tool", "--skill", "python", "--depth", "2")
        cli("sync")
    with as_device(b_home):
        cli("init", "--name", "laptop-b", "--role", "spoke", "--adapter", f"gdrive:{drive}", "--yes")
        cli("log", "--raw", "Built an MCP server exposing HEC-RAS", "--skill", "mcp-server-development", "--depth", "3")
        cli("log", "--raw", "Field ADCP survey of an estuary", "--skill", "adcp-survey", "--depth", "4", "--work")
        cli("sync")
    with as_device(hub_home):
        out = cli("sync")
        assert "merged" in out
    cards = read_jsonl(tmp_path / "vault" / "cards.jsonl")
    ids = [c["id"] for c in cards]
    assert len(ids) == len(set(ids)) == 3        # the MCP card arrived twice, kept once
    reg = json.loads((tmp_path / "vault" / "registry.json").read_text(encoding="utf-8"))
    assert {"mcp-server-development", "python", "adcp-survey"} <= set(reg["skills"])
    for h in (a_home, b_home):                    # registry flowed back to both spokes
        with as_device(h):
            cli("sync")
            cache = json.loads(paths.registry_cache().read_text(encoding="utf-8"))
            assert cache["rev"] == reg["rev"] and "adcp-survey" in cache["skills"]
    with as_device(a_home):                        # spoke A now knows B's skill: no new card
        out = cli("log", "--raw", "Did an ADCP survey", "--skill", "adcp-survey", "--depth", "4")
        assert "already known" in out.lower()


def test_merge_quarantines_invalid_and_foreign_lines(tmp_path, home):
    hub_home, cfg = setup_hub(tmp_path, [])
    inbox = tmp_path / "vault" / "inbox" / "spoke-a-0001"
    inbox.mkdir(parents=True)
    good = mk()
    tampered = dict(mk(d=4), d=5)                        # id no longer matches content
    foreign = mk(dev="someone-else-0002", s=["rust"])     # written into another device's folder
    lines = [json.dumps(good), json.dumps(tampered), json.dumps(foreign), "{not json", '{"partial": tr']
    (inbox / "2026-11.jsonl").write_text("\n".join(lines), encoding="utf-8")  # last line unterminated
    (inbox / "2026-11 (1).jsonl").write_text(json.dumps(good) + "\n", encoding="utf-8")  # Drive conflict copy
    with as_device(hub_home):
        rep = merge(config.load_device())
    assert rep.new_cards == 1 and rep.quarantined == 3
    assert [c["id"] for c in read_jsonl(tmp_path / "vault" / "cards.jsonl")] == [good["id"]]
    q = read_jsonl(tmp_path / "vault" / "quarantine" / "spoke-a-0001.jsonl")
    assert len(q) == 3


def test_merge_is_idempotent_and_rebuild_reproduces(tmp_path, home):
    hub_home, cfg = setup_hub(tmp_path, [])
    inbox = tmp_path / "vault" / "inbox" / "spoke-a-0001"
    inbox.mkdir(parents=True)
    cs = [mk(), mk(s=["pytorch"], t="2026-11-28T00:00:00Z")]
    (inbox / "2026-11.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cs), encoding="utf-8")
    with as_device(hub_home):
        first = merge(config.load_device())
        second = merge(config.load_device())
        before = (tmp_path / "vault" / "cards.jsonl").read_text(encoding="utf-8")
        rev_before = json.loads((tmp_path / "vault" / "registry.json").read_text())["rev"]
        cli("hub", "rebuild")
        after = (tmp_path / "vault" / "cards.jsonl").read_text(encoding="utf-8")
    assert first.new_cards == 2 and second.new_cards == 0
    assert sorted(before.splitlines()) == sorted(after.splitlines())
    assert rev_before >= 1


def test_suppress_hides_card_from_merge(tmp_path, home):
    hub_home, cfg = setup_hub(tmp_path, [])
    inbox = tmp_path / "vault" / "inbox" / "spoke-a-0001"
    inbox.mkdir(parents=True)
    c1, c2 = mk(), mk(s=["rust"])
    (inbox / "2026-11.jsonl").write_text(json.dumps(c1) + "\n" + json.dumps(c2) + "\n", encoding="utf-8")
    with as_device(hub_home):
        cli("suppress", c2["id"])
        merge(config.load_device())
        cli("hub", "rebuild")
    assert [c["id"] for c in read_jsonl(tmp_path / "vault" / "cards.jsonl")] == [c1["id"]]


def test_purge_rewrites_everywhere(tmp_path, home):
    drive = tmp_path / "drive"
    hub_home, cfg = setup_hub(tmp_path, ["--adapter", f"gdrive:{drive}"])
    with as_device(hub_home):
        cli("sync")
    spoke_home = tmp_path / "s-home"
    with as_device(spoke_home):
        cli("init", "--name", "s", "--role", "spoke", "--adapter", f"gdrive:{drive}", "--yes")
        cli("log", "--raw", "Used key handling in python", "--skill", "python", "--depth", "2")
        cli("sync")
        cid = read_jsonl(next((spoke_home / "outbox").rglob("*.jsonl")))[0]["id"]
        cli("purge", cid, "--yes")
        assert read_jsonl(next((spoke_home / "outbox").rglob("*.jsonl"))) == []
        assert all(cid not in p.read_text() for p in drive.rglob("*.jsonl"))
    with as_device(hub_home):
        cli("sync")
        assert cid not in (tmp_path / "vault" / "cards.jsonl").read_text(encoding="utf-8")
        assert cid in (tmp_path / "vault" / "purged.txt").read_text(encoding="utf-8")


def test_promote_bumps_epoch_and_old_hub_demotes(tmp_path, home):
    drive = tmp_path / "drive"
    hub_home, cfg = setup_hub(tmp_path, ["--adapter", f"gdrive:{drive}"])
    with as_device(hub_home):
        cli("sync")
    new_home = tmp_path / "new-hub"
    with as_device(new_home):
        cli("init", "--name", "newhub", "--role", "spoke", "--adapter", f"gdrive:{drive}", "--yes")
        cli("hub", "promote", "--vault", str(tmp_path / "vault2"))
        assert config.load_device()["role"] == "hub"
        hub = json.loads((drive / "hub.json").read_text(encoding="utf-8"))
        assert hub["epoch"] == 2 and hub["hub_device_id"] == config.load_device()["device_id"]
    with as_device(hub_home):
        out = cli("sync")
        assert "demoted" in out.lower()
        assert config.load_device()["role"] == "spoke"


def test_spoke_rejects_older_registry(tmp_path, home):
    from cvprism.sync.engine import accept_registry

    with as_device(tmp_path / "x"):
        assert accept_registry({"epoch": 1, "rev": 5, "skills": {}}) is True
        assert accept_registry({"epoch": 1, "rev": 4, "skills": {}}) is False
        assert accept_registry({"epoch": 2, "rev": 0, "skills": {}}) is True


def test_offline_spoke_pushes_whole_backlog_on_reconnect(tmp_path, home):
    """M3 criterion 3 / SYNC S1: the outbox is durable; nothing is lost while offline."""
    drive = tmp_path / "drive"
    hub_home, _ = setup_hub(tmp_path, ["--adapter", f"gdrive:{drive}"])
    with as_device(hub_home):
        cli("sync")
    s_home = tmp_path / "s"
    with as_device(s_home):
        cli("init", "--name", "s", "--role", "spoke", "--adapter", f"gdrive:{drive}", "--yes")
        drive.rename(tmp_path / "drive-offline")              # transport disappears
        for i, skill in enumerate(["rust", "go", "julia", "fortran", "matlab"]):
            cli("log", "--raw", f"Built a tool number {i}", "--skill", skill, "--depth", "2")
            out = cli("sync")
            assert "unavailable" in out
        (tmp_path / "drive-offline").rename(drive)             # back online
        assert "pushed 5" in cli("sync")
    with as_device(hub_home):
        cli("sync")
    assert len(read_jsonl(tmp_path / "vault" / "cards.jsonl")) == 5


def test_split_brain_same_epoch_higher_device_id_wins(tmp_path, home):
    from cvprism.sync.engine import _hub_key

    assert _hub_key({"epoch": 2, "hub_device_id": "b-0001"}) > _hub_key({"epoch": 2, "hub_device_id": "a-0001"})
    assert _hub_key({"epoch": 3, "hub_device_id": "a-0001"}) > _hub_key({"epoch": 2, "hub_device_id": "z-0001"})


def test_status_lists_adapters_and_backlog(tmp_path, home):
    drive = tmp_path / "drive"
    hub_home, _ = setup_hub(tmp_path, ["--adapter", f"gdrive:{drive}"])
    with as_device(hub_home):
        cli("sync")
    with as_device(tmp_path / "s"):
        cli("init", "--name", "s", "--role", "spoke", "--adapter", f"gdrive:{drive}", "--yes")
        cli("log", "--raw", "Built a rust tool", "--skill", "rust", "--depth", "2")
        out = cli("status")
        assert "gdrive [on, reachable, backlog 1 file(s)]" in out
