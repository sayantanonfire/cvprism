# Security policy

cvprism handles career data, so privacy and security reports get priority.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead: **Security → Report a vulnerability** on this repository. Include the version (`cvprism --version`), your OS, and steps to reproduce.

You can expect an acknowledgement within 5 days and a fix or mitigation plan within 30 days for confirmed issues.

## What counts

- Anything that could make cvprism capture or sync code, file contents, data, secrets or names it should not (see [docs/SECURITY_PRIVACY.md](docs/SECURITY_PRIVACY.md)).
- Cards leaking across vaults or devices, or bypassing the vault-id check.
- Ways for content in a transcript, job posting or card to make cvprism run commands or change files.
- A CV bullet passing the honesty gate with a number that is not in the evidence.

## Supported versions

Security fixes go to the latest release.
