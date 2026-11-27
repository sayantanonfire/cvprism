from cvprism.novelty.filter import Knowledge, decide
from cvprism.novelty.ids import card_id


def card(**over):
    c = {"k": "skill", "s": ["python"], "d": 2, "r": None, "ctx": None, "flags": []}
    c.update(over)
    c["id"] = card_id(c)
    return c


def test_unknown_skill_is_new():
    assert decide(card(), Knowledge()) == "new_skill"


def test_known_skill_same_depth_is_not_novel():
    k = Knowledge()
    k.add_card(card())
    assert decide(card(), k) is None


def test_lower_depth_is_not_novel():
    k = Knowledge()
    k.add_card(card(d=3))
    assert decide(card(d=2), k) is None


def test_higher_depth_is_depth_up():
    k = Knowledge()
    k.add_card(card(d=2))
    assert decide(card(d=3), k) == "depth_up"


def test_new_result_on_known_skill():
    k = Knowledge()
    k.add_card(card())
    r = {"m": "latency", "val": 40, "unit": "ms", "dir": "down"}
    assert decide(card(k="result", r=r), k) == "new_result"


def test_same_result_again_is_not_novel():
    k = Knowledge()
    r = {"m": "latency", "val": 40, "unit": "ms", "dir": "down"}
    k.add_card(card(k="result", r=r))
    assert decide(card(k="result", r=dict(r)), k) is None


def test_work_is_novel_unless_same_id_seen():
    k = Knowledge()
    w = card(k="work", s=["field-survey"])
    assert decide(w, k) == "work"
    k.add_card(w)
    assert decide(card(k="work", s=["field-survey"]), k) is None


def test_knowledge_from_registry():
    reg = {"skills": {"python": {"name": "Python", "max_d": 4, "first": "x", "last": "x", "n": 3,
                                 "rh": [], "aliases": ["py", "python3"]}}}
    k = Knowledge.from_registry(reg)
    assert decide(card(d=4), k) is None
    assert decide(card(d=5), k) == "depth_up"
    assert k.resolve_alias("Python3") == "python"
    assert k.resolve_alias("Totally New Thing") == "totally-new-thing"
