# Management stall and unclean-restart checkpoint — 3 November 2026

## Observed incident

The HTTPS shell, session and saved base-inventory requests could respond while
native NAS status remained pending. SSH connections completed TCP establishment
but timed out before their greeting, including from a second LAN host. The owner
reported the front power button did not respond, and performed a hard reset.
Removing a newly attached USB drive had not reliably restored management.
The owner later confirmed that this drive was not encrypted; its exact identity
and filesystem remain unconfirmed.
The original cause is unconfirmed. Do not label it a repaired USB fault.

The first successful post-reset capture showed a healthy two-member OS mirror,
ample memory and no data RAID assembled. No prior persistent journal existed,
so evidence of the original fault was lost. Current boot messages alone cannot
establish why the previous boot stalled.

## Management changes

The tested dashboard loading fix was deployed atomically with a retained rollback
copy and verified over HTTPS against source. No application service restart was
needed. Read requests time out, overlapping polling is prevented, and base status
can render while unavailable native operations remain disabled.

Persistent system journals are now enabled with a 128 MiB system cap, a 32 MiB
runtime cap and seven-day retention. Only the logging service was restarted.
The source installer carries the same configuration. Public source contains no
raw journals, device identities, credentials or private recovery plans.

## RAID checkpoint

All four original data members were present with matching array identity,
geometry, event counters and valid metadata checksums. The fourth member retained
about **90.86%** of initial recovery. Ordinary and explicit read-only assembly
refused an unclean array with three synchronized members and one still rebuilding.
This is the protective dirty/degraded RAID5 refusal described by the
[Linux MD documentation](https://docs.kernel.org/admin-guide/md.html#boot-time-assembly-of-degraded-dirty-arrays).

Before the approved override, each member's first 8 MiB was copied and verified,
with independent matching copies on NAS OS storage and the private local host.
These preserve RAID metadata and bitmaps; **they are not backups of file contents**.

The owner explicitly approved exact-member forced **read-only** assembly.
The tool marked array metadata clean to permit assembly; this did not verify or
repair parity. Kernel and block-device read-only state were verified, recovery
remained idle, no filesystems were mounted, and the original fourth-member
checkpoint and slot were retained. No member removal/re-add, formatting,
assume-clean creation, filesystem repair or reboot was performed.

Both original 8 MiB initialization proofs then matched their saved SHA-256 values,
filesystem/partition identities, paths, sizes and inode numbers. Reads used
`debugfs -c -D`, skipping eager allocation-bitmap loading while retaining checksum
validation and direct I/O. An initial ordinary debugfs invocation exceeded its
short read deadline and was stopped; a subsequent process/kernel capture did not
establish a repeat of the original management lockup. The successful proof check
is limited to those two files, not whole-volume integrity or all stored contents.

## Recovery progression (historical)

The owner separately approved the fresh writable-resume and existing-volume mount
plan. Exact identities, post-override header hashes and the saved rebuilding
checkpoint were checked before the single read-write activation. Kernel recovery
resumed near 90.86% with the original member; it did not restart from zero.
No second force operation, member removal/re-add or formatting occurred.

Normal system-managed mounting triggered ext4 journal recovery. The first
command's 90-second client wait expired while its existing filesystem-check/mount
job continued. That timeout was retained honestly; the operation was not blindly
resubmitted. An independent supervised continuation waited for the existing job,
verified data-1's exact mounted file identity and direct-read hash, then submitted
the already approved data-2 mount asynchronously. Both existing volumes completed journal recovery, mounted, and passed their
original exact-inode direct-read proof checks. The supervised continuation
recorded completion. Kernel recovery is progressing around 91%, with reduced
redundancy and a variable ETA.
The native status API, web services, cooling telemetry and hardware watchdog are
responsive. The OS mirror remains non-degraded.

The continuation records each phase and stops on errors without restarting RAID
operations. A read-only completion monitor checks current MD state and will verify
both exact proof files again once the array is fully non-degraded and idle. An OS
consistency check is reported separately from loss of OS mirror redundancy.

Original lockup root cause, complete contents/parity integrity and remaining
physical acceptance are still unverified. Writable recovery completion is
recorded below; the earlier client timeout evidence remains preserved.

## Recovery completed and final proofs verified — 4 November 2026

At the 09:41 UTC check the original four-member data RAID5 was fully non-degraded
and idle, with all four original disk identities and member partitions matching.
No force assembly, writable activation, member mutation, formatting, mount
resubmission, reboot or recovery tuning was repeated by completion monitoring.

Both original 8 MiB initialization proof files passed fresh aligned direct-read
SHA-256 checks. Verification pinned each filesystem UUID, partition UUID and byte
extent, mount, path, inode, size and unchanged file identity during the read. Both
existing data filesystems remain mounted read/write. These checks accept the two
sample files, not every file or whole-array parity consistency.

The two-member OS mirror remains non-degraded. Its previously queued consistency
check is now running; this is maintenance, not loss of redundancy. At the final
health snapshot that check was the only active warning, with no active critical
fault or failed monitoring scope. Full cooling, its independent guard and the
ten-second hardware watchdog were healthy. Trusted certificate-checked HTTPS
returned 200. No new kernel errors appeared during the completion interval.
External notification delivery remains disabled as previously configured; no
notification settings were changed and no test message was sent.

Raw proof hashes, identities, progress logs and original timeout/failed evidence
remain private. The completion monitor is stopped after reporting this result.
Original management-lockup root cause, complete contents/parity validation,
physical disk replacement and recovery cold-start acceptance remain open. A
metadata clean-state override and two correct hashes do not prove that all data
survived the unclean reset intact.
