# Transfer recovery and File Manager Properties — 5 November 2026

## Diagnosis

A whole-drive music import had two reviewed batches: the first 200 top-level
items completed; the second 145-item job waited behind the first, exceeded the
plan's ten-minute freshness window and failed before copying began. Its error
was “Plan is expired, used, or belongs to another operation.” It had no partial
stage or published destination items. This was a queued-approval lifetime fault,
not evidence of a USB write failure or lost source files.

A separate USB photo transfer completed successfully. Copying files into the
personal import area did not by itself add those files to the photo catalog.
The copied source inventory contained 29,827 eligible photo/video files totaling
98,750,925,004 bytes, with no completed local-source revisions yet indexed.
Unsupported companion/cache formats and hidden entries are not promised as photos.

## Correction and live work

- Fresh transfer approvals are checked on submission and bound durably to the
  exact job, actor, request and acceptance time. Waiting in the queue does not
  expire an accepted job. Plan digest, account, consumption, filesystem and
  source/destination identity checks remain authoritative at execution.
- The failed historical batch remains preserved. A fresh plan was compared with
  the original selected identities and destination, all 145 source items existed,
  and none of its targets existed. Only this unstarted batch was queued again.
  The copy contains 17,040 files / 277,435,281,708 bytes. Existing files are not
  overwritten, and each copy receives a readback checksum before publication.
- The local photo-folder import is running in the original personal account.
  Its source folder is also exposed in that account's watched-folder settings.
  iCloud downloading was paused at its retained checkpoint to give local import
  a turn; a supervised continuation restores its previous unpaused state after
  that import. Saved Apple approval can still require manual attention.
- A low-priority completion service monitors existing jobs, compares both music
  batches against the source with full file checksums, and checks all eligible
  photo source revisions against the import ledger. It never repeats copies or
  RAID changes. Initial monitor startup failed before doing work because its
  module search path was missing; this was corrected and its failure evidence
  retained privately. The actual imports were unaffected.

**Acceptance remains in progress.** Live copying and photo catalog growth were
observed, but neither full music verification nor complete photo import is yet
claimed. Raw paths, account IDs, plans, checkpoints and results stay private.
Both internal RAID arrays remained non-degraded; no NAS reboot or RAID operation
was performed. The controlled application reload also required starting its
HTTPS dependency again; the authenticated dashboard was subsequently verified.

## Properties

Properties is available at the bottom of file/folder and Places-drive context
menus, including read-only locations. The dialog reports logical/allocated size,
file and subfolder counts, share-relative location, volume, type, modification
and available creation date, access mode and excluded links. It shows a waiting
message during folder calculation and explicit partial-total warnings on limits,
unreadable/changing entries or excluded nested mounts. It uses existing personal
and encrypted-volume ownership checks, without arbitrary host-path access.

Live checks included an 88,383,483-byte folder with 32 files and one subfolder,
and an empty folder through Firefox's authenticated family account. The browser
menu and displayed zero-byte Properties result were manually verified. Closing
Properties returned to the continuing transfer progress without interrupting it.

Validation: 719 Python tests passed with 16 optional/environment skips; 90
JavaScript checks passed. Added coverage exercises delayed accepted jobs,
rejection of expired submissions and wrong accounts, changed source identities,
recursive sizes, private/link exclusions, invalid paths and bounded partial totals.
The eight-second / 100,000-entry / 64-level limits are intentional; a partial
calculation is not an exact full-tree storage audit.

## Music-copy milestone — 5 November, 12:43 PM Eastern

The replacement 145-item music batch completed successfully: all 17,040 files
and 277,435,281,708 bytes were copied and passed the worker’s readback verification.
No transfer error is recorded. This closes the missing-batch copy, but the
separate full source/destination checksum comparison of both batches is still
pending while local photo import continues. At the subsequent check, 7,694
photo/video source revisions had imported with zero local-import failures.
The monitor and dashboard services remained active and both RAID arrays healthy.
The USB source must remain connected until independent verification finishes.
