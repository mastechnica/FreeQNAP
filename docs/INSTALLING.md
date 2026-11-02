# Installing Debian on a TS-431XeU

This is the tested sequence expressed as reusable stages. It is a development walkthrough, not an invitation to run incomplete destructive commands. No public image is available in this source review. The final guided installer must generate and validate the session/proof records itself; the current tools must not be bypassed with hand-written “passed” JSON.

## Requirements

Use a verified TS-431XeU/AL314, disposable disks, a trusted wired network, a Python 3 host, and a working 115200 8N1 serial console. A dedicated Mac USB Ethernet adapter is **optional**. An ordinary wired LAN can carry the boot transfer. The tools never reconfigure the host network automatically.

Inspect board revision and UART voltage/pinout before connecting. Debug UART0 is not the enclosure MCU's UART1. Connect the measured ground and crossed RX/TX only. No adapter VCC connection is part of this process. A safe oriented pinout still needs to be added to this project; see [hardware](HARDWARE.md).

## 1. Capture the original boot

Choose a private session directory outside shared/synced folders. Start this with the NAS off, substituting the actual UART device:

```sh
python3 installer/capture.py --port /dev/YOUR_UART --directory /private/session/serial --stop-autoboot
```

Watch from another terminal:

```sh
tail -n +1 -F /private/session/serial/console.log
```

Power on. The capture process exclusively owns the UART and interrupts the explicit U-Boot countdown. Do not run another serial terminal against that device. Attach and inspect once stopped:

```sh
python3 installer/freeqnap.py attach --session /private/session/install --capture /private/session/serial --model TS-431XeU
python3 installer/freeqnap.py inspect --session /private/session/install
```

Inspection reads bootloader version/environment, NAND geometry/bad-block report, transfer capability and temperature. Model selection is an operator attestation, with observed family/geometry checks; it is not an independent PCB identification algorithm.

After any interruption, inspect the original journal before doing anything else:

```sh
python3 installer/freeqnap.py status --session /private/session/install
```

An incomplete recorded disk/flash write requires reconciliation. Do not rerun the
write stage, create a replacement session or edit success records. This status
command is read-only and does not independently verify the target hardware.

## 2. Obtain an audited release

A release needs the normal uImage, manifest and matching modules/root filesystem, all checksum-pinned, with complete corresponding source. Development build scripts currently depend on prepared build trees. They are **not a complete clean public build recipe**. Do not download a random related-model image or use a first-unit UUID-specific image.

A distributable generic image must contain no installation UUID, factory MAC, SSH host key, administrator key, password, static LAN address or application state. The initramfs reads a restricted per-installation record from the mirrored boot partitions, checks the factory identity, and requires matching records and a healthy OS mirror.

## 3. Transfer and boot in RAM

On a trusted network choose the host address and an unused temporary NAS address on that subnet. Serve only the reviewed artifact:

```sh
sudo python3 installer/transfer.py --release /path/to/release --bind HOST_IP --client TEMPORARY_NAS_IP --seconds 7200
```

Port 69 requires administrative access on the tested Mac. The helper drops privileges immediately after binding. This vendor U-Boot ignored the tested alternate-port setting, so a high port is not a validated substitute. A missing host address is reported/waited for; the helper does not assign one.

`freeqnap.py load-ram` takes the session, release, server/target IPs and explicitly selected `al_eth1` or `al_eth3`. It validates the image, transfer byte count, RAM CRC and uImage checksums. `boot-ram` repeats the integrity/temperature gate and performs the demonstrated SATA setup sequence before booting. These steps use temporary environment values; they do not save U-Boot environment or program flash.

Do not use vendor `scsi scan` or `ext4load` as a recovery shortcut. The tested `scsi scan` attempt faulted and reset this U-Boot. Disk-loader recovery remains unaccepted and the controller blocks that path.

## 4. Inspect hardware and make original-flash backups

Verify factory identity restoration, acknowledged full cooling, three visibly spinning fans, CPU temperature, all intended disks, and the exact network port. Stop on missing or conflicting evidence.

The explicit `flash-backup.py` stage reads both original 32 MiB kernel slots and the complete 2 MiB SPI twice. The optional transfer receiver accepts only three exact size-limited backup names, never arbitrary uploads or overwrite. Local files and receiver receipts must match independent UART-observed CRCs. Empty/partial uploads are failures, not backups. Store these privately; they contain device material and must not enter this repository.

## 5. Review and install the OS disks

The disk installer accepts a fresh identity-bound plan, including serial, WWN, capacity, SATA location and the exact installation ID. It checks active mounts, holders, arrays, swap, temperatures and artifact hashes again immediately before writes. The operator must explicitly confirm erasure of the selected disks.

New installer source reserves a separate 512 MiB boot partition and a 128 GiB ext4 OS RAID1 member on each of two internal disks (at least 130 GiB each). Older plans lacking the explicit 128 GiB geometry are refused; regenerate and review the disk plan rather than changing its interpretation. Previously built releases may still contain the historical 8 GiB installer and must be rebuilt/audited before claiming this default. The second unit was separately expanded to 128 GiB; see the dated OS-expansion validation. Other disks and remaining regions are not automatically converted into data storage. Removing old partition metadata is not a secure wipe of every old data sector.

This stage is currently exposed as `installer/target/install-disks.py` with separate orchestration, not one complete guided command. A failed destructive stage requires inspection and reconciliation; do not blindly rerun it or invent a completed stage record.

Root password options are private installer entry, first serial login, or deferred key-only access. No shared/default root password exists. Deferral requires the supplied administrator SSH key and leaves the password locked. It can be set later with `passwd`. Setting a root password does not enable password-based SSH root login.

## 6. Prove a normal disk-root boot before flash changes

Load the normal checked image into RAM and boot the installed mirror. Verify root identity, all disks, synchronized RAID, cooling, thermal sensors, factory networking, services and bidirectional transfers after interface restarts. No maintenance shell or debug arguments may be active.

The first image exposed unreadable networkd configuration/machine-ID files. Both must be mode 0644, and `audit-base.py` checks the exported base. The corrected installed system obtained ordinary DHCP. The installer does not install a persistent direct-cable IP profile.

The appended device tree controls the tested Linux command line. Merely changing temporary U-Boot `bootargs` did not enable maintenance access. Checked recovery uses a separate maintenance-only DTB overlay with identical kernel/hardware properties; normal installation rejects that artifact. See [sources](SOURCES.md).

## 7. Commit only the first NAND kernel slot

The separate `flash-install.py` tools provide `plan`, `preflight` and `program`. They require complete original backups, recent acceptance of the exact normal image and a fresh same-boot preflight. Explicit installation-ID confirmation is mandatory. The supported operation touches only the first 32 MiB NAND slot, compares the complete padded slot afterward, and rechecks the preserved second slot, SPI and saved boot command.

No SPI/bootloader/environment write is part of this procedure. The programmer does not reset/boot automatically. Interrupted-flash recovery, automatic bank fallback and full physical restoration are unaccepted. An intact second slot is not proof that the bootloader can select it automatically.

## 8. Accept autonomous operation

Disarm countdown interception for this test. Pause the transfer server and boot without intervention. Prove the expected image, healthy OS mirror, services, networking and cooling again. Two such software restarts and one physical cold start of the final installed image passed on the second unit. The cold start also exposed a brief mirror recovery after shutdown; see [the follow-up](SHUTDOWN-FOLLOWUP.md). Do not claim resync-free shutdown until that issue is resolved and retested.

The next public installer should combine these stages into one resumable wizard, generate proof records from actual observations, stop before destructive confirmation, and produce a redacted acceptance report. Until then, these components are maintainers' development tools, not an unattended consumer installer.

### Private RAM diagnostic images

The transfer helper can serve a deliberately non-installable image with `--allow-ram-only`. Its manifest must explicitly contain `ram_only: true` and `flash_allowed: false`. An optional `--additional-ram-release` serves a second same-kernel RAM-only image under the fixed alias `experiment.uImage`. This diagnostic mode rejects backup-upload arguments. Both manifests and cached boot bytes remain checksum-pinned. Ordinary image verification and the flash installer reject these manifests even when a RAM acceptance record exists. A private image containing a live device tree is not a redistributable release. This switch does not waive model, geometry, thermal, complete-transfer or target-side CRC checks.
