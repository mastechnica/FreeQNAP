# Cooling and hardware supervision

New/unvalidated installations default to **Full speed**. The validated second-unit high/full automatic profile has now passed its bounded thermal/software-fault campaign and is enabled. The dashboard's Settings page shows fan
RPM, CPU/four-disk temperatures, controller state and read-only watchdog state.
The separate local controller does not depend on the browser or network.

## Automatic cooling gate

Automatic cooling is unavailable until the exact installation has passed its
thermal/load and controller-failure campaign. Merely installing the service or
changing a configuration file does not establish physical acceptance. The current
policy uses only stock global levels 6 (high airflow) and 7 (full); it never stops
fans or uses unvalidated low-speed/PWM commands.

Full speed is selected for CPU temperature at least 60°C, any internal disk at
least 48°C, stale/missing/malformed sensors or abnormal fan feedback. A reduction
requires CPU at most 52°C and all four disks at most 42°C. The intermediate band
retains the previous accepted setting to avoid rapid switching. These conservative
policy thresholds are not measured silicon limits or an overheating test.

Every automatic decision requires three valid fan counters, four distinct
internal SATA identities with fresh SMART temperatures, a fresh CPU reading and
a live independent guard. The minimum accepted tach feedback is 5500 vendor RPM;
this is a fault boundary, not a requested fan speed. RPM uses the stock multiplier
and is not optical calibration.

A separate service watches a short controller lease. It binds process identity to
the current boot and start time, latches controller loss before terminating that
owner, and requests checked full speed. A restart cannot clear the same-generation
fault latch into automatic operation. Selecting Full speed then Automatic creates
a fresh owner-requested configuration generation, subject to acceptance checks.
Dead UART/MCU and host-hang safety remain separate physical requirements; a
software guard cannot send a command through a failed communication channel.

## Installation and rollback

Deploy the source generation first, then run `sh deploy/install-cooling.sh` on
the exact NAS as root. New installations default to full speed. The installer
never creates a hardware-acceptance receipt. Existing early full-speed startup
remains in place. The independent guard and controller are separate system services;
shutdown/stop hooks request full speed. Runtime state is bounded and local;
history rotates at approximately 3 MiB per file.

For rollback, select Full speed, stop both new cooling services, and retain the
early fixed-full service. Verify mode/RPM afterward. Keep UART rescue available
for firmware/kernel work. Never replace full cooling with an untested MCU command.

## Watchdog policy

The SP805 passed three attended 10-second expiry resets in diskless RAM and
explicit disarm checks. The validated installation now uses systemd PID-1 runtime supervision at ten seconds; live feeding and maintenance disarm/re-enable passed. Ordinary reboot/startup persistence remains pending.
`deploy/configure-watchdog.py status` is read-only and does not open the device.
Enable/disable defaults to inspection unless `--apply` is present; enabling needs
a private exact-install receipt for the prior expiry/disarm acceptance.

The prepared production owner is systemd PID 1, with a ten-second runtime timeout.
Reboot/kexec watchdogs stay disabled while their separate maintenance tests are
outstanding. A dashboard failure does not deliberately starve the hardware:
ordinary application/service recovery is separate from machine-hang supervision.
The enable tool checks fresh full cooling, existing ownership and reversible
`nowayout=0` before activation. It verifies manager ownership, active state and
actual timeout and retains a named persistent configuration for later boots.
Only its exact managed configuration is removed by the disable path.

See [physical cooling observations](COOLING-VALIDATION-2026-11-01.md),
[watchdog observations](WATCHDOG-VALIDATION-2026-11-01.md),
[systemd manager watchdog settings](https://www.freedesktop.org/software/systemd/man/latest/systemd-system.conf.html),
and [the kernel watchdog API](https://docs.kernel.org/watchdog/watchdog-api.html).

## Attended commissioning trials

`tools/cooling-load-validation.py` defaults to read-only preflight. An applied
campaign requires a fresh private root-owned exact-install plan, four internal
SATA identities, both array UUIDs, owner attendance and a bounded workload.
It reads disk sectors directly without issuing disk writes. CPU/disk temperature,
tach, array health, disk identity, worker health and independent guard freshness
are checked throughout. The initial stop limits are 65°C CPU and 48°C disks. A reviewed 70°C CPU campaign additionally requires the exact recorded thermal basis and unchanged 80°C kernel trip. These are commissioning limits, not silicon ratings; the automatic full-speed threshold stays at 60°C. See the dated record for the original-stock 105°C configuration evidence and its limits.

A temporary adaptive trial can exercise the real controller before permanent
acceptance. Its permission is bound to the current installation, boot, process
start and a refreshed three-second lease, with an absolute duration limit. A new
trial may start the proven high-speed step only within a cool entry envelope
(CPU at most 55°C and all disks at most 45°C). The normal heat/fault overrides
remain active. Stopping the harness, selecting Full speed, losing its heartbeat,
changing identity or reaching the deadline withdraws this permission. Normal
automatic entry thresholds are unchanged. The trial never creates a permanent
acceptance receipt or changes the saved full-speed preference.

Raw plans, disk identities and measurements belong in private validation storage.
The tool records high-speed sample counts and observed sample-interval duration;
these are sampled evidence, not a claim of uninterrupted electrical measurements.

## History and supervision alerts

Settings shows fresh cooling state without replacing other forms. The optional
Temperature & fan history panel reads bounded local samples for CPU, hottest disk
and each fan counter; missing data produces gaps rather than zero readings.
History is sampled every thirty seconds and is not instantaneous electrical proof.

The health rule scopes include `cooling` and `watchdog`. A managed watchdog policy
present with an inactive/unavailable device produces a critical supervision fault.
This does not enable email, push or sound, or change saved notification preferences.

`tools/cooling-fault-validation.py` prepares attended stale-inventory and stopped
controller checks. Its default is read-only preflight; apply requires a private,
fresh, exact-install plan. The stale-reading case changes only the inventory
sample timestamp, then obtains a new actual collector snapshot; it never restores
an old cached inventory over fresh data. The controller-stop case verifies the
service manager's exact main process plus boot/start identity before signaling.
Both cases retain full-speed cleanup and create no permanent acceptance receipt.
