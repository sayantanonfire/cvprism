# ADR-010: RenderCV for PDF, Pandoc for DOCX/MD

- **Status:** Proposed. This **amends** "LaTeX→PDF" in the kickoff spec, pending verification at M4.
- **Date:** 2026-11-27

## Context

We must not build a typesetter. RenderCV takes a YAML CV model and renders a PDF with several maintained themes. Recent major versions moved from LaTeX to **Typst** as the engine, which installs via pip as a small dependency. A full TeX distribution is around 1–4 GB, which conflicts with plug-and-play install from a USB stick. DOCX is still required by many recruiters and ATS portals.

## Decision

- The compiler emits a RenderCV-compatible YAML model, and RenderCV produces the PDF with whatever engine the pinned version uses (Typst expected).
- The compiler emits a Markdown CV. Pandoc (an external binary, optional dependency) converts it to DOCX using a reference `.docx` in `templates/`.
- LaTeX source output (`tex`) is offered only if the pinned RenderCV version supports it. Not a v1 requirement.
- Pin the RenderCV version and isolate it behind `compile/render/rendercv.py`, so it can be swapped.

## Verified at M4 (2026-11-27)

- RenderCV **2.8** renders via **Typst** (no TeX install), 9 themes: classic, ember, engineeringclassic, engineeringresumes, harvard, ink, moderncv, opal, sb2nov. Pinned as `rendercv[full]>=2.8,<3`. It needs Python ≥ 3.12, so PDF output is an optional extra (`pip install cvprism[pdf]`).
- A bare year must be passed as an integer (a string `"2023"` renders as "Jan 2023").
- Page count comes from RenderCV's per-page PNG export, so no PDF library is needed. When a CV exceeds the role's page limit, the build drops bullets per position until it fits.
- **DOCX: python-docx instead of Pandoc.** Pandoc is an external binary that most users lack (it was missing on the reference machine). python-docx is pip-installable and writes ATS-friendly DOCX directly from the CV model. Pandoc is no longer needed.

## Original verification checklist

The exact RenderCV version, its YAML schema, its engine (Typst or LaTeX) and its theme list. Re-confirm the licences of RenderCV and Pandoc against our Apache-2.0 licence (Pandoc is invoked as a separate process, not linked).

## Consequences

Install stays small. DOCX styling is limited to what a Pandoc reference document can express, which is acceptable for ATS-friendly output.
