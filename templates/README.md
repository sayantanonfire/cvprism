# templates

Layout is delegated to [RenderCV](https://github.com/rendercv/rendercv) themes for PDF (ADR-010). Set `template:` in a role profile to one of `classic`, `ember`, `engineeringclassic`, `engineeringresumes`, `harvard`, `ink`, `moderncv`, `opal`, `sb2nov`. DOCX output is generated with python-docx in a plain, ATS-friendly layout. Markdown output is always produced.

Each build writes `cv.rendercv.yaml` next to the PDF. You can hand-edit that file and re-render with `rendercv render cv.rendercv.yaml` for one-off tweaks. Content and ordering always come from role profiles and evidence cards.
