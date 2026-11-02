# Current status — 2 November 2026

## Personal Photos & Videos

The private timeline, albums, favorites, original downloads, metadata viewer and offline GPS map are locally deployed. The optional iCloud connector is installed, disabled and signed out; no real Apple account or archive is configured. Downloaded originals are retained independently of later cloud deletion. Native synthetic and permission/streaming regressions passed; real Apple sign-in and first-library acceptance still require owner setup. See [Personal Photos](PERSONAL-PHOTOS.md).

## Current physical expansion checkpoint — 2 November 2026

The approved physical operation has progressed beyond the historical preparation
and imaging-gate entries below. Thirteen encrypted recovery images were verified
before layout writes. The initial mixed-member image mismatch was reconciled to
54 unallocated filesystem blocks; a separate member-bound image passed exact
independent full rereads and decryption. Original evidence was retained.

Both OS member partitions are now 128 GiB. Root MD/filesystem UUIDs and all 12,132
critical manifest entries were preserved; the two-member root mirror is non-degraded.
Its scheduled consistency check is currently queued behind data recovery. One redundant writable-state request returned busy on an already writable
array; the error was retained and a separately checked continuation performed only
the required growth. No force-clean operation was used.

The new four-member internal RAID5 has been created under the approved plan and
initial recovery is running. The two approximately 14.794 TB unencrypted ext4 data
filesystems were created with the 64bit feature disabled. Registration, normal boot
and exact-identity post-boot proof checks passed. The OS filesystem reports about
126 GiB, with 116 GiB free at the first check. Strict trusted HTTPS returned 200;
saved full cooling and the ten-second hardware watchdog are active. USB devices
and installed flash were untouched by that OS operation. See [the physical report](OS-EXPANSION-VALIDATION-2026-11-02.md).
Early recovery ETA is unstable while filesystem creation competes for I/O; do not
present it as a guaranteed completion time. Synchronization completion and physical
cold-start/full-replacement recovery remain separate acceptance gates.


FreeQNAP is a locally managed Debian ARMhf NAS for the TS-431XeU/AL314. The
personal `mastechnica/FreeQNAP` source/showcase release is experimental. Public
source availability does not certify every hardware feature or a turnkey binary
installer. Raw identities, credentials, firmware and device evidence remain private.

## Current completion supervision

The queued scheduled OS consistency check exposed an overly strict idle-only
monitor assertion. The corrected read-only verifier passed eight policy tests
and its native preflight/service run. Original fault evidence remains private.
It records queued/running checks and still requires both arrays idle and
non-degraded before final direct-read proof acceptance. It never changes MD
recovery or maintenance settings.

## Historical RAM-only maintenance checkpoint

The owner-approved OS expansion is in its offline imaging stage. The NAS is
running a separate RAM maintenance image; the existing OS mirror is assembled
read-only, and the data array is not assembled. Installed NAS services and the
dashboard are intentionally offline. No partition changes, data-array erasure
or OS growth have occurred.

The first encrypted full-OS image passes decryption/integrity and exact-size
checks, but its initial independent native checksum comparison failed. The
write gate remains closed while bounded read-only chunk comparisons investigate
the discrepancy. The image, its private key material and failure receipts are
preserved. This is not a verified recovery image yet, and the failure must not
be bypassed by restarting the destructive plan.

See [the OS expansion plan](OS-EXPANSION-128G.md). The normal-system observations
below are historical checkpoints, not a claim that services run in maintenance.

## Last normal-system baseline

- Autonomous NAND boot, ordinary warm/cold starts, four SATA bays, both RJ45
  interfaces, enclosure indicators, buttons and orderly chassis power-off have
  bounded physical evidence. Later boot-discovery ordering was fixed without
  relaxing volume identity checks.
- The synchronized four-disk RAID5 provides two mounted **unencrypted** ext4 data
  volumes, about 14.97 TB each after filesystem overhead. The separate two-member
  OS mirror is healthy. Each ext4 filesystem stays below the ARM32 16 TiB limit.
- The approved real data-member logical failure/removal and same-member re-add
  passed. Independent direct reads verified both original proof files and the
  degraded-write proof again after the cooling workloads. No member mutation was
  repeated. At that checkpoint both arrays were non-degraded/idle and both data
  volumes were mounted.
- The final normal-system checkpoint after bounded archival cleanup had no failed
  system services or active capacity alert; thresholds were not lowered.

See [the data recovery record](VALIDATION-2026-11-01.md),
[shutdown follow-up](SHUTDOWN-FOLLOWUP.md) and
[production-readiness boundaries](PRODUCTION-READINESS.md).

## Cooling and watchdog checkpoint

Four covered-chassis ten-minute runs passed:

| Run | Peak CPU | Peak disk | Result |
| --- | ---: | ---: | --- |
| Lighter full-speed load | 57°C | 45°C | Passed |
| Reviewed heavy full-speed load | 67°C | 37°C | Passed |
| High-airflow adaptive idle/read load | 53°C | 35°C | Passed; approximately 580 seconds of observed high-speed sample intervals |
| Adaptive heavy load | 66°C | 34°C | Passed; high airflow changed to full at a sampled CPU temperature of 60°C |

All three fan counters responded and the owner confirmed normal visible rotation.
The earlier 65°C commissioning stops and interrupted guard-restart run remain
recorded. A reviewed 70°C load stop is below the unchanged 80°C kernel bench trip;
the retained stock board configuration's 105°C trip is not a silicon-rating or
physical thermal-protection claim. No thermal trip was exercised.

The permanent local controller, independent guard, full/automatic controls,
read-only status and bounded history are implemented. **The bounded high/full automatic profile is now accepted and enabled** after the final attended stale-input and stopped-controller checks. Stale readings restored full mode in 0.950 seconds; stopped-controller recovery took 3.747 seconds and retained its fault latch after restart. The owner confirmed all three fans stayed normal through both. Temporary trial permission expires on owner death,
cancellation or deadline. Only the tested high-airflow levels 6/7 are implemented;
no fan-stop, low-speed or arbitrary PWM setting is adopted.

Three ten-second SP805 expiry resets and explicit disarm observations passed in
diskless RAM. The **installed watchdog is active under systemd PID 1 at ten seconds**. Advancing heartbeats and one owner handle were observed across multiple timeout periods, including a short CPU load. Maintenance disarm stayed inactive without a late reset for 24 seconds, then re-enable passed. An ordinary restart of the installed kernel restored active watchdog supervision and permanent Auto without intervention; both arrays and mounts returned healthy and all direct proof hashes matched. The owner confirmed all fans and four bay indicators normal. Reboot/kexec watchdog timers remain disabled; no expiry was induced on mounted storage.

See [cooling controls](COOLING.md), [physical cooling record](COOLING-VALIDATION-2026-11-01.md),
[watchdog record](WATCHDOG-VALIDATION-2026-11-01.md) and
[remaining cooling/watchdog plan](WATCHDOG-COOLING-PLAN.md).

## Kernel maintenance

The installed kernel is **6.12.114**. The 1 November authoritative release check
reported maintained 6.12 LTS **6.12.115** available. A security-only FreeQNAP6 candidate preserving the exact accepted complete-mirror bootstrap, nine matching ARM modules and the independently pinned original installed-image rollback bundle passed artifact checks. The transfer helper can serve both exact images
without granting flash authority. **The newer kernel passed an initial RAM boot, healthy-array/mount checks and all three direct-read proof hashes; it remains uninstalled.** The independently pinned original image also passed RAM rollback, healthy-array/mount checks and all three direct-read proofs. Automatic cooling and watchdog supervision were restored afterward. A final normal boot from unchanged NAND restored both safety policies and healthy arrays/mounts without intervention. Broader driver regression and permanent installation remain pending. Board/shutdown source hashes and carried-forward Ethernet ordering
fixes were reviewed; those checks do not replace hardware regression or a complete
CVE review of external drivers. See [kernel maintenance](KERNEL-SECURITY.md) and
[restricted recovery candidate](BOOT-RECOVERY-CANDIDATE.md).

## USB and encrypted media

The exact-board EJ188 MRRS-128 workaround passed bounded normal-kernel flash-drive
and TR-004 write/readback tests, including a 1 GiB enclosure regression and offsets
beyond 16 TiB. The owner-approved TR-004 layout is now two approximately 15 TB
unencrypted ext4 volumes, mounted read/write. Three mounted cycles per volume
passed 3 GiB of writes and 6 GiB of direct verification, cache flushes, remounts
and both offline filesystem checks. Safe eject and owner-assisted physical USB
reconnection and a clean enclosure-only power cycle passed. Software reauthorization exceeded its readiness deadline
before returning; that limitation and remaining NAS-cold-boot/power-loss/controller-health
limits are retained in [the dated enclosure report](TR004-VALIDATION-2026-11-02.md).
Original interrupted operations were preserved, not blindly replayed.

The physical disposable USB passed LUKS2/ext4 AES-256/AES-128 password/key-file
checks, eight writable cycles, direct hashes and read-only/busy refusal. Temporary
volumes/secrets were removed. Experimental encrypted APFS read-only browsing/media
was observed; APFS writes, universal Mac encryption compatibility and complete
BitLocker browsing are not accepted. See [USB/TR-004](USB-TR004.md),
[USB validation](USB-VALIDATION-2026-11-01.md) and [encryption guidance](USB-ENCRYPTION.md).

## Application capabilities and commissioning

The compact local console covers storage/encryption, SMB/NFS/AFP controls, file
desktop, backups/restores, media/scanner/metadata, approved DLNA clients, USB,
network/private LAN, OpenVPN/WireGuard, DDNS, downloads/torrents, recovery,
health/rules and activity. Function-scoped expiring/revocable agent credentials and
optional approved-player UPnP controls are implemented. Existing agent grants do
not grow automatically when a function is added.

Optional services require their own configuration and intended-client acceptance.
Real NFS/AFP file operations, media renderer/codec interoperability, VPN/provider
and physical gateway clients, live DDNS, real torrent exchange and enabled external
notification receipt remain open. Fixture/protocol tests are not those results.
Email, push and buzzer preferences are unchanged; no test sound/message was sent.
Local private-CA HTTPS, signed package-update reachability and valid time sync have
prior evidence; phone PWA installation/push receipt remain owner tests.

Bounded file backup/staged restore and encrypted local configuration capture/download
passed. Fresh-install/system restoration and operational independent data backup
remain separate; the owner deferred an external destination. RAID/recycle bins and
same-pool copies are not independent disaster backups.

## Remaining release and hardware boundaries

Physical hot-unplug, distinct replacement-disk rebuild, degraded OS boot,
post-write/degraded cold-start and abrupt-power recovery, long mixed-workload soak,
10GbE/SFP+, broader USB SuperSpeed/fault testing and wake behavior remain unaccepted.
Host/MCU electrical failure, fan stall and actual overtemperature-trip behavior are
not inferred from the bounded cooling results. Full-chip/SPI restoration is
**excluded by owner decision**.

A turnkey binary release still needs a clean pinned build, complete corresponding
source/dependency/license review, signed immutable artifacts and independently
repeated installation/interruption/update recovery. Keep the accepted installed
image and private UART/TFTP recovery evidence while progressing through those gates.

### Hardening follow-up

Unprivileged eBPF is now disabled persistently on the installed baseline; a real
unprivileged creation attempt was denied. A separate 6.12.115 FreeQNAP7 hardening
candidate compiled with strict memory protections, strong stack/user-copy/bounds
checks and a boot W+X verifier; all nine module versions passed artifact review.
It passed a physical RAM boot, the positive boot W+X check and two bidirectional restart cycles on each RJ45. A ten-minute full-fan CPU/four-disk read run passed at peak CPU 64°C/disk 33°C, followed by all three direct proof hashes. Cold-start/final rollback and permanent installation remain pending. The firmware IBE warning remains open,
independently of potentially optimistic CPU vulnerability sysfs reporting.

See [the attended kernel validation record](KERNEL-VALIDATION-2026-11-01.md) for the current acceptance matrix.

### Remote maintenance checkpoint

With the owner away, further experimental RAM boots and cold-start checks are
deferred. UART capture is passive so an unexpected restart can use the retained
installed boot path. Full cooling and the PID-1 watchdog remain active.

Local HTTPS was restored on the actually connected RJ45 using a new leaf under
the unchanged private CA, the same LAN restrictions and retained private rollback
files. Strict response checks passed on both NAS and Mac; the real HTTPS alert
resolved without suppression. Only the existing OS-space warning remains.

The hardening-policy recovery capture is deployed. A fresh password-encrypted
configuration export passed independent Mac download, decryption and every member
hash check, including the managed BPF policy. Accepted older backups remain.
The TR-004 passed 512 MiB of repeated direct reads including beyond 16 TiB and near
its end; it remains read-only pending fresh initialization approval. This does
not accept mounted write/flush/reconnect behavior or controller RAID health.

## Additional unattended service checks

The hardened RAM kernel passed both isolated VPN/firewall/DLNA campaigns (25
userspace and 26 native-WireGuard checks). The approved two-volume bounded file
campaign also passed uploads, archives, authenticated media/downloads and encrypted
restic staged restore with metadata preservation and wrong-password denial. These
are local same-array recovery checks; independent disaster recovery and physical
media-player compatibility remain separate acceptance work. No reboot, flash write
or TR-004 formatting was performed.

The isolated native download campaign also passed partial HTTP resume after engine
restart, durable paused restoration, final checksum and unauthenticated RPC denial.
Torrent-peer exchange, reboot interruption and disk-full acceptance remain open.
The production-readiness plan has been reconciled with the dated records rather
than retaining completed synchronization/cooling/watchdog work as pending.

## Unattended failure-handling checkpoint

Real RAM-confined Restic tests passed full/interrupted/unavailable destination
failure with last-good restore, and fixture-only retention. A 2 MiB local two-peer
torrent transfer passed its checksum. A full-destination test exposed damaged
resume metadata; the deployed manager now preserves and flags that job instead
of blindly retrying, while later work continues. Automatic marker repair remains
unaccepted. Backup acceptance now also rechecks source directory device/inode
identity. Installer status reports recorded flash writes and incomplete mutations.

See [the dated report](UNATTENDED-VALIDATION-2026-11-01.md) for exact test counts,
negative results and limits, and [OS-space review](ROOT-SPACE-MAINTENANCE.md) for the
non-destructive cleanup plan. No NAS reboot, TR-004 formatting or cleanup occurred.

## OS-space cleanup checkpoint

After owner authorization and independent private archival verification, historical
source-review staging was removed with fresh identity/content and live-reference
checks. This reclaimed 2.35 GB and left 3.33 GB available on the OS filesystem.
The next normal inventory/health sample resolved the capacity warning naturally;
no active alerts or failed services remained. Both arrays/data mounts, HTTPS, full
cooling and watchdog supervision remained healthy. Releases, modules, flash backups
and encrypted recovery archives were retained. No reboot or service restart occurred.
See [the maintenance record](ROOT-SPACE-MAINTENANCE.md).

## Owner-requested OS expansion preparation

A disk-specific proposal now covers a 128 GiB OS mirror and destructive recreation
of the internal RAID5 as two approximately 14.794 TB unencrypted data filesystems
before overhead. Fresh encrypted configuration backup verification and an owned-loop
offline-resize rehearsal passed. The owner confirmed the exact plan. The physical layout remains unchanged; the
privileged transfer-helper restart, verified RAM maintenance and a consistent
offline OS image remain pre-write requirements. See [the expansion plan](OS-EXPANSION-128G.md).
