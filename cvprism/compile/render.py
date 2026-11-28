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


def label_groups(bullets: list[dict]) -> list[dict]:
    """Keep bullets of the same project together; show the project label only on the first one."""
    order: list = []
    groups: dict = {}
    for b in bullets:
        k = b.get("project")
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(b)
    out = []
    for k in order:
        for i, b in enumerate(groups[k]):
            out.append(dict(b, project=k if i == 0 else None))
    return out


def last_page_sparse(pngs: list[Path], ratio: float = 0.3) -> bool:
    """A nearly blank page compresses to a much smaller PNG than a full one (stdlib-only proxy)."""
    if len(pngs) < 2:
        return False
    first, last = pngs[0].stat().st_size, pngs[-1].stat().st_size
    return first > 0 and last < ratio * first


LINK_RGB = "rgb(0, 82, 204)"   # #0052CC: accessible blue on white
LINK_HEX = "0052CC"


def _proof_md(b: dict) -> str:
    from .evidence import short_url

    if b.get("link"):
        return f" ([{short_url(b['link'])}]({b['link']}))"
    if b.get("label"):
        return f" *({b['label']})*"
    return ""


def _bullet_text(b: dict) -> str:
    base = f"**{b['project']}:** {b['text']}" if b.get("project") else b["text"]
    return base + _proof_md(b)


def _evidence_proof_md(e: dict) -> str:
    from .evidence import short_url

    if e.get("link"):
        return f"[{short_url(e['link'])}]({e['link']})"
    from .evidence import no_link_text

    return e.get("label") or no_link_text(e.get("level"))


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
                lines += [f"- {_bullet_text(e)}"]
            elif k == "evidence":
                from .evidence import LEVEL_LABEL

                if not lines[-1].startswith("|"):
                    lines += ["| CV line | Proof level | Proof | Captured |", "| --- | --- | --- | --- |"]
                lines += [f"| {e['text'].replace('|', '/')} | {LEVEL_LABEL.get(e['level'], e['level'])} | "
                          f"{_evidence_proof_md(e)} | {e.get('date') or ''} |"]
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
        if sec["key"] == "evidence":
            lines += ["", "*Public proof links open the work itself. Private and local work is listed without links: "
                          "the skill is real, the code is not public.*"]
            if cv.get("verify_url"):
                lines += ["", f"Verify this CV: [{cv['verify_url']}]({cv['verify_url']})"]
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
                items.append({"bullet": _bullet_text(e)})
            elif k == "evidence":
                from .evidence import LEVEL_LABEL

                items.append({"label": LEVEL_LABEL.get(e["level"], e["level"]),
                              "details": f"{e['text']} ({_evidence_proof_md(e)}"
                                         f"{', ' + e['date'] if e.get('date') else ''})"})
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
    design = {"theme": theme if theme in RENDERCV_THEMES else "classic",
              "colors": {"links": LINK_RGB}, "links": {"underline": True}}
    if cv.get("verify_url"):
        out["custom_connections"] = [{"fontawesome_icon": "circle-check", "placeholder": "Verify this CV",
                                      "url": cv["verify_url"]}]
        if cv.get("qr_file"):
            # a "scan to verify" QR in the header's photo slot, sized to stay small
            out["photo"] = cv["qr_file"]
            design["header"] = {"photo_width": "2.1cm", "photo_position": "right"}
    return {"cv": out, "design": design}


def rendercv_available() -> bool:
    try:
        import rendercv  # noqa: F401

        return True
    except ImportError:
        return False


def render_pdf(model: dict, out_dir: Path) -> tuple[Path, int, bool]:
    """Run RenderCV; returns (pdf path, page count, last page nearly empty) from per-page PNGs."""
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
    pngs = sorted(work.glob("page*.png"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    pages = len(pngs) or 1
    sparse = last_page_sparse(pngs)
    final = out_dir / "cv.pdf"
    shutil.move(str(pdf), final)
    shutil.rmtree(work, ignore_errors=True)
    return final, pages, sparse


# ---- DOCX ------------------------------------------------------------------------------------------

def _md_runs(par, text: str) -> None:
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not part:
            continue
        run = par.add_run(part)
        run.bold = i % 2 == 1


def _docx_link(par, url: str, text: str) -> None:
    """Insert a real, blue, underlined hyperlink run (python-docx has no high-level API for this)."""
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    r_id = par.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), LINK_HEX)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(color)
    rpr.append(underline)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    par._p.append(link)


def _docx_bullet(d, b: dict) -> None:
    from docx.shared import RGBColor

    from .evidence import short_url

    par = d.add_paragraph(style="List Bullet")
    base = f"**{b['project']}:** {b['text']}" if b.get("project") else b["text"]
    _md_runs(par, base)
    if b.get("link"):
        par.add_run(" (")
        _docx_link(par, b["link"], short_url(b["link"]))
        par.add_run(")")
    elif b.get("label"):
        r = par.add_run(f" ({b['label']})")
        r.italic = True
        r.font.color.rgb = RGBColor(0x5A, 0x65, 0x77)


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
                    _docx_bullet(d, b)
            elif k == "bullet":
                _docx_bullet(d, e)
            elif k == "evidence":
                pass  # rendered as one table below
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
        if sec["key"] == "evidence":
            _docx_evidence(d, sec["entries"], cv.get("verify_url"), path.parent)
    d.save(str(path))
    return path


def _docx_evidence(d, entries: list[dict], verify_url: str | None, workdir: Path) -> None:
    from docx.shared import Inches

    from .evidence import LEVEL_LABEL, short_url

    table = d.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for cell, head in zip(table.rows[0].cells, ("CV line", "Proof level", "Proof", "Captured")):
        cell.paragraphs[0].add_run(head).bold = True
    for e in entries:
        row = table.add_row().cells
        row[0].text = e["text"]
        row[1].text = LEVEL_LABEL.get(e["level"], e["level"])
        if e.get("link"):
            _docx_link(row[2].paragraphs[0], e["link"], short_url(e["link"]))
        else:
            from .evidence import no_link_text

            row[2].text = e.get("label") or no_link_text(e.get("level"))
        row[3].text = e.get("date") or ""
    d.add_paragraph("Public proof links open the work itself. Private and local work is listed without links: "
                    "the skill is real, the code is not public.").runs[0].italic = True
    if verify_url:
        par = d.add_paragraph("Verify this CV: ")
        _docx_link(par, verify_url, verify_url)
        try:
            from .verify import qr_png

            png = qr_png(verify_url, workdir / ".verify-qr.png")
            d.add_picture(str(png), width=Inches(1.1))
            png.unlink(missing_ok=True)
        except ImportError:
            pass
