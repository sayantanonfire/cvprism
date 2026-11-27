"""M1 acceptance criteria 2, 3, 4, 7 exercised through the real CLI."""
import json

from typer.testing import CliRunner

from cvprism.cli import app
from cvprism.schemas import validate

runner = CliRunner()


def outbox_cards(home):
    cards = []
    for p in sorted((home / "outbox").rglob("*.jsonl")):
        cards += [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]
    return cards


def log(*args):
    return runner.invoke(app, ["log", *args])


RAW = ["--raw", "Built an MCP server exposing HEC-RAS runs", "--skill", "mcp-server-development", "--depth", "3"]


def test_raw_log_writes_one_valid_card(home, device):
    res = log(*RAW)
    assert res.exit_code == 0, res.output
    cards = outbox_cards(home)
    assert len(cards) == 1
    validate("card", cards[0])
    c = cards[0]
    assert c["s"] == ["mcp-server-development"] and c["d"] == 3 and c["src"] == "manual"
    assert c["why"] == "new_skill" and c["dev"] == device["device_id"]


def test_duplicate_log_bumps_counter_only(home, device):
    log(*RAW)
    res = log(*RAW)
    assert res.exit_code == 0, res.output
    assert len(outbox_cards(home)) == 1
    counters = json.loads((home / "counters.json").read_text(encoding="utf-8"))
    assert counters["mcp-server-development"]["n"] == 1
    assert "already known" in res.output.lower()


def test_higher_depth_and_new_result_create_cards(home, device):
    log(*RAW)
    log(*RAW[:-1], "4")
    log(*RAW, "--result", "latency:-40:%")
    cards = outbox_cards(home)
    assert [c["why"] for c in cards] == ["new_skill", "depth_up", "new_result"]
    assert cards[2]["k"] == "result"
    assert cards[2]["r"] == {"m": "latency", "val": -40, "unit": "%", "dir": "down"}
    for c in cards:
        validate("card", c)


def test_work_flag_creates_work_card(home, device):
    res = log("--raw", "Led a 10-day ADCP field survey", "--skill", "adcp-survey", "--depth", "4", "--work")
    assert res.exit_code == 0, res.output
    assert outbox_cards(home)[0]["k"] == "work"


def test_skill_aliases_and_multiple_skills(home, device):
    res = log("--raw", "Built flood API", "--skill", "FastAPI", "--skill", "HEC-RAS", "--depth", "3")
    assert res.exit_code == 0, res.output
    assert outbox_cards(home)[0]["s"] == ["fastapi", "hec-ras"]


def test_requires_init(home):
    res = log(*RAW)
    assert res.exit_code != 0
    assert "cvprism init" in res.output


def test_llm_mode_uses_claude_output(home, device, fake_claude):
    payload = json.dumps({
        "type": "result", "is_error": False,
        "structured_output": {
            "txt": "Developed a Model Context Protocol server exposing hydrodynamic simulations as LLM tools",
            "s": ["mcp-server-development", "hec-ras"], "d": 3,
            "meth": ["tool schema design"], "tl": ["python"], "dom": ["applied-ai", "hydrodynamics"],
            "r": None, "needs_metric": True, "work": False, "conf": 0.8,
        },
    })
    fake_claude(payload)
    res = log("built an mcp server for hec-ras runs, made it way faster")
    assert res.exit_code == 0, res.output
    c = outbox_cards(home)[0]
    validate("card", c)
    assert c["txt"].startswith("Developed a Model Context Protocol")
    assert c["k"] == "result" and c["r"] is None and "needs_metric" in c["flags"]
    assert c["s"] == ["hec-ras", "mcp-server-development"]


def test_llm_mode_rejects_invented_metric(home, device, fake_claude):
    payload = json.dumps({"type": "result", "structured_output": {
        "txt": "Cut latency by 73%", "s": ["python"], "d": 2, "r": {"m": "latency", "val": 73, "unit": "%", "dir": "down"},
        "needs_metric": False, "work": False, "conf": 0.9}})
    fake_claude(payload)
    res = log("made the python service faster")
    assert res.exit_code == 0, res.output
    c = outbox_cards(home)[0]
    assert c["r"] is None and "needs_metric" in c["flags"]


def test_llm_unavailable_falls_back_to_raw_with_warning(home, device):
    res = log("Calibrated Manning's n with Bayesian inference", "--skill", "bayesian-calibration", "--depth", "3")
    assert res.exit_code == 0, res.output
    assert "falling back" in res.output.lower()
    c = outbox_cards(home)[0]
    assert "manual_raw" in c["flags"] and c["s"] == ["bayesian-calibration"]


def test_llm_unavailable_without_skill_is_an_error(home, device):
    res = log("Did something clever")
    assert res.exit_code != 0
    assert "--skill" in res.output


def test_extracting_guard_prevents_recursion(home, device, monkeypatch):
    monkeypatch.setenv("CVPRISM_EXTRACTING", "1")
    res = log(*RAW)
    assert res.exit_code == 0
    assert outbox_cards(home) == []


def test_llm_keeps_grounded_baseline(home, device, fake_claude):
    payload = json.dumps({"type": "result", "structured_output": {
        "txt": "Cut model setup time from 120 to 15 minutes", "s": ["python"], "d": 3,
        "r": {"m": "setup time", "val": 15, "unit": "min", "dir": "down", "base": 120},
        "needs_metric": False, "work": False}})
    fake_claude(payload)
    log("cut model setup from 120 to 15 minutes with python")
    assert outbox_cards(home)[0]["r"]["base"] == 120


def test_llm_drops_ungrounded_baseline(home, device, fake_claude):
    payload = json.dumps({"type": "result", "structured_output": {
        "txt": "Cut setup to 15 minutes", "s": ["python"], "d": 3,
        "r": {"m": "setup time", "val": 15, "unit": "min", "dir": "down", "base": 999},
        "needs_metric": False, "work": False}})
    fake_claude(payload)
    log("cut model setup to 15 minutes with python")
    assert "base" not in outbox_cards(home)[0]["r"]
