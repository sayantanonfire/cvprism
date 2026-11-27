"""Renderers: Markdown (always), RenderCV PDF (ADR-010, Typst engine), DOCX via python-docx."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .. import yamlio

RENDERCV_THEMES = {"classic", "ember", "engineeringclassic", "engineeringresumes", "harvard", "ink", "moderncv",
                   "opal", "sb2nov"}


def _dates(e: dict) -> str:
    start, end = e.get("start") or "", e.get("end")
    if not start and not end:
        return ""
    return f"{start} – {end or 'present'}" if start else str(end)


def _authors(authors: list[str], highlight: str | None) -> str:
    return ", ".join(f"**{a}**" if highlight and a.strip() == highlight.strip() else a for a in authors)


def _bullet_text(b: dict) -> str:
    return f"**{b['project']}:** {b['text']}" if b.get("project") else b["text"]


# ---- Markdown -----------------------------------------------------------------------------------

def to_markdown(cv: dict) -> str:
    p = cv["person"]
    lines = [f"# {p['name']}", ""]
    if cv.get("headline"):
        lines += [f"**{cv['headline']}**", ""]
    contact = [x for x in [p.get("location"), p.get("email"), p.get("phone")] if x]
    contact += [f"[{l['label']}]({l['url']})" for l in p.get("links") or []]
    if contact:
        lines += [" · ".join(contact), ""]
    for sec in cv["sections"]:
        lines += [f"## {sec['title']}", ""]
        for e in sec["entries"]:
            k = e["kind"]
            if k == "text":
                lines += [e["text"], ""]
            elif k == "experience":
                head = f"### {e['title']}, {e['org']}"
                lines += [head, f"*{', '.join(x for x in [e.get('location'), _dates(e)] if x)}*", ""]
                lines += [f"- {_bullet_text(b)}" for b in e["bullets"]] + [""]
            elif k == "project":
                lines += [f"### {e['name']}", ""] + [f"- {_bullet_text(b)}" for b in e["bullets"]] + [""]
            elif k == "bullet":
                lines += [f"- {e['text']}"]
            elif k == "skills":
                lines += [f"- **{e['label']}:** {', '.join(e['items'])}"]
            elif k == "publication":
                bits = [_authors(e["authors"], cv.get("highlight_name"))]
                bits.append(f"({e['year']})." if e.get("year") else "")
                bits.append(f"*{e['title']}*.")
                if e.get("venue"):
                    bits.append(f"{e['venue']}.")
                if e.get("doi"):
                    bits.append(f"doi:{e['doi']}")
                lines += ["- " + " ".join(b for b in bits if b)]
            elif k == "education":
                lines += [f"- **{e['degree']}{', ' + e['field'] if e.get('field') else ''}**, {e['institution']}"
                          f"{' (' + _dates(e) + ')' if _dates(e) else ''}"
                          + (f". Thesis: *{e['thesis']}*" if e.get("thesis") else "")]
        if lines[-1] != "":
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---- RenderCV ------------------------------------------------------------------------------------

def _rcv_date(v) -> str | int | None:
    """RenderCV renders str 'YYYY' as 'Jan YYYY'; a bare year must be an int."""
    if not v:
        return None
    v = str(v)
    if re.fullmatch(r"\d{4}", v):
        return int(v)
    return v if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", v) else None


def to_rendercv(cv: dict, theme: str) -> dict:
    p = cv["person"]
    out = {"name": p["name"]}
    if cv.get("headline"):
        out["headline"] = cv["headline"]
    for k in ("location", "email", "phone"):
        if p.get(k):
            out[k] = p[k]
    links = p.get("links") or []
    if links:
        out["website"] = links[0]["url"]
    sections = {}
    for sec in cv["sections"]:
        items = []
        for e in sec["entries"]:
            k = e["kind"]
            if k == "text":
                items.append(e["text"])
            elif k == "experience":
                item = {"company": e["org"], "position": e["title"], "highlights": [_bullet_text(b) for b in e["bullets"]]}
                if _rcv_date(e.get("start")):
                    item["start_date"] = _rcv_date(e["start"])
                    item["end_date"] = _rcv_date(e.get("end")) or "present"
                if e.get("location"):
                    item["location"] = e["location"]
                items.append(item)
            elif k == "project":
                items.append({"name": e["name"], "highlights": [_bullet_text(b) for b in e["bullets"]]})
            elif k == "bullet":
                items.append({"bullet": e["text"]})
            elif k == "skills":
                items.append({"label": e["label"], "details": ", ".join(e["items"])})
            elif k == "publication":
                item = {"title": e["title"], "authors": [f"**{a}**" if a == cv.get("highlight_name") else a
                                                         for a in e["authors"]] or ["-"]}
                if e.get("venue"):
                    item["journal"] = e["venue"]
                if _rcv_date(e.get("year")):
                    item["date"] = _rcv_date(e["year"])
                if e.get("doi"):
                    item["doi"] = e["doi"]
                items.append(item)
            elif k == "education":
                item = {"institution": e["institution"], "area": e.get("field") or e["degree"], "degree": e["degree"]}
                if _rcv_date(e.get("end")):
                    item["end_date"] = _rcv_date(e["end"])
                    if _rcv_date(e.get("start")):
                        item["start_date"] = _rcv_date(e["start"])
                if e.get("thesis"):
                    item["highlights"] = [f"Thesis: {e['thesis']}"]
                items.append(item)
        if items:
            sections[sec["title"]] = items
    out["sections"] = sections
    return {"cv": out, "design": {"theme": theme if theme in RENDERCV_THEMES else "classic"}}


def rendercv_available() -> bool:
    try:
        import rendercv  # noqa: F401

        return True
    except ImportError:
        return False


def render_pdf(model: dict, out_dir: Path) -> tuple[Path, int]:
    """Run RenderCV; returns (pdf path, page count from per-page PNGs)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    yml = out_dir / "cv.rendercv.yaml"
    yamlio.dump(model, yml)
    work = out_dir / ".rendercv"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    cmd = [sys.executable, "-m", "rendercv", "render", str(yml), "--quiet",
           "--pdf-path", str(work / "cv.pdf"), "--png-path", str(work / "page.png"),
           "--dont-generate-html", "--dont-generate-markdown", "--typst-path", str(work / "cv.typ")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                       cwd=str(out_dir), timeout=300)
    pdf = work / "cv.pdf"
    if r.returncode != 0 or not pdf.exists():
        raise RuntimeError(f"RenderCV failed: {(r.stderr or r.stdout)[-800:]}")
    pages = len(list(work.glob("page*.png"))) or 1
    final = out_dir / "cv.pdf"
    shutil.move(str(pdf), final)
    shutil.rmtree(work, ignore_errors=True)
    return final, pages


# ---- DOCX ------------------------------------------------------------------------------------------

def _md_runs(par, text: str) -> None:
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not part:
            continue
        run = par.add_run(part)
        run.bold = i % 2 == 1


def to_docx(cv: dict, path: Path) -> Path:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    p = cv["person"]
    d.add_heading(p["name"], level=0)
    if cv.get("headline"):
        d.add_paragraph(cv["headline"]).runs[0].bold = True
    contact = [x for x in [p.get("location"), p.get("email"), p.get("phone")] if x]
    contact += [l["url"] for l in p.get("links") or []]
    if contact:
        d.add_paragraph(" | ".join(contact))
    for sec in cv["sections"]:
        d.add_heading(sec["title"], level=1)
        for e in sec["entries"]:
            k = e["kind"]
            if k == "text":
                d.add_paragraph(e["text"])
            elif k in ("experience", "project"):
                title = f"{e['title']}, {e['org']}" if k == "experience" else e["name"]
                h = d.add_paragraph()
                h.add_run(title).bold = True
                if k == "experience" and _dates(e):
                    h.add_run(f"    {', '.join(x for x in [e.get('location'), _dates(e)] if x)}").italic = True
                for b in e["bullets"]:
                    _md_runs(d.add_paragraph(style="List Bullet"), _bullet_text(b))
            elif k == "bullet":
                _md_runs(d.add_paragraph(style="List Bullet"), e["text"])
            elif k == "skills":
                par = d.add_paragraph()
                par.add_run(e["label"] + ": ").bold = True
                par.add_run(", ".join(e["items"]))
            elif k == "publication":
                par = d.add_paragraph(style="List Bullet")
                _md_runs(par, _authors(e["authors"], cv.get("highlight_name")) + (f" ({e['year']}). " if e.get("year") else ". "))
                par.add_run(e["title"]).italic = True
                if e.get("venue"):
                    par.add_run(f". {e['venue']}.")
            elif k == "education":
                par = d.add_paragraph(style="List Bullet")
                par.add_run(f"{e['degree']}{', ' + e['field'] if e.get('field') else ''}").bold = True
                par.add_run(f", {e['institution']}" + (f" ({_dates(e)})" if _dates(e) else ""))
    d.save(str(path))
    return path
