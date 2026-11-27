# vault-template

The empty vault scaffold now lives inside the package at [`cvprism/data/vault_template/`](../cvprism/data/vault_template/), so it ships with `pip install`. `cvprism init` copies it to a new vault location and adds `vault.json` (a fresh `vault_id`), `hub.json` and an empty `registry.json`. A vault is private user data and must never live inside this code repository. The wizard refuses such paths.
