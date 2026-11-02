# Installer components

These are the extracted development tools, now part of FreeQNAP. See [the walkthrough](../docs/INSTALLING.md) for ordering, boundaries and what is still unfinished.

- `capture.py`: exclusive 115200 8N1 serial owner, private control socket, logs and optional per-boot countdown interception.
- `freeqnap.py`: attach/inspect/status, checked RAM loading/boot, normal installed-root boot, read-only inventory and planning.
- `transfer.py`, `backups.py`: immutable one-client TFTP serving plus explicitly enabled size-limited original-backup uploads.
- `artifacts.py`: immutable, target-restricted local HTTP artifacts.
- `flash-backup.py`: independent repeated reads, UART CRC/local-file/receipt verification; no erase.
- `flash-install.py`: separate identity-bound plan/preflight/program stages for the first NAND slot only, full readback and preserved-area checks.
- `recovery.py`: checked maintenance-only RAM overlay; refuses changed kernel or device-tree hardware.
- `target/`: initramfs PID1 handoff, restricted installation record, OS mirror installer and private credential setup.
- `audit-base.py`: rejects inherited identity, unlocked root or unreadable service configuration.
- `audit-initramfs.py`: read-only checks of both the prepared bootstrap directory and actual uncompressed newc/CRC CPIO before packaging. Rejects known inherited keys, installation records, home/runtime files, fixed network settings, personal build paths, unlocked root passwords and human accounts. Required boot helpers must be present as regular files. Bounded parsing rejects traversal, duplicate paths, malformed/truncated archives and appended archives without extracting anything.
- `build-*.sh`: packaging recipes against prepared development trees; not a complete public clean builder.

No release binary is included. The host workflow does not require a dedicated USB Ethernet adapter or reconfigure networking. Do not run vendor disk-loading commands as an untested recovery shortcut. Do not fabricate successful proof records to satisfy destructive gates.

Both generic-image and separate native-kernel recipes now require the bootstrap audit before compilation and against the built CPIO before packaging. Copy this audit alongside any privately staged recipe; a missing auditor stops the build. This is a known-identity/configuration gate, not exhaustive binary secret scanning, provenance verification or a complete clean-source builder. All 43 installer tests passed. The existing uninstalled 6.12.115 candidate passed both audits (46 entries each); no image was booted or flashed by these checks.

## RAM update with a pinned rollback image

The transfer helper can optionally serve `rollback.uImage` alongside an explicit
flash-prohibited RAM candidate. Use `--allow-ram-only --rollback-release` and
`--rollback-sha256` with the independently saved hash from the prior installed-image
verification. The rollback must be a normal generic image that passes full
legacy-header/data checks; a maintenance or RAM-only image cannot substitute for
that installed-image fallback. Both payloads are pinned in memory before privilege
drop. No arbitrary filename, upload, automatic boot, environment write or flash
authority is added. Comparison-image and rollback modes cannot be combined.

A rollback image may deliberately use a different kernel. Same-kernel A/B mode
still requires exact matching versions, including manifests using `kernel_release`
instead of `kernel`; absent version fields do not satisfy that check. Keep both
matching module sets and demonstrate actual RAM update/return on the board before
any separately reviewed permanent installation. Hash checks do not replace release
signatures, source/license review or physical acceptance.

## Read-only status and interrupted operations

`freeqnap.py status --session /private/session/install` reads the retained disk and
flash operation journals. It reports recorded writes even after verified flash
completion; an interrupted write sets `requires_reconciliation` with a stop/inspect
instruction. Malformed or incomplete write records fail closed. Status never
rechecks physical hardware, retries an operation, authorizes another write or
replaces the session. Absence of a journal is not proof that no other tool wrote
the hardware. Retain the original session and backups when reconciling a fault.
