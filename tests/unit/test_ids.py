import hashlib
import json

import pytest

from cvprism.novelty.ids import canonical, card_id, kind_for, normnum, result_fp, slugify
from tests.conftest import FIXTURES


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("MCP Server Development", "mcp-server-development"),
        ("  HEC-RAS 2D ", "hec-ras-2d"),
        ("C++", "c-plus-plus"),
        ("C#", "c-sharp"),
        ("Node.js", "node-js"),
        ("scikit_learn", "scikit-learn"),
        ("---", ""),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


@pytest.mark.parametrize(
    "val, expected",
    [(0.50, "0.5"), (1e3, "1000"), (40, "40"), (-40.0, "-40"), (3.14159, "3.14159"), ("2.50", "2.5"), (0, "0")],
)
def test_normnum(val, expected):
    assert normnum(val) == expected


def base_card(**over):
    c = {
        "k": "skill", "s": ["mcp-server-development"], "d": 3, "r": None, "ctx": None,
        "txt": "Built an MCP server", "t": "2026-11-27T14:02:11Z", "dev": "office-01-7f3a",
        "src": "manual", "meth": ["x"], "tl": ["python"], "dom": ["applied-ai"], "conf": 1.0,
    }
    c.update(over)
    return c


def test_id_has_expected_shape():
    assert card_id(base_card()).startswith("c_") and len(card_id(base_card())) == 18


def test_id_matches_independent_sha256():
    expected_canon = '{"ctx":null,"d":3,"k":"skill","r":null,"s":["mcp-server-development"]}'
    assert canonical(base_card()) == expected_canon
    assert card_id(base_card()) == "c_" + hashlib.sha256(expected_canon.encode()).hexdigest()[:16]


@pytest.mark.parametrize(
    "field, value",
    [("txt", "Different wording entirely"), ("t", "2030-01-01T00:00:00Z"), ("dev", "lab-ws-3c1d"),
     ("src", "claude_session"), ("meth", []), ("tl", ["rust"]), ("dom", []), ("conf", 0.2)],
)
def test_id_ignores_non_canonical_fields(field, value):
    assert card_id(base_card(**{field: value})) == card_id(base_card())


@pytest.mark.parametrize("field, value", [("d", 4), ("ctx", "flood-copilot"), ("k", "work"), ("s", ["python"])])
def test_id_changes_with_canonical_fields(field, value):
    assert card_id(base_card(**{field: value})) != card_id(base_card())


def test_id_is_order_insensitive_for_skills():
    a = base_card(s=["python", "fastapi"])
    b = base_card(s=["fastapi", "python", "python"])
    assert card_id(a) == card_id(b)


def test_result_normalisation_in_id():
    r1 = {"m": "Inference Latency", "val": 40.0, "unit": "MS ", "dir": "down"}
    r2 = {"m": "inference latency", "val": 40, "unit": "ms", "dir": "down", "base": 100}
    assert card_id(base_card(k="result", r=r1)) == card_id(base_card(k="result", r=r2))


def test_result_fp_is_12_hex():
    fp = result_fp({"m": "latency", "val": 40, "unit": "ms", "dir": "down"})
    assert len(fp) == 12 and int(fp, 16) >= 0


@pytest.mark.parametrize(
    "work, r, flags, expected",
    [(True, None, [], "work"), (False, {"m": "x", "val": 1, "unit": "%", "dir": "up"}, [], "result"),
     (False, None, ["needs_metric"], "result"), (False, None, [], "skill")],
)
def test_kind_is_pure_function_of_content(work, r, flags, expected):
    assert kind_for(work=work, r=r, flags=flags) == expected


def test_golden_ids_are_stable():
    """Locks the canonical form across OSes / Python versions (M1 criterion 5)."""
    golden = json.loads((FIXTURES / "golden_ids.json").read_text(encoding="utf-8"))
    assert len(golden) >= 50
    for case in golden:
        assert canonical(case["card"]) == case["canonical"], case
        assert card_id(case["card"]) == case["id"], case
