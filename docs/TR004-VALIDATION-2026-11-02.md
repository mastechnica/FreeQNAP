# TR-004 mounted-storage validation — 2 November 2026

The owner approved erasing only the identified disposable 30 TB enclosure LUN.
Two approximately 15 TB unencrypted ext4 volumes were created, below the ARM32
16 TiB filesystem boundary, with the 64bit feature disabled. The hardware RAID
mode, internal disks, small USB drive and installed kernel/flash were unchanged.
The installed 6.12.114 kernel retained the exact-board EJ188 MRRS-128 workaround.

## Passed physical storage tests

- Both approved GPT images matched byte-for-byte through aligned direct reads.
- Both ext4 filesystems were registered and mounted through the storage backend.
- Three cycles per volume wrote/fsynced 512 MiB, verified direct-read SHA-256,
  unmounted, flushed the enclosure, remounted and verified UUID/path/inode/hash.
- Total: 3 GiB written, 6 GiB direct-verified; the mounted campaign and offline
  checks completed in approximately seven minutes.
- Every cache flush used a successful standard SCSI synchronize-cache command.
- Both unmounted `e2fsck -f -n` checks returned clean, without repair.
- The campaign's large temporary files were removed.
- Normal reviewed safe eject unmounted both filesystems and flushed the device.

## Preserved failures and inspection

The initial operation stopped after partition creation because an old validation
udev rule marked the new partitions read-only. Its operation record and GPT
metadata backups were retained. A separate single-use continuation verified the
exact unchanged GPT, retired only that enclosure's obsolete rule and finished
formatting; it did not replay partition creation. The new format-plan guard now
refuses a read-only child before layout mutation. The affected suites pass
34 tests.

A software USB deauthorization/reauthorization test exceeded its 30-second
readiness deadline. Linux logged a capacity-response delay, a USB reset, then
disk spin-up. The disk returned approximately 45 seconds after reauthorization.
The original failed test was retained and the disconnect was not repeated.
Separate late verification passed both exact filesystem/inode/direct hashes,
then safe eject passed again. This does not turn the deadline failure into a
passed fast-reconnect test.

Buffered probes on this ARM32 host reported an alternate-GPT warning on the
large LUN. Both actual GPT metadata regions matched the approved images using
direct I/O; the warning is not evidence that a table rewrite is needed. This
large-block-device tool-access limitation remains relevant to recovery tooling.

## Physical cable reconnection

After another verified safe eject, the owner disconnected and reconnected the
USB cable without changing enclosure power or RAID switches. It returned at
5 Gb/s with the same two filesystem UUIDs. Both saved inode/direct-read proof
hashes passed and both volumes mounted read/write. Temporary proof files were
removed. No USB reset was logged in this physical reconnection; the complete
SCSI disk and partitions appeared one second after the new-device kernel event.
That timestamp does not measure the owner's actual plug-in instant.

The cache-sync message after physical cable removal had a disconnected-host
result; both normal pre-unplug cache flushes had already succeeded and both
filesystems were unmounted. It is retained in the raw record, not treated as a
successful post-disconnect command.

## Clean enclosure power cycle

The owner powered off only the safely ejected enclosure, waited, then powered it
on with USB attached and RAID switches unchanged. It returned at 5 Gb/s. Both
exact UUID/inode/direct-read proof hashes passed after manual mounting through
the storage backend; both volumes remain mounted read/write. All temporary
proof files were removed. No USB reset was logged during this cold start.
The NAS stayed up, internal RAID recovery advanced, and no system services
were failed at the final check. This tests a clean enclosure power cycle, not
unexpected power removal during writes or unattended NAS boot with USB attached.

## Remaining acceptance

Unexpected power loss, NAS cold boot with the enclosure attached,
full-surface media verification, proprietary controller/member-health/rebuild
monitoring and regression under a permanently installed newer kernel remain
separate limits. Bounded successful I/O is not a claim of every failure mode.

Internal RAID5 initialization continued throughout. No MD member, recovery
setting, cooling policy, watchdog policy or notification preference was changed.
Raw identities, complete logs, filesystem UUIDs and proof records remain private.
