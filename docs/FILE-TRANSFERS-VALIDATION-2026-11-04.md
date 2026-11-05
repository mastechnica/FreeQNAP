# File-transfer progress and refresh acceptance — 4 November 2026

## Diagnosis

The owner's USB-to-private-Photos-folder copy was not running: the visible job had
failed during staging-directory creation with an operation-not-permitted error,
and had published no destination items. Recursive copying requested a setgid
permission bit prohibited by the broker's existing RestrictSUIDSGID protection.
The personal worker also created a separate nested operation ID, leaving a stale
running record and separating the visible job from its checkpoint.

The original failure/checkpoint evidence was retained privately. The stale nested
record was reconciled against the already failed parent; no source or staged data
was deleted. Folder copies and New folder now use ordinary descriptor-based group
permissions. Service hardening was not disabled or broadened.

## Changes and checks

- Personal transfers retain the actual queued job ID. Private durable telemetry
  records scan/copy/verification/publication phases, bytes, files and timing.
- The Files page shows current transfers, throughput and estimated remaining time;
  previous attempts remain available in collapsed history. Unknown/stale/stopped
  states do not fabricate an ETA.
- Folder refresh coalesces overlapping requests; manual Refresh/F5, timestamps,
  error feedback and private-library aliases remain usable. USB discovery does not
  block existing folder listings.
- A fresh retry plan revalidates access, source/destination identities and target
  collisions. Another active copy blocks duplicate retry review. Published files,
  original sources and failed staging evidence remain protected.
- Local regression: 516 tests, with 16 optional/environment skips and all remaining
  cases passing. Final JavaScript regression: 48 tests passed. Source/package and
  showcase checks passed.
- Sixteen native fixture tests passed under a transient unit with NoNewPrivileges,
  RestrictSUIDSGID, private networking and strict filesystem protection, including
  recursive verified copying and the personal-worker identity check. Fixture writes
  stayed in private OS scratch; these tests did not modify user media.

## Real authorized copy

A fresh plan was compared against the original explicitly confirmed copy: selection,
source identities, source share, destination share/path, destination filesystem and
directory identity, and copy mode all matched. Only that same no-overwrite copy was
submitted once under its original principal. A private submission receipt prevents
blind resubmission. The original failure remains recorded.

The source inventory contains 45,608 files totaling approximately 105.8 GB. Live
checks showed copied/verified counts advancing. At the latest recorded sample,
1,101 files and approximately 1.45 GB had been verified, with an average copy rate
of approximately 3.2 MB/s and an estimated 9.8 hours remaining. That early estimate
changes with file sizes and readback performance; it is not a completion claim.
A destination listing returned in approximately 0.1 seconds during the live copy.
The selected folder was still unpublished, as expected: whole selected folders
appear only after verification, while the transfer card reports staging progress.

The iCloud archive job was paused at its resumable checkpoint for backend activation,
then restored. Apple requested trusted-device approval and the owner approved it.
Both iCloud download and file copy were subsequently confirmed active. Later UI
updates restarted only the console and did not reconnect the Apple session or
restart the copy. No NAS reboot, disk-layout change, overwrite, notification-setting
change or operation on the first NAS occurred. Raw identities, filenames, snapshots
and receipts remain private and excluded from Git.

## Approval wording

The installed Apple connector exposes no supported device-name field for web-access
approval. FreeQNAP's local status now identifies its request and mentions trusted
Mac/iPhone approval. Apple's popup branding was not changed or promised; no active
Apple session was modified to experiment with labels.

The large copy, its final readback/publication, and whole-library iCloud completion
remain in progress. Additional owner visual acceptance of the live Files panel is
separate from the API/native/JavaScript checks. Nothing was publicly published.

## Path display and history follow-up

- Live paired source/output file descriptors yielded exact nested source and final
  destination file paths; private staging tokens are excluded from responses.
- Verified as the console service user that authorized transfer rows received path
  context. Unrelated job IDs received none in isolation tests.
- The scheduled collector was tested under its actual protected filesystem settings.
  Checkpointed SQLite reads reject concurrent changes; the collector gained no NAS
  state write permission. Hardware inventory collection remains independently guarded.
- History expansion and scroll state survive progress refreshes in DOM tests.
- The full regression run passed 517 Python tests (16 environment/optional skips)
  and 49 JavaScript tests. Subsequent metadata-consistency and paired-descriptor
  checks passed both targeted Python tests and both transfer-panel tests.
- Deployment restarted only the web console/proxy. The broker process remained
  unchanged and the real copy advanced past 4,300 verified files. Full-copy
  completion and an owner browser confirmation are still pending.

## Scoped storage and owner-approved continuation

- All 556 Python checks passed with 16 environment/optional skips; all 53 JavaScript
  checks passed. An additional continuation-checkpoint interruption test passed.
  Native ARM testing under root/freeqnap, strict filesystem protection, private
  temporary storage and special-permission restrictions passed all 34 fixture tests.
- Confirmed byte reuse and inode preservation across an intentional partial-file
  interruption. Mismatching retained bytes and another account were rejected.
  An interruption before rescan retained a new recoverable stage pointer.
- With the owner's explicit permission, paused only the operation broker after
  private state backups and unchanged source/destination identity checks. Saved
  an inventory of 8,143 staged files/about 8.8 GB; three sample hashes matched
  original sources. No reboot, formatting, source deletion or source overwrite.
- Submitted one fresh identity-matched continuation using the identical stage.
  Verified all retained file inodes, no size shrink, original-path presence and
  the three sample hashes afterward. At that check the job was running and had
  reused over 2.1 GB. Full-copy and whole-content completion remain pending.
- Mounted the unrelated 500 GB drive with the previously approved read-only options
  in 2.45 seconds while the continuation ran. Family file listing succeeded.
  Read-only lease probes refused source/destination unmount protection keys and
  allowed the unrelated volume. No in-use physical disconnect or forced unmount
  was attempted. Cooling services stayed active and RAID membership was unchanged.
- Typed dashboard confirmations now use CONFIRM; backend plan IDs/digests and
  exact target-bound confirmations are retained. UI errors and wait time appear
  inside the modal. Original failed/paused records and private evidence remain.

Live family-browser follow-up: the mounted music volume displayed 345 root items
as read-only while the continuation card visibly reported reused bytes and exact
source/final-destination paths. The updated explanatory UI was deployed with no
additional broker restart. A screenshot is retained only in ignored private
validation evidence. No new music copy was started. Whole-transfer completion is
still pending; the published folder appears only after verification finishes.

## USB layout and copy-destination follow-up

Verified the family browser displays one full-width USB row per physical device,
with the TR-004's two volume controls aligned together and no duplicate import
controls. The location dropdown/sidebar no longer repeat library shortcuts or
represented physical USB attachments. Distinct volume roots/shared folders and
unavailable private devices remain separate.

The live Open destination folder button opened the correct personal import share
and displayed Incoming copy: photo. The empty-folder explanation now states that
publication awaits complete verification. At the final check the copy remained
running, with about 11.09 GB processed of 105.81 GB, 8,963 files checked and no
published selected folders. Whole-copy completion is not claimed. No worker
restart, storage mutation or source change was performed for this UI update.

All 57 JavaScript tests and both read-only transfer-context tests passed. Live
screenshots remain in ignored private evidence, not public documentation assets.
Destination metadata reads now close their consistent SQLite snapshot before
reading plan/checkpoint files, avoiding unnecessary collisions with active imports.
