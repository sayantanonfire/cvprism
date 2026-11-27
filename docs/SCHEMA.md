# cvprism File Formats

> Status: **Phase 0 draft**. Schema version `v: 1` everywhere. JSON Schema dialect: draft 2020-12. At M1 the schemas below move verbatim into `cvprism/schemas/*.schema.json`, and this file then links to them.

| Artifact | Format | Owner | Location |
| --- | --- | --- | --- |
| [Evidence card](#-evidence-card) | JSONL, one card per line | Capturing device | `~/.cvprism/outbox/<dev>/YYYY-MM.jsonl` → `vault/inbox/<dev>/YYYY-MM.jsonl` → `vault/cards.jsonl` |
| [Skill registry](#-skill-registry) | JSON | Hub | `vault/registry.json` (spokes cache it as `~/.cvprism/registry.cache.json`) |
| [Device config](#-device-config) | YAML | Each device | `~/.cvprism/device.yaml` |
| [Profile](#-profile) | YAML (+ BibTeX) | User | `vault/profile.yaml` |
| [Role profile](#-role-profile) | YAML | User | `vault/roles/<role>.yaml` (starters in repo `roles/`) |
| Vault and hub identity | JSON | Hub | `vault/vault.json`, `vault/hub.json` (see [SYNC.md](SYNC.md)) |

---

## 📐 Conventions

- **Slugs** match `^[a-z0-9]+(?:-[a-z0-9]+)*$`, e.g. `mcp-server-development`, `hec-ras`.
- **Timestamps** are RFC 3339 UTC with a `Z` suffix, second precision.
- **Device IDs** are `<name-slug>-<4 hex>`, e.g. `office-01-7f3a`. The random suffix prevents two devices called "laptop" from colliding.
- **Compact keys** are used only in high-volume JSONL (cards). YAML files people edit use full words ([ADR-003](adr/ADR-003-plain-files-compact-jsonl.md)).
- **Unknown keys** are allowed on read (`additionalProperties: true` for forward compatibility) and never written by v1 code, except under an `x_` prefix for user extensions.

---

## 🃏 Evidence card

One immutable fact about the user's capability. Cards are never edited. A correction is a new card with `sup: [<old id>]` (supersedes).

### Key reference

| Key | Meaning | In ID hash? |
| --- | --- | :---: |
| `v` | Schema version (1) | no |
| `id` | `c_` + first 16 hex chars of sha256 over the canonical form | — |
| `k` | Kind, derived from content only: `work` (non-code achievement: paper, talk, field campaign, award), else `result` (has `r` or `needs_metric`), else `skill` | **yes** |
| `why` | Novelty reason at capture: `new_skill`, `depth_up`, `new_result`, `work`, `manual` (depends on device state, so never hashed) | no |
| `s` | Skill slugs, 1–5, sorted | **yes** |
| `d` | Depth level 1–5 (see [ADR-011](adr/ADR-011-depth-ladder-novelty.md)) | **yes** |
| `r` | Result `{m, val, unit, base?, dir}` or `null` | **yes** (normalised) |
| `ctx` | Project alias slug (mapped to display text in `profile.yaml`) or `null` | **yes** |
| `txt` | Market-facing one-line statement, ≤ 220 chars | no |
| `meth` | Methods and techniques, short phrases | no |
| `tl` | Tools, libraries, services (slugs) | no |
| `dom` | Domain tags (`applied-ai`, `hydrodynamics`, `geospatial`, `academic`, …) | no |
| `t` | Capture time (UTC) | no |
| `dev` | Device ID | no |
| `src` | `claude_session` · `git_commit` · `watcher` · `manual` · `import` | no |
| `ref` | Opaque evidence pointer, e.g. `git:<repo-alias>@a1b2c3d`, `cc:<session-hash>` | no |
| `conf` | Extractor confidence 0–1 (manual = 1) | no |
| `flags` | `needs_metric`, `needs_review`, `low_confidence`, `manual_raw` | no |
| `sup` | IDs this card supersedes | no |
| `lang` | BCP-47, default `en` | no |

### Canonical form for `id`

```text
canon = JSON(sort_keys, no whitespace, UTF-8) of
  { "k": k,
    "s": sorted(unique(s)),
    "d": d,
    "r": null | { "m": slug(m), "val": normnum(val), "unit": lower(unit), "dir": dir },
    "ctx": ctx }
id = "c_" + sha256(canon).hex()[:16]
```

`normnum` renders a number with no trailing zeros (`0.50` → `0.5`, `1e3` → `1000`). Free text (`txt`, `meth`) is excluded on purpose, because LLM wording varies between captures ([ADR-002](adr/ADR-002-content-hash-ids.md)).

### JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://cvprism.dev/schemas/card.v1.json",
  "title": "cvprism evidence card v1",
  "type": "object",
  "required": ["v", "id", "k", "s", "d", "r", "ctx", "txt", "t", "dev", "src"],
  "properties": {
    "v":    { "const": 1 },
    "id":   { "type": "string", "pattern": "^c_[0-9a-f]{16}$" },
    "k":    { "enum": ["skill", "result", "work"] },
    "why":  { "enum": ["new_skill", "depth_up", "new_result", "work", "manual"] },
    "s":    { "type": "array", "minItems": 1, "maxItems": 5, "uniqueItems": true,
              "items": { "$ref": "#/$defs/slug" } },
    "d":    { "type": "integer", "minimum": 1, "maximum": 5 },
    "r":    { "oneOf": [ { "type": "null" }, { "$ref": "#/$defs/result" } ] },
    "ctx":  { "oneOf": [ { "type": "null" }, { "$ref": "#/$defs/slug" } ] },
    "txt":  { "type": "string", "minLength": 8, "maxLength": 220 },
    "meth": { "type": "array", "maxItems": 8, "items": { "type": "string", "maxLength": 80 } },
    "tl":   { "type": "array", "maxItems": 12, "items": { "$ref": "#/$defs/slug" } },
    "dom":  { "type": "array", "maxItems": 6, "items": { "$ref": "#/$defs/slug" } },
    "t":    { "type": "string", "format": "date-time" },
    "dev":  { "type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{4}$" },
    "src":  { "enum": ["claude_session", "git_commit", "watcher", "manual", "import"] },
    "ref":  { "type": "string", "maxLength": 120 },
    "conf": { "type": "number", "minimum": 0, "maximum": 1 },
    "flags":{ "type": "array", "uniqueItems": true,
              "items": { "enum": ["needs_metric", "needs_review", "low_confidence", "manual_raw"] } },
    "sup":  { "type": "array", "items": { "type": "string", "pattern": "^c_[0-9a-f]{16}$" } },
    "lang": { "type": "string", "default": "en" }
  },
  "allOf": [
    { "if": { "properties": { "k": { "const": "result" } } },
      "then": { "anyOf": [
        { "properties": { "r": { "$ref": "#/$defs/result" } } },
        { "properties": { "flags": { "contains": { "const": "needs_metric" } } } }
      ] } }
  ],
  "$defs": {
    "slug": { "type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 64 },
    "result": {
      "type": "object",
      "required": ["m", "val", "unit", "dir"],
      "properties": {
        "m":    { "type": "string", "maxLength": 60, "description": "metric name, e.g. 'inference latency'" },
        "val":  { "type": "number" },
        "unit": { "type": "string", "maxLength": 20, "description": "'%', 'ms', 'x', 'km2', 'users', ..." },
        "base": { "type": ["number", "null"], "description": "baseline value if stated" },
        "dir":  { "enum": ["up", "down", "abs"], "description": "improvement direction or absolute figure" }
      }
    }
  }
}
```

### Example (one line in JSONL, wrapped here for reading)

```json
{"v":1,"id":"c_3f9a1c0e7b2d4a61","k":"skill","why":"depth_up","s":["mcp-server-development"],"d":3,
 "r":null,"ctx":"flood-copilot",
 "txt":"Built a Model Context Protocol (MCP) server exposing hydrodynamic model runs as LLM tools",
 "meth":["tool schema design","async job orchestration"],"tl":["python","fastmcp","hec-ras"],
 "dom":["applied-ai","hydrodynamics"],"t":"2026-11-27T14:02:11Z","dev":"office-01-7f3a",
 "src":"claude_session","ref":"cc:9c1e44","conf":0.86,"flags":["needs_metric"],"lang":"en"}
```

---

## 📚 Skill registry

Hub-generated and deterministic: rebuilding from `cards.jsonl` with the same seed taxonomy always gives the same file (apart from `generated`). Spokes use it only for the novelty check and alias normalisation.

### JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://cvprism.dev/schemas/registry.v1.json",
  "title": "cvprism skill registry v1",
  "type": "object",
  "required": ["v", "vault_id", "epoch", "rev", "generated", "skills"],
  "properties": {
    "v":         { "const": 1 },
    "vault_id":  { "type": "string", "format": "uuid" },
    "epoch":     { "type": "integer", "minimum": 1, "description": "hub epoch from hub.json" },
    "rev":       { "type": "integer", "minimum": 0, "description": "monotonic within epoch" },
    "generated": { "type": "string", "format": "date-time" },
    "skills": {
      "type": "object",
      "propertyNames": { "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$" },
      "additionalProperties": { "$ref": "#/$defs/entry" }
    }
  },
  "$defs": {
    "entry": {
      "type": "object",
      "required": ["name", "max_d", "first", "last", "n"],
      "properties": {
        "name":    { "type": "string", "description": "display / market name" },
        "aliases": { "type": "array", "items": { "type": "string" },
                     "description": "lower-cased surface forms mapped to this slug" },
        "cat":     { "enum": ["language", "framework", "library", "tool", "platform", "method",
                              "domain", "soft", "standard", "other"] },
        "dom":     { "type": "array", "items": { "type": "string" } },
        "max_d":   { "type": "integer", "minimum": 1, "maximum": 5 },
        "first":   { "type": "string", "format": "date-time" },
        "last":    { "type": "string", "format": "date-time" },
        "n":       { "type": "integer", "minimum": 1, "description": "number of cards citing this skill" },
        "rh":      { "type": "array", "items": { "type": "string", "pattern": "^[0-9a-f]{12}$" },
                     "description": "fingerprints of known results: sha256(m|val|unit|dir)[:12]" },
        "parent":  { "type": ["string", "null"], "description": "broader skill slug, e.g. mcp-server-development -> llm-tooling" }
      }
    }
  }
}
```

### Example entry

```json
{
  "v": 1, "vault_id": "2b7c6f0e-8a8d-4f6a-9a51-0f3e5c8b1d22", "epoch": 1, "rev": 42,
  "generated": "2026-11-27T15:00:00Z",
  "skills": {
    "mcp-server-development": {
      "name": "MCP server development",
      "aliases": ["mcp server", "model context protocol server", "fastmcp"],
      "cat": "method", "dom": ["applied-ai"], "max_d": 3,
      "first": "2026-09-02T10:11:00Z", "last": "2026-11-27T14:02:11Z", "n": 4,
      "rh": ["a91c03be77f2"], "parent": "llm-tooling"
    }
  }
}
```

**Local counter file** (`~/.cvprism/counters.json`, device-only, not schema-versioned in the vault):
`{"python": {"n": 312, "last": "2026-11-27T14:02:11Z"}, ...}`. See Open question 1 in [ARCHITECTURE.md](ARCHITECTURE.md#-open-questions) on syncing usage rollups.

---

## 💻 Device config

### JSON Schema (YAML validated as JSON)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://cvprism.dev/schemas/device.v1.json",
  "title": "cvprism device config v1",
  "type": "object",
  "required": ["v", "device_id", "name", "role", "vault_id", "adapters"],
  "properties": {
    "v":         { "const": 1 },
    "device_id": { "type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{4}$" },
    "name":      { "type": "string", "maxLength": 40 },
    "role":      { "enum": ["hub", "spoke"] },
    "vault_id":  { "type": "string", "format": "uuid" },
    "vault_path":{ "type": "string", "description": "hub only: absolute path to the vault directory" },
    "capture": {
      "type": "object",
      "properties": {
        "claude_session": { "type": "object", "properties": { "enabled": { "type": "boolean" } } },
        "git": { "type": "object", "properties": {
          "enabled": { "type": "boolean" },
          "exclude_repos": { "type": "array", "items": { "type": "string" }, "description": "globs on repo path" } } },
        "watcher": { "type": "object", "properties": {
          "enabled": { "type": "boolean" },
          "paths":  { "type": "array", "items": { "type": "string" } },
          "ignore": { "type": "array", "items": { "type": "string" } },
          "debounce_s": { "type": "integer", "minimum": 5, "default": 60 } } },
        "manual": { "type": "object", "properties": { "enabled": { "type": "boolean" } } }
      }
    },
    "extraction": {
      "type": "object",
      "properties": {
        "model": { "type": ["string", "null"], "description": "passed to claude -p --model; null = account default" },
        "max_input_tokens": { "type": "integer", "default": 6000 },
        "timeout_s": { "type": "integer", "default": 120 }
      }
    },
    "privacy": {
      "type": "object",
      "properties": {
        "review_mode":   { "type": "boolean", "default": false },
        "exclude_paths": { "type": "array", "items": { "type": "string" } },
        "redact_file":   { "type": "string", "default": "~/.cvprism/redact.yaml" }
      }
    },
    "adapters": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object",
        "required": ["type", "enabled"],
        "properties": {
          "type":    { "enum": ["git", "gdrive", "usb", "syncthing", "local"] },
          "enabled": { "type": "boolean" },
          "name":    { "type": "string" },
          "remote":  { "type": "string", "description": "git: remote URL" },
          "branch":  { "type": "string", "default": "main" },
          "path":    { "type": "string", "description": "gdrive/local/syncthing: folder path" },
          "volume_marker": { "type": "string", "default": "cvprism-dropbox", "description": "usb: folder name searched on mounted volumes" },
          "interval_s": { "type": "integer", "minimum": 30, "default": 900 }
        }
      }
    }
  }
}
```

### Example `~/.cvprism/device.yaml`

```yaml
v: 1
device_id: lab-ws-3c1d
name: lab-ws
role: spoke
vault_id: 2b7c6f0e-8a8d-4f6a-9a51-0f3e5c8b1d22
capture:
  claude_session: {enabled: true}
  git: {enabled: true, exclude_repos: ["**/client-*/**"]}
  watcher:
    enabled: true
    paths: ["D:/projects", "~/research"]
    ignore: ["**/node_modules/**", "**/.venv/**", "**/data/**"]
  manual: {enabled: true}
extraction: {model: claude-haiku-5-5, max_input_tokens: 6000}
privacy: {review_mode: false, exclude_paths: ["~/Documents/clients"]}
adapters:
  - {type: git, enabled: true, remote: "git@github.com:me/cvprism-vault.git"}
  - {type: usb, enabled: true, volume_marker: cvprism-dropbox}
```

---

## 👤 Profile

User-owned facts that cvprism never infers: identity, education, positions, publications and certifications. Cards attach to positions through `projects[].ctx`.

### JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://cvprism.dev/schemas/profile.v1.json",
  "title": "cvprism profile v1",
  "type": "object",
  "required": ["v", "person"],
  "properties": {
    "v": { "const": 1 },
    "person": {
      "type": "object", "required": ["name"],
      "properties": {
        "name": { "type": "string" }, "email": { "type": "string" }, "phone": { "type": "string" },
        "location": { "type": "string" },
        "links": { "type": "array", "items": { "type": "object", "required": ["label", "url"],
          "properties": { "label": { "type": "string" }, "url": { "type": "string", "format": "uri" } } } }
      }
    },
    "positions": { "type": "array", "items": { "type": "object",
      "required": ["id", "title", "org", "start"],
      "properties": {
        "id": { "type": "string" }, "title": { "type": "string" }, "org": { "type": "string" },
        "location": { "type": "string" },
        "start": { "type": "string", "pattern": "^\\d{4}(-\\d{2})?$" },
        "end":   { "type": ["string", "null"], "pattern": "^\\d{4}(-\\d{2})?$" },
        "dom":   { "type": "array", "items": { "type": "string" } } } } },
    "projects": { "type": "array", "items": { "type": "object",
      "required": ["ctx", "display"],
      "properties": {
        "ctx": { "type": "string", "description": "slug used in cards" },
        "display": { "type": "string", "description": "public-safe name shown on CVs" },
        "position": { "type": "string", "description": "positions[].id" },
        "confidential": { "type": "boolean", "default": false } } } },
    "education": { "type": "array", "items": { "type": "object",
      "required": ["degree", "institution", "end"],
      "properties": { "degree": { "type": "string" }, "field": { "type": "string" },
        "institution": { "type": "string" }, "start": { "type": "string" }, "end": { "type": "string" },
        "thesis": { "type": "string" }, "grade": { "type": "string" } } } },
    "publications": { "type": "object", "properties": {
      "bibtex": { "type": "string", "description": "path relative to vault, e.g. pubs.bib" },
      "orcid":  { "type": "string", "pattern": "^\\d{4}-\\d{4}-\\d{4}-\\d{3}[\\dX]$" },
      "highlight_name": { "type": "string", "description": "author name to bold" } } },
    "certifications": { "type": "array", "items": { "type": "object", "required": ["name", "issuer", "date"],
      "properties": { "name": { "type": "string" }, "issuer": { "type": "string" },
        "date": { "type": "string" }, "url": { "type": "string" } } } },
    "awards":    { "type": "array", "items": { "type": "object" } },
    "languages": { "type": "array", "items": { "type": "object" } },
    "facts": { "type": "array", "description": "user-asserted metrics usable by the honesty gate",
      "items": { "type": "object", "required": ["id", "text"],
        "properties": { "id": { "type": "string" }, "text": { "type": "string" } } } }
  }
}
```

### Example `vault/profile.yaml`

```yaml
v: 1
person:
  name: Jane Doe
  email: jane@example.org
  location: Kolkata, India
  links:
    - {label: GitHub, url: "https://github.com/janedoe"}
    - {label: ORCID, url: "https://orcid.org/0000-0002-1825-0097"}
positions:
  - {id: acme-ds, title: Senior Data Scientist, org: Acme Water, start: "2024-03", end: null,
     dom: [applied-ai, hydrodynamics]}
projects:
  - {ctx: flood-copilot, display: "LLM copilot for flood forecasting", position: acme-ds}
  - {ctx: client-x-dam, display: "Dam-break study for a utility client", position: acme-ds, confidential: true}
education:
  - {degree: PhD, field: Civil Engineering, institution: IIT Example, end: "2023", thesis: "Coupled 1D-2D flood modelling"}
publications: {bibtex: pubs.bib, orcid: "0000-0002-1825-0097", highlight_name: "Doe, J."}
certifications:
  - {name: "AWS Certified ML – Specialty", issuer: AWS, date: "2025-06"}
facts:
  - {id: f_team, text: "Mentored 4 junior engineers"}
```

---

## 🎭 Role profile

Copy a file to add a role. `extends` allows inheriting from a starter role.

### JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://cvprism.dev/schemas/role.v1.json",
  "title": "cvprism role profile v1",
  "type": "object",
  "required": ["v", "id", "title", "sections"],
  "properties": {
    "v":       { "const": 1 },
    "id":      { "type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$" },
    "title":   { "type": "string", "description": "headline under the name" },
    "extends": { "type": "string", "description": "id of a base role" },
    "sections": { "type": "array", "minItems": 1, "items": { "enum": [
      "summary", "experience", "projects", "skills", "publications", "education",
      "certifications", "awards", "talks", "fieldwork", "teaching", "languages" ] } },
    "include": { "type": "object", "properties": {
      "dom":       { "type": "array", "items": { "type": "string" } },
      "skills_any":{ "type": "array", "items": { "type": "string" } },
      "min_depth": { "type": "integer", "minimum": 1, "maximum": 5, "default": 2 },
      "since":     { "type": "string", "description": "YYYY or YYYY-MM" } } },
    "exclude": { "type": "object", "properties": {
      "dom":    { "type": "array", "items": { "type": "string" } },
      "skills": { "type": "array", "items": { "type": "string" } },
      "ctx":    { "type": "array", "items": { "type": "string" } } } },
    "weights": { "type": "object", "description": "relative 0-1 weights for scoring",
      "properties": {
        "publications": { "type": "number" }, "delivery": { "type": "number" },
        "research": { "type": "number" }, "results": { "type": "number" },
        "recency": { "type": "number" }, "depth": { "type": "number" } } },
    "vocabulary": { "type": "array", "items": { "type": "string" },
      "description": "market phrases to prefer when true; never used to add claims" },
    "limits": { "type": "object", "properties": {
      "pages": { "type": "number", "minimum": 1 },
      "bullets_per_position": { "type": "integer", "default": 5 },
      "skills_max": { "type": "integer", "default": 24 },
      "cards_to_llm": { "type": "integer", "default": 60 } } },
    "template": { "type": "string", "description": "RenderCV theme or templates/<name>" },
    "outputs":  { "type": "array", "items": { "enum": ["pdf", "docx", "md", "tex"] } },
    "tone":     { "type": "string", "description": "short style hint, e.g. 'impact-first, past tense'" }
  }
}
```

### Example `roles/applied-ai.yaml`

```yaml
v: 1
id: applied-ai
title: Applied AI Scientist
sections: [summary, experience, projects, skills, publications, education]
include: {dom: [applied-ai, ml, llm], min_depth: 2, since: "2022"}
exclude: {dom: [teaching]}
weights: {delivery: 0.9, results: 1.0, publications: 0.4, research: 0.6, recency: 0.7, depth: 0.8}
vocabulary: ["LLM agents", "retrieval-augmented generation", "evaluation harness", "MLOps", "tool use"]
limits: {pages: 2, bullets_per_position: 5, skills_max: 24, cards_to_llm: 60}
template: engineeringresumes
outputs: [pdf, docx, md]
tone: "impact-first, past tense, quantified where evidence exists"
```
