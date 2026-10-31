# Current source-review status — 31 October 2026

This overview supersedes older implementation-status prose, not the detailed
historical observations or remaining acceptance gates. FreeQNAP is an independent
personal project targeting TS-431XeU-2G-US/AL314. The owner approved source publication to the personal
`mastechnica/FreeQNAP` repository and its GitHub Pages showcase. This is an
experimental source release, not a binary installer certification.

## Running application

The native Debian ARMhf NAS runs the local console, privileged fixed-operation
broker and board helpers. The compact dashboard includes storage/crypto, shares,
file desktop, backup/restore, media, USB, networking/private LAN, OpenVPN/WireGuard,
DDNS, downloads, recovery, health/rules and activity. Optional services still
require configuration and their own commissioning. No media library or external
VPN is configured merely to decorate the public screenshots. Notifications and
SMART schedules remain opt-in; no sound/message test was triggered for this page.

## Hardware and storage evidence

- Installed Debian boot and autonomous NAND loading, warm restarts, a physical
  cold start, four SATA devices, RJ45 transfers and enclosure controls are recorded.
- Fixed full-speed cooling is the accepted policy. Adaptive cooling and fault
  response are not accepted.
- The final power-off callback passed an owner-observed idle shutdown/cold start
  without the earlier root reconstruction report. Post-write/data-array and
  abrupt-power recovery remain separate open tests.
- Internal four-disk RAID5 and two bounded unencrypted ext4 data filesystems are
  physically created. Initial synchronization was still in progress during the
  screenshots; the critical incomplete-protection alert is intentionally retained.
- EJ188 MRRS 128-byte startup workaround passed bounded flash-drive and TR-004
  write/readback tests on the normal installed kernel. The enclosure remains
  read-only/quarantined, with no new formatted NAS volume registered. This is not
  a full-surface, long-duration or power-loss certification.
- Physical LUKS/ext4 writable browsing/folder/upload checks and experimental
  encrypted APFS read-only browsing/media checks are recorded. BitLocker full
  browsing, every encryption variant and APFS writes are not accepted.

## Software verification

The recent native ARMhf regression suite passed 221 tests. The matching Mac suite
passed 222 tests with four platform skips; these are separate runs, not an added
combined count. Focused network aggregate and media metadata checks passed eight
tests on both hosts after the last logic change. The subsequent compact layout
was checked on all 15 live application sections with JavaScript syntax and diff
checks. Exact current packaging validation is recorded with the review bundle.

Fixture tests cover useful failure and authorization cases but do not substitute
for real clients, providers, physical RAID failure/rebuild or disaster restoration.

## Required before depending on important data

Complete initial resync; verify independent backups and staged restoration; run
controlled degraded/rebuild/replacement and post-write cold-start tests; validate
intended SMB/NFS/AFP clients, players, VPN/private LAN and enabled notifications;
finish a sustained workload/temperature/space campaign. SFP+ traffic, watchdog,
wake and adaptive cooling remain unaccepted. Full flash restoration is excluded.

A public **source** release can describe this experimental state honestly. A
public **turnkey binary installer** additionally needs a clean pinned build,
complete corresponding source/dependency/license review, signed artifact manifests,
and interruption/recovery/update acceptance. No prebuilt image is in this review.

See [production readiness](PRODUCTION-READINESS.md), [acceptance chronology](ACCEPTANCE.md),
[USB evidence](USB-TR004.md), [kernel review](KERNEL-SECURITY.md), and
[publication package](PUBLICATION-PACKAGE.md).
