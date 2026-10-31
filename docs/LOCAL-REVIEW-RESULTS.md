# Local review results — 29 October 2026

- Installer: 33 host tests passed; pure C identity decoder compiled with warnings-as-errors and passed framing/checksum/metadata/MAC rejection cases.
- Management: 14 tests passed on the Mac and native Debian ARMhf, including failed-job isolation across restart and archive integrity failures.
- Real collector: four disks, four SMART health passes, no inventory errors, synchronized non-degraded OS mirror.
- Real service backup: private service-account archive created and verified, no administrator/session identity imported.
- Boundaries: web service unprivileged, no device access, loopback-only; collector separate and root-owned; no failed systemd units.
- Source-package audit: required source files, board-file hashes, Markdown links and private-path/key-marker checks passed. Manual review remains required; this is not an exhaustive secret or security audit.
- Installed-image cold start: automatic NAND boot with transfer helper paused, all disks/services restored, all four SMART checks passed, 51°C CPU, three reporting fans; owner confirmed all fans and all four drive LEDs. A fresh post-boot backup verified.
- Shutdown follow-up: RAID1 reported unclean metadata and performed a brief bitmap recovery, then returned clean/non-degraded. Final power-off ordering is not yet fully accepted.
- No data pool, shares or destructive storage change was made by console deployment. Nothing was published and no Git remote was configured.

The interface preview uses synthetic data. See ACCEPTANCE.md and RELEASE-REVIEW.md for unfinished hardware, installer and NAS work. Raw device evidence and SSH access metadata are private and excluded from Git.

## Full-NAS expansion in progress

The owner expanded the scope to sharing, encrypted data volumes, shared-file backup/restore, media services and a guided installer. The source now includes a peer-checked Unix broker and fixed native-operation registry, a nine-workspace manual dashboard and a photographed HTML tutorial. The owner-selected appearance is black/dark red with white/grey text, fixed top navigation and a circle containing an inscribed triangle.

Twenty-five management/guard tests pass on the host. The earlier 23-test set also passed natively on ARMhf. All nine dashboard workspaces render in the read-only synthetic preview with no browser errors and no enabled modifying submit controls. These statements concern the tested source; the expanded broker/servers are not yet commissioned on the NAS.

The first loop-backed test stopped because the accepted kernel lacked a loop driver. A matching optional module was then built in an isolated copy of the exact kernel tree and loaded without changing NAND. The next disposable test verified chunked-upload readback and a real encrypted Restic backup/staged restore while preserving the changed live file. It then stopped at the isolated SMB listener check, so SMB/NFS/AFP/DLNA client acceptance is not claimed yet. Its temporary devices and processes were cleaned up without physical disk writes. Native service validation continues.

The original photo copies now have deterministic identifying-label masks, unchanged pixels outside those masks and no EXIF/GPS metadata. Only the rightmost GND pin has been explicitly reconfirmed for publication; other diagram labels are marked as related-model references. The rejected generative preview is not included.

## File manager and optional network control (October 30 UTC)

The local source now includes four file-manager panes, drag/drop and copy/cut/paste, staged verified copies, same-volume atomic moves, duplicate/rename, reviewed bulk recycle/permanent deletion, configurable 30-day expiry, original-folder recovery and failed-copy-stage cleanup. Search and folder paging are available; preservation and transfer limits are documented in FILE-MANAGER.md.

The independent network controller supports DHCP/static port profiles, DNS/MTU/route settings and an optional isolated private LAN with its own DHCP/DNS, reservations, friendly names, notes and block controls. Private LAN is disabled on the NAS. Seventeen isolated native packet/DHCP cases passed, and a live static-address test on disconnected LAN2 passed automatic 120-second rollback while retaining LAN1 access. No physical-port DHCP server was enabled. Boot/confirmation edge cases have separate state tests.

The privileged broker, console, collector, network controller and internal-only SMART monitoring run locally. The console still requires private first-run administrator initialization and LAN HTTPS commissioning; the preview is synthetic. The physical TR-004 write fault remains unresolved and the enclosure is quarantined read-only. Its two 15 TB volumes are not commissioned. Nothing was published.


## Archives, browser playback and encrypted USB (October 30 UTC)

The local file manager now provides safe extraction into the current or archive-named folder, reviewed on-volume ZIP creation, single-file download and streaming ZIP64 downloads for selected items or an entire folder. Media dialogs provide browser playback/fullscreen and raster-image viewing without a transcoder. The silent synthetic browser sample played; source/codec limits are documented in FILE-MANAGER.md.

The complete application suite passed 103 tests on both the Mac and native ARMhf NAS; 36 installer tests also passed. Native read-only fixtures passed LUKS1/ext4, LUKS2/ext4, LUKS2/NTFS and software-encrypted APFS known-file access, write denial and clean lock. Official BitLocker/To Go crypto vectors matched their complete known decrypted hashes; those fixture NTFS metadata did not mount, so complete BitLocker file browsing is still unaccepted. See ENCRYPTED-USB.md for exact boundaries and reader-source pins. No physical encrypted USB disk has passed acceptance.

The required FUSE, userspace skcipher and dm-zero modules match the installed kernel. The APFS reader was built locally from pinned source with a private stdin credential handoff; neither it nor any new kernel/module binary is included in the public candidate. The unsuccessful RAM-only PCIe coherency experiment was rolled back to the installed image. The TR-004 remains read-only, no data pool exists, private DHCP stays disabled and first-run console administration remains owner-initialized. No configuration, media, fleet data or secrets were imported. Nothing was published.
