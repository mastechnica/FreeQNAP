> Historical first-unit engineering record. Counts and internal v15 references below refer to that milestone, not the generic second-unit installer. See [current acceptance](ACCEPTANCE.md) for the FreeQNAP state.

# Hardware map and acceptance ledger

Scope: one TS-431XeU-2G-US, AL314, QZ11 REV:1.0, through the installed Linux
6.12.114 v15 milestone on 28 October 2026. “Tested” refers to the stated bench
case, not every operating or fault condition. Two disks were moved between
bays while powered off; four simultaneous disks were not tested.

The [validation plan](VALIDATION-PLAN.md) defines how to test the remaining
features. It does not promote untested functions to passed. Complete
flash/bootloader restoration and external-programmer testing are excluded by
owner decision, so those recovery guarantees remain unavailable.

## Driver and control matrix

| Component | Implementation used | Evidence and remaining limits |
| --- | --- | --- |
| CPU/RAM | ARMv7 Alpine platform, GIC/timer, SMP, LPAE | Four cores and 2 GiB boot Debian. CPU power states, extended stress and larger RAM not accepted. |
| Internal PCI/MSI | Alpine internal host description, generic ECAM/MSI integration | SATA and three Ethernet functions enumerate and operate for the tested cases. General PCI error recovery untested. |
| External PCIe | `pcie-al` enabled for ARM Alpine, board-specific match and AL314 register layout | Onboard `1b6f:7052` xHCI enumerates. Relies on firmware-trained link; full reset/error recovery not accepted. |
| SATA, four bays | AHCI, active SATA link policy from first probe | Both disks/read traffic and mirror boot worked in bays 1/2 and 3/4. Six v15 warm boots passed. Hotplug, four-disk load, degraded/rebuild, power interruption and link power saving not accepted. |
| Two RJ45 ports | Pinned and patched `al_eth`, upstream Motorcomm YT8531 PHY | 100 Mbps direct link and 1 Gbps LAN tested. 24 v14 plus four v15 administrative restart cases passed. Broader speed/MTU/offload/fault matrix open. |
| SFP+ | `al_eth` 10G/SerDes path enumerates as an interface | No transceiver/DAC, 10GbE traffic, hotplug or indication test. Enumeration is not 10GbE acceptance. |
| Four rear USB ports | PCI xHCI, USB storage | Same USB2 flash drive checksum-read successfully in each port. No SuperSpeed transfer, power-limit or USB fault matrix. |
| Debug console | 8250/of_serial, UART0 (`ttyS0`) | Bidirectional console/U-Boot at 115200 8N1. Oriented physical pinout and measured voltage not recorded for publication. |
| Enclosure MCU | Userspace SPEC3 owner on UART1 (`ttyS1`) | Bounded checked exchanges, fan mode/tach, LED/button/buzzer/identity operations. MCU firmware retained. Not validated with the upstream QNAP MCU driver. |
| Cooling | Early small native helper plus systemd full-speed request | Exact ACK/mode readback and three visibly spinning fans. Fixed 100% bench policy only; adaptive control, fan stall and host-crash safety unaccepted. |
| CPU temperature | Pinned `al_thermal` plus Linux thermal framework | Readings available under custom kernel. Independent calibration, stale-sensor response and real critical-trip shutdown not tested. |
| Enclosure temperature | MCU NTC2 query | Raw decoding available, explicitly uncalibrated. Sensor position/correction not independently established. |
| GPIO | Six PL061 banks | LED outputs and reset input work. Do not generalize unused GPIOs into safe probe targets. |
| Reset button | `gpio-keys`, bank 4 offset 0, active-low | Passive press/release then assigned orderly reboot passed. Local policy does not erase data; long hardware holds not characterized. |
| Power button | MCU state query, bounded polling, deliberate local policy | Approximately four-second hold/release produced orderly shutdown and physically confirmed chassis off. Longer force-off behavior not characterized. |
| Status indicator | MCU control with readback | Red, blinking green, solid green physically confirmed. Other protocol modes are not all physically accepted. |
| Red drive indicators | MCU per-bay error LED commands | All four individually observed; original state restored after tests. This does not inject or validate real disk-fault detection. |
| Green drive indicators | MCU global enable plus active-low GPIO LEDs and per-port disk-I/O policy | Presence/activity physically confirmed in all four populated bays. Empty bays dark. Defined software policy, not a native AHCI hardware activity trigger. |
| Sound | MCU buzzer | One bounded short beep physically heard. No speech/audio-card support established. Alarm duration/muting/failure behavior not accepted. |
| RTC | DesignWare I2C plus RX8010 at address `0x32` | Clock reads work. Alarm IRQ, wake and power-loss retention not accepted. |
| Restart/watchdog | SP805 driver restart path | Repeated Linux restarts and three attended 10-second RAM expiry resets passed. Watchdog remains unarmed; unattended ownership/policy and broader failure modes remain unaccepted. |
| Chassis poweroff | Guarded native late-shutdown MCU hook | Filesystems shut down before power removal; fans/indicators physically off. General emergency/overtemperature poweroff not accepted. |
| NAND | Vendor U-Boot ECC path for first-slot programming | Full 32 MiB readback matched. Modern Linux MTD disabled. Bad-block growth, interrupted-write recovery, bank fallback and full-chip restore untested. |
| SPI NOR | Read-only U-Boot comparison | Full 2 MiB unchanged across tested NAND updates. No bootloader/environment writes; complete physical restore untested. |
| Factory identity | Read-only MCU blocks, MACs mapped to PCI functions | Unit's own MACs restored early; no EEPROM rewrite. Other VPD/SPD endpoints not validated. |
| SoC DMA/crypto accelerators | Stock drivers catalogued; no accepted modern offload port | Normal storage/network operation does not prove separate RAID/crypto hardware acceleration. Software functionality must not be labeled offloaded. |
| OS storage/services | md RAID1, ext4, systemd, SSH | UUID-selected mirrored root and durable test markers across six warm reboots. Full backup/restore and degraded-service policy remain separate tests. |
| Optional containers | ARM-native runtime, overlay2, cgroupv2 | Native ARM execution, persistent bind write and LAN-reachable bridged HTTP passed. This is a capability smoke test, not application compatibility or a security audit. |

## MCU protocol and ownership

The stock model configuration identified **SPEC3 on UART1**, not an I2C MCU.
Some stock DT nodes suggested other devices; node names alone did not establish
the active enclosure-control transport. Debug UART0 and MCU UART1 must never
be treated as interchangeable consoles.

The implementation uses a private shared process lock plus exclusive TTY access
for each complete operation. It checks board identity before control, configures
115200 8N1, drains only bounded stale input, writes complete frames, applies a
deadline, and rejects unexpected reply sizes/prefixes/checksums. No raw arbitrary
command interface or EEPROM-write interface is exposed by the intended helper.

Observed SPEC3 framing appends an XOR checksum over the ASCII payload. For
example, the short ACK is `@0` followed by byte `0x70`; that is not a newline.
These strings are protocol notes, **not shell commands**. Sending the wrong MCU
command can affect cooling or power. A public helper needs the same guards and
exclusive ownership before any of the operations below are exposed.

| Operation | Observed payload / validation |
| --- | --- |
| Request global full fan mode | `@F7` plus checksum `0x31`; exact ACK, then `@FS` mode readback |
| Fan counters | `@FA`, `@FB`, `@FC`; strict response decoding |
| CPU temperature | Separate kernel thermal driver; not a fan-command side effect |
| NTC2 temperature | `@T3`; decoded byte minus 128, explicitly uncalibrated |
| Status LED read | `@CS`; control payload `@C` plus validated mode, then readback |
| Green drive path enable | `@O61`; ACK observed; no gate-state query established |
| Red drive LED | `@R0` through `@R3` with mode; query/readback and restoration |
| Power-button state | `@CV`; validate state byte before acting |
| Short buzzer | `@C2`; ACK plus human observation |
| Final chassis power removal | `@C0` plus checksum `0x33`; late shutdown only |

Fan counter conversion follows the stock convention **counter × 30** for a
vendor RPM value. It was not calibrated with an optical tachometer. Three
nonzero counters and physical fan rotation are stronger evidence than either
alone; neither proves safe airflow under load or a safe failure response.

The stock configuration contained temperature adjustments and shutdown-policy
values. They were useful reverse-engineering clues, not validated hardware
limits. The new DTS has an 80°C bench critical trip, but actual trip behavior
was not exercised. A configured threshold is not proof of thermal protection.

## Green LEDs: two prerequisites and a physical test

Early tests showed GPIO changes in software while the owner saw no light.
The vendor implementation revealed a necessary **MCU global enable**. After
that enable, occupied bays lit, but the initial GPIO polarity was still wrong:
idle looked dark with brief pulses. Physical observation established active-low
outputs. Correcting the LED-class polarity produced steady idle presence with
activity flicker.

| Bay | PL061 bank | Bank-local offset | Physical polarity |
| --- | --- | --- | --- |
| 1 | 3 | 0 | Active-low |
| 2 | 3 | 1 | Active-low |
| 3 | 4 | 4 | Active-low |
| 4 | 4 | 5 | Active-low |

Do not mistake these bank-local offsets for stable global GPIO numbers. The
software policy maps disks through AHCI/ATA ports, not mutable `/dev/sdX` names.
It shows occupied bays green, empty bays dark, and uses changes in actual block
I/O counters to generate activity flicker. A successful brightness readback
does not establish a lit lamp.

Tests first confirmed bays 1/2, then shut down the chassis, moved the complete
trays to 3/4 and repeated isolated read traffic and mirrored-root boot. The
trays were returned while off. Empty-bay darkness alone could not validate bays
3/4; populating and observing them resolved that uncertainty.

## Buttons and shutdown sequencing

The stock reset mapping `I20:P` was **hexadecimal GPIO line `0x20`**, bank 4
offset 0, active-low. Treating it as decimal line 20 would have selected the
wrong input. The modern device tree exposes it through `gpio-keys` with a
non-power key code, so an early diagnostic press cannot accidentally invoke
system login-manager shutdown policy.

Button handling began in observe-only mode with durable event logs. The final
policy acts on reset release after debounce and maps a short reset press to
normal reboot. Power state is polled from the MCU, requiring a known released
state before arming. Neither policy resets credentials or reformats storage.
The human test used about a four-second power hold and prompt release; do not
recommend an arbitrarily longer hold because hardware may force power off.

Orderly chassis shutdown is a separate operation from Linux halting. The final
hook checks the board and shutdown context, requires the root filesystem to be
read-only, takes the MCU lock, syncs, then sends the chassis-off frame. It must
run after ordinary services and filesystem shutdown, never as an early
power-button shortcut. Physical fans/indicators off plus the shutdown trace
established the result; an ACK or closed SSH connection alone would not.

## Reproduce acceptance, not just configuration

For a second unit, record its board revision, exact kernel/source manifest and
the result of each test without publishing unique identities. At minimum:

1. Observe all fans through cold startup, U-Boot, RAM rescue and installed OS.
   Verify full-speed command and mode readback before longer tests.
2. Record thermal/tach data with timestamps and failures. Do not stop fans to
   identify channels or overheat the machine to test a trip.
3. Isolate each populated bay's read traffic, check data hashes and physical
   LEDs, and validate shutdown before tray moves.
4. Restart each RJ45 under traffic and check fresh sessions and fresh hashed
   transfers. Treat clean UP state or cached data as insufficient evidence.
5. Test both warm and physical cold startup with the boot server unavailable.
   Check that both mirror members are present at **initial** assembly, without
   a repair command silently masking missing-disk startup.
6. Verify actual reset reboot and orderly power-button shutdown with serial
   traces and physical observation. Avoid uncharacterized long holds.
7. Keep separate cases for unaccepted failures: fan/controller loss, stale
   temperature, disk disappearance/rebuild, watchdog expiry, interrupted flash,
   USB/SFP faults, wake and AC return. Do not mark them passed from normal boot.

## Known unsafe diagnostic shortcuts

- **U-Boot `scsi reset` data-aborted.** Do not use it as a recovery prerequisite.
- **SGPO address `0xfd8b4000` is not an approved probe.** A wrong-generation
  layout caused an external abort even on a read. Do not load that diagnostic
  module, repeat its read, or guess neighboring reset registers.
- Do not open MCU UART1 alongside QTS HAL or another control owner.
- Do not write MCU EEPROM, arbitrary I2C registers or boot environment to
  suppress baseline warnings. Preserve evidence and identify the real cause.
- Fixed full-speed cooling is an accepted bench setting. An unattended,
  adaptive, fault-safe enclosure controller is still work to do.
