# Kernel installation-review package — 2 November 2026

A private local package now preserves the **exact previously tested** hardened
6.12.115 complete-mirror candidate, its nine matching ARM modules and module
indices, plus the independently pinned original 6.12.114 rollback image and its
ten matching modules. This is preparation, not an installed update. Neither
image nor its original manifest was rewritten to imply greater acceptance.

The existing candidate already uses a persistent disk-root bootstrap. Its
“RAM-only” restriction describes how it may be tested and prohibits flash
installation; it does not mean the running root filesystem is diskless. A new
ABI/rebuild would introduce a new artifact requiring fresh physical acceptance,
so none was created solely to rename the same accepted functionality.

The review audit checked:

- Both original image SHA pins and legacy header/payload CRCs.
- All nine candidate and ten retained rollback ARM ELF/module versions, plus
  the candidate's complete module dependency index.
- The actual embedded CPIO's pinned accepted complete-mirror init, root selector
  and boot-record helper; Ethernet/thermal driver and hardware-helper bytes.
- The strict memory/BPF configuration and continued exclusion of the unaccepted
  CPU-register experiment.
- The unchanged restrictive candidate manifest: ordinary installer verification
  still rejects it, while explicitly requested RAM verification passes.

The unit-specific read-only session gate uses the enlarged OS identity and the
**new** RAID5/data-proof identities. Retired data-array/proof identities are not
substituted. Its live inspection correctly refused a kernel session while initial
RAID recovery was active. It has no reboot, module installation, flash, repair or
synchronization-control operation. No NAS files/services were changed by this task.

Before any permanent update: finish initial RAID synchronization, preserve a fresh
post-expansion encrypted configuration backup, review the precise installation and
rollback plan, retain UART recovery access, test the candidate and original rollback
against the current layout, and explicitly authorize any eventual flash operation.
The original candidate remains flash-prohibited. Source/license review is also
required before distributing binaries. Cold-start, final rollback and permanent
promotion remain open acceptance gates; prior bounded RAM results are not silently
converted into permanent-installation acceptance.

All private images, current identifiers, proof hashes and detailed receipts remain
in ignored local storage. No public upload or device modification was performed.
