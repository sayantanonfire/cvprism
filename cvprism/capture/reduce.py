"""Code-only reducers (ADR-007, SECURITY_PRIVACY.md): raw signals -> small allow-listed digests.

Nothing here ever copies file contents, tool outputs, diffs or data. Only names, counts and the
user's own (truncated, scrubbed) prompts survive.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from .redact import Redactor

_TAGGED = re.compile(r"<([a-z][\w-]*)[^>]*>.*?</\1>", re.S)
_SPLIT_CMDS = re.compile(r"&&|\|\||;|\|")
_INSTALL = {
    ("pip", "install"), ("pip3", "install"), ("uv", "add"), ("uv", "pip"), ("poetry", "add"), ("conda", "install"),
    ("mamba", "install"), ("npm", "install"), ("npm", "i"), ("pnpm", "add"), ("yarn", "add"), ("cargo", "add"),
    ("go", "get"), ("gem", "install"), ("brew", "install"), ("apt", "install"), ("apt-get", "install"),
}
_PKG_VERSION = re.compile(r"(?<=[A-Za-z0-9_\-.])(?:\[.*?\])?(?:[=<>!~^@]=?.*)$")
_FILE_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead"}


def _clean_pkg(tok: str) -> str | None:
    if tok.startswith("-") or tok in (".", "..") or "/" in tok and not tok.startswith("@"):
        return None
    if tok.startswith("@"):  # scoped npm: @scope/name@1.2
        head, _, rest = tok[1:].partition("@")
        return "@" + head if head else None
    name = _PKG_VERSION.sub("", tok)
    return name.lower() if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-.]*", name) else None


def parse_command(cmd: str) -> tuple[list[str], list[str]]:
    """Return (command verbs, installed package names) from a shell command line."""
    verbs, pkgs = [], []
    for part in _SPLIT_CMDS.split(cmd):
        try:
            toks = shlex.split(part.strip(), posix=True)
        except ValueError:
            toks = part.split()
        while toks and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", toks[0]):  # leading VAR=x only
            toks = toks[1:]
        if not toks:
            continue
        exe = PurePath(toks[0]).name.lower()
        exe = re.sub(r"\.(exe|cmd|bat)$", "", exe)
        if exe in ("python", "python3", "py") and len(toks) > 2 and toks[1] == "-m":
            exe = toks[2].lower()
            toks = toks[2:]
        verbs.append(exe)
        if len(toks) > 1 and (exe, toks[1]) in _INSTALL:
            for t in toks[2:]:
                p = _clean_pkg(t)
                if p and p not in ("install", "add", "pip"):
                    pkgs.append(p)
        elif exe in ("pip", "pip3") and len(toks) > 1 and toks[1] == "install":
            pass
    return verbs, pkgs


@dataclass
class Digest:
    source: str
    prompts: list[str] = field(default_factory=list)
    tools: Counter = field(default_factory=Counter)
    extensions: Counter = field(default_factory=Counter)
    packages: list[str] = field(default_factory=list)
    commands: Counter = field(default_factory=Counter)
    mcp_servers: list[str] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)
    final_summary: str = ""
    extra: dict = field(default_factory=dict)

    def render(self, max_chars: int = 24000) -> str:
        def block() -> dict:
            return {
                "source": self.source,
                "user_prompts": self.prompts,
                "tools_used": dict(self.tools.most_common(15)),
                "file_types_touched": dict(self.extensions.most_common(12)),
                "packages_installed": self.packages[:40],
                "commands_run": dict(self.commands.most_common(15)),
                "mcp_servers_used": self.mcp_servers[:10],
                "claude_skills_used": self.skills_used[:10],
                "final_summary": self.final_summary,
                **self.extra,
            }

        text = json.dumps(block(), ensure_ascii=False, indent=0)
        # shrink until within budget: drop middle prompts first, then trim summary, then lists
        while len(text) > max_chars and len(self.prompts) > 2:
            del self.prompts[len(self.prompts) // 2]
            text = json.dumps(block(), ensure_ascii=False, indent=0)
        if len(text) > max_chars:
            self.final_summary = self.final_summary[: max(0, len(self.final_summary) - (len(text) - max_chars) - 3)]
            self.prompts = [p[:120] for p in self.prompts]
            self.packages = self.packages[:10]
            text = json.dumps(block(), ensure_ascii=False, indent=0)
        while len(text) > max_chars and (self.prompts or self.packages):
            if self.prompts:
                self.prompts.pop()
            else:
                self.packages.pop()
            text = json.dumps(block(), ensure_ascii=False, indent=0)
        return text[:max_chars]


def _user_text(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(texts) if texts else None
    return None


def reduce_transcript(path: Path, redactor: Redactor, *, max_chars: int = 24000,
                      prompt_chars: int = 300, max_prompts: int = 15) -> Digest:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    d = Digest(source="claude_code_session")
    prompts: list[str] = []
    pkgs: list[str] = []
    last_text = ""
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("type")
            msg = rec.get("message") if isinstance(rec.get("message"), dict) else None
            if t == "user" and msg and not rec.get("isMeta") and not rec.get("isCompactSummary"):
                txt = _user_text(msg.get("content"))
                if txt:
                    txt = _TAGGED.sub(" ", txt).strip()
                    if txt and not txt.startswith(("<", "Caveat:")):
                        prompts.append(redactor.scrub_text(" ".join(txt.split()))[:prompt_chars])
            elif t == "assistant" and msg and isinstance(msg.get("content"), list):
                for b in msg["content"]:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and b.get("text", "").strip():
                        last_text = b["text"]
                    elif b.get("type") == "tool_use":
                        name = str(b.get("name", ""))
                        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                        if name.startswith("mcp__"):
                            server = name.split("__")[1] if name.count("__") >= 2 else name
                            d.tools["mcp"] += 1
                            if server not in d.mcp_servers:
                                d.mcp_servers.append(server)
                            continue
                        d.tools[name] += 1
                        if name in _FILE_TOOLS:
                            fp = inp.get("file_path") or inp.get("notebook_path") or ""
                            ext = PurePath(str(fp).replace("\\", "/")).suffix.lower()
                            if ext and len(ext) <= 10:
                                d.extensions[ext] += 1
                        elif name in ("Bash", "PowerShell") and isinstance(inp.get("command"), str):
                            verbs, found = parse_command(inp["command"])
                            d.commands.update(verbs)
                            pkgs += [p for p in found if p not in pkgs]
                        elif name == "Skill" and inp.get("skill"):
                            s = str(inp["skill"])
                            if s not in d.skills_used:
                                d.skills_used.append(s)
    if len(prompts) > max_prompts:  # keep the start (intent) and the end (outcome)
        half = max_prompts // 2
        prompts = prompts[:half] + prompts[-(max_prompts - half):]
    d.prompts = prompts
    d.packages = pkgs
    d.final_summary = redactor.scrub_text(" ".join(last_text.split()))[:600]
    d.render(max_chars)  # applies budget trimming in place
    return d


# ---- git ---------------------------------------------------------------------------------------

MANIFESTS = ("requirements", "pyproject.toml", "package.json", "environment.yml", "environment.yaml",
             "Pipfile", "Cargo.toml", "go.mod", "setup.cfg", ".mcp.json")


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=30).stdout


def reduce_commits(repo: str, shas: list[str], redactor: Redactor, *, max_chars: int = 24000) -> Digest:
    d = Digest(source="git_commits")
    subjects, added_deps = [], []
    for sha in shas:
        subj = _git(repo, "log", "-1", "--format=%s", sha).strip()
        if subj:
            subjects.append(redactor.scrub_text(subj)[:200])
        numstat = _git(repo, "show", "--numstat", "--format=", sha)
        changed = []
        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                changed.append(parts[2])
                ext = PurePath(parts[2]).suffix.lower()
                d.extensions[ext or PurePath(parts[2]).name] += 1
        for f in changed:
            if any(PurePath(f).name.startswith(m) or PurePath(f).name == m for m in MANIFESTS):
                diff = _git(repo, "show", "--format=", "--unified=0", sha, "--", f)
                for ln in diff.splitlines():
                    if ln.startswith("+") and not ln.startswith("+++"):
                        name = _dep_from_line(ln[1:])
                        if name and name not in added_deps:
                            added_deps.append(name)
    d.prompts = subjects
    d.packages = added_deps
    d.extra = {"commit_count": len(shas), "project": redactor.scrub_text(PurePath(repo).name)}
    d.render(max_chars)
    return d


_DEP_LINE = re.compile(r"""^\s*["']?(@?[A-Za-z0-9][A-Za-z0-9_\-./]*)["']?\s*(?:[:=<>~!^@\[,;"']|$)""")


def _dep_from_line(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith(("#", "//", "[", "{", "}")):
        return None
    m = _DEP_LINE.match(line)
    if not m:
        return None
    name = m.group(1).rstrip(".").lower()
    if name in ("version", "name", "description", "dependencies", "python", "requires-python", "-e"):
        return None
    return name


def reduce_watch(payloads: list[dict], redactor: Redactor) -> Digest:
    d = Digest(source="project_file_changes")
    for p in payloads:
        for name in p.get("added", []):
            if name not in d.packages:
                d.packages.append(name)
        d.extensions[p.get("file_kind", "?")] += 1
    d.extra = {"projects": sorted({redactor.scrub_text(str(p.get("project", ""))) for p in payloads})}
    return d
