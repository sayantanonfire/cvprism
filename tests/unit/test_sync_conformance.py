"""Shared adapter conformance suite: invariants I1-I5 and scenarios from docs/SYNC.md.

Every adapter must pass every test here (ADR-005). Folder-like adapters run in all environments;
git runs when git is installed.
"""
from __future__ import annotations

import json
import shutil

import pytest

from cvprism.sync.adapters import make_adapter
from cvprism.sync.adapters.base import VaultMismatch
from cvprism.sync.outbox import Outbox
from tests.conftest_sync import bare_repo

VID = "2b7c6f0e-8a8d-4f6a-9a51-0f3e5c8b1d22"
OTHER_VID = "11111111-2222-4333-8444-555555555555"


def _card(i: int, dev: str) -> dict:
    return {"id": f"c_{i:016x}", "t": "2026-11-27T10:00:00Z", "dev": dev, "txt": f"card {i}"}


@pytest.fixture(params=["local", "gdrive", "usb", "syncthing", "git"])
def transport(request, tmp_path, monkeypatch, home):
    """Return (make(device_id) -> adapter) for one adapter type, transport initialised with VID."""
    kind = request.param
    if kind == "git" and shutil.which("git") is None:
        pytest.skip("git missing")
    if kind == "git":
        remote = bare_repo(tmp_path / "remote.git")
        spec = {"type": "git", "enabled": True, "name": "git", "remote": remote}
    elif kind == "usb":
        drive = tmp_path / "USBDRIVE"
        (drive / "cvprism-dropbox").mkdir(parents=True)
        monkeypatch.setenv("CVPRISM_USB_ROOTS", str(drive))
        spec = {"type": "usb", "enabled": True, "name": "usb"}
    else:
        root = tmp_path / f"{kind}-root"
        root.mkdir()
        spec = {"type": kind, "enabled": True, "name": kind, "path": str(root)}

    def make(device_id: str, vault_id: str = VID):
        return make_adapter(spec, device_id=device_id, vault_id=vault_id,
                            state_dir=tmp_path / "state" / device_id)

    hub = make("hub-0000")
    hub.init_transport()
    return make


def test_push_then_hub_reads_inbox(transport, tmp_path):
    a = transport("spoke-a-0001")
    ob = Outbox(tmp_path / "ob", "spoke-a-0001")
    ob.append(_card(1, "spoke-a-0001"))
    rep = a.push(ob)
    assert rep.files == 1
    hub = transport("hub-0000")
    got = {c["id"] for c in hub.iter_inbox_cards()}
    assert got == {"c_0000000000000001"}


def test_push_is_idempotent_and_incremental(transport, tmp_path):
    a = transport("spoke-a-0001")
    ob = Outbox(tmp_path / "ob", "spoke-a-0001")
    ob.append(_card(1, "spoke-a-0001"))
    assert a.push(ob).files == 1
    assert a.push(ob).files == 0           # cursor: nothing new
    ob.append(_card(2, "spoke-a-0001"))
    assert a.push(ob).files == 1
    hub = transport("hub-0000")
    assert len(list(hub.iter_inbox_cards())) == 2


def test_i1_device_writes_only_its_inbox(transport, tmp_path):
    a = transport("spoke-a-0001")
    ob = Outbox(tmp_path / "ob", "spoke-a-0001")
    ob.append(_card(1, "spoke-a-0001"))
    a.push(ob)
    written = {p for p in a.list_files() if p.startswith("inbox/")}
    assert written and all(p.startswith("inbox/spoke-a-0001/") for p in written)


def test_push_never_loses_remote_lines(transport, tmp_path):
    """If the remote has lines the local outbox lacks (e.g. outbox restored from backup), keep both."""
    a = transport("spoke-a-0001")
    ob1 = Outbox(tmp_path / "ob1", "spoke-a-0001")
    ob1.append(_card(1, "spoke-a-0001"))
    a.push(ob1)
    a2 = transport("spoke-a-0001")
    a2.state_dir = tmp_path / "state" / "fresh"   # forget cursors
    ob2 = Outbox(tmp_path / "ob2", "spoke-a-0001")
    ob2.append(_card(2, "spoke-a-0001"))
    a2.push(ob2)
    hub = transport("hub-0000")
    assert {c["id"] for c in hub.iter_inbox_cards()} == {"c_0000000000000001", "c_0000000000000002"}


def test_i5_wrong_vault_refused(transport, tmp_path):
    a = transport("spoke-a-0001", vault_id=OTHER_VID)
    assert a.available() is False
    ob = Outbox(tmp_path / "ob", "spoke-a-0001")
    ob.append(_card(1, "spoke-a-0001"))
    with pytest.raises(VaultMismatch):
        a.push(ob)


def test_registry_publish_and_pull_highest(transport):
    hub = transport("hub-0000")
    hub.publish({"registry.json": json.dumps({"v": 1, "vault_id": VID, "epoch": 1, "rev": 3,
                                              "generated": "2026-11-27T10:00:00Z", "skills": {}})})
    spoke = transport("spoke-a-0001")
    reg = spoke.pull()
    assert reg["rev"] == 3


def test_status_reports(transport):
    st = transport("spoke-a-0001").status()
    assert st.available is True and st.kind in ("local", "gdrive", "usb", "syncthing", "git")
