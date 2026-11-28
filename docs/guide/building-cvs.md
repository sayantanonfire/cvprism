# Building CVs

CVs are built on the hub from your evidence cards plus `profile.yaml`: the facts cvprism never infers, such as your name, positions, education and publications.

## For a role

```bash
cvprism roles                         # academic, industry-ds, applied-ai, hydrodynamics, geospatial, + yours
cvprism build --role academic
```

Each build writes a timestamped folder in `vault/build/<role>/` containing:

| File | What it is |
| --- | --- |
| `cv.pdf` | Typeset with [RenderCV](https://github.com/rendercv/rendercv), fitted to the role's page limit |
| `cv.docx` | Plain, ATS-friendly Word file |
| `cv.md` | Markdown |
| `evidence.md` | Every bullet with the cards it cites |
| `rejected.md` | Drafted claims removed because no evidence supported them |
| `cv.rendercv.yaml` | Editable source for one-off layout tweaks |

`--no-llm` uses your card text directly, with no Claude call.

## For a specific job posting

```bash
cvprism build --jd posting.txt        # or a URL
```

You also get `gaps.md`: skills the posting asks for that you have no evidence of, skills with thin evidence, and related evidence you do have. cvprism never adds a skill to your CV without evidence.

## Your own role

Create `roles/<id>.yaml` in your vault and inherit from a starter:

```yaml
v: 1
id: ml-engineer
title: Machine Learning Engineer
extends: applied-ai
vocabulary: [PyTorch, distributed training, inference optimisation]
limits: {pages: 1}
template: sb2nov
```

Themes: `classic`, `ember`, `engineeringclassic`, `engineeringresumes`, `harvard`, `ink`, `moderncv`, `opal`, `sb2nov`.

## Mirror the market's language

```bash
cvprism market add applied-ai posting1.txt
cvprism market add applied-ai https://example.com/jobs/456
cvprism market extract applied-ai
```

Phrases that recur in at least 30% of your saved postings are added to the role's vocabulary. They influence which evidence is chosen and how it is worded, never what is claimed.

## The honesty rule

Every bullet must cite at least one card. Every number in a bullet must appear in a cited card's result, a value derived from it (87.5% from 120 → 15 minutes), the card text, or a fact you wrote in `profile.yaml`. Vague quantities like "dozens" are rejected too. This is enforced by code ([ADR-009](../adr/ADR-009-honesty-gate.md)).
