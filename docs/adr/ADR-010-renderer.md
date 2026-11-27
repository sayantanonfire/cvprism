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

## Verify at M4

The exact RenderCV version, its YAML schema, its engine (Typst or LaTeX) and its theme list. Re-confirm the licences of RenderCV and Pandoc against our Apache-2.0 licence (Pandoc is invoked as a separate process, not linked).

## Consequences

Install stays small. DOCX styling is limited to what a Pandoc reference document can express, which is acceptable for ATS-friendly output.
