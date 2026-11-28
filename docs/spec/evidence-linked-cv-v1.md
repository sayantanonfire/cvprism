# Evidence-linked CV, version 1 (open specification)

- **Status:** Draft standard, implemented by cvprism 1.2
- **Licence:** Apache-2.0. Anyone may implement it, in any tool.
- **Schema:** [`manifest.schema.json`](https://github.com/sayantanonfire/cvprism/blob/main/cvprism/schemas/manifest.schema.json) (JSON Schema 2020-12)

## Purpose

Hiring has a trust problem: AI made every CV look polished, so polish stopped meaning anything. An evidence-linked CV ships with a machine-readable **manifest** that says, for every line, what proof backs it. The CV files carry fingerprints, and the manifest can optionally be signed with the author's existing SSH key. A recruiter, an ATS or a verification service can check all of this without trusting the tool that made the CV.

The format is deliberately small, so that any CV builder can produce it and any ATS can read it.

## 1. The manifest

`manifest.json`, UTF-8, published next to the CV (for example on the author's own website):

| Field | Required | Meaning |
| --- | :---: | --- |
| `v` | ✓ | `1` |
| `name` | ✓ | Person's name as on the CV |
| `headline` |  | Headline/role title on the CV |
| `role` |  | Identifier of the CV variant |
| `built` | ✓ | RFC 3339 time the CV was produced |
| `file` | ✓ | Main CV file name the `sha256` refers to |
| `sha256` | ✓ | SHA-256 (hex) of `file` |
| `files` | ✓ | Map of every produced CV file name → SHA-256 |
| `bullets` | ✓ | One entry per CV line, below |

Each `bullets[]` entry:

| Field | Required | Meaning |
| --- | :---: | --- |
| `text` | ✓ | The line as printed (without its link) |
| `level` | ✓ | Proof level (section 2) |
| `links` |  | Public `https://` URLs proving the line |
| `label` |  | Human label when no link exists, e.g. `private repository` |
| `date` |  | `YYYY-MM-DD` when the underlying evidence was first recorded |
| `cites` |  | Opaque IDs of the author's evidence records |
| `section` |  | Where the line appears (`pos`, `proj`, `work`) |

## 2. Proof levels

A producer MUST compute levels from evidence. It MUST NOT let the author choose them.

| Level | Rule |
| --- | --- |
| `public` | At least one link a third party can open that shows the work itself |
| `confirmed` | Confirmed by an independent party (e.g. a DOI-registered publication, an issued credential) |
| `captured` | Recorded automatically by a tool at the time the work happened |
| `self-reported` | Entered by the author |

Private work is first-class. Lines from closed-source or confidential work MUST be allowed, without links, typically labelled `private repository`. A consumer MUST NOT treat the absence of a link as evidence of falsehood.

## 3. Links on the printed CV

- Links SHOULD appear as visible URL text, not icons, so ATS parsers keep them.
- A link MUST point at the work (a commit, release, paper, video), not at a profile page that merely restates the claim.
- Producers SHOULD check that links open before publishing.

## 4. Fingerprints

`sha256` and `files` let anyone confirm a received file is byte-for-byte the one described. A fingerprint proves **integrity, not truth**, and consumers SHOULD present it that way.

## 5. Signatures (optional)

- `manifest.json.sig` is an OpenSSH signature (`ssh-keygen -Y sign`) over the exact bytes of `manifest.json`, with namespace **`cvprism-cv`**.
- Verification uses the author's public SSH keys, for example those GitHub publishes at `https://github.com/<user>.keys`:

  ```bash
  echo "<user> namespaces=\"cvprism-cv\" <public key>" > allowed_signers
  ssh-keygen -Y verify -f allowed_signers -I <user> -n cvprism-cv -s manifest.json.sig < manifest.json
  ```

- A valid signature proves the manifest was produced by whoever controls that key. It still does not prove the claims; the links do.

## 6. Verifying a CV, step by step

1. Fetch `manifest.json` (and `.sig` if present) from the URL printed on the CV.
2. Compare the received file's SHA-256 with `files`.
3. Optionally verify the signature against the author's published keys.
4. Open the `links` for the lines that matter to the role.

With cvprism: `cvprism verify cv.pdf --manifest https://you.github.io/cv/manifest.json --github you`.

## 7. Versioning

Additive fields keep `v: 1`. Any change in meaning increments `v`, and consumers MUST reject versions they do not understand.
