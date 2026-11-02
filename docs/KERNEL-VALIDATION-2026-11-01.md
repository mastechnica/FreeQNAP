# Attended kernel validation — 1 November 2026

This records bounded physical tests on the second TS-431XeU. Raw identifiers,
serial captures, credentials, original flash and binary images remain private.
The installed NAND image is still 6.12.114; all newer images here are RAM-only.

| Check | Result |
| --- | --- |
| Initial security-only 6.12.115 FreeQNAP6 RAM boot | Passed |
| Independently pinned original-image RAM rollback after FreeQNAP6 | Passed |
| Normal unchanged-NAND boot after initial rollback | Passed; Auto cooling/watchdog restored |
| Hardened 6.12.115 FreeQNAP7 artifact review | Passed; all nine matching ARM modules and actual CPIO helper/driver bytes checked |
| Hardened RAM boot and strict memory configuration | Passed |
| ARM boot W+X check | Passed; no W+X pages found |
| Three exact-identity direct-read data proofs on FreeQNAP7 | Passed |
| Connected RJ45 close/open regression | Passed twice; 1 MiB upload and direct-read download hashes per cycle |
| Other RJ45 close/open and payload regression | Passed twice; 1 MiB upload/direct-read download hashes per cycle |
| Watchdog live feeding on FreeQNAP7 | Passed; 35 seconds, eight samples and one PID-1 owner, no induced expiry |
| FreeQNAP7 full-fan CPU/four-disk read load | Passed; 601.509 seconds, 421 samples, peak CPU 64°C / disk 33°C, full-speed cleanup verified |
| FreeQNAP7 cold-start and final rollback | Pending |
| Permanent update installation | Not performed; diagnostic manifest forbids it |
| Mounted TR-004 long-I/O and reconnect acceptance | Pending separate fresh storage plan |

The first checker rejected the boot W+X success line because its final period was
absent. The retained raw report records that false negative. The parser now accepts
the complete native line with optional final punctuation, still rejects missing,
partial or failed checks, and passes 19 focused policy/evidence tests. No image or
kernel setting was changed to get the corrected evidence result.

## Network test safeguards

`tools/kernel-network-cycle.py` defaults to read-only preflight. Physical application
requires the exact installation, kernel, RJ45 MAC, one connected uplink, a route
through that interface, full cooling and healthy idle arrays. Each cycle runs in
an independent bounded service with an unconditional link-up stop action. It uses
ordinary link close/open and network reconfiguration; no driver unbind, PCI reset,
profile change or disk mutation. Unique private results retain failure evidence and
prevent blind repeats. Host upload/download checks are recorded separately; a
successful ping alone is not accepted as complete bidirectional transfer evidence.

The second-port address is observed through a temporary read-only UART observer,
without broad network scans or a required direct Mac Ethernet adapter.

## Explicit remaining limits

Strict memory permissions and disabled unprivileged BPF do not repair the firmware
IBE state. All four cores still report the firmware warning; the CPU vulnerability
sysfs summary alone is insufficient. No firmware replacement, exploit test or
complete external-driver CVE audit is claimed. See [security maintenance](KERNEL-SECURITY.md).
No forced watchdog expiry was induced with mounted storage. No physical RAID
unplug/replacement or new data-member mutation is part of these kernel checks.

A separate [CPU IBE experiment](CPU-IBE-EXPERIMENT.md) is prepared but unbooted; it is not part of the accepted running-image results above.

The owner confirmed all three fans and four occupied bay indicators normal on the hardened RAM kernel. Original flash backups were also independently hash-verified into the standalone private recovery workspace; no restoration or flash write was performed.

All three exact-identity direct-read proofs passed again after the load. Both arrays
remained healthy/idle with no failed services. The boot identity was unchanged and
the ten-second watchdog was active afterward. A planned additional short feeding
observer declined preflight because the load was already too near completion; no
under-load sampler was started and no such sampled result is claimed. The earlier
35-second/eight-sample feeding result remains separate.

During the second-port test the NAS obtained a different DHCP address and the
configured LAN HTTPS endpoint reported a real critical availability alert. It was
not acknowledged away or silenced. Returning the cable to the original port and
verifying HTTPS recovery remains an explicit checkpoint before the next boot.
The existing OS-filesystem capacity warning also remains visible.

The owner subsequently became unavailable for physical steps. No further reboot
was attempted. UART interception was disarmed while retaining capture. Local HTTPS
was restored remotely on the connected port with the existing CA and LAN scope;
strict NAS/Mac probes passed and the critical alert resolved. Full cooling and
watchdog remain active. A fresh encrypted configuration backup passed independent
Mac decryption/member-hash checks; old accepted backups were retained.

## Isolated service regression on the hardened RAM kernel

Both native-host namespace campaigns passed: 25 checks with userspace WireGuard
and 26 with the actual kernel WireGuard interface. Checks included encrypted HTTP
and handshake evidence, OpenVPN mutual TLS and revoked-certificate denial,
unsolicited VPN-WAN blocking, IPv4/IPv6 kill-switch behavior, gateway NAT and
approved-client controls, and pending/approved/revoked DLNA stream access.
The tool enters private mount/network namespaces before changing virtual interfaces
or firewall rules. Production LAN configuration was unchanged. These results do
not accept a physical VPN peer or hardware media-renderer playback.

## Approved bounded file and staged-restore regression

Passed on both commissioned internal data filesystems using newly owned disposable
folders and a 4 MiB generated payload: chunked upload/direct-read hash, cross-volume
copy, rename, overwrite denial, recycle/restore, ZIP creation and both extraction
modes, authenticated media byte ranges and unauthenticated denial, and multi-file
ZIP download. An encrypted disposable restic repository passed full data checking,
fresh staged restore, preserved modes/ACLs/xattrs, explicit promotion and wrong-key
denial. The original post-snapshot source was not overwritten; production NAS
configuration and RAID membership were unchanged. Successful-run fixtures were
removed with ownership/inode checks. This is same-array recovery, not an independent
disaster backup or bare-metal recovery.

The first attempt stopped at a missing media fixture after earlier file checks.
Its evidence and partial owned fixtures remain private for reconciliation. The
lookup now uses the installed package location and checks presence before creating
data files. The corrected run completed without repeating any RAID operation.

## Isolated download interruption regression

On the running hardened RAM kernel, a generated 32 MiB HTTP download was stopped
partway through by terminating only the isolated test download engine. Its durable
session and resume file survived, restored work started paused, and deliberate
resume issued a nonzero HTTP Range. The final SHA-256 matched the source. Missing
RPC tokens were denied and missing-job responses were reconciled. All traffic
used loopback inside a separate network namespace; production queues, real peers,
LAN routes and notification preferences were untouched. Temporary fixtures were
removed. This does not accept torrent exchange, NAS reboot interruption or disk-full
behavior. Both arrays remained non-degraded/idle and the watchdog active afterward;
the existing OS-space warning remained the only active alert.

Five agent-access and 24 management/TLS source tests also passed on the development
host, including grant/catalog parity, revocation/expiry, denied operations, reviewed
plan ownership, token privacy and session/HTTPS boundaries. These are fixture
checks, not a newly issued production agent credential or a physical client test.
