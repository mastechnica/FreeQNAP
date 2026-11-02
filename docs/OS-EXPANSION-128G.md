# Proposed OS expansion to 128 GiB

Prepared 1 November 2026 after the owner requested a larger OS partition and
explicitly permitted destruction of the internal data RAID. This is a reviewed
proposal, **not a completed physical resize**. The original OS mirror and data
array remain unchanged. The owner has now confirmed the exact disk plan; execution
awaits the privileged transfer-helper restart and offline recovery preparation.

## Intended result

- Two preserved boot partitions and an enlarged two-member **128 GiB** OS mirror
  (about 137.44 GB decimal per partition, with a slightly smaller MD/filesystem).
- Existing OS files, administrator access, root filesystem/array identity and boot
  records preserved. No kernel flash or bootloader change is part of this work.
- Destroy both existing internal data filesystems and recreate the four-disk RAID5
  with two new **unencrypted** ext4 volumes, each about **14.794 TB** before
  filesystem overhead, about **26.91 TiB combined** before overhead.
- USB storage, including the external enclosure and flash drive, excluded.
- New data-array synchronization starts again; old recovery proof files and old
  filesystem identities do not transfer to the new array.

The exact disk serials/WWNs, partition starts/ends/GUIDs, current array identities,
new geometry, plan digest and backup records remain in the private plan.

## Preparation completed

Fresh identity/geometry and health reads found both physical arrays healthy/idle,
with no configured data shares, users, media libraries or backup repositories and
no active application jobs. A fresh password-encrypted configuration backup was
independently downloaded, decrypted and verified on the owner's host: all 227
manifest members matched. Older accepted recovery archives remain retained.
This is configuration protection, not a full OS image or a backup of destroyed
user data.

A disposable four-loop-disk rehearsal passed member-partition enlargement,
MD-mirror enlargement, offline ext4 enlargement, unchanged root UUID/inode/payload,
unchanged boot bytes/partition identifiers and recreation of a working RAID5.
It never selected a physical disk. The initial fixture stopped too early during
new-array recovery; a corrected mounted-resize attempt then received “device busy.”
Those failures remain private negative evidence. The final offline test passed.
**Online filesystem enlargement is not accepted by these tests.**

`tools/os-expand-loop-smoke.py --confirm-loop-fixture` exposes the bounded rehearsal,
requires Linux root and selects only newly owned loop devices. A fixture result
is not physical acceptance or permission to edit the real root-disk table.

## Gates before physical writes

1. Obtain the repository-required confirmation of the exact destructive plan and
   revalidate every live disk/partition identity and the absence of data consumers.
2. Establish verified UART and pinned RAM maintenance access. Do not attempt an
   untested offline boot or run the procedure from the installed root filesystem.
3. With installed filesystems unmounted, capture a consistent full OS image plus
   boot/GPT recovery records to private host storage. Independently verify these
   before changing partitions. Never substitute a live raw read for a consistent
   offline recovery image.
4. Quiesce application writers and prevent automatic reassembly/remount of the old
   data array. Stop only that exact data array and retire its recorded mappings.
5. Preserve boot regions and root-partition starts/identifiers while enlarging the
   two root members; grow the root mirror and checked offline filesystem. Stop on
   any identity, geometry, filesystem or metadata inconsistency. No fabricated
   clean state, automatic rollback of disk metadata or blind retry is authorized.
6. Verify the expanded root and preserved OS contents, then create only the new
   explicitly planned internal data regions and split data filesystems.
7. Verify ordinary boot, credentials, services, HTTPS, cooling, watchdog, mounts,
   UUID mappings and file I/O; monitor both mirror/data synchronization to healthy
   idle state. Cold-start and new-array recovery remain separate acceptance gates.

The private operation journal must distinguish planned, started, completed and
failed steps. A failure requires reconciliation; do not rerun a destructive stage
because a supervised process timed out. Full-chip/SPI recovery remains excluded.

## Approved maintenance preparation

The owner confirmed execution of the exact plan. A separate flash-prohibited RAM
maintenance image was built from the tested hardened kernel configuration, changing
the initramfs and boot arguments rather than board hardware properties. Header,
CRC/SHA, unchanged hardware-tree properties and the built 46-entry CPIO identity
audit passed. It has not yet booted on the physical NAS.

[The maintenance init](../tools/os-expansion-rescue-init) forces full cooling, loads
thermal/Ethernet support and restores factory MACs. It never selects, assembles or
mounts a disk root, starts a watchdog, assigns a network address or writes flash.
Its ready marker requires subsequent inspection; it is not disk-write authority.

The cached generic RAM tools archive had the previously known unreadable network
and machine-ID permissions. A private derivative corrected only those two modes,
verified all 9,564 regular-file contents unchanged and passed the complete base
identity/configuration audit. These tools will run in RAM; they do not replace the
installed OS. Temporary SSH access must use a newly generated RAM host key pinned
through UART, with key-only owner access and separate strict host-key checking.

The owner must restart the immutable boot-transfer helper because its existing
process pins the older image and macOS requires administrator access to its port.
No reboot, application stop, physical array destruction or partition change has
been performed during this preparation. Consistent offline OS/boot/GPT capture
and independent verification still precede every physical layout mutation.

## Current physical expansion checkpoint — 2 November 2026

The approved physical operation has progressed beyond the historical preparation
and imaging-gate entries below. Thirteen encrypted recovery images were verified
before layout writes. The initial mixed-member image mismatch was reconciled to
54 unallocated filesystem blocks; a separate member-bound image passed exact
independent full rereads and decryption. Original evidence was retained.

Both OS member partitions are now 128 GiB. Root MD/filesystem UUIDs and all 12,132
critical manifest entries were preserved; the two-member root mirror is healthy
and idle. One redundant writable-state request returned busy on an already writable
array; the error was retained and a separately checked continuation performed only
the required growth. No force-clean operation was used.

The new four-member internal RAID5 has been created under the approved plan and
initial recovery is running. The two approximately 14.794 TB unencrypted ext4 data
filesystems are being created with the 64bit feature disabled. Data registration,
normal boot and post-boot proof/service checks are still pending. Full-speed cooling
is retained in diskless maintenance; USB devices and installed flash are untouched.
Early recovery ETA is unstable while filesystem creation competes for I/O; do not
present it as a guaranteed completion time. Synchronization completion and physical
cold-start/full-replacement recovery remain separate acceptance gates.
