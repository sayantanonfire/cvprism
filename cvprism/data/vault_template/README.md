# Your cvprism vault

This folder is **private**: it holds your career evidence. Never put it inside the public cvprism code repository.

| Path | Owner | What |
| --- | --- | --- |
| `vault.json` | cvprism | Vault identity (`vault_id`); adapters refuse mismatching vaults |
| `hub.json` | hub | Which device is the hub, and its epoch |
| `registry.json` | hub | Merged skill registry, published back to spokes |
| `cards.jsonl` | hub | All merged evidence cards |
| `inbox/<device-id>/` | each device | Append-only cards from that device |
| `profile.yaml` | you | Degrees, positions, publications, certifications |
| `roles/*.yaml` | you | Role profiles for `cvprism build --role` |
| `market/` | hub | Market-phrase intel per role (M5) |
