# Sources, board integration and licensing

This repository is an allowlisted source extraction with a fresh Git history. It excludes private deployment evidence, original flash dumps, vendor binaries, root images, packages, accounts and application source.

| Component | Recorded input |
| --- | --- |
| Linux | 6.12.114 upstream archive; SHA-256 `7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3` |
| Alpine Ethernet | https://github.com/mornepousse/al_eth-standalone at `2f0c081eb8d9a2ab11489b2d194b8e33c8c429ff`, plus reviewed local lifecycle patches |
| Alpine thermal | https://github.com/delroth/al_thermal-standalone at `b55385eb572fe981c3c495141c09a32715b38153` |
| Userspace | Debian 13 armhf; complete pinned package snapshot/toolchain recipe still required for a release |
| Related research | [TS-431P](https://github.com/mornepousse/liberate_nas_qnap-ts431p), [TS-231P](https://github.com/pushpushhorse/qnap-ts231p-debian), [TS-x32x](https://github.com/delroth/linux-qnap-tsx32x) |

External sources are references, not bundled dependencies or instructions to run their model-specific flash commands. Pin/hash every fetched input in a future clean builder. No claim is made that the current build is bit-for-bit reproducible.

## Included source

`hardware/ts431xeu` contains the board DTS, minimal kernel configuration, patch application script, MCU helpers and hardware service definitions. `docs/hardware-source-files.json` records hashes of this sanitized set. Installer/initramfs and target disk/credential sources are under `installer`; the independent NAS service and console are under `freeqnap`, `web` and `deploy`.

Some filenames, sysfs LED names, locks, service names and kernel guards retain `eyeq` identifiers from the accepted board integration. These identify the tested hardware ABI, not an application dependency. A full rename requires a coordinated kernel/userspace regression; do not simply strip safety checks. Public-facing product pages use FreeQNAP.

The Ethernet patch initializes delayed link work at probe, retains MDIO across close/reopen, fixes cleanup and duplicate freeing, drains MAC/UDMA under the PHY lock before PHY stop, ignores callbacks while down, and resumes the retained PHY before reset/initialization. Preserve ordering and failure propagation. The SATA fix requires `CONFIG_SATA_MOBILE_LPM_POLICY=1` from initial probe; a late userspace override is not equivalent.

Factory identity reads use a checked 204-byte MCU frame. Byte 3 differs between units and is treated as opaque metadata. Framing, checksum and all three valid/distinct/global-unicast MAC fields must pass. No EEPROM programming is performed. PID1, rather than its child helper, performs the final switch-root handoff.

## Build limitations

`installer/build-generic-image.sh` expects a prepared kernel, initramfs/tool tree and Debian filesystem. `build-base-rootfs.sh` packages a prepared Debian tree. Both are development recipes, not complete public clean-build entry points. Missing release work includes toolchain/container pins, signed package acquisition, BusyBox source/config, complete dependency closure and package manifest, all matching modules, clean build verification, image signatures and update/rollback acceptance.

The accepted boot format is a legacy uImage with an embedded uncompressed initramfs and appended DTB; load/entry is `0x00008000`. The vendor loader uses a different RAM staging address. Source and build metadata must distinguish those addresses. Runtime UUIDs/keys must be generated outside the generic image. Maintenance-only artifacts are not release/flash images.

## License boundaries

The root MIT license is proposed for original FreeQNAP code/documentation, subject to owner review. The DTS and Linux-derived patch script retain GPL-2.0-only; the GPL text from the local upstream kernel source is preserved under `licenses/GPL-2.0.txt`. Existing per-file SPDX notices remain authoritative. Out-of-tree drivers, BusyBox, Linux and Debian packages retain their own terms; they are not relicensed by this repository.

No binary release should be distributed until its complete corresponding source, notices, configurations, exact modifications and build instructions are reviewed and available as required. Vendor firmware availability does not authorize redistribution of every proprietary QTS utility or private hardware dump. Do not add those to “help” reproduce a build.


Optional Dynamic DNS uses Debian ddclient; optional Web Push uses Debian python3-cryptography, python3-http-ece and python3-py-vapid. Their upstream/distribution licenses remain authoritative and their package copyright/source records must accompany any future binary release. These dependencies are not bundled or relicensed here. The PWA icon PNGs are code-rendered from the original repository SVG; tools/render-pwa-icons.py records the Pillow development-only rendering step.
