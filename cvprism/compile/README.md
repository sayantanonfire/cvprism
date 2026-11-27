# compile

CV generation on the hub: load a role profile (or derive an ad-hoc one from a JD), filter and score cards in code, send a bounded subset plus profile facts to `claude -p` to draft bullets with card citations, enforce the deterministic honesty gate (ADR-009), and render through RenderCV (PDF) and Pandoc (DOCX/MD) (ADR-010). Market-phrase extraction (M5) also lives here.
