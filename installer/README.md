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
