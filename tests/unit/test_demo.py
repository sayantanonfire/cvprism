import re
from pathlib import Path

from typer.testing import CliRunner

from cvprism import paths
from cvprism.cli import app

runner = CliRunner()


def test_demo_builds_everything_offline_without_touching_config(home, tmp_path):
    res = runner.invoke(app, ["demo", "--out", str(tmp_path / "demo"), "--format", "md"])
    assert res.exit_code == 0, res.output
    assert not paths.device_file().exists()
    outs = [Path(p.strip()) for p in re.findall(r"-> (.+)", res.output)]
    assert len(outs) == 4
    for o in outs:
        assert (o / "cv.md").exists() and (o / "evidence.md").exists()
    assert any((o / "gaps.md").exists() for o in outs)
    assert "Asha Verma" in (outs[0] / "cv.md").read_text(encoding="utf-8")
