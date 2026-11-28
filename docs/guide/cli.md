# CLI reference

Turn everyday work across many computers into evidence-backed, role-specific CVs.

**Usage**:

```console
$ cvprism [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--version`: Show version and exit.
* `--help`: Show this message and exit.

**Commands**:

* `init`: First-run setup: device name, hub or...
* `log`: Record an achievement manually.
* `status`: Show this device&#x27;s capture and sync state.
* `install`: Register capture hooks, skills and the...
* `uninstall`: Remove hooks, skills and the login agent,...
* `worker`: Process queued capture jobs once (the...
* `agent`: Background capture agent: folder watcher +...
* `doctor`: Check the environment and configuration.
* `show`: Pretty-print the most recent cards from...
* `build`: Build a tailored CV on the hub.
* `import-linkedin`: Bootstrap profile facts and evidence cards...
* `import-cv`: Turn an existing CV into evidence cards...
* `import-orcid`: Fetch your public ORCID works and add new...
* `demo`: Build sample CVs (3 roles + a job posting)...
* `link`: Attach a public proof link to an existing...
* `verify`: Check a CV file against its published...
* `roles`: List starter roles and the roles in your...
* `sync`: Push this device&#x27;s cards to every...
* `suppress`: Hide a card from merge and compile without...
* `purge`: Erase a card everywhere this device can...
* `market`: Market intel: recurring phrases from job...
* `project`: Projects: public (linked), private or local.
* `hub`: Hub-only operations: merge, rebuild, promote.

## `cvprism init`

First-run setup: device name, hub or spoke, vault location, watch paths.

**Usage**:

```console
$ cvprism init [OPTIONS]
```

**Options**:

* `--name <str>`: Device name, e.g. office-01.
* `--role <str>`: hub or spoke.
* `--vault <path>`: Vault folder (hub) or synced vault folder (spoke).
* `-a, --adapter <list[str]>`: Sync transport (repeatable): git:&lt;url&gt;, gdrive:&lt;folder&gt;, usb, syncthing:&lt;folder&gt;, local:&lt;folder&gt;.
* `--watch <list[str]>`: Project folder to watch (repeatable).
* `--no-claude-capture`: Disable Claude Code session capture.
* `-y, --yes`: Non-interactive; requires --name, --role, --vault.
* `--force / --no-force`: Redo setup on an already configured device.  [default: no-force]
* `--web`: Use a setup page in your browser instead of the terminal.
* `--help`: Show this message and exit.

## `cvprism log`

Record an achievement manually.

**Usage**:

```console
$ cvprism log [OPTIONS] {text}
```

**Arguments**:

* `text <str>`: One line describing what you did.  [required]

**Options**:

* `-s, --skill <list[str]>`: Skill name (repeatable).
* `-d, --depth <int range>`: 1 used, 2 applied, 3 built, 4 led/production, 5 authored/taught.  [1&lt;=x&lt;=5]
* `-r, --result <str>`: metric:value:unit[:up|down|abs]
* `--work`: Non-code achievement (paper, talk, field work, award).
* `--project <str>`: Project alias (mapped to a display name in profile.yaml).
* `--raw`: Skip Claude; store your words as-is.
* `--link <list[str]>`: Public proof URL, e.g. a DOI, PyPI page or video (repeatable).
* `--help`: Show this message and exit.

## `cvprism status`

Show this device&#x27;s capture and sync state.

**Usage**:

```console
$ cvprism status [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `cvprism install`

Register capture hooks, skills and the background agent (all reversible with `cvprism uninstall`).

**Usage**:

```console
$ cvprism install [OPTIONS]
```

**Options**:

* `--no-claude`: Skip the Claude Code SessionEnd hook.
* `--no-git`: Skip the global git hook dispatcher.
* `--no-skills`: Skip installing /cv-log and /cv-build skills.
* `--no-service`: Skip the background agent at login.
* `--dry-run`: Show what would change, change nothing.
* `--help`: Show this message and exit.

## `cvprism uninstall`

Remove hooks, skills and the login agent, restoring previous settings. Data is kept.

**Usage**:

```console
$ cvprism uninstall [OPTIONS]
```

**Options**:

* `--no-service`: Leave the login agent registration alone.
* `--help`: Show this message and exit.

## `cvprism worker`

Process queued capture jobs once (the agent does this automatically).

**Usage**:

```console
$ cvprism worker [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `cvprism agent`

Background capture agent: folder watcher + queue worker. Started at login by `cvprism install`.

**Usage**:

```console
$ cvprism agent [OPTIONS]
```

**Options**:

* `--interval <int>`: Seconds between queue drains.  [default: 30]
* `--iterations <int>`: Stop after N iterations (0 = run forever).  [default: 0]
* `--help`: Show this message and exit.

## `cvprism doctor`

Check the environment and configuration.

**Usage**:

```console
$ cvprism doctor [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `cvprism show`

Pretty-print the most recent cards from this device.

**Usage**:

```console
$ cvprism show [OPTIONS]
```

**Options**:

* `--n <int>`: How many recent cards.  [default: 10]
* `--help`: Show this message and exit.

## `cvprism build`

Build a tailored CV on the hub. Every bullet cites evidence; unsupported numbers are rejected.

**Usage**:

```console
$ cvprism build [OPTIONS]
```

**Options**:

* `-r, --role <str>`: Role profile id (vault/roles or a starter).
* `--jd <str>`: Job description file or URL to tailor to.
* `--no-llm`: Use card text directly; no Claude call.
* `-f, --format <str>`: Comma list: pdf,docx,md (default: role outputs).
* `--out <path>`: Output root (default: vault/build/&lt;role&gt;/).
* `--check-links`: Open every proof link; drop dead ones.
* `--publish`: Publish the verify page (profile.yaml `verify:`).
* `--sign`: Sign the manifest with your SSH key (profile `verify.signing_key`).
* `--help`: Show this message and exit.

## `cvprism import-linkedin`

Bootstrap profile facts and evidence cards from a LinkedIn data export.

**Usage**:

```console
$ cvprism import-linkedin [OPTIONS] {src}
```

**Arguments**:

* `src <path>`: LinkedIn data export (.zip or unzipped folder).  [required]

**Options**:

* `--no-llm`: Keyword matching only.
* `--help`: Show this message and exit.

## `cvprism import-cv`

Turn an existing CV into evidence cards (flagged for review).

**Usage**:

```console
$ cvprism import-cv [OPTIONS] {path}
```

**Arguments**:

* `path <path>`: Existing CV: .md, .txt, .docx (or .pdf with pypdf installed).  [required]

**Options**:

* `--no-llm`: Keyword matching on bullet points only.
* `--help`: Show this message and exit.

## `cvprism import-orcid`

Fetch your public ORCID works and add new ones to the vault&#x27;s BibTeX file (hub only).

**Usage**:

```console
$ cvprism import-orcid [OPTIONS] {orcid}
```

**Arguments**:

* `orcid <str>`: Your ORCID iD, e.g. 0000-0002-1825-0097.  [required]

**Options**:

* `--help`: Show this message and exit.

## `cvprism demo`

Build sample CVs (3 roles + a job posting) for a synthetic person. Needs no setup.

**Usage**:

```console
$ cvprism demo [OPTIONS]
```

**Options**:

* `--out <path>`: Folder for the demo vault and CVs.  [default: cvprism-demo]
* `--llm`: Draft bullets with Claude (default: offline, card text).
* `-f, --format <str>`: Comma list: pdf,docx,md.
* `--help`: Show this message and exit.

## `cvprism link`

Attach a public proof link to an existing card (hub only).

**Usage**:

```console
$ cvprism link [OPTIONS] {card_id} {url}
```

**Arguments**:

* `card_id <str>`: Card ID (see `cvprism show` or evidence.md).  [required]
* `url <str>`: Public proof URL (https).  [required]

**Options**:

* `--help`: Show this message and exit.

## `cvprism verify`

Check a CV file against its published fingerprint, and optionally who signed it.

**Usage**:

```console
$ cvprism verify [OPTIONS] {file}
```

**Arguments**:

* `file <path>`: The CV file you received (PDF, DOCX or MD).  [required]

**Options**:

* `--manifest <str>`: manifest.json path or URL from the verify page.  [required]
* `--github <str>`: Also check the signature against this GitHub user&#x27;s published SSH keys.
* `--keys <path>`: Also check the signature against SSH public keys in this file.
* `--help`: Show this message and exit.

## `cvprism roles`

List starter roles and the roles in your vault.

**Usage**:

```console
$ cvprism roles [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `cvprism sync`

Push this device&#x27;s cards to every transport; on the hub, merge and publish the registry.

**Usage**:

```console
$ cvprism sync [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `cvprism suppress`

Hide a card from merge and compile without deleting it (hub only).

**Usage**:

```console
$ cvprism suppress [OPTIONS] {card_id}
```

**Arguments**:

* `card_id <str>`: Card ID to hide from CVs (history kept).  [required]

**Options**:

* `--help`: Show this message and exit.

## `cvprism purge`

Erase a card everywhere this device can reach (the one deliberate exception to append-only).

**Usage**:

```console
$ cvprism purge [OPTIONS] {card_id}
```

**Arguments**:

* `card_id <str>`: Card ID to erase.  [required]

**Options**:

* `--yes`: Confirm the rewrite.
* `--help`: Show this message and exit.

## `cvprism market`

Market intel: recurring phrases from job postings you saved (hub only).

**Usage**:

```console
$ cvprism market [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `add`: Save a job posting under...
* `extract`: Aggregate recurring phrases into...

### `cvprism market add`

Save a job posting under vault/market/raw/&lt;role&gt;/.

**Usage**:

```console
$ cvprism market add [OPTIONS] {role} {src}
```

**Arguments**:

* `role <str>`: Role id, e.g. applied-ai.  [required]
* `src <str>`: Posting file or URL.  [required]

**Options**:

* `--help`: Show this message and exit.

### `cvprism market extract`

Aggregate recurring phrases into vault/market/&lt;role&gt;.json (used as role vocabulary in builds).

**Usage**:

```console
$ cvprism market extract [OPTIONS] {role}
```

**Arguments**:

* `role <str>`: Role id.  [required]

**Options**:

* `--no-llm`: Keyword matching only.
* `--help`: Show this message and exit.

## `cvprism project`

Projects: public (linked), private or local. Private work always keeps its skills.

**Usage**:

```console
$ cvprism project [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `set`: Set a project&#x27;s visibility on the hub...
* `map`: On this computer: tag work captured inside...
* `list`: Show projects, their visibility and folder...

### `cvprism project set`

Set a project&#x27;s visibility on the hub (profile.yaml). Applies to all past and future cards.

**Usage**:

```console
$ cvprism project set [OPTIONS] {ctx}
```

**Arguments**:

* `ctx <str>`: Project alias, e.g. flood-copilot.  [required]

**Options**:

* `--public`: Link proof to this project&#x27;s public repo/page.
* `--private`: Show &#x27;(private repository)&#x27; instead of links.
* `--local`: Local-only work: no link, no label.
* `--url <str>`: Repository or project URL (https).
* `--display <str>`: Public-safe name shown on CVs.
* `--help`: Show this message and exit.

### `cvprism project map`

On this computer: tag work captured inside PATH with the project alias.

**Usage**:

```console
$ cvprism project map [OPTIONS] {ctx} {path}
```

**Arguments**:

* `ctx <str>`: Project alias.  [required]
* `path <path>`: Folder whose work belongs to this project.  [required]

**Options**:

* `--help`: Show this message and exit.

### `cvprism project list`

Show projects, their visibility and folder mappings on this computer.

**Usage**:

```console
$ cvprism project list [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `cvprism hub`

Hub-only operations: merge, rebuild, promote.

**Usage**:

```console
$ cvprism hub [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `merge`: Pull every inbox from every transport and...
* `rebuild`: Recreate cards.jsonl and registry.json...
* `promote`: Make this device the hub (epoch+1) and...

### `cvprism hub merge`

Pull every inbox from every transport and merge into cards.jsonl.

**Usage**:

```console
$ cvprism hub merge [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `cvprism hub rebuild`

Recreate cards.jsonl and registry.json from inboxes alone.

**Usage**:

```console
$ cvprism hub rebuild [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `cvprism hub promote`

Make this device the hub (epoch+1) and rebuild the vault from every transport&#x27;s inboxes.

**Usage**:

```console
$ cvprism hub promote [OPTIONS]
```

**Options**:

* `--vault <path>`: Folder for this device&#x27;s new hub vault.  [required]
* `--help`: Show this message and exit.
