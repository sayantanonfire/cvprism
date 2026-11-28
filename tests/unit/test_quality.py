"""ADR-016: no repetition, no weak openers, merged near-duplicates."""
from cvprism.compile.quality import first_verb, merge_duplicates, review, vary_verbs


def b(text, cites=("c_1",), level="captured"):
    return {"text": text, "cites": list(cites), "level": level}


def test_first_verb():
    assert first_verb("Built an MCP server") == "built"
    assert first_verb("**P:** Built x") == "built"
    assert first_verb("") == ""


def test_repeated_opening_verbs_are_varied():
    out, changed = vary_verbs([b("Built a flood model"), b("Built an API"), b("Built a dashboard"),
                               b("Designed a RAG pipeline")])
    verbs = [first_verb(x["text"]) for x in out]
    assert verbs[0] == "built" and len(set(verbs)) == 4 and changed == 2
    assert out[1]["text"].endswith("an API") and out[1]["text"][0].isupper()


def test_unknown_verbs_are_left_alone():
    out, changed = vary_verbs([b("Calibrated Manning's n"), b("Calibrated a SWAT model")])
    assert changed == 0 and [x["text"] for x in out] == ["Calibrated Manning's n", "Calibrated a SWAT model"]


def test_near_duplicates_are_merged_keeping_stronger_proof():
    cards = {"c_1": {"s": ["mcp-server-development"]}, "c_2": {"s": ["mcp-server-development"]},
             "c_3": {"s": ["python"]}}
    bullets = [
        b("Built a Model Context Protocol server exposing HEC-RAS runs as tools", ["c_1"], "captured"),
        b("Built a Model Context Protocol server exposing HEC-RAS 2D runs as LLM tools", ["c_2"], "public"),
        b("Wrote Python tooling for data pipelines", ["c_3"]),
    ]
    out, merged = merge_duplicates(bullets, cards)
    assert merged == 1 and len(out) == 2
    keep = out[0]
    assert keep["level"] == "public" and set(keep["cites"]) == {"c_1", "c_2"}


def test_different_skills_are_not_merged():
    cards = {"c_1": {"s": ["python"]}, "c_2": {"s": ["rust"]}}
    out, merged = merge_duplicates([b("Built a fast data pipeline tool", ["c_1"]),
                                    b("Built a fast data pipeline tool", ["c_2"])], cards)
    assert merged == 0 and len(out) == 2


def test_review_flags_weak_openers_buzzwords_and_length():
    issues = review([b("Responsible for flood models"), b("Results-driven engineer who built APIs"),
                     b(" ".join(["word"] * 40)), b("Cut setup time from 120 to 15 minutes")])
    kinds = {(i["index"], i["issue"]) for i in issues}
    assert (0, "weak opener") in kinds
    assert (1, "buzzword") in kinds
    assert (2, "too long") in kinds
    assert not any(i["index"] == 3 for i in issues)
