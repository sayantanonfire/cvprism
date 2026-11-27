from cvprism.capture.redact import Redactor, find_secrets


def test_detects_common_secret_formats():
    text = ("aws AKIAABCDEFGHIJKLMNOP gh ghp_" + "a" * 36 + " anthropic sk-ant-api03-" + "x" * 30
            + " jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123def456")
    kinds = {k for k, _ in find_secrets(text)}
    assert {"aws", "github", "anthropic", "jwt"} <= kinds


def test_high_entropy_token_detected_but_words_not():
    assert find_secrets("token 9fX2kLq8Zr4Tn7Wb3Yv6Hc1Md5Pg0Js") != []
    assert find_secrets("bayesian-calibration-of-manning-roughness") == []


def test_scrub_text_removes_secrets_paths_urls_and_deny_terms():
    r = Redactor(deny_terms=["Contoso"], replace=[{"pattern": "(?i)acme water", "with": "a water utility"}])
    out = r.scrub_text(
        r"Contoso run with AKIAABCDEFGHIJKLMNOP at C:\Users\jane\x.txt and /home/jane/y.py "
        "see https://intra.example.com/a?b=1 for Acme Water"
    )
    assert "Contoso" not in out and "AKIA" not in out
    assert "jane" not in out and "https://" not in out
    assert "a water utility" in out


def test_card_with_secret_is_dropped():
    r = Redactor()
    card = {"txt": "Used key AKIAABCDEFGHIJKLMNOP to deploy", "meth": [], "tl": [], "flags": []}
    assert r.apply_card(card) is None


def test_card_with_deny_term_is_scrubbed_and_flagged():
    r = Redactor(deny_terms=["Contoso"])
    card = {"txt": "Built flood model for Contoso", "meth": ["contoso calibration"], "tl": [], "flags": []}
    out = r.apply_card(card)
    assert "contoso" not in out["txt"].lower() and "contoso" not in out["meth"][0].lower()
    assert "needs_review" in out["flags"]


def test_plugin_can_drop_card():
    r = Redactor(plugins=[lambda c: None if "secret project" in c["txt"] else c])
    assert r.apply_card({"txt": "the secret project", "meth": [], "tl": [], "flags": []}) is None


def test_load_from_yaml(tmp_path):
    p = tmp_path / "redact.yaml"
    p.write_text("v: 1\ndeny_terms: [Nightingale]\nexclude_paths: ['~/clients/**']\non_secret: drop\n", encoding="utf-8")
    r = Redactor.load(p)
    assert r.deny_terms == ["Nightingale"]
    assert r.is_excluded_path(str(tmp_path / "x")) is False


def test_excluded_paths(tmp_path):
    r = Redactor(exclude_paths=[str(tmp_path / "clients") + "/**"])
    assert r.is_excluded_path(str(tmp_path / "clients" / "acme" / "a.py"))
    assert not r.is_excluded_path(str(tmp_path / "research" / "a.py"))
