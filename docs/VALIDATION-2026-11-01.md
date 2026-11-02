# Post-synchronization validation — 1 November 2026

This is an observed checkpoint on the physical TS-431XeU, not production sign-off.
Private identities and raw evidence remain outside the public source tree.

## RAID and health checkpoint

- Initial internal RAID5 synchronization is complete: all four members present,
  degraded count zero, synchronization idle. The two-member OS mirror is also
  non-degraded and idle. A later query showed the data array clean between writes.
- Both unencrypted ext4 data filesystems are mounted, each about 14.97 TB after
  filesystem overhead (about 27.23 TiB combined). The layout has not changed.
- All four internal SATA SMART overall checks passed. Reallocated, pending and
  offline-uncorrectable sector raw values were zero; temperatures were 36–42°C
  at the initial read. No new disk self-test was started for this checkpoint.
- No active monitored health alert or failed systemd service was reported.
- The OS filesystem has about 1.1 GiB free. Large test backing files therefore
  belong on an explicitly identified data filesystem, not the OS volume. Retained
  source/release generations need a reviewed retention/archive plan before broad
  cleanup; no rollback image was silently deleted.

The 31 October screenshots intentionally retain the earlier initial-sync warning.
They are historical captures, not a current-status feed. Their pixels were not
changed to present an artificially healthy system.

## Bounded physical-filesystem backup and restore

`tools/native-data-volume-smoke.py` used two UUID-bound existing internal data
filesystems and separate disposable state. No permanent NAS share, repository,
user or service configuration was created. The payload was 4 MiB plus small
metadata/media/archive fixtures.

Passed:

1. Chunked upload and direct-read SHA-256 verification.
2. Cross-filesystem staged copy and atomic rename, with overwrite refusal.
3. Recycle and reviewed restoration.
4. ZIP creation, named extraction and current-folder extraction.
5. Authenticated media Range response, unauthenticated denial and multi-file ZIP
   download from the real data filesystem; this did not play test audio.
6. Explicit same-RAID backup acknowledgement and Restic full-data verification.
7. Staged restore with matching bytes, modes, ACLs and extended attributes.
8. Modified live source was not overwritten by restoration.
9. Reviewed promotion of the staged restore into a separate test destination.
10. Wrong repository password was refused; the last good backup remained readable.
11. Production configuration remained byte-for-byte unchanged. Successful-run
    disposable folders and repository were removed only after identity checks.

An initial launch outside the checkout stopped at a missing bundled media fixture
before reaching backup. It was a test-launch error, not a storage failure. Its
owned artifacts were retained until a separate date/path/device/inode/expected-
content reconciliation removed only those disposable folders; isolated evidence
state was kept. The corrected complete-checkout launch passed. Do not silently count the first attempt
as successful or broadly delete unrelated validation directories.

Both filesystems share one physical RAID. This validates file/restore mechanics,
not an independent disaster backup or bare-metal recovery. An off-NAS production
backup destination remains deferred by the owner.

## Encrypted NAS configuration capture

A separate disposable-state capture of the current real NAS configuration passed:
194 captured files, about 18.8 MB encrypted, matching streamed download SHA-256,
verified decrypted manifest and SQLite integrity, consistent Samba credential
capture, wrong-password rejection and no persisted export password. Only this
validation archive/state was removed afterward; no owner archive was pruned and
no live configuration was restored. This is capture/download/decryption evidence,
not a fresh-system or full disaster restore.

## Physical-member test preparation

Two new 16 MiB proof files (one per internal data filesystem) were fsynced and
independently copied to the owner's Mac with matching SHA-256. They remain private
and are retained for the proposed physical-member test. These independent copies
protect only the disposable proof data, not all NAS data or configuration.

A fresh plan binds the selected data-only member to its disk/partition identity,
array UUID and both filesystem identities; it excludes OS mirror members, physical
unplugging, formatting, boot/flash changes and USB storage. The proposed logical
failure/remove/re-add test is **prepared, not executed**, pending explicit fresh-plan
approval. It can reduce redundancy and may require a lengthy rebuild. The array
remains fully populated while that approval is pending.

## Native file-backed RAID5 failure and recovery

`tools/native-raid-recovery-smoke.py` creates bounded owned loop files on one
explicitly identified internal data filesystem. It guards filesystem UUID,
backing-file device/inode/size, loop identity, array UUID and owned membership.
A wrong filesystem UUID was refused before fixture creation.

On the running NAS, the test used four disposable 160 MiB members and one new
replacement file. It performed a real Linux MD RAID5 test-member failure/removal,
then verified:

- 4 MiB direct-read hash while degraded;
- another 4 MiB fsynced write and direct-read hash while degraded;
- replacement-member rebuild to non-degraded/idle and both matching hashes;
- stop and exact-UUID, explicit-member, read-only reassembly; read-only ext4 mount
  without journal replay and both matching hashes.

The test array was unmounted/stopped and its owned loop devices detached after
verification. Successful-run backing files were removed after identity checks.
No raw physical-device formatting, physical array membership change, installed
boot change, flash update or reboot occurred. No force/assume-clean/broad scan
assembly was used. External notifications and buzzer were checked as disabled;
no preference was changed and no test message/audio was sent.

This is native kernel/MD/filesystem recovery evidence on file-backed devices.
It does **not** accept physical SATA disconnect, physical-array degraded boot,
controller fault recovery, physical replacement/rebuild or power-loss recovery.

## Next acceptance boundaries

1. Preserve independent hashes/test copies before any physical member test.
2. Review a fresh exact-partition plan and obtain explicit approval before
   deliberately degrading the real data array. Prefer a data-only member so the
   OS mirror remains intact. Do not unplug or fail an entire shared OS/data disk.
3. Verify degraded reads, bounded writes if approved, re-add/rebuild, member health
   and both filesystems afterward. A fast bitmap recovery is not a full replacement
   disk rebuild campaign.
4. Capture post-write orderly shutdown/restart and a physical cold start with UART
   recovery ready and independently saved hashes. Reconfirm clean assembly/mounts.
5. Complete intended client tests, independent backup/restore, sustained workload,
   and the remaining hardware acceptance gates.

See [current status](CURRENT-STATUS.md), [production readiness](PRODUCTION-READINESS.md),
[storage and backups](STORAGE-BACKUPS.md) and [acceptance chronology](ACCEPTANCE.md).

## Approved real-array member test — completed

After the earlier checkpoint, the owner explicitly approved the fresh data-only
member plan. The original proof copies on the Mac were re-hashed; the same disk,
partition, array, filesystem and root-exclusion identities passed a new preflight.

`tools/native-data-member-validation.py` ran under a non-restarting supervised
service so SSH disconnection would not interrupt the exact-member rejoin sequence.
The operation plan was consumed before the first mutation and checkpoints were
saved durably in private state. The helper defaults to read-only preflight and
requires a fresh private plan and exact confirmation for `--apply`. Its root
operations lock covers the short mutation sequence, not the potentially long
rebuild. It does not format, wipe, force assembly, stop recovery, change boot
metadata or alter the OS mirror/USB devices.

Observed sequence:

- Only the approved existing data-only partition was logically failed and removed.
  The kernel reported continued operation on three devices.
- Both original 16 MiB files matched their saved SHA-256 values using direct reads
  while degraded.
- One new 16 MiB file was written/fsynced in the owned proof folder and its direct
  read hash matched while degraded.
- `--re-add` successfully returned that same member; the ordinary-add fallback was
  not used. Kernel recovery started.
- Recovery completed with all four data members present, degraded count zero and synchronization idle. The OS mirror stayed healthy and idle; both data filesystems remain mounted.
- The supervised verifier passed, followed by an independent read-only completion check of exact disk/partition/array/filesystem/path/inode identities and direct-read SHA-256 hashes for both original 16 MiB proof files and the new degraded-write proof.
- Completion took about 71 minutes for the same-member re-add, benefiting from bitmap recovery. This is not a full replacement-disk rebuild duration.
- Current health monitoring reports zero active alerts and no failed scopes; there are no failed system services. The temporary degraded-array alert resolved automatically. Notification and buzzer preferences were unchanged.
- The completion monitor was removed after verification; no further member mutations were performed.

**Acceptance limit:** this passed a logical failure/removal and same-member re-add. Physical hot-unplug, full replacement-disk rebuild and degraded cold-start/power-loss recovery remain unaccepted.

A completion follow-up checks the existing supervised result and actual arrays;
it performs no repeat failure/removal. The supervised observation window is bounded;
a timeout does not stop kernel recovery or permit replaying the operation. Raw
records, exact identities and proof copies stay private. This remains a same-member
logical failure/re-add test: hot unplug, a distinct replacement disk, degraded
boot and cold-start/power-loss recovery are not established.


## Agent access and playback boundary

- Passed 233 Python tests on the development host (four platform-dependent skips)
  and all 14 JavaScript tests. The eleven new credential/renderer tests also passed
  natively on ARMhf, including HTTP byte-range reads and revoked stream denial.
- Checked operation inventory parity against every fixed NAS broker handler.
  Confirmed exact rights, hash-only storage, expiry/revocation, unknown-operation
  denial, browser/API separation, request limits and cross-principal plan denial.
- Checked renderer URL/identity restrictions, XML entity rejection, item selection,
  failed-play ticket cleanup, source-IP binding, player/token revocation, SOAP
  escaping and forward/rewind position arithmetic using controlled fixtures.
- Deployed only the console/source update. No reboot, broker restart, RAID member
  mutation, drive format, notification preference change or playback command was
  used for this installation. Optional media streaming remains disabled.
- A short-lived health-only installation credential passed real trusted-HTTPS
  discovery/read checks; ungranted power, administrator endpoints and credential
  delegation were denied. It was revoked and verified unusable, with no token
  included in public output or saved test evidence.
- Real TV/speaker playback, device-specific codecs and seek behavior still need
  owner-attended acceptance. No AirPlay/Cast or transcoding support is claimed.
- New source is committed locally; no private history or new public push is part
  of this validation.
