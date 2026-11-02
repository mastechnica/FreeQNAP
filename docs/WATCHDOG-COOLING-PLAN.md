> **1 November adoption:** the bounded high/full cooling profile passed four ten-minute thermal runs plus stale-input and controller-stop checks and is enabled on the validated installation. PID-1 runtime watchdog supervision is active at ten seconds; live feeding and maintenance disarm/re-enable passed. Ordinary reboot/startup persistence remains the next check. The older investigation/plan below retains wider failure boundaries; see the dated physical records.

# Watchdog and adaptive cooling: remaining board work

Observed on the running TS-431XeU on 1 November 2026. This is a development and
acceptance plan, not evidence that the untested modes are ready for unattended use.
The initial investigation was read-only. Later attended tests established bounded watchdog expiry and a guarded high-speed fan step; see the dated records below.

## Current position

| Feature | Present now | Remaining acceptance |
| --- | --- | --- |
| Hardware watchdog | SP805 identified by Linux; inactive, `nowayout=0`, timeout reported as 10 seconds; reboot path already works | Three real expiry resets and disarm passed in diskless RAM; production ownership and broader failure recovery remain open |
| Cooling | Accepted MCU global full-speed request, exact ACK/readback, three fan counters and CPU temperature | Global high levels 6/7 respond on all three fans; wider range, physical mapping, thermal soak and independent host/MCU failure behavior remain open |
| Standard fan interface | No accepted writable PWM hwmon interface on this board | Board-specific interface/controller integration |

An inactive watchdog's `timeleft` reading is not a running countdown or proof of
expiration behavior. Do not open `/dev/watchdog` just to inspect it: opening can
arm it. Re-read actual limits and ownership in the test environment.

## Watchdog: mostly validation and operating policy

1. Keep UART recovery, fixed full cooling and a known RAM rescue image available.
   Preserve current proof/configuration copies. Schedule a short attended outage.
2. Boot disposable RAM rescue with persistent filesystems unmounted and arrays
   inactive/idle as applicable. Exactly one test process owns the watchdog.
3. Select a supported timeout and read back what the driver actually accepted;
   do not assume an arbitrary 30/60-second setting fits this clock/hardware.
4. Verify feeding and explicit disarm first. Then deliberately stop feeding and
   capture the physical reset, elapsed interval, reset cause if available, and
   return to the safe boot/cooling state. Repeat three times.
5. Verify normal reboot and power-off do not create a late reset or boot loop.
6. Only after that, choose one production owner, preferably the service manager.
   Separate service supervision from the hardware reset policy: an unavailable
   dashboard should normally get a service restart before considering NAS reboot.
   Do not treat a loop that always feeds the watchdog as proof services are healthy.
7. Document maintenance/disarm behavior, supported interval, startup/shutdown
   ownership and reset reasons in status/alerts. Keep an explicit rollback path.

The present SP805 driver means an additional watchdog board is not the first
requirement. Reset routing passed three attended expiry tests in diskless RAM. Watchdog expiry with mounted persistent storage remains unaccepted; successful ordinary reboot alone does not establish it.

References: [Linux watchdog API](https://docs.kernel.org/watchdog/watchdog-api.html),
[SP805 driver](https://github.com/torvalds/linux/blob/master/drivers/watchdog/sp805_wdt.c),
and [service-manager watchdog configuration](https://www.freedesktop.org/software/systemd/man/latest/systemd-system.conf.html).

## Adaptive cooling: protocol, policy and failure behavior

1. Review retained stock protocol evidence and the exact SPEC3 MCU framing.
   Determine the supported nonzero speed commands and readback. Do not probe
   arbitrary command bytes or write MCU/EEPROM firmware.
2. Map all three tach channels to physical fans without stopping any fan. Verify
   whether speed control is global, grouped or individual. Existing counter × 30
   readings are vendor-derived values, not optical tachometer calibration.
3. Starting at accepted full speed, perform short attended nonzero steps, prove
   actual RPM changes and restore full speed after each. Establish a safe minimum
   with the actual installed fans and loaded disk bays. Never assume zero duty is
   a safe automatic setting.
4. Build an independent local controller using valid CPU and disk temperatures;
   calibrate board/NTC input before using it. Include hysteresis, gradual ramps,
   sensor freshness, minimum duty and a full-speed fault request. Align thermal
   policy with the board's existing trips and real observed limits.
5. Test policy with simulated stale/malformed temperature and tach inputs, UART
   failures/lock contention, daemon termination and restart before hardware load.
   A detected software fault must request full speed within two policy intervals,
   capped at five seconds. The controller must not depend on the web UI/network.
6. Verify an **independent** safe response if the host hangs or cannot talk to the
   MCU. A command to set full speed cannot work over a dead UART. Prefer a proven
   autonomous MCU control/failsafe if available. A host watchdog reset by itself
   does not prove the MCU changes a previously reduced speed during boot failure.
7. Run attended idle/load/RAID-I/O and thermal-soak tests, then repeat cold/warm
   boot, normal shutdown, controller loss and network-loss checks. Use synthetic
   missing tach data first; do not physically unplug or stall fans for development.
8. After acceptance, expose Auto / Full speed, temperature/RPM/duty history and
   explicit fault state. Retain the accepted early full-speed helper for fallback.

Upstream has a QNAP MCU hwmon/thermal driver, but that does not establish support
for this SPEC3 board. Its documented reply framing and supported TS133/TS233/TS433
variants differ from the TS-431XeU protocol already observed here. Porting requires
variant-specific validation rather than loading a similarly named driver.

References: [QNAP MCU hwmon source](https://github.com/torvalds/linux/blob/master/drivers/hwmon/qnap-mcu-hwmon.c),
[QNAP MCU binding](https://github.com/torvalds/linux/blob/master/Documentation/devicetree/bindings/mfd/qnap%2Cts433-mcu.yaml),
and the [related TS-431P project](https://github.com/mornepousse/liberate_nas_qnap-ts431p).
Related models provide clues; AL-212 and newer MCU variants are not this AL314 board.

**Priority:** finish watchdog expiry/ownership acceptance first, then guarded fan
command mapping and the adaptive-controller failure tests. Fixed full cooling
remains the adopted setting until those steps pass. No new hardware purchase is
established as necessary; the existing controller's variable/failsafe capabilities
must be proven before deciding whether any hardware change is needed.

The [watchdog record](WATCHDOG-VALIDATION-2026-11-01.md) documents the bounded physical expiry acceptance. The [cooling record](COOLING-VALIDATION-2026-11-01.md) documents the high-speed step, initial guard failure and corrected controller-loss test.
