"""ATS read-back (ADR-016): read the generated file the way a parser would, and check nothing got lost."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .evidence import short_url


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def normalise(text: str) -> str:
    """Lowercase alphanumerics only: survives line wrapping, hyphenation and markup."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def pdf_text(path: Path) -> str:
    import pypdf

    return "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(str(path)).pages)


def docx_text(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts += [c.text for c in row.cells]
    # hyperlink runs are not in paragraph.text in older python-docx; read raw XML text as a fallback
    xml = d.element.xml
    parts += re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
    return "\n".join(parts)


def read_back(out_dir: Path) -> tuple[str, str]:
    """(file name read, extracted text), preferring what recruiters upload: PDF, then DOCX, then MD."""
    pdf, docx_f, md = out_dir / "cv.pdf", out_dir / "cv.docx", out_dir / "cv.md"
    if pdf.exists():
        try:
            return "cv.pdf", pdf_text(pdf)
        except ImportError:
            pass
    if docx_f.exists():
        try:
            return "cv.docx", docx_text(docx_f)
        except ImportError:
            pass
    return "cv.md", md.read_text(encoding="utf-8")


def _bullets(cv: dict) -> list[dict]:
    out = []
    for s in cv["sections"]:
        if s["key"] == "evidence":
            continue
        for e in s["entries"]:
            out += e.get("bullets") or ([e] if e.get("kind") == "bullet" else [])
    return out


def ats_checks(text: str, cv: dict, size_bytes: int) -> list[Check]:
    n = normalise(text)
    checks = []
    person = cv["person"]
    pos = [n.find(normalise(x)) for x in (person.get("name"), person.get("email")) if x]
    top = all(0 <= p < 300 for p in pos)
    checks.append(Check("contact details at the top", top,
                        "name and email are read first" if top else "name or email not found near the top"))
    missing = [s["title"] for s in cv["sections"] if normalise(s["title"]) not in n]
    checks.append(Check("standard section headings", not missing,
                        "all headings found" if not missing else "not found: " + ", ".join(missing)))
    bullets = _bullets(cv)
    lost = [b["text"] for b in bullets if normalise(b["text"])[:60] not in n]
    checks.append(Check("bullets readable", not lost,
                        f"all {len(bullets)} lines read back" if not lost else
                        f"{len(lost)} of {len(bullets)} bullet(s) could not be read back, e.g. '{lost[0][:60]}'"))
    links = [b["link"] for b in bullets if b.get("link")]
    hidden = [u for u in links if normalise(short_url(u)) not in n]
    checks.append(Check("links visible as text", not hidden,
                        f"{len(links)} proof link(s) readable" if not hidden else
                        f"{len(hidden)} link(s) not readable as text, e.g. {short_url(hidden[0])}"))
    checks.append(Check("file size under 2 MB", size_bytes < 2_000_000, f"{size_bytes / 1e6:.2f} MB"))
    return checks


def keyword_match(text: str, jd_skills: dict[str, str], evidence: set[str]) -> dict:
    n = normalise(text)
    low = (text or "").lower()

    def found(term: str) -> bool:
        if len(normalise(term)) <= 3:  # "Go", "R", "AWS": whole words only, never inside "Google"
            return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", low) is not None
        return normalise(term) in n

    def present(slug, name):
        return found(name) or found(slug.replace("-", " "))

    matched = sorted(name for slug, name in jd_skills.items() if present(slug, name))
    opportunities = sorted(name for slug, name in jd_skills.items() if not present(slug, name) and slug in evidence)
    gaps = sorted(name for slug, name in jd_skills.items() if not present(slug, name) and slug not in evidence)
    score = round(100 * len(matched) / len(jd_skills)) if jd_skills else 0
    return {"matched": matched, "opportunities": opportunities, "gaps": gaps, "score": score}


def ats_md(file_name: str, checks: list[Check], km: dict | None) -> str:
    passed = sum(c.ok for c in checks)
    out = ["# ATS read-back", "", f"Read from: {file_name}. {passed} of {len(checks)} checks passed.", "",
           "| Check | Result | Detail |", "| --- | --- | --- |"]
    out += [f"| {c.name} | {'✓' if c.ok else '✗'} | {c.detail} |" for c in checks]
    if km is not None:
        out += ["", f"## Keyword match: {km['score']}%", "",
                f"- **On your CV:** {', '.join(km['matched']) or '(none)'}",
                f"- **You have evidence, but it's not on this CV:** {', '.join(km['opportunities']) or '(none)'}",
                f"- **Asked for, no evidence (never added):** {', '.join(km['gaps']) or '(none)'}"]
    out += ["", "_ATS checks are heuristics: they catch lost text, hidden contacts and links, but no tool can "
                "guarantee every ATS vendor's behaviour._"]
    return "\n".join(out) + "\n"
