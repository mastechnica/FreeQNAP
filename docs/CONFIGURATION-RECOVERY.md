# Private configuration recovery

FreeQNAP offers two distinct recovery outputs. Neither is an automatic live-system restore, a shared-file backup, an OS disk image, or a flash image.

## Local password-encrypted download

In **Backup & restore → Local NAS configuration backups**, enter and confirm a new export password of at least twelve characters. The root broker captures the selected NAS state consistently, creates an OpenPGP AES-256 password-encrypted archive with integrity protection, decrypts it again privately, and verifies every manifest hash before accepting it. Download the resulting `.tar.gz.gpg` and retain its displayed SHA-256 and password independently. The password is never saved in a job, arguments, environment, settings or logs.

The archive remains root-private on the NAS. The download endpoint requires the dashboard administrator session and is served through the existing protected transport, with no-store and same-origin resource headers. Downloads support byte ranges and reject replaced archives. No named plaintext archive is retained; private capture staging and unlinked temporary files are bounded and removed after success. A failed capture can retain a root-private diagnostic stage, with a separately reviewed cleanup action. Failed creation does not prune or replace accepted archives. At eight retained encrypted archives or partial outputs, further creation stops for review rather than deleting history. There is no automatic archive-pruning policy.

A copy on the same NAS does not protect against losing that NAS. Download an independent copy when desired. External backup is optional; it is not configured merely by installing this feature.

For manual inspection on a trusted recovery computer with GnuPG:

```sh
gpg --output recovery.tar.gz --decrypt YOUR_ARCHIVE.tar.gz.gpg
tar -tzf recovery.tar.gz
```

GnuPG prompts for the password. Keep decrypted contents private and inspect them before any manual restoration. The manifest records original modes, account IDs, installation identity and file checksums. Never extract over a running system or publish recovered private files through a share.

## Selected recovery coverage

- Consistent NAS broker SQLite state, account/share/pool mappings, backup repositories and schedules, media/network/VPN/download desired configuration.
- Root-private repository/VPN credentials, LUKS header artifacts and selected network configuration.
- Account ID/group mappings and password databases; Samba TDB credentials use `tdbbackup` for consistent snapshots rather than raw live file copies.
- Selected fstab/MD/network/service/SSH host configuration, matching optional modules, the accepted shutdown helper, and the local application source generation.

**Dashboard login state, active sessions, enrollment tokens and the root SSH authorized-keys file are excluded.** Keep an owner SSH key separately and initialize a fresh dashboard administrator during recovery. This preserves the existing broker filesystem isolation. Other arbitrary `/etc`, `/root`, logs, caches, DHCP leases, media or downloaded payloads are not claimed as covered.

Capture refuses pending network/VPN changes, unexpected symlinks, source changes and excessive file/space limits. Installation identities, array/filesystem UUIDs, account IDs and exports must be reconciled against the recovery target. Saved jobs and enabled policies require review before activation. No handler applies the captured configuration automatically.

## Optional encrypted Restic repository

The NAS recovery panel can write the same selected capture to a configured encrypted Restic repository, tagged `freeqnap-system`. File snapshots retain their separate tag and retention scope. System snapshots may be staged privately for manual review; the file-share promotion operation rejects them because they contain credentials. No repository or recurring policy is enabled by default.

Recurring policies can independently schedule file or system snapshots and full-data repository checks. Repository/source bindings are pinned; changing the destination or source mapping requires a fresh review. Missed intervals coalesce, queue-full admission defers work, simultaneous repository failures remain independent, failed jobs stay retryable, and the last successful result stays visible. There is no automatic pruning; reviewed retention is separate from scheduling.

## Validation and remaining acceptance

Host and native ARMhf tests cover encryption/decryption, wrong-password denial, no password in persistent state, changed-archive refusal, source loss, retained last-good backups, scheduling fairness/restart/clock/capacity and private restore boundaries. A native capture under unchanged broker-style filesystem protections included 155 real configuration/artifact files; encrypted download SHA-256, decrypted manifest and consistent Samba credentials were verified. The disposable validation archive was removed and no live configuration was restored.

This is verified capture/export, **not accepted bare-metal recovery**. Recovery on a fresh installation, interrupted/full-destination behavior with actual owner storage, complete account/ACL/share restore and independently received alerts remain operational acceptance work. Install GnuPG and `tdb-tools` alongside the normal NAS dependencies. The source-only console installer does not install missing system packages automatically.

Cooling preferences under `/etc/freeqnap` and the named FreeQNAP watchdog manager
policy are included when present. Hardware-acceptance receipts and temporary
attended-trial leases are not restored automatically. Keep hardware supervision
disabled until the recovery target and its watchdog/cooling behavior have been
validated; inspect saved enablement settings before activating any recovered unit.
