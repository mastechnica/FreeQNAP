## Private personal photo archive — 2 November 2026

- Added a private photo/video timeline, year/month views, albums, favorites, captions, original downloads and offline GPS map.
- Added an optional pinned iCloud connector with private MFA setup, resumable verified downloads and no cloud-deletion propagation.
- Kept private originals outside general file/media grants; added explicit photo agent permissions and authenticated range streaming.
- Isolated metadata/preview decoders with read-only input, reduced privileges, no network and resource limits.
- Deployed locally with rollback generation retained; connector remains disabled and signed out pending owner setup.
- Passed 378 host tests (four skips), 74 targeted native tests and native synthetic JPEG/HEIC/QuickTime checks. Real Apple account acceptance remains pending.

## Installer OS allocation correction — 2 November 2026

- New installer source reserves 128 GiB per OS mirror member and requires at least 130 GiB on each selected OS disk.
- Target validation requires explicit reviewed boot/OS geometry and refuses old/missing 8 GiB plans; no silent reinterpretation of an approved plan.
- All 52 offline installer tests pass, including capacity, legacy-plan refusal and unchanged non-OS disk handling.
- Source-only correction: existing built releases and installed devices are not automatically modified or republished.

## Expanded OS and restored normal operation — 2 November 2026

- Completed the approved 128 GiB mirrored OS expansion with preserved identities, boot bytes and critical-file manifest.
- Created the two approved unencrypted ext4 volumes and verified direct-read proofs before and after ordinary boot.
- Preserved all unrelated SQLite rows/ownership; normal dashboard, trusted HTTPS, full cooling and watchdog returned.
- Initial data RAID5 recovery is running, not complete. Installed NAND kernel remains unchanged; security promotion and remaining physical acceptance are separate.

## Current physical expansion checkpoint — 2 November 2026

The approved physical operation has progressed beyond the historical preparation
and imaging-gate entries below. Thirteen encrypted recovery images were verified
before layout writes. The initial mixed-member image mismatch was reconciled to
54 unallocated filesystem blocks; a separate member-bound image passed exact
independent full rereads and decryption. Original evidence was retained.

Both OS member partitions are now 128 GiB. Root MD/filesystem UUIDs and all 12,132
critical manifest entries were preserved; the two-member root mirror is healthy
and idle. One redundant writable-state request returned busy on an already writable
array; the error was retained and a separately checked continuation performed only
the required growth. No force-clean operation was used.

The new four-member internal RAID5 has been created under the approved plan and
initial recovery is running. The two approximately 14.794 TB unencrypted ext4 data
filesystems are being created with the 64bit feature disabled. Data registration,
normal boot and post-boot proof/service checks are still pending. Full-speed cooling
is retained in diskless maintenance; USB devices and installed flash are untouched.
Early recovery ETA is unstable while filesystem creation competes for I/O; do not
present it as a guaranteed completion time. Synchronization completion and physical
cold-start/full-replacement recovery remain separate acceptance gates.

## Offline imaging integrity gate — 1 November 2026

- Entered the approved, identity-pinned RAM-only OS-expansion environment; the OS mirror is read-only and the data array remains unassembled.
- Preserved a full encrypted OS image that passes independent decryption/integrity and exact byte-count checks, but stopped before writes when its native reread checksum did not match.
- Retained the original image and private receipts; bounded read-only chunk diagnosis is in progress. No partition/data-array mutation or OS growth has occurred.

## Approved OS-expansion maintenance preparation — 1 November 2026

- Recorded owner confirmation of the exact destructive internal-disk plan; physical layout remains unchanged.
- Built and checked a separate RAM-only maintenance image with no automatic root assembly, unchanged board properties and a passing built-CPIO identity audit.
- Prepared strict UART-pinned ephemeral SSH and audited RAM tools; corrected only two cached archive permission modes while preserving all file contents.
- The privileged helper and pinned RAM boot subsequently passed. Offline OS/boot/GPT imaging remains mandatory; the later imaging-integrity gate is described above.

## OS expansion preparation — 1 November 2026

- Prepared a private identity-bound 128 GiB OS expansion/internal RAID5 recreation proposal, excluding all USB storage. No physical array or partition was changed.
- Independently decrypted/verified a fresh 227-file encrypted configuration backup.
- Passed an owned-loop offline root/MD expansion and RAID5 recreation rehearsal, preserving root identity/content and boot bytes/identifiers; retained earlier negative fixture evidence.
- Documented fresh confirmation, pinned RAM maintenance, consistent offline OS imaging and post-layout acceptance requirements.

## Bounded OS-space cleanup — 1 November 2026

- Privately archived historical source-review staging and independently verified all 18,752 entries, including 17,503 regular-file hashes and metadata.
- Removed only that staging directory after fresh source identities/hashes and live-reference checks; reclaimed 2.35 GB, leaving 3.33 GB available.
- Preserved active/rollback releases, module sets, flash backups, validation evidence and unchanged encrypted recovery archives. No reboot, service restart or broad pruning occurred.
- Verified fresh inventory/health cleared the capacity warning naturally; arrays, mounts, HTTPS, cooling and watchdog remained healthy, with no failed services or active alerts.

## Unattended failure-handling validation — 1 November 2026

- Added RAM-confined native Restic full/interrupted/unavailable destination and retention checks; last-good restores passed.
- Passed a local two-peer torrent payload/hash test; reproduced damaged resume metadata on a full destination and retained negative recovery evidence.
- Deployed safe per-job recovery-required handling without deleting partial files, exposing private engine paths or blocking later downloads.
- Bound backup acceptance to source-directory device/inode identity before and after verification; retained last-good acceptance on replacement.
- Fixed read-only installer status to show recorded flash writes and incomplete-operation reconciliation.
- Passed 305 application tests (four skipped), 50 installer tests, 14 dashboard checks and 27 native staged-source checks.
- Recorded current healthy arrays/SMART and prepared an archival OS-space plan without deleting retained history.

## Download interruption and readiness reconciliation — 1 November 2026

- Passed isolated native HTTP resume after download-engine restart with matching SHA-256, durable paused restoration and unauthenticated RPC denial. No production queue was changed.
- Passed five agent-access and 24 management/TLS source tests.
- Reconciled the readiness plan with completed RAID recovery, cooling, watchdog and RAM-kernel evidence while retaining physical-client, replacement-disk and permanent-installation gates.
- Confirmed both arrays idle/non-degraded and watchdog active; the existing OS-space warning remains visible.

## Additional isolated network validation — 1 November 2026

- Added explicit native/userspace WireGuard test selection, retaining namespace isolation and the userspace default.
- Passed 25 userspace and 26 native-kernel VPN/firewall/DLNA checks on the hardened RAM kernel.
- Passed the approved two-volume file/ZIP/media and encrypted staged-restic restore campaign; preserved metadata, denied wrong passwords and removed successful-run fixtures.
- Corrected the bounded file campaign's installed media-fixture lookup and added a pre-write presence check; retained the initial failure evidence.

## Unattended-safe remote maintenance — 1 November 2026

- Restored local HTTPS on the connected port under the unchanged private CA and LAN allowlist, retaining old private certificates/configuration. Strict NAS/Mac probes passed and the real critical alert resolved.
- Deployed managed hardening-policy backup coverage; independently downloaded, decrypted and checked all 227 files of a fresh encrypted export on the Mac. Older accepted backups remain.
- Corrected console/HTTPS startup sequencing and bounded readiness verification after a transient deployment check triggered rollback; the ordered native deployment passed.
- Left UART capture passive, full cooling and watchdog active; further experimental/cold boots await the owner.
- Passed 512 MiB of repeated direct TR-004 reads without releasing read-only quarantine; prepared the separate owner-reviewed two-volume proposal.
- Fixed split external-volume label truncation before formatting; 25 external-storage fixture tests passed. No TR-004 initialization has run.

## Hardened-kernel load regression — 1 November 2026

- Passed 601.509 seconds of supervised full-fan CPU/four-disk direct-read load on FreeQNAP7: 421 samples, peak CPU 64°C and peak disk 33°C; full-speed cleanup verified.
- Verified unchanged boot identity, active watchdog afterward, both healthy arrays and all three post-load direct proof hashes.
- Kept the additional under-load feeding sampler unstarted after its late preflight refusal; no sampled result is claimed for it.
- Staged nine matching modules for the separate unbooted CPU experiment; strict per-core readback acceptance remains required.

## Both-port kernel regression — 1 November 2026

- Passed two restart-and-transfer cycles on each RJ45 under the hardened RAM kernel, with exact identities and independently verified 1 MiB uploads/direct-read downloads.
- Recorded the owner's normal fan/bay indicator observations; started the supervised ten-minute full-fan CPU and read-only four-disk regression.
- Strengthened CPU experiment acceptance to require all four positive per-core mitigation paths without contradictory warnings; 15 checker tests passed.
- Added the managed hardening policy to private recovery captures with a focused allowlist test; all 12 recovery tests passed. Native backup acceptance remains pending.
- Consolidated and independently verified original flash backups privately without restoring or programming flash.

## Hardened kernel physical checkpoint — 1 November 2026

- Passed the hardened RAM boot, strict-memory configuration and native boot W+X check; retained the unresolved firmware warning on all four cores.
- Rechecked all three exact-identity direct-read data proofs and both healthy arrays/data mounts.
- Passed two independently supervised RJ45 restart cycles with 1 MiB bidirectional verified transfers per cycle.
- Corrected the hardening evidence parser's punctuation mismatch, retaining the initial false-negative report; 19 focused checks pass.
- Added the guarded physical network-cycle helper and a dated acceptance matrix; watchdog feeding passed 35 seconds with eight samples and one owner.
- Prepared a separately gated, default-off CPU IBE RAM experiment with unchanged per-core readback/warnings; build/module/assembly checks and six profile-denial tests passed. It remains unbooted.
- Other-port, load/cold-start, final rollback, permanent update and TR-004 acceptance remain pending.

## Kernel hardening preparation — 1 November 2026

- Persistently disabled unprivileged eBPF on the physical NAS and verified an actual denied map-creation request; preserved privileged use and notification preferences.
- Added a separately gated 6.12.115 RAM-only hardening build, strict memory protections, stack/user-copy/bounds defenses and boot W+X checks.
- Added a read-only hardening verifier that keeps firmware IBE warnings separate from sysfs mitigation claims.
- Passed 17 focused policy/evidence checks and 45 installer regressions; hardened physical kernel acceptance and TR-004 completion remain pending.

## Security kernel RAM checkpoint — 1 November 2026

- RAM-booted the security-only 6.12.115 candidate without programming flash or saving bootloader settings.
- Verified matching loaded board drivers, full cooling, both healthy arrays, both mounted data volumes and three direct-read proof hashes.
- Recorded unresolved Spectre-v2 firmware mitigation and disabled strict memory-protection options; broader regression and permanent installation remain pending.
- Passed the independently pinned original-image RAM rollback and repeated all three exact-identity direct-read data checks; restored accepted automatic cooling and watchdog supervision.
- Verified a final unattended boot from unchanged NAND with both safety policies, healthy arrays and both data mounts restored.

# Changes

## Startup persistence and security-only kernel preparation — 1 November 2026

- Passed a normal installed-kernel restart with automatic cooling and the ten-second watchdog restored, healthy arrays/mounts and matching direct proof hashes; owner confirmed fans and four bay indicators.
- Built an isolated 6.12.115/FreeQNAP6 RAM-only image retaining the exact accepted complete-mirror bootstrap, separated from experimental survivor behavior.
- Verified actual embedded helper hashes and all nine ARM module versions; staged matching modules without loading them. Kernel RAM boot, rollback and any permanent flash plan remain separate.

## Bounded adaptive cooling and watchdog enabled — 1 November 2026

- Passed actual stale-temperature and stopped-controller checks (full mode observed in 0.950 / 3.747 seconds), fault-latched restart and owner-observed fan continuity.
- Enabled the exact-install high/full automatic profile after all evidence checks; no unvalidated low-speed settings were admitted.
- Enabled sole-owner PID-1 hardware supervision at ten seconds, verified advancing live/load heartbeats, and passed maintenance disarm/no-late-reset/re-enable. Ordinary reboot persistence is pending.
- Saved and independently verified a fresh private encrypted configuration backup; kept notification preferences and all data/boot layouts unchanged.

## Timed adaptive commissioning checkpoint — 1 November 2026

- Passed ten-minute high-airflow and adaptive heavy-load campaigns; observed automatic full-speed switching at 60°C and normal fan feedback.
- Reverified all original data proof hashes, healthy arrays/mounts and an empty covered-test kernel-warning log; retained the existing OS-capacity warning.
- Added bounded sanitized cooling history, compact live controls, an explicit history API grant and configured-but-inactive watchdog health detection.
- Prepared default-read-only attended stale-input/controller-stop checks. Permanent Auto stays locked and the watchdog remains inactive until final acceptance.
- Consolidated current status to separate accepted results, experimental capabilities and pending commissioning. No publication or kernel flash occurred.

## Covered-chassis cooling campaign — 1 November 2026

- Reestablished bidirectional UART and passed both covered-chassis ten-minute full-speed baselines: lighter load peaked at CPU 57°C/disks 45°C; reviewed heavy load peaked at CPU 67°C/disks 37°C. Adaptive acceptance remains in progress.
- Serialized manual Full speed and trial cleanup with reduction authorization, preventing a stale controller decision from overriding cancellation.
- Added an exact-install, boot/process-bound, expiring attended trial permit; cancelling Full speed or losing the harness lease withdraws reduced-speed permission. Permanent automatic mode stays locked.
- Added a reproducible direct-read-only cooling workload campaign with immutable private plans, sensor/array/identity guards and full-speed cleanup. Longer physical results are recorded separately as they finish.

## Local cooling-controller commissioning — 1 November 2026

- Implemented and deployed a full-speed-default controller, independent boot/PID-bound guard, fault latch, conservative high-airflow policy and bounded local history.
- Added gated dashboard controls, cooling-health checks and explicitly scoped cooling/watchdog status API functions; existing agent grants and notification preferences remain unchanged.
- Passed native control/safety tests and actual stopped-controller recovery at full speed. Preserved the initial full-load thermal stop; longer cooling acceptance remains in progress.
- Prepared a receipt-gated reversible PID-1 watchdog configuration tool without enabling hardware or changing the kernel.
- Preserved both guarded full-speed load stops (27 seconds / 339 seconds); automatic acceptance remains blocked pending airflow and thermal investigation. Saved an independently hashed private rollback bundle matching the original installed-image verification.

## Guarded high-speed cooling trials — 1 November 2026

- Verified a ten-second stock high-speed step on all three fan counters and full-speed RPM recovery.
- Preserved an initial controller-loss guard failure, added bounded shared-lock handling and error evidence, and passed the corrected attended loss test.
- Added an unenabled high-speed-only hysteresis policy with stale-input and tach fault tests; retained full-speed production cooling and explicit thermal/failsafe acceptance gates.

## Watchdog physical expiry acceptance and startup fix — 1 November 2026

- Passed three attended SP805 10-second expiry resets in RAM, plus disarm/late-reset observations; retained inactive production watchdog and fixed full cooling.
- Restored the installed boot path without flash/environment writes and verified exact arrays, both data mounts and three independent direct proof hashes.
- Fixed MD partition discovery ordering with bounded udev settling while preserving UUID/extent checks; passed native tests and a normal-reboot mount regression.
- Retained the explicit root-capacity warning and broader watchdog/cooling acceptance limits.


## Watchdog RAM test preparation — 1 November 2026

- Built and audited a private RAM-only rescue with full-speed cooling and no disk-root selector, persistent mounts or automatic watchdog arming.
- Added a guarded static ARM probe for attended disarm/expiry checks; ordinary-system invocation fails before watchdog open.
- Physical reset acceptance awaits the attended UART/transfer session. Installed watchdog and cooling policies remain unchanged.


## USB encryption presets and physical acceptance — 1 November 2026

- Added explained AES-256/passphrase, AES-128/passphrase and separate-key presets, explicit reviewed cipher parameters and appropriate credential fields.
- Passed physical password/key-file creation, alternate-key enrollment, eight read/write remount cycles, direct hashes, read-only denial and busy-unmount refusal; removed disposable volumes and secrets.
- Fixed pre-format rejection of valid 512-byte-aligned flash capacities and narrowly handled unsupported cache sync on reported write-through devices.
- Added a guarded native USB campaign and documented watchdog/adaptive-cooling remaining work without arming/resetting the watchdog or reducing fans.


## Local agent API and approved-player control — 1 November 2026

- Added one-time-display, hashed agent tokens with expiry, revocation, exact function grants, presets, group selection, request limits and private audit history.
- Added a bearer-only HTTPS API over the fixed NAS operation registry, preserving reviewed confirmations and credential ownership of transient operation references.
- Added a compact dashboard for credentials, permission selection and optional player discovery/approval.
- Added optional UPnP playback, pause/stop/seek and forward/rewind skips with temporary IP-bound single-item streams; no test audio was sent.
- Verified local security/regression tests and native ARMhf tests, plus live trusted-HTTPS health-read, denied escalation and immediate revocation. Physical player playback remains pending.


## Approved data-member recovery — completed, 1 November 2026

- Completed the approved logical failure/removal and same-member re-add without repeating mutations.
- Independently verified three direct-read proof hashes, exact identities, four-member idle RAID5, healthy OS mirror and both mounted data volumes.
- Confirmed zero active health alerts; retained physical hot-unplug, full replacement and degraded cold-start limits. Removed the completed monitor.

## Post-sync validation — 1 November 2026

- Confirmed four-member RAID5 initial synchronization complete and a healthy OS mirror.
- Repeated bounded backup/staged-restore, direct hashes, ACL/xattr and failure-denial checks on the physical data filesystems.
- Added and passed an identity-checked native loop-file RAID5 failure/replacement/reassembly test without degrading the physical array.
- Preserved physical-member, independent-backup and cold-start acceptance boundaries.

## Initial public source publication — 31 October 2026

- Owner approved the personal mastechnica/FreeQNAP repository and Pages showcase.
- Rechecked source/assets for private data and retained the screenshot redaction receipts.
- Published-source history starts from a clean snapshot with personal-account attribution; private development history and binary OS images are excluded.

## 0.1 source review — 31 October 2026

- Added the complete local NAS dashboard: storage/crypto, sharing, file desktop, backups, media, USB, networking/private LAN, VPN, DDNS, downloads, recovery and notifications.
- Added compact graphical summaries, actual network history, SMART reports/schedules and rule-based optional buzzer/email/push controls.
- Recorded the bounded EJ188 USB write workaround and physical encrypted USB checks without extending their acceptance claims.
- Prepared the public project showcase, current-status overview and real redacted dashboard screenshots.
- Added reproducible source-only review packaging and static/provenance checks. Publication remains owner-gated; no remote or binary image is included.

## 0.1.0-dev — local review candidate, 29 October 2026

- Started an independent FreeQNAP source history without private project history or application configuration.
- Extracted tested TS-431XeU board integration and separate guarded installer components.
- Added a local storage console, read-only inventory/SMART collection and unprivileged service boundary.
- Added verified private configuration snapshots, daily scheduling, UUID-bound mirror copies and durable independent jobs.
- Recorded actual second-unit autonomous NAND boot results and outstanding hardware, installer and NAS acceptance.
- Kept all publication and binary-release gates pending owner review.

### Cold-start check

- Verified the installed NAND image boots without the transfer helper after a full chassis-off/on cycle. All four disks, both mirror members, networking, cooling and console services returned; a fresh backup verified.
- Recorded an unclean-metadata/bitmap-recovery observation as an unresolved shutdown follow-up. No metadata-forcing or power-off change was applied.

### RAID completion supervision correction — 2 November 2026

- Recognize scheduled OS-mirror checks queued behind data recovery without falsely faulting or prematurely accepting the array.
- Retain both-idle/non-degraded final acceptance, original fault evidence and read-only operation; eight policy tests and native service preflight passed.

### TR-004 mounted validation — 2 November 2026

- Initialized the two owner-approved unencrypted ext4 volumes using exact enclosure/partition guards; retained the quarantined-child interruption and inspected continuation.
- Refuse future format plans with read-only child partitions before layout mutation; 34 focused tests passed and the guard is deployed.
- Passed three write/direct-read/flush/remount cycles per volume, both read-only filesystem checks, safe eject and physical cable reconnection with exact proof identities.
- Preserved the software reauthorization readiness timeout and late successful verification as distinct evidence; no fast-software-reconnect claim. Internal RAID recovery continued throughout.

### TR-004 clean cold-start completion — 2 November 2026

- Passed owner-assisted enclosure-only power-off/on after verified safe eject; both exact filesystem/inode/direct hashes passed and both volumes are mounted read/write.
- Removed temporary files, retained original timeout/interruption evidence, and confirmed no failed services while internal RAID recovery advanced.
- Preserve unexpected-power-loss, NAS cold-boot-with-enclosure, full-surface and proprietary controller-health limits.
