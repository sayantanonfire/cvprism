"""Import publications from the public ORCID API into the vault's BibTeX file (deduplicated by DOI)."""
from __future__ import annotations

import json
import re
import urllib.request

from .bibtex import parse_bibtex

API = "https://pub.orcid.org/v3.0"
_TYPES = {"journal-article": "article", "conference-paper": "inproceedings", "book": "book",
          "book-chapter": "incollection", "preprint": "misc", "dissertation-thesis": "phdthesis", "report": "techreport"}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cvprism"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_bulk(orcid: str) -> dict:
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid):
        raise ValueError(f"not an ORCID iD: {orcid}")
    summary = _get(f"{API}/{orcid}/works")
    codes = [str(s["put-code"]) for g in summary.get("group", []) for s in g.get("work-summary", [])[:1]]
    bulk: dict = {"bulk": []}
    for i in range(0, len(codes), 100):
        bulk["bulk"] += _get(f"{API}/{orcid}/works/{','.join(codes[i:i + 100])}").get("bulk", [])
    return bulk


def _v(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def works_to_entries(bulk: dict) -> list[dict]:
    out = []
    for item in bulk.get("bulk", []):
        w = item.get("work")
        if not w:
            continue
        doi = next((x.get("external-id-value") for x in _v(w, "external-ids", "external-id") or []
                    if x.get("external-id-type") == "doi"), "")
        out.append({
            "key": f"orcid{w.get('put-code')}",
            "type": _TYPES.get(w.get("type", ""), "misc"),
            "title": _v(w, "title", "title", "value") or "",
            "authors": [c["credit-name"]["value"] for c in _v(w, "contributors", "contributor") or []
                        if _v(c, "credit-name", "value")],
            "venue": _v(w, "journal-title", "value") or "",
            "year": _v(w, "publication-date", "year", "value") or "",
            "doi": doi or "",
        })
    return out


def to_bibtex(e: dict) -> str:
    venue_field = "booktitle" if e["type"] in ("inproceedings", "incollection") else "journal"
    fields = [("title", e["title"]), ("author", " and ".join(e["authors"])), (venue_field, e["venue"]),
              ("year", e["year"]), ("doi", e["doi"])]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
    return f"@{e['type']}{{{e['key']},\n{body}\n}}\n"


def merge_into_bib(bib_text: str, entries: list[dict]) -> tuple[str, int]:
    existing = parse_bibtex(bib_text)
    dois = {e["doi"].lower() for e in existing if e.get("doi")}
    titles = {e["title"].lower() for e in existing}
    added = []
    for e in entries:
        if (e["doi"] and e["doi"].lower() in dois) or e["title"].lower() in titles or not e["title"]:
            continue
        added.append(to_bibtex(e))
    text = bib_text.rstrip() + ("\n\n" if bib_text.strip() else "") + "\n".join(added)
    return text, len(added)
