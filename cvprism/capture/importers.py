"""Bootstrap a vault from what people already have: a LinkedIn data export or an existing CV (M6).

Imported claims are self-reported, so every card is flagged `needs_review`. LinkedIn's skill list
becomes depth-1 cards (known to the novelty filter, excluded from CVs by default min_depth 2).
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import llm, yamlio
from ..novelty.ids import slugify
from .manual import load_knowledge, load_redactor
from .pipeline import build_and_emit, utcnow
from .prompts import EXTRACT_PROMPT, EXTRACT_SCHEMA

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"], 1)}


@dataclass
class ImportReport:
    cards: int = 0
    known: int = 0
    positions: int = 0
    education: int = 0
    certifications: int = 0
    notes: list[str] = field(default_factory=list)


def li_date(s: str | None) -> str | None:
    """'Mar 2024' -> '2024-03'; '2019' -> '2019'; '' -> None."""
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{4})", s)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}"
    m = re.search(r"\d{4}", s)
    return m.group(0) if m else None


def _read_csvs(src: Path) -> dict[str, list[dict]]:
    files: dict[str, str] = {}
    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as zf:
            for n in zf.namelist():
                if n.lower().endswith(".csv"):
                    files[Path(n).name] = zf.read(n).decode("utf-8-sig", errors="replace")
    elif src.is_dir():
        for p in src.glob("*.csv"):
            files[p.name] = p.read_text(encoding="utf-8-sig", errors="replace")
    else:
        raise FileNotFoundError(f"{src} is not a LinkedIn export folder or .zip")
    out = {}
    for name, text in files.items():
        lines = text.splitlines()
        # some exports start with a "Notes:" preamble before the header row
        start = next((i for i, ln in enumerate(lines) if "," in ln and not ln.lower().startswith("notes")), 0)
        out[name] = list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))
    return out


def _skills_in(text: str) -> list[str]:
    from ..compile.jd import extract_jd_deterministic

    return extract_jd_deterministic(text)["skills"][:5]


def _llm_cards(text: str, source: str, cfg: dict, known) -> list[dict]:
    ext = cfg.get("extraction") or {}
    digest = json.dumps({"source": source, "text": text[:12000]}, ensure_ascii=False)
    prompt = EXTRACT_PROMPT.format(known=", ".join(sorted(known.skills)[:300]) or "(none yet)", digest=digest)
    res = llm.run_json(prompt, EXTRACT_SCHEMA, model=ext.get("model"), timeout=int(ext.get("timeout_s", 120)))
    return [c for c in res.get("cards", []) if isinstance(c, dict)]


def _emit(fields: dict, cfg: dict, known, redactor, rep: ImportReport, source_text: str, t: str | None,
          ref: str) -> None:
    oc = build_and_emit(fields, cfg=cfg, known=known, src="import", source_text=source_text, redactor=redactor,
                        flags=["needs_review"], ref=ref, now=t)
    if oc.card:
        rep.cards += 1
    elif not oc.dropped:
        rep.known += 1


def _text_cards(text: str, source: str, t: str | None, cfg: dict, known, redactor, rep: ImportReport,
                use_llm: bool, fallback_txt: str | None = None) -> None:
    if use_llm:
        try:
            for cand in _llm_cards(text, source, cfg, known):
                _emit(cand, cfg, known, redactor, rep, text, t, ref=source)
            return
        except llm.LLMUnavailable as e:
            rep.notes.append(f"Claude unavailable ({e}); used keyword matching")
    skills = _skills_in(text)
    if skills:
        txt = " ".join((fallback_txt or text).split())
        _emit({"txt": txt, "s": skills, "d": 2, "conf": 0.6}, cfg, known, redactor, rep, text, t, ref=source)


def _merge_list(existing: list, new: list, key) -> tuple[list, int]:
    have = {key(e) for e in existing}
    added = [n for n in new if key(n) not in have]
    return existing + added, len(added)


def import_linkedin(src: Path, cfg: dict, *, use_llm: bool = True) -> ImportReport:
    rep = ImportReport()
    data = _read_csvs(Path(src))
    known = load_knowledge(cfg["device_id"])
    redactor = load_redactor(cfg)

    if cfg.get("role") == "hub" and cfg.get("vault_path"):
        pf = Path(cfg["vault_path"]) / "profile.yaml"
        prof = (yamlio.load(pf) if pf.is_file() else None) or {"v": 1, "person": {"name": "Your Name"}}
        person = prof.setdefault("person", {})
        for row in data.get("Profile.csv", [])[:1]:
            full = " ".join(x for x in [row.get("First Name", "").strip(), row.get("Last Name", "").strip()] if x)
            if full and person.get("name") in (None, "", "Your Name"):
                person["name"] = full
            if row.get("Geo Location") and not person.get("location"):
                person["location"] = row["Geo Location"].strip()
            urls = re.findall(r"https?://[^\s,\]]+", row.get("Websites", "") or "")
            links = person.setdefault("links", [])
            for u in urls:
                if all(l.get("url") != u for l in links):
                    label = "GitHub" if "github.com" in u else "Website"
                    links.append({"label": label, "url": u})
            if not links:
                person.pop("links")
        new_pos = []
        for row in data.get("Positions.csv", []):
            start = li_date(row.get("Started On"))
            if not (row.get("Company Name") and row.get("Title") and start):
                continue
            p = {"id": slugify(f"{row['Company Name']}-{start}")[:40], "title": row["Title"].strip(),
                 "org": row["Company Name"].strip(), "start": start, "end": li_date(row.get("Finished On"))}
            if row.get("Location"):
                p["location"] = row["Location"].strip()
            new_pos.append(p)
        prof["positions"], rep.positions = _merge_list(prof.get("positions") or [], new_pos,
                                                       lambda p: (p["org"].lower(), p["title"].lower(), str(p["start"])))
        new_edu = []
        for row in data.get("Education.csv", []):
            if row.get("School Name"):
                e = {"degree": (row.get("Degree Name") or "Studies").strip(), "institution": row["School Name"].strip(),
                     "end": li_date(row.get("End Date")) or li_date(row.get("Start Date")) or ""}
                if li_date(row.get("Start Date")):
                    e["start"] = li_date(row.get("Start Date"))
                new_edu.append(e)
        prof["education"], rep.education = _merge_list(prof.get("education") or [], new_edu,
                                                       lambda e: (e["institution"].lower(), e["degree"].lower()))
        new_cert = [{"name": r["Name"].strip(), "issuer": (r.get("Authority") or "").strip() or "-",
                     "date": li_date(r.get("Started On")) or ""}
                    for r in data.get("Certifications.csv", []) if r.get("Name")]
        prof["certifications"], rep.certifications = _merge_list(prof.get("certifications") or [], new_cert,
                                                                 lambda c: c["name"].lower())
        yamlio.dump(prof, pf)
    else:
        rep.notes.append("profile facts are only written on the hub; cards were still captured here")

    for row in data.get("Skills.csv", []):
        name = (row.get("Name") or "").strip()
        if name:
            _emit({"txt": f"Lists {name} as a skill on LinkedIn (self-reported)", "s": [name], "d": 1, "conf": 0.6},
                  cfg, known, redactor, rep, "", None, ref="linkedin:skills")
    for row in data.get("Positions.csv", []):
        desc = (row.get("Description") or "").strip()
        start = li_date(row.get("Started On"))
        if desc:
            t = f"{start}-01T00:00:00Z" if start and len(start) == 7 else (f"{start}-01-01T00:00:00Z" if start else None)
            _text_cards(desc, "linkedin:position", t, cfg, known, redactor, rep, use_llm)
    return rep


def cv_text(path: Path) -> tuple[str, list[str]]:
    """(full text, bullet-like lines)."""
    suf = path.suffix.lower()
    if suf == ".docx":
        import docx

        doc = docx.Document(str(path))
        paras = [p for p in doc.paragraphs if p.text.strip()]
        bullets = [p.text.strip() for p in paras if "list" in (p.style.name or "").lower()]
        return "\n".join(p.text for p in paras), bullets
    if suf == ".pdf":
        try:
            import pypdf
        except ImportError as e:
            raise ValueError("Reading PDFs needs `pip install pypdf` (or save your CV as .docx/.md)") from e
        text = "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(str(path)).pages)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    bullets = [re.sub(r"^\s*[-*•●▪]\s+", "", ln).strip() for ln in text.splitlines()
               if re.match(r"^\s*[-*•●▪]\s+\S", ln)]
    return text, bullets


def import_cv(path: Path, cfg: dict, *, use_llm: bool = True) -> ImportReport:
    rep = ImportReport()
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    text, bullets = cv_text(path)
    known = load_knowledge(cfg["device_id"])
    redactor = load_redactor(cfg)
    if use_llm:
        try:
            chunks = [text[i:i + 6000] for i in range(0, len(text), 6000)] or [""]
            for ch in chunks:
                for cand in _llm_cards(ch, "existing CV", cfg, known):
                    _emit(cand, cfg, known, redactor, rep, ch, None, ref="cv-import")
            return rep
        except llm.LLMUnavailable as e:
            rep.notes.append(f"Claude unavailable ({e}); used keyword matching on bullet points")
    for b in bullets:
        if len(b) >= 8:
            _text_cards(b, "cv-import", None, cfg, known, redactor, rep, use_llm=False, fallback_txt=b[:220])
    return rep


__all__ = ["import_linkedin", "import_cv", "li_date", "utcnow"]
