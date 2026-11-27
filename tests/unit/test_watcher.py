"""M2 criterion 5: manifest changes produce signals; ignored paths produce none."""
import json

from cvprism import paths
from cvprism.capture.queue import Queue
from cvprism.capture.watcher import SignalScanner, dependency_names, is_signal_file


def test_signal_file_detection():
    for name in ["requirements.txt", "requirements-dev.txt", "pyproject.toml", "package.json", "environment.yml",
                 ".mcp.json", "SKILL.md", "analysis.ipynb", "Cargo.toml", "go.mod", "dvc.yaml"]:
        assert is_signal_file(name), name
    for name in ["notes.txt", "main.py", "data.csv", "README.md"]:
        assert not is_signal_file(name), name


def test_dependency_parsers(tmp_path):
    (tmp_path / "requirements.txt").write_text("torch>=2.1\n# comment\nnumpy==1.26 ; python_version>'3'\n-e .\n",
                                               encoding="utf-8")
    assert dependency_names(tmp_path / "requirements.txt") == {"torch", "numpy"}
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "^18"},
                                                       "devDependencies": {"vitest": "1"}}), encoding="utf-8")
    assert dependency_names(tmp_path / "package.json") == {"react", "vitest"}
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["httpx>=0.27", "Pydantic"]\n'
                                             '[project.optional-dependencies]\ndev = ["pytest"]\n', encoding="utf-8")
    assert dependency_names(tmp_path / "pyproject.toml") == {"httpx", "pydantic", "pytest"}
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"hecras": {}, "github": {}}}), encoding="utf-8")
    assert dependency_names(tmp_path / ".mcp.json") == {"mcp:hecras", "mcp:github"}
    (tmp_path / "SKILL.md").write_text("---\nname: flood-mapper\ndescription: x\n---\nbody", encoding="utf-8")
    assert dependency_names(tmp_path / "SKILL.md") == {"skill:flood-mapper"}
    nb = {"metadata": {"kernelspec": {"language": "python"}},
          "cells": [{"cell_type": "code", "source": ["import geopandas as gpd\n", "from rasterio.mask import mask\n",
                                                     "x = 'import fake'\n"]}]}
    (tmp_path / "a.ipynb").write_text(json.dumps(nb), encoding="utf-8")
    assert dependency_names(tmp_path / "a.ipynb") == {"geopandas", "rasterio", "lang:python"}


def test_new_dependency_enqueues_once(home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    req = proj / "requirements.txt"
    req.write_text("numpy\n", encoding="utf-8")
    sc = SignalScanner(watch_paths=[str(proj)], ignore=["**/node_modules/**"])
    sc.baseline()                       # existing deps are not "new"
    q = Queue(paths.queue_dir())
    assert sc.handle(req) is False and q.pending() == []
    req.write_text("numpy\ntorch\n", encoding="utf-8")
    assert sc.handle(req) is True
    jobs = q.pending()
    assert len(jobs) == 1 and jobs[0]["payload"]["added"] == ["torch"]
    assert jobs[0]["payload"]["file_kind"] == "requirements.txt"
    assert str(proj) not in json.dumps(jobs[0])   # no absolute paths in the job
    assert sc.handle(req) is False                 # same state again -> nothing


def test_ignored_paths_produce_nothing(home, tmp_path):
    proj = tmp_path / "proj"
    nm = proj / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    sc = SignalScanner(watch_paths=[str(proj)], ignore=["**/node_modules/**"])
    sc.baseline()
    (nm / "package.json").write_text('{"dependencies": {"left-pad": "1"}}', encoding="utf-8")
    assert sc.handle(nm / "package.json") is False
    assert Queue(paths.queue_dir()).pending() == []


def test_files_outside_watch_paths_are_ignored(home, tmp_path):
    sc = SignalScanner(watch_paths=[str(tmp_path / "proj")], ignore=[])
    other = tmp_path / "elsewhere" / "requirements.txt"
    other.parent.mkdir(parents=True)
    other.write_text("torch\n", encoding="utf-8")
    assert sc.handle(other) is False
