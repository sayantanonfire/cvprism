from cvprism.capture.reduce import reduce_transcript
from cvprism.capture.redact import Redactor
from tests.conftest import FIXTURES

SESSION = FIXTURES / "sessions" / "mcp_build.jsonl"


def digest():
    return reduce_transcript(SESSION, Redactor(deny_terms=["Contoso"]), max_chars=8000)


def test_digest_keeps_signals():
    d = digest()
    assert "fastmcp" in d.packages and "boto3" in d.packages and "@modelcontextprotocol/sdk" in d.packages
    assert d.tools["Bash"] == 3
    assert ".py" in d.extensions and ".hdf" in d.extensions
    assert "hecras" in d.mcp_servers
    assert "geomaster" in d.skills_used
    assert "pytest" in d.commands and "git" in d.commands
    assert any("MCP server" in p for p in d.prompts)
    assert "async job queue" in d.final_summary


def test_digest_drops_content_and_secrets():
    text = digest().render()
    assert "SECRET DATA ROW" not in text            # tool output never included
    assert "API_KEY" not in text                    # file contents never included
    assert "AKIA" not in text                       # secrets scrubbed from prompts
    assert "Contoso" not in text and "contoso" not in text   # deny terms scrubbed (also in cwd/paths)
    assert "jane" not in text                       # absolute paths scrubbed
    assert "/clear" not in text                     # meta/command messages skipped


def test_digest_respects_budget():
    assert len(digest().render()) <= 8000
    small = reduce_transcript(SESSION, Redactor(), max_chars=600).render()
    assert len(small) <= 600


def test_missing_transcript_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        reduce_transcript(tmp_path / "gone.jsonl", Redactor())
