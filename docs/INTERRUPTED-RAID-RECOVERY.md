# Recover an interrupted registered data array

Open **Storage & RAID → RAID & recovery → Recover an interrupted array**. This
workflow exposes the guarded recovery operations needed after the observed
unclean-reset incident; it is not automatic force-assembly or a general data
rescue tool. A stopped or degraded array is not proof that disks should be erased.

Dashboard and agent recovery require a responsive installed OS, management service
and network. They cannot revive an unreachable machine or a hung kernel. Those
cases still require the separately documented physical/serial recovery path.

## Three deliberate stages

1. **Recover read-only…** identifies all four original internal RAID5 members,
   checks their metadata and recorded geometry, and saves a verified metadata
   backup before displaying the review. Download it to an independent device.
   Acknowledge its limited coverage and type the displayed phrase. If the exact
   accepted dirty/incomplete pattern requires it, the review explicitly discloses
   the metadata clean-state override. Assembly remains read-only; volumes are not
   mounted and rebuilding is not started.
2. **Resume rebuild & mount…** is a separate fresh plan and confirmation. It is
   offered only for the assembled read-only array. Enabling writes may resume
   recovery and replay ext4 journals. Do not assume that successful assembly proves
   parity or every file is intact. Make this decision with an independent file
   backup and the available evidence.
3. **Bring volumes online…** mounts the registered existing filesystems if the
   array is already writable. Existing mount/check jobs are observed rather than
   repeated. Large filesystem checks may take several minutes. A submitted result
   is not reported as completed mounting: refresh the volume state and Activity.

Before applying a plan the broker rechecks the running root, immutable disk
serial/WWN/size, exact member/array identities, GPT region geometry, filesystem
bindings and metadata. Plans expire after ten minutes and are consumed before
the first array mutation. A failed or timed-out operation is recorded as requiring
inspection and is never automatically resubmitted. Inspect actual membership,
read-only state, mount jobs and logs before deciding the next action.

## What it deliberately refuses

- Missing original disks, ambiguous/repeated roles, unequal event counters,
  unexpected holders, changed geometry or multiple rebuilding members. Ordinary
  mounts of an already active exact writable array tolerate naturally advancing
  event counters; stopped/read-only recovery does not relax that check.
- OS/root ancestors, USB disks, unregistered arrays, broad scan/assembly,
  repartitioning, formatting, recreation, member failure/remove/re-add and arbitrary
  filesystem repair. Existing replacement/import controls remain separate plans.
- Automatically unlocking encrypted filesystems. Unlock them separately using the
  existing encryption controls; this recovery path does not store unlock secrets.

The guided override currently supports the registered four-member RAID5 v1.2
layout only. Other failure patterns stop for specialist inspection. Kernel errors,
missing devices or changed identities must not be worked around by repeated
clicks. The original stall's root cause remains undetermined; successful recovery
is not a fix for that original fault.

## Metadata backup management

Recovery metadata archives contain the first 8 MiB of each verified member and
an identity manifest. They **do not contain a backup of your files or parity** and
are sensitive private device records. They remain local, downloadable only after
administrator authentication or a specific `raid.backup-read` agent grant. Each
archive is checked before the associated plan can be applied. The latest complete
archive for each array is retained. An older archive can be removed only after an
explicit saved-copy acknowledgment and its exact deletion phrase; current plans
and the latest recorded operation protect their archive. Capacity is bounded at
16 complete archives and requires at least 512 MiB free before another backup.
There is no automatic metadata-restoration button or automatic cleanup.

## Agent access

`raid.recovery-status` and `raid.backups` are read-only grants. Inspection,
writable resume and mounting each have separate `*-plan` and `*-apply` grants.
No existing token or preset gains them automatically. The same exact confirmation,
backup acknowledgment, freshness, identity and phase checks apply. One agent
cannot use another agent's plan. See [the API contract](MY-RADIO-AND-RECOVERY-API.md).

The new recovery mutations are validated with fixtures and failure-injection
tests. They have **not** been replayed against the running array merely to test
buttons. The actual incident's previously approved recovery and proof verification
are recorded separately in [the dated incident report](LOCKUP-RECOVERY-2026-11-03.md).
Physical unplug, full replacement, broader file-content/parity verification and
recovery cold starts remain separate acceptance cases.
