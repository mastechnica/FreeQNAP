# Cooling validation — 1 November 2026

## Accepted bounded observations

On an attended TS-431XeU/AL314, the stock-supported global high-speed level 6
was selected for ten seconds from accepted full-speed level 7. All three
vendor-derived tachometer readings responded, and full-speed mode and RPM were
restored. No fan-stop command, low-speed level, raw PWM write or firmware change
was used. The normal cooling service remains fixed at full speed.

| Reading | Full before | High-speed step, settled | Full after recovery |
| --- | ---: | ---: | ---: |
| Fan counter 0, RPM | 8760 | 8070–8100 | 8670 |
| Fan counter 1, RPM | 8730 | 8070–8100 | 8670 |
| Fan counter 2, RPM | 8370 | 7680 | 8280 |
| CPU temperature | 54°C | 53–54°C | 53°C |

These RPM values use the stock counter multiplier; they are not optical
calibration or a mapping of each counter to its physical fan. The owner confirmed
all three fans continued spinning normally during the step.

## Controller-loss guard

A separate service watches a short lease from the attended test controller.
It identifies the owner by process ID, start time and boot identity, terminates
only that owner on lease failure, and requests verified full speed. The web
interface and network are not part of this guard.

The first controller-loss trial detected the missing heartbeat but its full-speed
helper failed. A subsequent direct query still reported level 6. Full speed was
restored immediately using the accepted helper. Both arrays remained healthy.
The first harness did not retain the helper error, so the cause of this specific
failure is unresolved and must not be presented as proven lock contention.

The harness was hardened to preserve the error and wait at most four seconds
through explicit MCU lock contention. Other helper errors fail immediately.
A deliberate 1.5-second lock hold was recovered while cooling remained full;
the verified full-mode observation completed in 1.965 seconds. The corrected
physical controller-loss trial then passed: full mode was verified 0.452 seconds
after lease-failure detection. The lease is 2.5 seconds with a 0.1-second poll.
Mode readback precedes mechanical fan spin-up; it is not an instantaneous RPM
recovery measurement. Native tests cover bounded lock waiting and refusal to
retry protocol failures.

## Policy preparation and remaining gates

A pure, unenabled policy prototype permits only levels 6 and 7. It requires fresh
CPU and four-disk temperatures and all three valid tachometer readings, uses
hysteresis, and selects full speed for missing, stale, malformed or hot inputs.
Its unit tests are policy evidence, not physical thermal acceptance. No adaptive
controller has been enabled or production watchdog policy changed.

Still required before unattended adaptive operation:

- Integrate a single local owner, independent guard, bounded shared-MCU access,
  restart/exit recovery and explicit Auto/Full controls and history.
- Validate disk-temperature collection, physical fan mapping and realistic
  loaded-disk idle/load/thermal-soak behavior at the retained high-speed minimum.
- Exercise stale inputs, lock contention, process termination, restart, network
  loss and warm/cold boot with the actual controller.
- Establish a safe independent response to a hung host or dead MCU UART. A
  software full-speed command cannot recover a dead communication channel.
  The stock autonomous mode was not established; no unsupported setter was sent.
- Keep full speed when these requirements cannot be demonstrated. Broader speed
  levels, fan unplug/stall and arbitrary PWM remain outside this acceptance.

Raw device identities, plans, logs and original vendor analysis stay private.
The public package contains only original test tools and sanitized observations.

## Production-controller implementation checkpoint

The permanent local owner, separate lease guard, exact-install acceptance gate,
full/automatic dashboard controls, bounded history and cooling-health integration
are implemented and deployed at **fixed full speed only**. No acceptance receipt
was fabricated and automatic mode remains unavailable. Sixteen focused control,
policy/runtime and watchdog-tool tests passed natively on ARMhf. The watchdog
configuration tool was inspected only; the hardware remains inactive.

Stopping the actual controller with SIGSTOP caused the guard to latch the fault,
kill that exact owner and restore verified full mode. The service restarted with a
new process identity; fresh controller/guard status returned after 6.518 seconds.
Full mode was reported throughout. This is total service-return time, not a claim
that full-mode restoration waited that long. This test did not start at level 6.

A read-only four-disk/three-CPU-worker full-speed baseline stopped after 27.15
seconds at its conservative 65°C CPU guard. Disk temperature peaked at 46°C; full
mode was retained, and the immediate post-load CPU reading was 58°C. The campaign
therefore did not pass its intended duration. The lighter one-worker baseline also stopped at the same conservative guard after 338.65 seconds (143 samples; peak observed CPU 66°C, disks 46°C). Sampling is discrete, so the observed value can cross the configured 65°C stop between reads. The immediate post-load CPU reading was 62°C. No writes were issued, all load workers stopped, both arrays stayed healthy and the owner is checking cover/airflow before another thermal campaign. Neither duration test passed; automatic mode remains locked. A stop threshold is
not the board's silicon maximum, and must not be raised merely to produce a pass.

The current kernel version check still reports installed 6.12.114 and maintained
6.12.115 available. No watchdog activation, kernel installation or TR-004 format
is part of this checkpoint. The enclosure remains read-only and unmounted.

## Covered-chassis baseline

After the owner refitted the top cover, cleared the vents and reconnected UART,
the same one-worker/four-disk-read full-speed baseline passed 601.1 seconds and
252 samples. Peak CPU was 57°C, peak disk temperature 45°C, all three fan counters
remained normal and cleanup verified full mode. No disk writes were issued.
CPU after load was 51°C. During the run, disk temperatures fell into the 36–40°C
range. This is strong observed airflow evidence; it does not independently
calibrate the temperature sensors. The heavier three-worker full-speed campaign
is still in progress; permanent automatic mode remains locked.

The first covered heavy campaign stopped after 55.532 seconds because the cooling
guard was deliberately restarted during a source deployment. Peak CPU was 61°C;
full cooling remained verified. This is an interrupted validation run, not a
thermal pass or an unexplained hardware fault. A fresh identical-scope plan was
prepared after services stabilized; no supervisor changes are made during that
repeat. A guarded sequence may proceed to timed adaptive idle/load trials only
after heavy full-speed success and cooling into the normal entry envelope.

## Thermal test-bound review

The stable-services three-worker repeat reached the initial 65°C commissioning
stop after 107.244 seconds. It stopped normally; disks peaked at 39°C and full
mode remained verified. The queued adaptive sequence stopped before any reduction.

A subsequent review of the retained original board device tree decoded its
critical CPU trip as 105000 millidegrees (105°C). The installed custom board tree
uses an intentionally conservative 80000-millidegree (80°C) bench critical trip.
Neither setting is an independently established silicon rating or a physically
exercised thermal-trip guarantee. This new board-specific evidence establishes
that the initial 65°C test cap was not a documented component overheat boundary.

A separately reviewed campaign permits a 70°C load stop only with the exact
thermal-basis declaration and unchanged 80°C installed trip. This retains a 10°C
margin below that configured bench trip and leaves the automatic full-speed
threshold at 60°C and disk stop at 48°C. No kernel trip, sensor conversion, health
threshold or fan policy was relaxed. Earlier stops remain recorded, not relabeled
passed. The new heavy campaign and dependent adaptive trials are in progress.

The reviewed full-speed heavy campaign passed 600.674 seconds and 417 samples
with three CPU workers plus four direct-read disk workers. Peak CPU was 67°C,
peak disk temperature 37°C, and full mode was retained throughout. Cleanup
verified all three counters and full mode; both arrays remained non-degraded and
idle. No disk writes or permanent automatic-mode receipt were created. The
sequence waits for normal cool-entry conditions before timed adaptive trials.

## Timed adaptive idle and load response

The attended high-airflow idle/read campaign passed 600.695 seconds with 422
samples, 415 at level 6 and 579.972 seconds of adjacent observed high-speed sample
intervals. Peak CPU was 53°C and disks 35°C. Other samples were full mode; this
is sampled evidence, not uninterrupted electrical monitoring. A short diagnostic
trace saw 75 consecutive high-speed controller observations with no fault. The
owner confirmed all three fans visibly spinning normally. Cleanup verified full
mode; its immediate RPM sample can precede mechanical acceleration.

The following three-worker adaptive load campaign passed 601.481 seconds and
415 samples. Sampled transitions were full at 0.302 seconds/50°C, high at 1.875
seconds/51°C, then full at 79.386 seconds/60°C. The actual controller reported
`warm`, establishing policy response rather than relying on cleanup. Peak CPU was
66°C and disks 34°C; final full-speed counters were 8700/8700/8340 vendor RPM.
No disk writes, kernel changes or permanent acceptance receipt were created.

A subsequent independent direct read verified all three prior RAID proof hashes
with exact identities/inodes, both arrays non-degraded and idle, both data mounts,
and no failed system services after archiving intentional test failures. Kernel
warning records during the covered campaigns were empty. The existing OS-capacity
warning remains. Notification preferences were not changed.

The live status/history interface and expected-but-inactive watchdog detection are
deployed. Twenty-five focused native ARMhf tests passed. The last two attended
stale-reading/stopped-controller checks remain pending owner readiness; saved
cooling is Full speed, permanent Auto is locked and the watchdog remains inactive.

## Attended fault acceptance and adoption

Both final exact-install checks passed with the owner watching. Stale disk
telemetry caused the actual controller to request and verify full mode in 0.950
seconds. A new actual collector snapshot restored freshness; no old inventory was
restored over newer data. Stopping the exact cooling service owner from high mode
caused the independent guard to kill that owner and verify full mode in 3.747
seconds. The restarted owner remained fault-latched at full speed. Final counters
were 8730/8700/8340 vendor RPM. The owner confirmed all three fans stayed normal.

After verifying every result and the saved evidence hashes, a private exact-install
receipt admitted only levels 6/7. Permanent Auto was enabled and physical level 6
readback observed without any temporary trial. Full mode was selected during
watchdog commissioning, then permanent Auto resumed. This is bounded covered-case,
bench-environment and software-fault acceptance, not proof of physical fan-stall,
electrical UART/MCU failure, environmental extremes or critical-trip behavior.

A fresh encrypted configuration capture (226 files, 21,333,388 bytes) was
independently downloaded/hash-verified on the owner's computer before production
supervision was enabled. It and its separate password remain private.
