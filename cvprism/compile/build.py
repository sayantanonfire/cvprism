"""`cvprism build`: role -> selected cards -> drafted + gated bullets -> Markdown / PDF / DOCX."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import llm, yamlio
from ..hub.merge import read_cards
from ..schemas import errors
from . import draft, render
from .bibtex import parse_bibtex
from .gate import check_bullet
from .roles import load_role
from .select import eligible, select_cards


class BuildError(RuntimeError):
    pass


@dataclass
class BuildResult:
    out_dir: Path
    log: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def _ids(p: Path) -> set[str]:
    return set(p.read_text(encoding="utf-8").split()) if p.is_file() else set()


def load_profile(vault: Path) -> dict:
    p = vault / "profile.yaml"
    if not p.is_file():
        raise BuildError(f"No profile at {p}. Fill in your name, positions and education first.")
    prof = yamlio.load(p) or {}
    errs = errors("profile", prof)
    if errs:
        raise BuildError("profile.yaml is invalid: " + "; ".join(errs[:5]))
    return prof


def publications(vault: Path, profile: dict) -> list[dict]:
    pubs = profile.get("publications") or {}
    bib = pubs.get("bibtex")
    entries = []
    if bib and (vault / bib).is_file():
        entries = parse_bibtex((vault / bib).read_text(encoding="utf-8"))
    return sorted(entries, key=lambda e: (e.get("year") or "0000"), reverse=True)


def _gate_all(groups: dict[str, list[dict]], cards_by_id: dict, facts: list, cfg: dict, use_llm: bool,
              log: list[str]) -> tuple[dict[str, list[dict]], list[dict]]:
    rejected: list[dict] = []
    failing: list[tuple[str, int, list[str]]] = []
    for g, bullets in groups.items():
        for i, b in enumerate(bullets):
            ok, why = check_bullet(b, cards_by_id, facts)
            if not ok:
                failing.append((g, i, why))
    if failing and use_llm:
        fixed = draft.repair([groups[g][i] for g, i, _ in failing], [w for _, _, w in failing], cards_by_id, cfg)
        if fixed:
            still = []
            for (g, i, _), nb in zip(failing, fixed):
                ok, why = check_bullet(nb, cards_by_id, facts)
                if ok:
                    groups[g][i] = nb
                else:
                    still.append((g, i, why))
            log.append(f"repair pass fixed {len(failing) - len(still)} of {len(failing)} bullet(s)")
            failing = still
    drop = {(g, i) for g, i, _ in failing}
    for g, i, why in failing:
        rejected.append({"section": g, "text": groups[g][i]["text"], "cites": groups[g][i].get("cites"),
                         "reasons": why})
    clean = {g: [b for i, b in enumerate(bs) if (g, i) not in drop] for g, bs in groups.items()}
    return clean, rejected


def assemble(profile: dict, role: dict, bullets: dict, selected: list[dict], registry: dict, pubs: list[dict],
             cards_by_id: dict, per_pos: int) -> dict:
    sections = []
    for key in role["sections"]:
        entries: list[dict] = []
        if key == "summary" and bullets.get("summary"):
            entries = [{"kind": "text", "text": bullets["summary"]["text"]}]
        elif key == "experience":
            for p in sorted(profile.get("positions") or [], key=lambda p: str(p["start"]), reverse=True):
                bs = render.label_groups(
                    draft.order_bullets(bullets["positions"].get(p["id"], []), cards_by_id, role)[:per_pos])
                entries.append({"kind": "experience", "title": p["title"], "org": p["org"],
                                "location": p.get("location"), "start": p.get("start"), "end": p.get("end"),
                                "bullets": bs})
        elif key == "projects":
            for name, bs in bullets["projects"].items():
                bs = draft.order_bullets(bs, cards_by_id, role)[:per_pos]
                if bs:
                    entries.append({"kind": "project", "name": name, "bullets": bs})
            for b in bullets["work"].get("projects", []):
                entries.append({"kind": "project", "name": b.get("project") or "Selected work",
                                "bullets": [dict(b, project=None)]})
        elif key == "skills":
            entries = draft.skills_section(selected, registry, role)
        elif key == "publications":
            entries = [dict(e, kind="publication") for e in pubs]
        elif key == "education":
            entries = [{"kind": "education", **e} for e in profile.get("education") or []]
        elif key == "certifications":
            entries = [{"kind": "bullet", "text": f"{c['name']}, {c['issuer']} ({c['date']})"}
                       for c in profile.get("certifications") or []]
        elif key in ("talks", "fieldwork", "teaching", "awards"):
            entries = [{"kind": "bullet", "text": b["text"], "cites": b["cites"]} for b in bullets["work"].get(key, [])]
            if key == "awards":
                entries += [{"kind": "bullet", "text": a.get("name") or a.get("text", "")}
                            for a in profile.get("awards") or [] if a.get("name") or a.get("text")]
        elif key == "languages":
            entries = [{"kind": "bullet", "text": l.get("name", "") + (f" ({l['level']})" if l.get("level") else "")}
                       for l in profile.get("languages") or []]
        if entries:
            sections.append({"key": key, "title": draft.SECTION_TITLES.get(key, key.title()), "entries": entries})
    return {"person": profile["person"], "headline": role["title"], "sections": sections,
            "highlight_name": (profile.get("publications") or {}).get("highlight_name")}


def _evidence_md(cv: dict, cards_by_id: dict) -> str:
    out = [f"# Evidence trace: {cv['person']['name']} / {cv['headline']}", "",
           "Every bullet below lists the evidence cards it cites.", ""]
    for sec in cv["sections"]:
        rows = []
        for e in sec["entries"]:
            for b in e.get("bullets", []) or ([e] if e.get("cites") else []):
                rows.append(b)
        if sec["key"] == "summary":
            rows = [dict(text=sec["entries"][0]["text"], cites=cv.get("summary_cites") or [])]
        if not rows:
            continue
        out += [f"## {sec['title']}", ""]
        for b in rows:
            out.append(f"- {b['text']}")
            for cid in b.get("cites") or []:
                c = cards_by_id.get(cid)
                if c:
                    out.append(f"  - `{cid}` ({c['t'][:10]}, {c['src']}, depth {c['d']}): {c['txt']}")
        out.append("")
    return "\n".join(out)


def _rejected_md(rejected: list[dict]) -> str:
    if not rejected:
        return "# Rejected bullets\n\nNone. Every drafted bullet passed the honesty gate.\n"
    out = ["# Rejected bullets", "", "These drafted bullets were removed by the honesty gate (ADR-009).", ""]
    for r in rejected:
        out += [f"- **{r['text']}** ({r['section']})", *[f"  - {why}" for why in r["reasons"]]]
    return "\n".join(out) + "\n"


def build_cv(cfg: dict, role_name: str, *, use_llm: bool = True, formats: list[str] | None = None,
             out_root: Path | None = None, role_override: dict | None = None) -> BuildResult:
    if cfg.get("role") != "hub":
        raise BuildError("CVs are built on the hub. This device is a spoke.")
    vault = Path(cfg["vault_path"])
    profile = load_profile(vault)
    role = role_override or load_role(role_name, vault)
    from .market import vocabulary_for

    market_vocab = vocabulary_for(role["id"], vault)
    if market_vocab:
        role = dict(role, vocabulary=list(dict.fromkeys(list(role.get("vocabulary") or []) + market_vocab)))
    hidden = _ids(vault / "suppressed.txt") | _ids(vault / "purged.txt")
    cards = [c for c in read_cards(vault) if c["id"] not in hidden]
    cards_by_id = {c["id"]: c for c in cards}
    reg_file = vault / "registry.json"
    registry = json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.is_file() else {}
    selected = select_cards(cards, role)
    log = [f"role {role['id']}: {sum(1 for c in cards if eligible(c, role))} eligible card(s), "
           f"{len(selected)} selected (limit {role['limits']['cards_to_llm']})"]

    used_llm = False
    if use_llm and selected:
        try:
            bullets = draft.llm_bullets(selected, profile, role, cfg)
            used_llm = True
        except llm.LLMUnavailable as e:
            log.append(f"warning: Claude unavailable ({e}); using card text directly")
            bullets = draft.deterministic_bullets(selected, profile, role)
    else:
        bullets = draft.deterministic_bullets(selected, profile, role)

    groups = {f"pos:{k}": v for k, v in bullets["positions"].items()}
    groups |= {f"proj:{k}": v for k, v in bullets["projects"].items()}
    groups |= {f"work:{k}": v for k, v in bullets["work"].items()}
    if bullets.get("summary"):
        groups["summary"] = [bullets["summary"]]
    facts = profile.get("facts") or []
    clean, rejected = _gate_all(groups, cards_by_id, facts, cfg, used_llm, log)
    bullets = {
        "summary": (clean.get("summary") or [None])[0],
        "positions": {k[4:]: v for k, v in clean.items() if k.startswith("pos:")},
        "projects": {k[5:]: v for k, v in clean.items() if k.startswith("proj:")},
        "work": {k[5:]: v for k, v in clean.items() if k.startswith("work:")},
    }
    kept = sum(len(v) for v in clean.values())
    log.append(f"bullets: {kept} kept, rejected {len(rejected)}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = (out_root or vault / "build" / role["id"]) / stamp
    out.mkdir(parents=True, exist_ok=True)
    pubs = publications(vault, profile)
    per_pos = int(role["limits"]["bullets_per_position"])
    cv = assemble(profile, role, bullets, selected, registry, pubs, cards_by_id, per_pos)
    cv["summary_cites"] = (bullets.get("summary") or {}).get("cites")

    wanted = formats or role.get("outputs") or ["md"]
    meta = {"role": role["id"], "created": draft.now_iso(), "llm": used_llm, "cards_total": len(cards),
            "cards_selected": len(selected), "bullets": kept, "rejected": len(rejected),
            "page_limit": role["limits"]["pages"], "pages": None, "formats": []}
    if "pdf" in wanted:
        if render.rendercv_available():
            theme = role.get("template") or "classic"
            def _render(n):
                c = assemble(profile, role, bullets, selected, registry, pubs, cards_by_id, n)
                c["summary_cites"] = (bullets.get("summary") or {}).get("cites")
                return c, render.render_pdf(render.to_rendercv(c, theme), out)

            cv, (pdf, pages, sparse) = _render(per_pos)
            while pages > role["limits"]["pages"] and per_pos > 1:
                per_pos -= 1
                cv, (pdf, pages, sparse) = _render(per_pos)
            if pages > 1 and sparse and per_pos > 2:
                # a nearly empty last page: one bullet fewer per position may pull it back
                cv2, (pdf2, pages2, sparse2) = _render(per_pos - 1)
                if pages2 < pages:
                    cv, pages, per_pos = cv2, pages2, per_pos - 1
                    log.append("tightened layout to avoid a nearly empty last page")
                else:
                    cv, (pdf, pages, sparse) = _render(per_pos)
            meta["pages"] = pages
            meta["formats"].append("pdf")
            if pages > role["limits"]["pages"]:
                log.append(f"warning: {pages} pages exceeds the {role['limits']['pages']}-page limit")
            else:
                log.append(f"pdf: {pages} page(s) (limit {role['limits']['pages']}, {per_pos} bullets/position)")
        else:
            log.append("pdf skipped: install the PDF renderer with `pip install cvprism[pdf]`")
    (out / "cv.md").write_text(render.to_markdown(cv), encoding="utf-8")
    meta["formats"].append("md")
    if "docx" in wanted:
        try:
            render.to_docx(cv, out / "cv.docx")
            meta["formats"].append("docx")
        except ImportError:
            log.append("docx skipped: install with `pip install cvprism[docx]`")
    (out / "evidence.md").write_text(_evidence_md(cv, cards_by_id), encoding="utf-8")
    (out / "rejected.md").write_text(_rejected_md(rejected), encoding="utf-8")
    meta["bullets_per_position"] = per_pos
    (out / "build.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return BuildResult(out_dir=out, log=log, meta=meta)
