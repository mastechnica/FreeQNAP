# 128 GiB OS expansion — physical completion checkpoint, 2 November 2026

The owner-approved four-internal-disk layout was applied. The OS partitions are
128 GiB each; the mounted ext4 filesystem reports about 126 GiB, with 116 GiB free
at the first post-boot check. The two-member OS mirror is non-degraded and idle.

Thirteen encrypted recovery images passed independent verification before writes.
An initial whole-MD backup mismatch was retained and reconciled to unallocated
blocks; a separate exact-member image passed independent full rereads/decryption.
No failed image was overwritten or accepted merely because its archive opened.

Root filesystem/MD identities, partition starts/GUIDs, both 512 MiB boot partition
byte hashes and all 12,132 pre-growth critical manifest entries were preserved.
A redundant writable-state request returned busy before growth; a specifically
checked continuation grew the already-writable mirror without replaying assembly.

The approved replacement internal RAID5 is 29,588,159,201,280 bytes, split into two
unencrypted ext4 partitions of approximately 14.794 TB each (about 26.91 TiB total
before filesystem overhead). Both are below 16 TiB; the ext4 64bit feature is off.
Each accepted an 8 MiB random write/fsync/direct-read proof. After the ordinary
installed-image boot, exact filesystem UUID, path, inode and direct-read hashes
matched again. Both data filesystems mounted automatically.

The storage database was updated as its existing UID/GID. Every other logical
SQLite row, database ownership and permissions were preserved. Arrays were cleanly
checkpointed/unmounted for normal boot; no force-clean or assume-clean operation
was used. The kernel resumed initial data recovery rather than starting it over.

The normal dashboard and broker returned, strict CA-verified LAN HTTPS returned
200, and no system services were failed. Saved full-speed cooling was retained,
all three fan counters were normal, and PID 1's ten-second hardware watchdog was
active. USB devices remained excluded; the external enclosure stayed read-only
and unmounted. No notification preference or firmware flash was changed.

## Still running / explicit limits

Initial RAID5 recovery is running and the array remains temporarily non-redundant
until it finishes. The early post-boot estimate changed substantially as formatting
and boot I/O ended; use live MD progress rather than a promised finish time.
Do not call this synchronization complete or the array fully protected yet.

The installed NAND kernel is still the retained 6.12.114 image. Earlier 6.12.115
RAM-only security/hardening results are not a permanent update. This resize did not
close that promotion/rollback gate, firmware IBE limits, physical cold-start,
full-replacement RAID recovery, full flash restoration or external-enclosure
mounted long-I/O/reconnect acceptance. Existing bounded hardware tests remain
separate evidence, not proof of every failure mode.

Raw identities, keys, complete journals, GPT originals, recovery images, proof
records and verification output remain only in ignored private local storage.

## Completion supervision

A root-private read-only verifier now runs every five minutes. It pins this
installation, both MD identities and all four physical disk serial/WWN/capacity
identities. It records progress without changing synchronization settings. A
missing/faulty member, foreign identity or thirty-minute lack of progress latches
a fault for inspection; it never repairs/recreates an array or blindly retries.
Once recovery is non-degraded and idle, it rechecks both saved direct-read proof
files with exact filesystem/path/inode identities and records the result. Further
checks skip after completion or a latched fault. The actual restricted service
preflight passed. No email/webhook, alert silence or notification policy changed.

## Completion-verifier correction

The first verifier latched a false-positive fault when Debian's scheduled
`mdcheck_continue` service requested an OS-mirror consistency check. The OS
mirror remained non-degraded, with both members present and zero reported
mismatches; its `check` operation was queued (`sync_completed=delayed`) behind
the shared-disk data-array recovery. Requiring the OS operation to be `idle`
at every progress sample incorrectly treated this expected wait as a fault.

The read-only policy now records queued/running OS checks or resyncs without
claiming completion. Both arrays must still be idle and non-degraded before
final direct-read proof verification. Degraded OS mirrors, stopped degraded
data arrays, unexpected operations and unexplained delayed maintenance remain
errors. Eight focused policy tests passed, followed by a physical current-state
preflight and a successful restricted service run. Original failed evidence was
archived intact. No MD synchronization operation, priority or disk was changed.
