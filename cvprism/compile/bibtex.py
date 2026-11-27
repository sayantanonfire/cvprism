"""Small dependency-free BibTeX reader for publication lists (handles nested braces and quotes)."""
from __future__ import annotations

import re

_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.S)


def _read_value(s: str, i: int) -> tuple[str, int]:
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], len(s)
    if s[i] == '"':
        j = i + 1
        depth = 0
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
            elif s[j] == '"' and depth == 0:
                return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], len(s)
    m = re.match(r"[^,}\s]+", s[i:])
    return (m.group(0), i + m.end()) if m else ("", i)


def _clean(v: str) -> str:
    v = re.sub(r"\\[`'^\"~=.](\{?)(\w)\}?", r"\2", v)  # simple accents: \'{e} -> e
    v = v.replace("{", "").replace("}", "").replace("\\&", "&").replace("~", " ")
    return " ".join(v.split())


def parse_bibtex(text: str) -> list[dict]:
    out = []
    for m in _ENTRY.finditer(text):
        etype, key = m.group(1).lower(), m.group(2)
        if etype in ("comment", "string", "preamble"):
            continue
        i, fields = m.end(), {}
        while i < len(text):
            fm = re.match(r"\s*([A-Za-z_\-]+)\s*=", text[i:])
            if not fm:
                break
            name = fm.group(1).lower()
            val, i = _read_value(text, i + fm.end())
            fields[name] = _clean(val)
            cm = re.match(r"\s*,", text[i:])
            if cm:
                i += cm.end()
            if re.match(r"\s*\}", text[i:]):
                break
        authors = [a.strip() for a in re.split(r"\s+and\s+", fields.get("author", "")) if a.strip()]
        out.append({
            "key": key, "type": etype, "title": fields.get("title", ""), "authors": authors,
            "venue": fields.get("journal") or fields.get("booktitle") or fields.get("publisher") or "",
            "year": fields.get("year", ""), "doi": fields.get("doi", ""), "url": fields.get("url", ""),
        })
    return out
