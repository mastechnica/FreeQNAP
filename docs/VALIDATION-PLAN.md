> Historical first-unit engineering record. Counts and internal v15 references below refer to that milestone, not the generic second-unit installer. See [current acceptance](ACCEPTANCE.md) for the FreeQNAP state.

# Plan to complete hardware acceptance

This is a **test plan**, not completed acceptance. It extends the
[v15 hardware ledger](HARDWARE.md) while preserving its existing limitations.
Run isolated tests on the spare before service-impacting tests. The second unit
must retain its current role until it has its own approved maintenance window.

**Full-chip/bootloader flash restoration and external-programmer testing are
excluded by owner decision.** They remain unvalidated, with no guarantee of
recovery from damaged SPI, bootloader or environment. Do not buy programming
equipment, erase preserved loader regions or interrupt flash writes for this
plan. Preserve the demonstrated UART/TFTP RAM-rescue path, private backups,
known-good artifacts and kernel-slot readback evidence.

## Status and evidence rules

| Status | Meaning |
| --- | --- |
| Untested | No adequate physical test, including when a device merely enumerates. |
| Blocked | A named equipment, capability or recovery prerequisite is missing. |
| Failed | A defined case ran and failed; preserve its evidence. |
| Unsupported in this implementation | Source/board investigation establishes that the current implementation cannot provide the function. Explain why. |
| Passed, bounded scope | The named case met its criteria on the named unit/image. Other cases remain untested. |
| Excluded | Deliberately outside this plan. This does not imply support or acceptance. |

Missing wake-related sysfs attributes do not prove that the hardware cannot
wake. A USB bus advertising 5000 Mbps does not prove a SuperSpeed peripheral
transfer. A watchdog node does not prove an expiration reset. A preserved
second kernel slot does not prove automatic fallback.

For each case retain privately: unit/board identity, kernel/source manifest,
pre/post configuration, UTC and monotonic times, serial transcript, kernel log,
negotiated speed, test parameters, hashes, temperatures/fan counters, array state,
physical observation and actual recovery. Publish redacted case results with
no real addresses, serials, MACs, UUIDs or credentials. Retain failures as well
as passes. Changes to relevant sources/configuration require regression tests.

## Phase 0 — Baseline and equipment preflight

**Equipment:** verified UART wiring, stable local wired management, off-device
backups, checksum-pinned rescue/TFTP artifacts, and a person watching the NAS.
A USB3 flash drive and disposable SATA disk are available. A 10G-capable switch
is available; exact port type, compatible DAC/module/cable and distance must
still be established before promising an SFP+ test.

Safe reads can establish image identity, fan-mode ACK/readback and all three
tach counters, CPU temperature, RTC, interfaces, USB topology, watchdog settings
and array health. USB/SATA preflight should identify devices without mounting
unknown filesystems or writing anything:

- Confirm the USB3 drive and cable negotiate SuperSpeed on another host first;
  record its private identity and capacity before attaching it to the spare.
- Check the disposable SATA disk's identity, capacity, health and existing
  partition/mount state. “Disposable” still requires selecting the correct
  physical disk. Do not use mutable `/dev/sdX` names as the only selector.
- Confirm the switch actually exposes a compatible SFP+ path; a 10G copper
  RJ45 port alone does not supply the required module/cable combination.
- Inventory whether candidate physical disks contain both OS and data-array
  members. Removing one drive can degrade multiple arrays.

**Storage gate:** while any array is initially synchronizing, rebuilding,
checking or recovering, defer disk removal, reboot, forced reset and power
interruption. Wait for actual completion and healthy idle membership, not an
estimated finish time. Keep safe preflight distinct from tests that add heavy
I/O or threaten current storage. Service-impacting tests need stopped services,
verified off-device backups and a scheduled window.

After that gate, verify UART input/output and a known-good RAM rescue boot
without flash changes. Confirm full cooling and Linux storage/network access.
Then complete the outstanding installed-v15 **physical cold-start test** with
TFTP stopped: three cold starts and three warm boots, both OS mirror members
at initial assembly, no hidden recovery/rejoin, durable root markers retained,
fresh hashed reads and working fans/controls/network.

**Pass:** exact current image starts independently and known-good RAM rescue
is demonstrated. **Stop:** unknown identity/image, unverified backup, active
array work, missing cooling evidence, ATA errors or failure to regain baseline.

## Phase 1 — USB SuperSpeed and SFP+ traffic

Keep fixed full-speed cooling and independent serial/RJ45 management.

### USB SuperSpeed

Use the known-good USB3 device, compatible cable and a confirmed disposable
external filesystem. For each of four rear ports, record topology and require
actual **5000 Mbps** peripheral negotiation for the intended SuperSpeed case.
Read a known dataset and compare hashes. For allowed writes, use a uniquely
named scratch file on the positively identified external mount; flush, unmount
cleanly, reconnect and verify persisted bytes. Do not raw-write a selected disk.

Run 30 minutes of bounded traffic per port and three safe unmount/reconnect
cycles. Record throughput, CPU use, temperature and USB/kernel errors.
**Pass:** SuperSpeed negotiation and correct persisted data on every tested
port, no unexplained resets/stalls/I/O errors. Bus rate is not a throughput
promise. **Stop/rollback:** incorrect disk/mount selection, escalating errors or
cooling fault; safely unmount and return to the known-good configuration.
A 480 Mbps attachment remains a USB2 test regardless of connector color.

**Additional USB cases:** repeat simultaneous bounded transfers through multiple
ports, checking controller errors and hashes. Bus-power limits require a known
load, suitable USB power measurement and the documented per-port/current budget;
do not infer them from a working flash drive or deliberately short/overload a
port. For disconnect/error recovery, begin with read-only scratch-device I/O and
an isolated mount, verify prompt error reporting and successful re-enumeration,
then remount and hash known files. Unexpected unplug during writes is a separate
disposable-filesystem corruption/recovery case; do not claim preservation of
unflushed writes. If power/fault equipment is unavailable, mark those cases
blocked while retaining ordinary transfer passes.

### SFP+ / 10GbE

For a short connection, a passive SFP+ DAC includes both plugs, avoiding separate
optical modules. Obtain explicit compatibility for both endpoints. QNAP lists
`CAB-DAC15M-SFPP` and `CAB-DAC30M-SFPP` among the
[TS-431XeU accessories](https://www.qnap.com/en-uk/product/ts-431xeu).
As one switch example, the Extreme X460-G2 front-port matrix accepts its
1 m/3 m DACs (`10304`/`10305`) but excludes its 5 m/10 m DACs on those ports;
see the [manufacturer's matrix, page 14](https://extr-p-001.sitecorecontenthub.cloud/api/public/content/0d57eced308e4a24986044df40bb15e0?v=87e0fa92).
Two separate compatibility lists do not establish that an arbitrary cable is
qualified at both ends. Specify both models to the cable supplier. A 10GbE
switch establishes a possible link path; a 10GbE traffic endpoint is also
needed to measure throughput beyond a slower management computer's link.

Use a verified 10GbE peer/switch and compatible DAC or matched modules/fiber.
Confirm electrical/module compatibility before connecting it. Begin with MTU
1500 and leave RJ45 management intact. Record module identity, link/SerDes logs,
negotiation, peer settings and error counters.

Transfer fresh hashed files both ways; then run 30 minutes each direction and
30 minutes bidirectionally. Record throughput, CPU, temperature and packet/error
counters. Repeat ten cable/link reconnects, including two during bounded scratch
traffic. Module hotplug and jumbo frames are separate cases after ordinary
link/traffic acceptance and only where supported.

**Pass:** independently confirmed 10GbE link, correct bidirectional bytes,
fresh reconnections and no DMA faults/corruption or unexplained loss. Define
any workload throughput requirement before testing; negotiated link speed
does not promise line-rate transfer on this CPU. **Stop/rollback:** driver crash,
unsupported module, recurring errors or lost independent management; remove
the test link and recover through RJ45/serial. If source review finds a missing
driver path, label the current implementation unsupported and plan a source
change. Do not guess SerDes registers.

### RJ45 speed, MTU, offload and mixed traffic

Extend the existing restart evidence with known-good peers/cables at advertised
10/100/1000 modes, one port at a time. A peer that cannot provide a mode blocks
that case; avoid forcing unsupported speed/duplex combinations. Record actual
negotiation, carrier changes, fresh hashed transfers and PHY/MAC counters.
Use MTU 1500 as the baseline. Test any supported jumbo MTU only with matching
peer/path configuration; compare boundary packet sizes and restore the baseline.

Record advertised versus active checksum/segmentation offloads. Compare an
independent receiver's payload hashes with supported offloads enabled/disabled,
including small control packets, large transfers, concurrent bidirectional TCP
and bounded UDP. Receiver-side validation matters because local captures can
show uncomputed transmit checksums before offload. Run 30 minutes per adopted
configuration and a final simultaneous two-RJ45/mixed-storage case. Repeat cable
loss, peer restart and administrative restart under bounded traffic. Distinguish
expected loss on deliberately interrupted traffic from unexplained corruption,
DMA timeouts, queue lockups or failure to accept fresh sessions.

**Pass:** correct data and fresh recovery at each tested mode/MTU/offload setting,
no unexplained hardware errors, and recorded throughput/CPU/loss limits. Invalid
MTU or unavailable peer modes do not silently become passes. **Stop/rollback:**
unexpected faults or loss of independent management; restore MTU/offload/link
baseline through serial and retain the failing configuration/logs.

## Phase 1B — CPU/RAM, RTC and remaining physical indications

### Bounded CPU/RAM stress

After array work has finished, keep fixed full-speed cooling, serial capture
and independent temperature observation. Check detected memory/core count and
choose bench temperature/available-memory limits before loading the system.
Begin with one core for ten minutes, then four cores for 30 minutes using
known-answer compute checks. Add a bounded memory-pattern check using no more
than 25% of RAM while retaining at least 512 MiB available; combine CPU/memory
load for another 30 minutes only if temperatures have stabilized. Record clock,
temperature, fan counters, kernel faults, OOM events and verification results.

**Pass:** no calculation/memory mismatches, crashes, OOM or unexplained kernel
errors, stable observed cooling and correct post-test I/O/clock operation.
**Stop/rollback:** threshold exceedance, temperature/tach loss or first mismatch;
stop workloads and restore idle/full-speed baseline. This is bounded stress,
not proof of every RAM cell, CPU power state, upgraded RAM module or offload.

### RTC time, retention, interrupt and wake are separate cases

Use a trusted independent clock and document initial offset and measurement
resolution. In a maintenance window, synchronize through the normal RTC/clock
interfaces only if needed; preserve prior settings and avoid stepping time
while services rely on event timestamps. Check monotonic progression and repeat
reads over one hour. Then compare retention after five-minute and thirty-minute
power-off intervals, followed by a 24-hour drift measurement if feasible.
Adopt an explicit accuracy tolerance from the RTC specification and measurement
resolution before testing; record measured drift, not an invented universal
accuracy rating.

Separately investigate whether the RTC alarm IRQ is physically wired and
described correctly. If supported, schedule a short alarm while Linux is
running, observe the attributable interrupt/event, and cancel/clear it. An
alarm register accepting a time is not proof of an IRQ. Shutdown wake is tested
later in Phase 5; a running-kernel alarm interrupt does not prove wake or
power-loss retention. Do not invent an IRQ assignment or scan registers.

**Pass:** each named case meets its declared timing tolerance and evidence.
**Stop/rollback:** clock discontinuity, unsupported alarm path, interrupt storm
or stale alarm; cancel supported test alarms, restore settings and mark only
the affected function failed/unsupported/blocked. Retain ordinary RTC-read
acceptance separately.

### Remaining LED and buzzer indications

Catalogue protocol modes against actual fitted indicators. Under an operator's
observation, test each still-unobserved material status color/blink mode, USB
indicator if a physical lamp exists, RJ45 link/activity/speed indications and
SFP+ link/activity only with a working 10G path. Give each transition a timestamp
and enough dwell to see it; restore prior state afterward. An MCU “USB LED”
command does not establish that the board actually has that lamp.

Existing short-beep acceptance remains valid; other tones/durations and mute
policy are separate bounded audible tests, with the owner present. Do not emit
unsolicited warning tones. **Pass:** named physical indicator/behavior observed,
restoration confirmed and no side effects. **Stop:** unexpected power/fan
behavior or inability to restore a known state. Unsupported/unfitted indicators
are documented explicitly rather than simulated into a hardware pass.

## Phase 2 — Adaptive cooling and safe failure response

**Equipment:** independent temperature/airflow observation, guarded workload,
serial capture, an operator able to stop promptly, and injectable sensor/control
test interfaces. An optical tachometer can calibrate vendor RPM conversion.

Identify physical fan/channel correspondence without stopping a fan. Compare
sensor readings with independent measurements and the stock reference where
available. Keep uncalibrated NTC data and vendor counter-derived RPM labeled.
Define minimum speed, units/calibration, hysteresis, ramps, freshness bounds,
fault reporting and explicit full-speed fallback. Choose conservative bench
temperature limits before load; they are not newly inferred silicon ratings.

First test off-device with simulated stale/missing/malformed/out-of-range input,
blocked UART, lock contention, daemon termination and restart. Require an explicit
fault and full-speed request within **two policy intervals, capped at five
seconds**, after a detected bad condition. Failed commands must not become
healthy status. Retain the independent fixed-full-speed helper.

Then validate safe nonzero speed steps and actual tach response on the spare,
followed by gradual bounded load. Repeat injected software failures individually
under observation. Verify startup, shutdown, daemon kill and network loss;
cooling must not depend on network/UI availability. Inject missing tach data
before considering any physical fault test. Do not unplug or stall fans.

**Pass:** calibrated inputs, temperatures within declared bench limits, no fan
stall, stable hysteresis, honest fault/freshness reporting and observed fallback.
An ACKed last command does not prove safety after MCU loss or host hard hang.
If independent hardware fallback is unproven, retain that gap; detecting failed
UART communication is not equivalent to controlling fans through it.
**Stop/rollback:** airflow loss, rising temperature beyond limits, zero/implausible
tach or unavailable sensors. Restore fixed full speed if possible; otherwise
use the prepared shutdown/operator intervention. No arbitrary MCU commands.
Replace the full-speed default only after policy and failure limits pass.

## Phase 3 — Watchdog expiry in disposable RAM rescue

Use serial capture, fixed full cooling, stable power and RAM-only rescue.
Persistent filesystems must be unmounted and arrays idle; stop services first.
Inspect watchdog ownership/settings without accidentally opening or arming it.
The observed baseline was SP805 inactive, `nowayout=0`, timeout 10 seconds;
re-read the actual values. Only one watchdog owner is permitted.

Prove healthy disarm first, then intentionally stop feeding it in RAM. Capture
actual expiration/reset, reset cause where available, boot and cooling. Repeat
three times; separately verify orderly reboot/poweroff does not cause late
unintended resets.

**Pass:** three real expiration resets within documented hardware tolerance,
return to baseline and no unintended armed watchdog. Missing-heartbeat logs
alone do not count. **Stop/rollback:** reset loop, no bounded reset, ambiguous
ownership or cooling loss; recover through serial/manual power control and
restore an unarmed baseline. Disk-OS watchdog adoption remains a later policy
decision; a live keepalive process alone is not proof of service health.

## Phase 4 — Disposable storage failure and rebuild

The owner has explicitly designated the two installed mirror disks as
disposable. They currently carry the OS and any data mirror, so removal affects
more than a scratch disk. A third disposable disk is available but its capacity
must be measured. Do not require two additional disks unnecessarily: use a
checkpointed fail/reintegrate sequence on the existing mirrors after initial
synchronization completes, with services stopped, backups verified and RAM/
network rescue ready. First perform standalone scratch read/write/health tests
on the spare and prove off-device restoration of the OS/configuration/test data.

A replacement for a roughly 9 TiB data member must provide enough actual
sectors for that member's partition, not merely have a similar marketing size.
A smaller spare may validate a small scratch mirror or an explicitly isolated
OS-member case, but cannot replace the full data member. Record this capacity
prerequisite before selecting the rebuild case. Reusing an existing member is
also possible; record whether it performs bitmap catch-up or a full rebuild,
and do not call the former a tested blank replacement/full rebuild.

Create a deterministic hashed dataset with durable sequence markers. Validate
clean shutdown and assembly. Exercise one logical member failure, degraded
reads/writes, restart with one member absent, replacement, full rebuild and
post-rebuild scrub/hash comparison. Repeat with the other member absent. Begin
with powered-off physical removal; live hotplug is a separate later case after
backplane/driver support and scratch recovery are established. Faults during
rebuild, near-full operation and power loss follow basic acceptance, not the
first degraded boot. Change one member/array at a time wherever possible and
checkpoint healthy membership plus off-device evidence before each next fault.
When an entire physical drive is absent, record the expected degraded state of
every affected array. Measure rebuild time and load.

**Pass:** acknowledged durable writes survive; intended authoritative member
stays authoritative; faults are visible; replacement fully rebuilds/checks clean;
no corruption, unrelated I/O halt or wrong-array selection. A returning stale
member must not overwrite newer data. Record manual repair separately from
automatic assembly. Never force ambiguous members together to claim success.
Validate the documented degraded-root policy independently from data-array
availability. Repeat opposite-member testing only after every affected array
has fully returned to healthy idle state and the data hashes/checkpoints pass.

**Stop/rollback:** unexpected second failure, identity mismatch, corruption,
failed rebuild or array ambiguity. Stop new writes, preserve members/metadata,
and restore verified copies if needed. Do not hide failures behind repair/rejoin.
Return every affected installed array to the checkpointed healthy state before
resuming services or moving to another test. A plan to restore from backup is
not permission to lose track of which member is authoritative.

### Four-disk simultaneous load is a separate equipment gate

Earlier bay tests moved two disks between four positions. The present two
installed disks plus one spare provide only three disks. **Four simultaneous
populated-bay acceptance needs a fourth suitable disposable disk**, adequate
power/cooling and a reviewed layout; it cannot be inferred from four individual
bay passes. With that prerequisite met, run hashed concurrent reads and bounded
scratch writes across all four bays for at least one hour, observing per-port
errors, SMART changes, power/cooling and physical activity LEDs. Keep OS-root
availability independent where practical. Require correct bytes, no link resets/
unexplained I/O errors and retained thermal margins; otherwise stop load and
return to the healthy checkpoint. Until equipment is available, mark this
particular case blocked, not the entire two-disk validation effort.

## Phase 5 — Wake and AC return

Use an independent LAN peer, operator, serial capture and safe external switched
power/UPS. Never open or modify the PSU. Services must be quiesced, arrays idle,
and backups verified.

Investigate documented PHY/board/MCU and driver support for Wake-on-LAN, RTC
wake and AC-return policy. Read capability/source paths first; neither missing
sysfs attributes nor sibling behavior settles support. Use only documented,
supported settings, recording/restoring prior values. No arbitrary power-register
or MCU EEPROM writes.

Test each supported wake source separately from orderly poweroff, three times,
with a negative control where no packet/alarm is sent. Record standby link,
attributable wake source, elapsed time and actual boot. Suspend/resume is separate.
For AC return, first remove/restore external AC after clean shutdown and observe
the real policy. Abrupt-loss characterization can later run in RAM without
mounted disks. Disk-OS power loss belongs after storage fault testing and a
separate agreed recovery/data-loss test definition.

**Pass:** requested documented behavior repeats, wake source is attributable,
no spontaneous negative-control boot, and baseline fans/storage/network return.
**Stop/rollback:** boot loop, unexplained source or unsupported setting; restore
supported prior settings and normal manual startup. Report missing implementation
support explicitly rather than inventing an EEPROM workaround.

## Phase 6 — Two-unit reproduction and bounded completion

The separate SoC DMA/RAID and crypto acceleration paths are **implementation
gaps**, requiring a separately reviewed source port and known-answer/coherency/
stress testing if desired. Native software RAID, software hashes/AES and working
Ethernet DMA do not validate those distinct accelerators. Keep them unsupported
in the current implementation rather than treating software test success as
offload acceptance. Their port must not silently enter this hardware-validation
scope or block completion of the explicitly adopted software-backed functions.

Finish the spare's isolation/recovery work before withdrawing the second unit
from service. Preserve that unit's own data, identity and backups. Verify board
and chip revisions; use its own array UUID and manifest. Never clone the first
unit's environment, identity or array metadata. Revision differences reopen the
relevant investigation.

Repeat current-image cold/warm boots, controls/cooling, all populated bays and
adopted USB3/SFP+/fault policies on unit 2. After individual cases pass, run a
**24-hour attended or independently monitored mixed-I/O soak**, with thermal
and integrity checks. A soak complements fault tests; it does not replace them.
Unit 1 passing does not make unit 2 passed.

Update the ledger with case IDs, image/source hashes, equipment classes, results
and unresolved limits. Keep unsupported and excluded features visible. In
particular, **complete flash/bootloader restoration remains excluded and
unvalidated** even if every planned test passes. Only reviewed documentation,
sources and redacted evidence may be published after owner approval.
