> For the current source-review summary, start with [Current status](CURRENT-STATUS.md). The dated observations below remain a chronology, not a claim that their older implementation wording is current.

# Acceptance at the local-review milestone

Recorded 29 October 2026. Two matching TS-431XeU units informed this work. The original board engineering record is retained separately; test counts from that record must not be added to second-unit counts as if they were one campaign.

## Second-unit base system: observed

- Generic dev004 image boots the unit's own mirrored Debian 13 armhf root. Per-installation identity/records replace hard-coded first-unit UUIDs.
- Both original 32 MiB NAND kernel slots and full 2 MiB SPI were privately backed up and matched two independent UART-observed reads each.
- Only the first NAND kernel slot was programmed. Full padded 32 MiB readback compared equal. SPI, second kernel slot and saved boot command remained unchanged.
- Two unattended software restarts and one physical cold start booted that installed image with the TFTP helper paused and no bootloader intervention. The owner confirmed all fans had stopped before the cold start. Fresh OS checks passed afterward; see the shutdown follow-up below.
- Healthy synchronized two-member 8 GiB OS mirror, all four SATA disks identified, no failed systemd services, key-authenticated SSH, factory MAC restoration and ordinary DHCP on LAN1.
- Two administrative restart cycles per RJ45, each with matching bidirectional 256 KiB transfers. LAN1 negotiated 1 Gbps; the direct Mac adapter limited LAN2 to 100 Mbps.
- Acknowledged full cooling, three reporting fan counters, working CPU thermal readings; the owner observed all three fans spinning during the second-unit process. RESET-triggered orderly reboot was observed.
- Normal boot has no maintenance shell/debug arguments. Root password is locked and deferred; a supplied private installation key is used for administration. No application configuration was imported.
- RTC was explicitly set/read back as UTC. External NTP did not reply and outbound HTTPS was unavailable in the test network. The precise upstream cause is unproven; time synchronization and WAN access must not be claimed healthy.

## What these results do not establish

The final installed-image cold start passed: a new boot ID, observed automatic NAND read, no TFTP download, healthy synchronized OS mirror, all four disks and SMART health checks, all expected services, three nonzero fan counters and a CPU reading of 51°C. The owner confirmed three visibly spinning fans and correct green/activity indications in all four occupied bays. A fresh service-account configuration backup completed and verified after startup.

The boot also reported an unclean RAID1 state and a brief bitmap recovery despite the preceding orderly filesystem shutdown. Recovery completed and the mirror was clean/non-degraded at acceptance. Final RAID metadata/power-off ordering remains an explicit defect to investigate; this test does not establish resync-free clean shutdown. See [shutdown follow-up](SHUTDOWN-FOLLOWUP.md).

No disk-loader fallback, interrupted-NAND recovery or full physical flash restoration is accepted. The latter is excluded by owner decision.

USB2 reads on all ports, bay LED presence/activity, buzzer, physical orderly chassis-off and earlier warm SATA/network fixes are documented on the original unit. The new generic installer still needs its own complete peripheral regression. Four disks enumerating is not four-disk load, hotplug or rebuild acceptance.

SFP+ traffic, USB SuperSpeed, adaptive cooling, stalled-fan/thermal fault response, watchdog expiration, wake/RTC alarm, degraded OS boot, array rebuild, data power-loss recovery and a general kernel update/rollback path remain unaccepted. The root selector currently stops on a degraded root; high-availability degraded boot is not promised.

## Standalone console acceptance

The local suite covers SQLite/WAL consistency and session exclusion, archive corruption, retained good backups after failure, retention, wrong/missing mirror UUID, verified mirror copy, job failure isolation across restart, interruption reconciliation, daily schedule persistence, root/stale/changed disk protection, login/session hashing, forged identity headers, CSRF/origin/Host rejection and read-only synthetic preview. All 14 management tests passed both on the Mac and natively on Debian ARMhf. The root collector reported all four drives with SMART health passed and no inventory errors. A real service-account configuration backup completed and independently verified; state/backup directories were mode 0700 and the root-owned inventory mode 0640. The console listens only on 127.0.0.1, with its separate administrator still unconfigured. These checks do not accept destructive array recovery or a full restore.

Public installation is not ready until clean source builds, artifact/license packaging, a unified guided workflow, remaining native integration/failure tests and the release checklist are complete. Keep private evidence out of the public repository; publish redacted results only after owner review.


## Native NAS/network software fixture campaign — 29 October 2026

The expanded source includes real shared-file backup/staged restore, guarded storage/recovery and crypto controls, media approval, VPN and download operations. This is separate from real-data commissioning.

- Disposable file-backed loop RAID/LUKS/ext4: recovery-key add/verification, private header backup/readback, chunked file transfer hash, Restic backup and staged restore without overwriting modified live data, encrypted SMB3 file write/read, NFSv4 RPC response, AFP DSI response, ffprobe/NFO scan, accepted Gerbera configuration and wrong/right-key reopen checks passed. NFS/AFP file-client interoperability is not inferred from those protocol responses.
- Isolated network namespaces on the ARMhf NAS: default-deny DLNA IPv4/IPv6, observed pending identities parsed for dashboard use, approve/revoke/address separation and fallback-port protection; VPN WAN input/reply policy, selective gateway NAT and functional fallback-WAN denial; actual encrypted WireGuard userspace and OpenVPN mutual-TLS HTTP, handshake and certificate revocation passed.
- Isolated generated HTTP data: actual aria2 saved-session restart, nonzero Range resume, complete SHA-256, private RPC authentication/unknown-GID handling and paused startup before desired-state reconciliation passed.
- Local host tests additionally cover private plans, refused hooks/scope expansion, stale VPN confirmation, rollback independent of storage locks, concurrent media revocation, ambiguous admission and fairness across many permanently failing downloads.

Live provider interoperability, physical player devices, real torrent payload exchange, systemd mount-loss/early-boot behavior, native VPN kernel RAM boot and physical data-array recovery remain acceptance gates. No actual NAS data pool/share or external VPN is configured by these fixtures. See [the network/download guide](VPN-DOWNLOADS-MEDIA-ACCESS.md) and [dated security review](KERNEL-SECURITY.md). These test results do not remove the shutdown metadata, degraded-array or remaining hardware limits.


## Live control-service checkpoint

The committed console and privileged broker have been deployed on the second NAS with empty data-pool, share, media, VPN-client/server and download settings. An actual request from the unprivileged console UID to the private broker succeeded; startup errors were empty and the independent worker was healthy. The browser administrator is still uninitialized: no default password was introduced. The console listens on loopback only; unconfigured media, VPN and download listeners remain closed.

The initial broker lock path was outside its allowed state directory; it was moved inside that directory without weakening isolation. A subsequent systemd mount fixture verified the same UUID and file readback inside the retained private namespace and on the host. `findmnt` reported identical propagated aliases twice; exact deduplication now accepts those, while tests reject a different source, filesystem root or options. The loop file/device and test mount were cleaned up. No real disk, data-pool layout or boot flash was changed by this fixture.

The normal installed kernel remains unchanged. The matching TUN driver is now persisted for that exact kernel, and its module lookup was verified. The separate kernel with native WireGuard remains an uninstalled RAM-test candidate. Full boot/kill-switch behavior, encrypted real pools, physical clients and recovery drills are not inferred from a running broker.


## External USB storage preparation

Separate USB identity/import/create/eject controls and the read-only external browser are implemented. Host/native fixture tests and a real GPT/LUKS/ext4 loop campaign passed; actual TR-004 transport, cache flush, hot removal/reconnect, speed and controller health/rebuild remain unaccepted until the enclosure is connected and tested. Automatic USB vendor SMART probes are disabled because the specialized TR-004 method uses sector writes. See [the TR-004 guide](USB-TR004.md). No physical external disk has been formatted by these fixture tests.


## Subsequent maintenance checkpoint — 30 October 2026

The original dated observations above remain historical evidence. The owner has now initialized the dashboard administrator privately. LAN-only private-CA HTTPS passed real certificate-verified endpoint and isolated authentication/security checks; client trust remains an owner action. See [local HTTPS](LOCAL-HTTPS.md).

After upstream access was restored, direct verified HTTPS, official signed Debian main/updates/security metadata and valid NTP synchronization passed. The update simulation reported no pending packages, and the temporary administration-computer package relay was retired. Later clock tracking showed about 1.2 ms system offset and 3.4 ms root dispersion.

The approved internal RAID5 has two mounted bounded ext4 filesystems; initial synchronization is still running and is not accepted as full redundancy. The installed kernel remains 6.12.114. A signed-checksum-verified 6.12.115 source increment compiled separately with matching modules and the restricted root-survivor candidate. Image/header/checksum/module-index checks and all 39 installer tests passed. Either surviving RAID1 member passed owned-loop validation. None of this changes the physical boot, failure/rebuild, USB-controller or production-readiness gates. See [current readiness](PRODUCTION-READINESS.md), [kernel security](KERNEL-SECURITY.md) and [candidate recovery](BOOT-RECOVERY-CANDIDATE.md).


## Local health, PWA, SMTP and DDNS — 30 October 2026

The local incident dashboard and independent workers are deployed. Live checks report fresh monitoring, only the expected protection-incomplete RAID incident during initial synchronization, no startup/worker errors, verified HTTPS, zero push subscriptions/outbound notification jobs and no DDNS profiles. Email/push remain disabled. The signed DDNS driver is installed with its stock daemon masked and a separate non-login execution account.

All 192 native ARMhf application tests passed, including real Web Push encryption/decryption and VAPID signatures. Six Node desktop/PWA checks passed. Isolated native SMTP STARTTLS/implicit-TLS authentication, later-recipient acceptance despite another recipient failure, restart recovery and untrusted-CA rejection passed. The real DynDNS2 driver passed verified-TLS/authentication/cache receipt, provider rejection and untrusted-CA refusal inside its unprivileged transient-unit sandbox and a disconnected namespace. Native HTTPS authentication/origin/CSRF/subnet checks passed again. No owner mailbox, browser subscription or external DDNS account was contacted by these tests.

The live manifest, worker, icons and new scripts were independently retrieved over strict CA-verified HTTPS. This is not proof of phone installation/permission/receipt, live provider updates, external reachability or production storage acceptance. See [health/push/email](HEALTH-NOTIFICATIONS.md), [DDNS](DYNAMIC-DNS.md) and [readiness](PRODUCTION-READINESS.md). No kernel flash, chassis reboot, RAID member change or firewall expansion occurred.

### Generic bootstrap identity gate — 30 October 2026

All 43 installer tests passed. Both prepared-directory and actual uncompressed embedded-CPIO audits passed for the existing uninstalled 6.12.115 candidate (46 entries each). Future generic/native recipes stop if known inherited identities or required-file/archive defects are detected. This does not replace source/provenance review, clean public builds, boot tests, repeat installation or hardware acceptance; the candidate remains RAM-only and uninstalled.
