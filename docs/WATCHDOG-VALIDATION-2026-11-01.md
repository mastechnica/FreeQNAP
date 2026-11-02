# Watchdog RAM expiry validation — 1 November 2026

**Bounded physical expiry test passed.** With the owner present, three intentional
SP805 resets completed from diskless RAM. The watchdog remains inactive in the
installed OS; no unattended reset policy has been enabled. Fixed full-speed
cooling was retained throughout and the owner observed all three fans spinning.

## Physical results

| Cycle | Driver-accepted timeout | Feed stop to next boot banner |
| --- | --- | --- |
| 1 | 10 s | 10.766 s |
| 2 | 10 s | 10.777 s |
| 3 | 10 s | 10.807 s |

These are serial observation intervals including boot-ROM/banner latency, not
oscilloscope measurements of the reset edge. No software reboot command was sent
for these expiry cycles. The driver did not establish an authoritative reset-cause
register value, so that remains unavailable rather than inferred from zero.

The arm/feed/disarm check passed before the expiry sequence and again afterward,
each with a 23-second inactive observation and no late reset. Every RAM session
showed only volatile mounts, no assembled arrays and acknowledged full-speed mode.
CPU readings were 49–50°C. The owner confirmed normal fans and all four bay LEDs
on return. The original saved boot command was used; no flash or saved environment
write was performed.

The approved fresh configuration export was encrypted, verified and independently
copied to the owner's private Mac folder, with its password kept private. Private
raw serial records, identities, checksums and backup material remain ignored.

### Return-to-service issue found and fixed

Both arrays returned healthy, but initial data mounting failed its exact partition
identity/extent check. After device discovery settled, the same resolver accepted
the exact saved UUIDs, sizes and offsets. Startup now explicitly waits for udev
before resolving MD partitions; it does not weaken any identity or extent check.
Native tests cover discovery ordering and continued refusal of a wrong identity.
A subsequent clean ordinary reboot automatically mounted both volumes with no
startup errors. Independent direct reads matched all three saved proof hashes,
and both arrays were again non-degraded and idle. No failed data mutation was
retried and no array membership or layout changed.

The remaining active health warning is OS filesystem capacity near the existing
1 GiB threshold after retaining the new encrypted backup. Notification preferences
and thresholds were not changed to hide it.

## Prepared controls

- The existing exclusive UART capture is receiving the running NAS console.
  A newline transmit check returned its login prompt. It does not require logging
  into the installed console to load the later RAM test environment.
- A dedicated local RAM image was built from the accepted prepared 6.12.114 board
  tree. Its DTS source matches the accepted source inventory; watchdog driver and
  kernel ABI are retained. Only the rescue filesystem and chosen boot arguments
  differ for this experiment. The artifact remains private, explicitly RAM-only
  and prohibited from installation/flash by its manifest.
- The wrapper, image size, SHA-256 and CRC checks passed. Normal installer image
  verification rejects this diagnostic unless RAM diagnostics are explicitly
  requested. It is not a replacement for the installed image or a public binary
  release.
- The actual embedded CPIO was inspected without execution. It contains only the
  reviewed RAM init, BusyBox, full-speed helper, thermal module, static ARM probe
  and necessary directories/shell link. There are no credentials, disk-root
  selector, installer, disk assembly script or persistent mounts.
- Boot parameters disable RAID autodetection and leave panic timeout disabled.
  The init requests and verifies full speed, then waits at a serial RAM shell.
  It never arms the watchdog automatically. Visible fan confirmation is required.

## Probe safeguards

[watchdog-ram-probe.c](../tools/watchdog-ram-probe.c) requires root on the exact
board, the dedicated rescue marker and cooling ACK, a RAM root, only volatile
mounts, no assembled MD arrays, inactive SP805, and `nowayout=0`. It holds a
single-owner lock and verifies the watchdog character-device identity.
No arbitrary device path or timeout is accepted. It requests 10 seconds and
checks the actual driver-returned value before testing.

The probe compiled statically for ARM with warnings treated as errors. A native
builder invocation correctly refused the ordinary Linux environment before the
watchdog-open path. This verifies a guard, not hardware reset behavior.

Two explicit operations are provided only for the accepted RAM shell:

- `watchdog-ram-probe disarm RAM-WATCHDOG-TEST`: arm, successfully feed, explicitly
  disarm, and observe for more than twice the accepted timeout. Only a completed
  observation with inactive state reports PASS.
- `watchdog-ram-probe expire RAM-WATCHDOG-TEST`: feed successfully, keep its file
  descriptor open, stop feeding and wait for physical reset. If no bounded reset
  occurs, report failure and attempt explicit disarm. Interrupt/termination signals
  request an abort/disarm; a failed disarm retains ownership/feeding and requests
  operator intervention rather than silently abandoning an armed timer.

## Attended sequence used / remaining policy

1. Have the owner at the correct NAS with UART and Ethernet retained, and start
   the checksum-pinned transfer helper on the Mac. It serves only this image to
   this NAS, drops elevated privileges and accepts no uploads.
2. Preserve the reviewed pre-test recovery material. Any new export containing
   credentials/private keys requires explicit destination authorization.
3. Cleanly stop services and restart into intercepted U-Boot. No NAND/SPI writes
   or saved environment changes are authorized. Load and verify only the RAM
   artifact; require its unique rescue receipt, volatile mount list, no arrays,
   temperature and full-speed cooling evidence before opening the watchdog.
4. Prove disarm first. Perform three expiry/reset cycles with serial timestamps,
   re-intercepting each boot. Record actual accepted timeouts, reset/boot evidence,
   reset-cause availability and cooling after each. Stop on ambiguity or failure.
5. Disarm and observe again, then return to the installed image with the watchdog
   unarmed. Verify all disks, both healthy arrays, mounted data volumes, service
   health, saved proof hashes and unchanged full cooling. Normal reboot/power-off
   and any later production ownership policy remain explicit acceptance steps.

No automatic production watchdog policy was enabled by this campaign. Adaptive
cooling work remains behind the watchdog checkpoint and the separately documented
[protocol and failure-response plan](WATCHDOG-COOLING-PLAN.md).

## Production ownership and maintenance

Following completed bounded cooling/fault acceptance, systemd PID 1 was enabled as
the sole hardware owner at the driver-accepted ten-second runtime interval. The
manager property and actual device state/timeout matched. One PID-1 watchdog
handle and eight advancing heartbeats were observed over 35.12 seconds; a separate
short three-core load observation also showed advancing heartbeats and active
hardware. No feeding-stop test was performed on mounted persistent storage.

The exact managed policy was then disarmed. The driver stayed inactive and the
boot identity unchanged throughout a 24.03-second observation beyond two former
timeout periods. Re-enable passed; runtime hardware supervision is now active.
Reboot/kexec watchdogs remain off. Configurations are fsynced along with their
parent directory; disable refuses unknown policy files. Ordinary reboot/startup
persistence remains pending the next attended reboot. This protects kernel/PID-1
liveness; it does not claim that every NAS application is healthy whenever PID 1
feeds the device.

The subsequent ordinary restart of the installed 6.12.114 kernel passed with a new
boot identity. The managed ten-second watchdog became active automatically and
accepted permanent Auto cooling resumed. Both arrays were non-degraded/idle and
both data volumes mounted without startup errors. Independent direct proof hashes
matched again; the owner confirmed all three fans and all four occupied bay
indicators normal. This establishes the tested warm-start persistence case, not
power-loss or watchdog-expiry recovery with mounted filesystems.
