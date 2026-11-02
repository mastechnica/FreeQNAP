# Unattended reliability checks — 1 November 2026

These checks required no physical intervention, NAS reboot, flash write, internal
RAID mutation or TR-004 initialization. Raw results, identities and diagnostics
remain in the ignored private validation workspace. No public push was performed.

## Backup failure handling

A new native Linux fixture enters private mount and network namespaces before
mounting bounded RAM filesystems. It uses a newly generated source, random private
password and disposable encrypted Restic repository. No commissioned data pool,
real repository or production backup configuration is opened.

Passed:

- A real full destination caused backup failure without publishing another snapshot.
  After removing only the fixture's capacity filler, full-data checking and an
  exact-hash staged restore of the prior successful snapshot passed.
- A running rate-limited backup process was terminated. After it exited and its
  fixture-only stale lock was reconciled, the old snapshot passed full checking
  and restoration. The interrupted process did not publish a new snapshot.
- A temporarily unavailable fixture repository failed access. Returning that exact
  repository restored full-data checking and the prior snapshot's readability.
- Explicit fixture-only tagged retention kept the newest snapshot, which passed
  checking and restoration. No real repository was pruned.
- Temporary payloads, credentials and repository were confined to RAM and removed.

These are real Restic-engine failure tests, not a claim that every filesystem,
SFTP outage or power-loss scenario has been accepted. Independent off-NAS disaster
recovery remains unaccepted and its destination deferred by the owner.

### Source-root identity safeguard

The application now binds backup sources to their filesystem, device and directory
inode and rechecks them both before and after repository verification. Replacement
of a source directory, including a symlink swap, leaves a new snapshot unaccepted.
Tests cover replacement during backup and during the repository check and prove
that the previously accepted snapshot registry remains unchanged. This does not
make live application files transactionally consistent or create a filesystem
snapshot; applications needing quiescence still require their own backup procedure.

## Download reliability

The earlier isolated native HTTP test passed engine interruption/restart, saved
paused state, nonzero Range resume and final SHA-256 verification. The additional
local BitTorrent test passed a generated **2 MiB** transfer between two unprivileged
engines through a loopback tracker with matching SHA-256. Public DHT, peer exchange,
local peer discovery and public trackers were disabled inside an isolated network
namespace. No actual download queue, public peer or owner file was involved.

A deliberately tiny RAM destination reproduced ENOSPC after verified partial
pieces. The engine's resume-control file could become unreadable. Straight resume
then failed; attempted fixture reconciliation also timed out. Those failed runs
are retained as negative evidence, not counted as successful recovery. The first
fixture also lacked the application's existing resume options; these were corrected
before the later checks. The separate normal-peer fixture uses a bounded payload
and disables the seeder's ratio stop; it does not erase the full-destination result.

The application now detects the engine's damaged segment-file error and retains
that job with `recovery_required: true` and a fixed human-readable explanation.
It suppresses blind retry for that item, rejects Resume, preserves partial files
and continues later jobs. Removing the record retains its files. A new job uses a
fresh directory. Automatic damaged-control reconstruction is **not implemented or
accepted**. Raw engine paths are not copied into public job status.

## Access controls, installer and deployment

- Final development-host application suite: **305 tests, four skipped**, no failures.
- Installer suite: **50 tests**, all passed.
- Dashboard checks: **14 tests**, all passed.
- Native ARMhf backup/download regression fixtures: **27 tests**, all passed against
  the staged source before activation.
- Installer status now reads both disk and flash journals. It reports recorded
  flash writes instead of always saying false, flags incomplete mutations for
  reconciliation and rejects malformed write records. It does not probe hardware,
  retry a write or authorize the next installation stage.
- The backup/download safeguards were deployed as a new immutable source generation,
  reusing unchanged files without modifying retained generations. Active work was
  checked before the ordered application restart. Certificate-verified HTTPS
  readiness passed; the prior application generation remains available.

These tests include agent grant/catalog parity, revocation/expiry, denied functions,
reviewed-plan ownership, token privacy, session and management HTTPS boundaries.
No production agent credential was issued or broadened by this campaign.

## Read-only health and capacity review

Both internal arrays were non-degraded and synchronization idle. All four internal
SMART overall checks passed at 30–31°C. There were no failed services; the health
monitor was fresh. Full cooling and watchdog supervision remain in place. The
existing OS-space warning remained the only active alert; no acknowledgment,
notification preference or threshold was changed.

Approximately 983 MB remained available on the OS filesystem at the initial space
review. A separate [space-maintenance plan](ROOT-SPACE-MAINTENANCE.md) identifies
historical staging and release archives for review. Nothing was deleted.

## Still separate

Attended kernel rollback/cold-start and permanent installation, fresh approved
TR-004 formatting/mounted write tests, physical replacement/degraded boot, intended
external clients/providers, complete full-disk torrent recovery and long mixed
soak remain open. These bounded tests are not production sign-off. Full-chip/SPI
restoration remains excluded by the owner.
