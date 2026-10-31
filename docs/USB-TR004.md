# USB external storage and QNAP TR-004

FreeQNAP treats USB storage as separately registered data volumes. It never selects a USB device as an internal RAID member or boot-install target. Connecting a device does not format, mount, unlock or change its enclosure RAID mode automatically.

## What the TR-004 presents

QNAP documents the TR-004 as USB direct-attached storage usable by Linux, with individual/JBOD and hardware RAID modes configured by the enclosure. Its settings determine the logical disks Linux sees. FreeQNAP manages partitions and filesystems on those presented disks; it does not replace the controller firmware or implement QNAP's proprietary RAID Manager. Controller RAID health/rebuild, fan/temperature status and enclosure button behavior are not inferred from a healthy Linux filesystem.

Connect the enclosure directly to a rear USB port using a suitable USB 3 cable, without a hub. Leave its existing mode switches unchanged for discovery. The dashboard shows the actual negotiated speed and storage driver; host USB 3 capability is not proof of a completed 5 Gb/s transfer test.

QNAP's mode-switch procedure can destroy existing data. Choose a physical hardware RAID policy using the model's manual only after preserving needed data. FreeQNAP never presses Set, changes mode switches, recreates controller arrays or assumes an unknown mode is RAID5. The manufacturer's individual-mode hot-swap restriction also remains relevant; do not treat individual member removal as a safe Linux volume eject.

References: [TR-004 product and Linux support](https://www.qnap.com/en-us/product/tr-004), [official TR-series user guide](https://download.qnap.com/TechnicalDocument/Storage/Expansion%20Unit/TR%20Series/tr-00x-ug-03-en-us.pdf).

## Dashboard workflow

Open **USB storage** and discover the connected devices. Enclosures with no usable logical disk can still appear. Missing/ambiguous serial identity, a protected OS ancestor, an active holder, swap or an unrelated mount blocks initialization. Device identity includes USB vendor/product/serial, interface, SCSI channel/target/LUN and capacity. Initialization uses a stable USB by-id link and rechecks the attachment before destructive phases. A changed kernel disk sequence makes an old mounted attachment unavailable until deliberately reconciled. Volume/partition UUIDs bind later use; changing `/dev/sdX` letters is not authority to use another disk.

For existing ext4/LUKS2 data, select the exact filesystem UUID and review an import. Read-only is the default. Read-only ext4 uses `ro,noload` to avoid journal replay; it is inspection, not a clean-filesystem certification. LUKS2 needs an owner-supplied password or key before its inner ext4 filesystem can be used. The external-volume browser permits read-only traversal/downloads without changing existing file permissions or creating a share. Symlinks, private FreeQNAP directories and nested filesystems are not followed.

For disposable storage, request a new volume plan. The review displays the exact enclosure/LUN, current geometry and signatures and requires **ERASE EXTERNAL name**. This creates one or more GPT data partitions and ext4 filesystems (4 KiB blocks, one inode per 256 KiB, zero root-reserved data-volume percentage and lazy table/journal initialization), optionally inside LUKS2; it destroys the previous data on that presented LUN. It does not reconfigure the TR-004's hardware RAID. Interrupted mutations retain their operation evidence and cannot be blindly retried.

A mounted writable external ext4 pool can be chosen for ordinary NAS shares, media folders, Restic repositories and managed downloads. It remains separate from internal Linux MD arrays. Encrypted volumes stay locked on boot. Existing unencrypted imports support an explicitly chosen auto-mount policy; the dashboard defaults to manual mounting. Lost or changed USB identity makes dependent exports unavailable rather than writing into the root filesystem underlay.

Use **Review safe eject** before unplugging. The plan covers every visible logical disk and registered volume in the same enclosure. Active jobs or unmanaged mounts block it. It stops dependent services, performs normal unmounts, closes encryption mappings and requests standard cache flushes. There is no force/lazy unmount, controller RAID command or automatic device power-off. Only a completed result says safe to unplug. Other mounted NAS shares are reconciled afterward. The enclosure's hardware eject/copy buttons are not integrated shortcuts.

An unmounted external registration can be removed with a separate reviewed **FORGET USB name** plan after dependencies are removed. This forgets only metadata; it does not erase files, backup snapshots or encryption headers. Old history can retain unavailable references to the former pool name.

## SMART and health boundary

The specialized smartmontools `jmb39x-q` method for this enclosure communicates using volume-sector reads/writes and has an interruption-related sector-restoration warning. It is not a harmless read-only probe. FreeQNAP therefore does not run it, select `force`, poll member ports or start tests automatically. USB devices are excluded from automatic vendor SMART probing. Unavailable controller/member health is displayed as unavailable, never as a passed disk check. Linux MD health describes the NAS's MD arrays, not the enclosure's independent RAID.

See the [upstream smartctl manual](https://github.com/smartmontools/smartmontools/blob/main/src/smartctl.8.in). Any future vendor-health integration needs a separately reviewed, verified protocol and recovery strategy. The current implementation makes no claim of full proprietary enclosure-management support.

## Validation boundary

Unit fixtures cover stable descriptor identity, changed/disconnected devices, OS protection, active mounts/holders/swap, read-only import, duplicate UUIDs, unsupported filesystems and eject guards. A native owned-loop campaign executed actual GPT/LUKS2/ext4 creation, read-only re-import/unlock, preserved-content readback, refused writes on the read-only mount and normal unmount/crypto close. It did not use physical USB transport; the loop fixture simulates the enclosure identity and cannot test bridge cache-flush behavior.

The installed board kernel already includes xHCI, USB mass storage, UAS and ext4. This is sufficient driver availability for initial testing, not physical acceptance of this particular TR-004. Real enclosure discovery, negotiated SuperSpeed, sustained hash-verified transfers, disconnect/reconnect, standby/wake, eject/cache flushing and controller degraded/rebuild behavior remain device tests. NTFS/exFAT and other foreign filesystems can be identified, but are not automatically converted or offered as managed NAS volumes in this milestone.


## Initial physical TR-004 discovery

The connected enclosure enumerated as a USB mass-storage device at 5 Gb/s, using the `usb-storage` driver. It presented one approximately 30 TB logical disk with a model string reporting hardware RAID5, an existing ext4 partition and an invalid backup GPT. This is observed identity/layout information, not independent confirmation of controller member health or sustained transfer performance. The format request did not run during discovery and preformat checks. A later controller failure logged a failed block WRITE despite no format job; its origin has not been established, so those checks are not claimed to prove zero host writes. No controller RAID mode change was requested. The owner selected unencrypted ext4 for the initial volume, with any later encryption change performed by backup/reformat/restore. A fresh identity-bound plan still precedes each initialization. Private serials, UUIDs and captures are deliberately excluded here.

## Large disks on this ARM32 system

The accepted 4 KiB-page, 32-bit kernel cannot safely mount one ext4 filesystem larger than 16 TiB. This is a filesystem/page-cache addressability limit, separate from the enclosure capacity and ext4's 64-bit feature. The runtime rejects oversized single-volume plans before writes. A 30 TB enclosure can instead use two approximately 15 TB ext4 partitions; both belong to the same enclosure storage group and share its hardware RAID failure boundary. Only small alignment/partition-table regions are reserved. They are separate folders/volumes, not one combined 30 TB filesystem.

For split layouts, primary and secondary GPT metadata use aligned direct I/O. This avoids ARM32 buffered whole-device access limits at the far end of a disk larger than 16 TiB. Both original metadata regions are saved privately and checksummed before writes; both new GPT regions are read back exactly. These small metadata copies are **not a backup of the old filesystem or files**. Later mounts use partition UUIDs, not an assumed USB-by-id partition alias. Native owned-loop tests check both GPT CRCs, two actual ext4 filesystems, hash-preserving read-only remounts and group eject.

The source boundary is Linux `include/linux/fs.h` (`MAX_LFS_FILESIZE`), `fs/libfs.c` (`generic_check_addressable`) and `fs/ext4/super.c` in the accepted 6.12.114 tree. Raw direct reads can reach beyond 16 TiB without making an oversized filesystem mountable.

During physical preformat checks the Etron EJ188 USB host controller stopped responding. A targeted USB PCI-function reset and driver rebind restored the TR-004 without restarting the NAS. A temporary exact-enclosure read-only rule protected subsequent diagnostics; 2 GiB of direct reads across widely separated offsets passed. This is evidence of recovery, **not acceptance of long-term USB reliability**. Repeated sustained writes/readback, safe eject/reconnect and stable operation remain required.

Unencrypted-to-encrypted conversion is backup, verify, reviewed reformat as LUKS2/ext4, then restore and verify. There is no in-place encryption promise. Recreating this group erases both partitions, so preserve both before that operation.

## Historical write-path commissioning failure

The first identity-bound split-volume initialization saved both original metadata regions, then the USB host controller failed during the initial GPT write. The operation stopped and remains recorded; neither new ext4 volume was registered. A separately authorized diagnostic reduced the queue transfer size to 32 KiB and tried a same-content 4 KiB write. That also failed and disconnected the controller. This rules out the proposed transfer-size reduction as a solution; it does not establish the root cause.

USB-only recovery restored enumeration and an exact-enclosure read-only quarantine, retained locally across reboot, protects subsequent checks. No format retry was performed. The USB/PCIe DMA/write path needs further investigation and serial-backed recovery for any new kernel test. Do not use this enclosure for live NAS data until hash-verified writes, recovery and repeated reconnects pass. The two-volume source implementation and virtual-disk tests are not physical write acceptance.

Stock smartd DEVICESCAN has also been replaced on the test NAS with explicit stable internal SATA targets, preserving its prior options and notification settings. Four internal SATA disks are monitored; USB bridges are not scanned. The public helper preserves custom per-device policies and reports that their USB exclusions need manual review.

A serial-observed RAM-only A/B test retained the exact installed kernel and changed only the external PCIe host's coherency declaration. Both images booted; the experiment showed the intended `dma-noncoherent` property. The first approved same-content 4 KiB write still killed the EJ188 controller. This specific device-tree change is therefore **not a fix** and has not been installed in flash or promoted into the generic board source. USB-only reset/rebind recovered the enclosure under its exact-device read-only rule; the NAS then returned to its installed image. No second formatting attempt was made. The USB write/format acceptance gate remains open.

For password-unlocking existing encrypted USB disks from other systems, see [foreign encrypted USB sessions](ENCRYPTED-USB.md). These read-only readers do not convert the enclosure into supported writable storage or resolve the SuperSpeed write fault.

## Non-disruptive investigation — 31 October 2026

Read-only live inspection confirmed that the enclosure still uses usb-storage at 5 Gb/s and its block device remains read-only. Internal RAID initialization continued at 58.4%; no reset, rebind, write, format or reboot was issued.

Offline inspection of the prepared 6.12.115 candidate found the EJ188-specific ETRON_HOST, RESET_ON_RESUME, BROKEN_STREAMS and NO_SOFT_RETRY flags already present. Adding these flags again is not a justified fix. The historical broken-streams workaround targets UAS streams; this enclosure is currently using bulk-only usb-storage, so that workaround alone does not explain the observed write failure. The candidate has not been booted and does not establish runtime acceptance.

Next isolate transfer-ring completion versus PCIe outbound-DMA/addressing and controller error recovery using the original failure trace and exact installed source. Prepare instrumentation offline first. After internal synchronization and serial recovery readiness, compare a small disposable USB device with the enclosure, then USB2 versus SuperSpeed, using separately reviewed bounded writes. This can distinguish controller-wide failures from bridge/large-LUN-specific behavior. No such physical comparison has passed yet. Keep the existing failed noncoherent experiment and 32 KiB transfer-size result as negative evidence rather than repeating them as fixes.

Upstream background: [EJ188 broken-streams patch](https://lkml.iu.edu/hypermail/linux/kernel/2405.2/05085.html), [Etron controller workaround series](https://lkml.iu.edu/hypermail/linux/kernel/2412.0/00372.html). These describe candidate mechanisms, not a diagnosis of this NAS.

### Cold boot and second-device investigation

The owner-requested orderly shutdown/cold boot resumed the physical data-array recovery near its saved 66% checkpoint rather than starting over. The TR-004 enumerated at SuperSpeed under its read-only quarantine. A newly attached Seagate Portable (USB 0bc2:2344) enumerated through usb-storage after UAS stream support was refused, reached SCSI inquiry, but had not exposed a block disk during the initial observation. No test write was issued to it; identity/size/holders must be established before a reviewed write plan. This is not yet proof it shares the TR-004 write fault.

The exact EJ188 PCI function reports revision 00, a 5 GT/s x1 link, and 64-bit streaming/coherent DMA masks. The offline kernel contains XHCI_NO_64BIT_SUPPORT (bit 23); its global quirks parameter is read-only at runtime. A 32-bit-addressing experiment therefore requires a separately prepared boot/module change, not a live sysfs toggle. It remains an untested hypothesis. Do not change unrelated controller quirks or bypass read-only quarantine to claim a fix.

A separate cold-boot issue was observed: both internal data pools refused startup mounting with an exact partition identity/extent error, although later read-only partition/filesystem probes returned their recorded UUIDs. Investigate readiness versus geometry validation without weakening identity guards. RAID recovery continued independently; the volumes are not claimed mounted or accepted by this boot.

### Small-device write reproduction — 31 October 2026

The owner substituted a disposable 16 GB SanDisk flash drive. It enumerated at SuperSpeed with usb-storage and no mounted filesystem/holders. A serial/capacity/attachment-bound probe saved a 4 KiB original block, then attempted an unchanged-content direct write at 1 MiB. The write stalled and the controller failure removed both USB devices; no successful write/readback was recorded. This reproduces a USB write-path failure independently of the TR-004 and its large capacity, although it does not prove the ultimate cause. The original bytes and diagnostic plan remain private. No formatting or write to the TR-004 occurred.

An exact EJ188 PCI-function unbind/reset/rebind restored host-controller operation. This was USB-only: the internal SATA array continued recovery beyond 66.5%, and the OS mirror remained healthy. This is recovery evidence, not a write-fault fix. The 32-bit DMA-address restriction remains a prepared investigation direction requiring a controlled boot change; no runtime global-quirk write was attempted.

## USB write workaround validated — 31 October 2026

The first-write controller failure was reproduced on both the enclosure and a small disposable SanDisk drive. Restricting xHCI to 32-bit DMA addresses did **not** fix it. Reducing the EJ188 endpoint PCIe Maximum Read Request Size (MRRS) from 512 bytes to 128 bytes made the same bounded write/readback succeed. A normal installed-image reboot then restored the original kernel command line and 64-bit streaming/coherent DMA masks; writes continued to pass with only the MRRS workaround. This isolates the effective workaround from the unsuccessful DMA-width experiment. It does not establish whether the ultimate defect is in endpoint silicon, host-bridge setup or firmware.

`tools/usb-pcie-workaround.py` checks the exact board, PCI domain/function, EJ188 vendor/device/revision/class, bounded capability chain and reviewed current MRRS. It preserves all other Device Control bits, changes only MRRS and reads it back. There is no disk write, reset/rebind, DMA-mask override, flash update or saved bootloader change in the startup helper. `deploy/install-usb-pcie.sh` installs the helper and ordered startup service; native NAS provisioning invokes it before enabling the broker. Repeated invocation is idempotent. After a manual PCI function reset, explicitly rerun this service before any USB writes: function reset can restore the unsafe setting. Unrelated boards/controllers/settings are refused.

On the original installed kernel with the persistent workaround, three 8 MiB random direct-write/readback cycles passed on the flash drive. The TR-004 passed the same cycles at 64 MiB, beyond 16 TiB, and near the end of its 30 TB logical disk. Each selected region was backed up privately, restored byte-for-byte and verified. The enclosure returned to read-only afterward. Internal RAID recovery advanced independently and the OS mirror stayed healthy. No formatting, partition-table replacement or enclosure RAID-mode change was performed.

This clears the reproduced small-write regression for the tested configuration. It does not imply a formatted/mounted external NAS volume, complete enclosure management, encrypted physical-media compatibility, every USB device, power-loss safety or a long-duration soak. Keep exact-device quarantine until a deliberately reviewed next storage operation; do not automatically retry the historical failed format job. Original SPI/NAND contents are unchanged. The 32-bit DMA diagnostic image was RAM-only and is no longer running.

The normal-kernel extended regression also passed **128 × 8 MiB random direct write/readback cycles (1 GiB written and 1 GiB verified)** on the TR-004, followed by restoration and verification of the original region. The controller stayed responsive, the exact-device read-only flag was restored, no systemd service was failed, and internal RAID recovery advanced to 66.8%. This is a bounded regression, not a full-surface or long-duration reliability certification.
