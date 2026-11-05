# File-copy progress and folder refresh

File Manager shows **Your file transfers** above the folder desktop. Each entry
reports counting/copying/verifying/finishing/completed/stopped state, bytes copied
and verified, files completed, average throughput and estimated time remaining.
Totals are calculated by a bounded read-only tree scan. ETA includes the remaining
copy and readback verification; it is an estimate, not a completion guarantee.
Unknown totals, stale updates and stopped jobs never show a fabricated ETA.

Copies are staged on the destination filesystem, hash-verified, then published
without overwriting existing targets. A selected folder appears only when that
entire folder is verified. The live transfer card reports progress while it is
unpublished. This is separate from importing its supported files into the Personal
Photos gallery. Sources and failed stages are retained; nothing is silently retried.

Each folder has a **Refresh** button, supports F5, and refreshes automatically.
Only one listing runs per window; manual refresh requests coalesce behind it,
preventing overlapping polls from continually discarding responses. USB discovery
does not gate refresh of existing locations. The last refresh time/error is visible.
Private library shortcuts use their accessible share aliases instead of a hidden
NAS-volume root.

A stopped copy offers **Try copy again…**. This prepares a fresh plan from the
original source/destination selection and requires review before another attempt.
Source and destination identities, current access, target collisions and no-overwrite
rules are rechecked. Existing partial stages and failure evidence are retained.
Some partially published multi-item copies require selecting the remaining items
manually if a target already exists; an existing target is never overwritten.

## Source and destination paths

Transfer cards show **From** and **To** locations. The existing read-only inventory
collector samples the worker's open source files without acquiring its storage
lock or reading their contents. When exactly one selected source file is observed,
the card displays its complete source path and final destination path, including
nested folders. The observation time is shown: it is a periodic sample, not a
promise that the worker is still processing that file. Ambiguous observations
show the selected folders and current filename instead of inventing a path.
Unpublished staging locations and tokens are never displayed.

Path observations are joined only to transfer rows already authorized by the
broker. They are not a new job lookup API. Stale/unavailable observations do not
stop live counters or file copying. **Previous transfers** keeps its expanded state
and scroll position while progress refreshes.

## API

Authenticated `POST /api/nas/files.transfers` takes `{}` and returns
`{transfers: [...]}`. Each row contains `id`, `status`, timestamps, `error`,
`published_count`, a publication explanation and `progress`. Progress includes:

- `phase`, `started_at`, `updated_at`, `current_file`;
- `total_bytes`, `total_files`, `totals_ready`, `scanned_folders` when available;
- `copied_bytes`, `verified_bytes`, `files_completed`;
- `copy_seconds`, `verify_seconds`, average `copy_bytes_per_second` and
  `verify_bytes_per_second`;
- `percent` (nullable), `eta_seconds` (nullable), and `stale`.

Dashboard users need `files.read` and see only their own transfer principals within
their namespace. An explicitly granted agent operation is also principal-filtered;
existing tokens are not expanded automatically. Unpublished staging locations are not returned as browsable paths.
`POST /api/nas/files.transfer-retry-plan` takes `{id: "<failed-job-id>"}`, needs
`files.write` for a family account and rejects another principal's job. It returns
the existing immutable review-plan envelope. Submit that fresh plan's `plan_id`,
`digest`, and exact `confirmation` to `files.transfer` only after review.

## Service compatibility

Copy/create directories use ordinary group permissions, set through an opened
no-follow directory descriptor. They do not request setuid/setgid bits. This works
with the broker's `RestrictSUIDSGID` hardening, which remains enabled. Personal
background transfers use the actual queued job ID for durable progress; they do
not create an unrelated nested running job.

## Continue an interrupted copy

**Continue partial copy…** prepares a fresh identity-checked plan for a retained
single-selection copy (not a move and not a partially published multi-selection
operation). It checks the original requester, source/destination identities and
retained stage identity. No operation starts until the new plan is confirmed.
Existing staged bytes are compared with the source before reuse; remaining bytes
are appended, then the entire staged file is read back and SHA-256 verified.
Unexpected files, hard links, symlinks, changed identities or mismatching bytes
stop continuation and retain both source and stage. Original files and existing
published destinations are never overwritten. The previous attempt remains in
history and points to its continuation; its active stage cannot be purged through
the old entry. `reused_bytes` reports bytes retained rather than rewritten.

`POST /api/nas/files.transfer-resume-plan` takes `{id: "<interrupted-job-id>"}` and
requires `files.write`. It returns a normal `file-transfer` plan with private
retained-stage identity fields. Submit its ID, digest and exact returned confirmation
to `files.transfer`; the new job carries `continued_from`. Scoped agent grants must
explicitly include the new operation; existing tokens are not expanded.

Copies hold shared leases only on their source and destination volumes. A short
NAS metadata lock serializes review/lease acquisition and configuration changes;
it is released before long copying. Unrelated mounted volumes may be added or
removed. Lock/unmount/eject checks refuse volumes held by an active copy, before
stopping services. Mounted-source, immutable-identity and protected-OS checks still
apply to formatting. No force or lazy unmount is introduced.

## Simple confirmations and waiting feedback

Whenever the dashboard asks for typed confirmation, type **CONFIRM**. The selected
operation, exact disks and consequences remain visible in its review; the client
still submits the original plan-bound confirmation internally with its ID and
digest. API clients continue using the returned confirmation unchanged. Direct
share/DDNS/notification/metadata-backup prompts use the same word.

Busy storage changes receive an inline explanation before submission when the
collector observes the metadata lock occupied. A stale/unavailable observation
also blocks submission rather than guessing. Waiting operations show elapsed time
inside their dialog and are never automatically resubmitted. This observation is
an early usability check; actual per-volume leases and immutable identity checks
remain authoritative if lock state changes after the observation.

## Finding incoming and completed folders

File Manager's transfer cards include **Open destination folder**. The destination
window displays an **Incoming copy** notice for the exact selected names while
copying/verification continues. This is a status notice, not a partially published
file entry. Verified folders appear there automatically after the selected folder
is completely checked. Finished transfer cards retain **Open completed destination**
in Previous transfers. The private path observation includes the logical
`target_share`, `target_path`, `target_names` and sampled `published_names`, and is
still joined only to broker-authorized transfer rows.

Drive selectors, the Places sidebar and folder pickers use canonical library names.
An already represented mounted/registered USB drive does not also get a disabled
physical-attachment entry. Private unavailable media remains unavailable; duplicate
suppression never grants additional access. An unchanged drive selector is not
rebuilt during ordinary refreshes.

## Whole-drive imports and destination folders — 4 November 2026

Right-click a drive and choose Import to… to copy all accessible root contents, including subfolders, directly into a destination. The picker asks only for that destination; it does not ask for a source selection. A selected subfolder still imports that folder. FreeQNAP private system entries and symbolic links are excluded; unsupported/unreadable data stops its affected job without source deletion. Existing destination names are never overwritten or silently merged.

Whole-drive imports prepare all immutable copy plans before confirmation, in groups of at most 200 top-level items. One CONFIRM queues the reviewed jobs; each appears in Files and Activity. All source/destination authorization and identity checks still run in the existing service. Above 10,000 root items, import folders separately. If a submission fails, confirmed receipts remain visible and the interface refuses blind retries because the last request might have reached the NAS. Cancel stops further submissions; already queued jobs continue. This is a grouped copy, not an all-or-nothing volume snapshot. Files added after inventory are not included.
