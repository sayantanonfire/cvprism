# Many computers, one hub

Pick one computer as the **hub**. It keeps the vault and builds CVs. Every other computer is a **spoke**: it records your work and sends cards to the hub. Spokes never talk to each other.

## Choose how cards travel

| Transport | Use it when | Set it up with |
| --- | --- | --- |
| Private git repo | Computers on different networks | `--adapter git:git@github.com:you/cvprism-vault.git` |
| Synced folder | You already use Google Drive, OneDrive or Dropbox | `--adapter gdrive:~/Google Drive/cvprism` |
| USB stick | Offline or locked-down machines | `--adapter usb` (create a `cvprism-dropbox` folder on the stick) |
| Syncthing | Computers on the same network, no cloud | `--adapter syncthing:~/Sync/cvprism` |

You can use several at once. A card that arrives twice by different routes is stored once.

## Set up

```bash
# on the hub
cvprism init --name home-pc --role hub --vault ~/cvprism-vault --adapter git:git@github.com:you/cvprism-vault.git --yes
cvprism sync

# on each spoke
cvprism init --name office-01 --role spoke --adapter git:git@github.com:you/cvprism-vault.git --yes
cvprism sync
```

The background agent (`cvprism install`) syncs every 15 minutes and immediately when a USB drop-box appears. Offline? Cards wait in the local outbox and go out when any transport is reachable. `cvprism status` shows the backlog.

## Common tasks

- **Replace the hub:** run `cvprism hub promote --vault ~/cvprism-vault` on the new computer. It rebuilds everything from the transports. The old hub steps down by itself the next time it syncs.
- **Hide a card from CVs:** `cvprism suppress <card-id>` on the hub. History is kept.
- **Erase a card everywhere:** `cvprism purge <card-id>`. Git history keeps old commits; cvprism prints the `git filter-repo` command if you need those gone too.

How this stays conflict-free: [Sync protocol](../SYNC.md).
