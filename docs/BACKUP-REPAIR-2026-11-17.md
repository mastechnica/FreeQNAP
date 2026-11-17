# Configuration backup repair — 17 November 2026

The two retained failed local configuration captures were reviewed against their
private stages and the earlier remote-UART engineering record. The first stopped
at the console SQLite snapshot inside the broker’s read-only filesystem namespace.
The second passed that snapshot but exceeded the former database size limit. The
larger-database fix had previously been used only by an isolated capture process;
it was not installed in the live broker.

## Repair

Installed the existing bounded recovery changes in the current application:
64 MiB ordinary files, 128 MiB SQLite databases, 256 MiB aggregate, streamed hashes
and archive verification, and a database-copy deadline. Existing source and service
settings were retained privately for rollback.

I explicitly approved `ReadWritePaths=/var/lib/freeqnap`. A dedicated
`recovery-sqlite.conf` broker drop-in grants that directory access so SQLite can
create its working files during consistent snapshots. Other service restrictions
remain. The source service definition now carries the same directory allowance.

A live-service verification attempt discovered that the network guardian changes
the ctime of `network/lock` while capture is reading it. Configuration capture now
excludes only that runtime lock and `vpn/operations.lock`, records those exclusions
in its manifest, and continues to include network/VPN configuration. That refused
verification attempt was retained alongside the original two failures.

Added a maintenance-only `LocalRecovery.reconcile_failed` operation. It requires
a distinct newer successful local capture and verifies its accepted archive
identity and full checksum before marking a failed capture `reconciled`. Original
error text, prior result and private stages remain; the result links the verified
replacement. The health monitor excludes only explicitly reconciled local captures
from failed-job warnings. A later success alone still does not dismiss a failure.

## Validation and result

- 35 recovery/encryption/health regression tests passed in the actual source tree;
  whitespace verification passed. Tests include replacement corruption refusal,
  failure-history preservation, unrelated backup warnings, and lock exclusions.
- No queued/running durable jobs were present before either broker restart.
- A fresh backup through the running broker accepted 338 files, producing a
  50,836,377-byte encrypted archive. Full encrypted-file SHA-256, decryption and
  all manifest member checksums passed. Console and personal databases and Samba
  credentials were included. An incorrect password was rejected.
- A separate Mac copy matched the encrypted archive’s SHA-256 and byte count.
  Archive, password and evidence are in the ignored private maintenance directory,
  with private file/directory permissions; none are public source artifacts.
- The two original failures and the refused verification attempt were explicitly
  reconciled to the accepted replacement. No failed attempt was called successful,
  and no previous accepted archive or failed stage was removed.
- The normal broker health worker resolved the alerts: zero active alerts, fresh
  inventory/monitor, no failed scopes. Broker, console, collection timer and cooling
  were active. The MCU transaction confirmed the green status-light setting.

This is an encrypted configuration recovery backup, not a backup of media originals
or a demonstrated full disaster restore. Private rollback and verification evidence
remain on the NAS and under `.private/backup-repair-20261117/` on the Mac. No whole
state database was restored, and no pending job was replayed.
