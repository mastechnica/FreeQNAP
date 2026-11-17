# Native management outage investigation — 11 November 2026

## Current observations

I reported successful cloud sign-in and a loaded dashboard, with native
NAS operations unavailable and stale hardware-health monitoring. A fresh public
anonymous session check still reaches the web console. Pinned SSH does not reach
authentication: earlier attempts were rejected before key exchange; the latest
bounded attempt timed out during the server banner. These observations establish
a partial management outage, not total loss of network connectivity. Current RAID,
filesystem, memory, cooling and watchdog health remain unverified. Earlier healthy
snapshots must not be presented as current acceptance.

I cannot connect serial access while the unit is racked. No reboot,
service restart, driver unload, network change, storage mutation or notification
change was performed during this investigation. Raw connection evidence is private.

## Strongest existing fault evidence

The retained previous-boot evidence records an asynchronous external abort in
`al_eth_mac_stats_get`, called from `al_eth_get_stats64` during an `ip` route-netlink
link dump. The timestamp is 9 November 2026 at 01:49:13 UTC. Subsequent journal
entries record 19 SSH MaxStartups rejections and 13–35 unfinished startup
connections. The exact register failure, retained-lock chain and individual stuck
connection stacks were not captured. This proves an earlier Ethernet statistics
fault; it does not prove that the current boot has repeated it.

See [the staged driver repair](ETHERNET-STATISTICS-REPAIR.md). The candidate passed
isolated compilation and callback fixtures but has not been installed or physically
accepted. The known faulty driver therefore has not been replaced by that work.

## Source review and possible amplification

`Metrics.sample()` reads physical-interface `statistics/rx_bytes` and `tx_bytes`
directly; `metrics_worker()` calls it every 30 seconds. These Linux statistics reads
use the driver's network-statistics callback. The NAS status path also calls
`Network.ports()`, which runs `ip -j address show`. The recorded abort specifically
occurred in a link dump; the review does not establish that this address command
caused that recorded abort.

The native broker admits at most 16 concurrent request handlers, with a 600-second
client timeout. Browser status refresh gives up earlier, without an application
cancellation mechanism for an already executing native operation. Network status
and filesystem capacity checks run within the overall status request. Consequently,
stalled kernel/filesystem operations can consume workers and make other native
functions unavailable. Python command timeouts cannot reliably release a process
blocked in uninterruptible kernel I/O. This is a source-based failure-amplification
risk, not a measured current worker count or proof of the current stall's cause.

The interface correctly refuses to submit operations when native status is
unavailable. Successful cloud authentication and an available web server do not
verify native service, disks or cooling. Removing the warning would conceal the
problem.

## Remaining repair and acceptance

Fresh serial or authenticated operating-system access is needed to capture the
current journal, boot/module identity, blocked tasks, SSH startup children and
native worker stacks before resetting away the evidence. Avoid network statistics
probes while the suspect callback remains active. Do not blindly restart services
or raise SSH connection limits as a substitute for identifying the blocked work.

The durable driver repair still needs a pinned RAM-test boot image and rollback,
configuration backup, recovery access and hardware acceptance. The accepted boot
loads the network module from initramfs: copying a module onto the root filesystem
alone is insufficient. Unloading the only active network driver over SSH is not
a safe activation method. Test bounded statistics reads, fresh SSH sessions and
hashed transfers after activation, followed by a soak and kernel-log review.

Separately, native monitoring should isolate slow probes, deduplicate status work
and reserve management capacity, while reporting stale/unknown component states
honestly. Such application containment cannot repair a kernel fault. No application
containment deployment or driver activation is claimed by this investigation.

## Power-cycle follow-up

The initially reported successful SSH login and software reboot were subsequently
identified as being on the other NAS. They do not establish that SSH was available
on the affected FreeQNAP unit or that this outage was source-specific. I
then explicitly reported hard-power-cycling FreeQNAP and seeing the same state
return. A fresh check again reaches the public web session endpoint, while direct
SSH is reset before authentication. The alternate authorized LAN jump host is
unavailable; that failure says nothing about NAS acceptance from another source.

The new boot ID and kernel journal remain unread, so the restart is reported directly
and the recurring kernel-fault hypothesis remains unconfirmed. No current RAID,
filesystem, cooling or watchdog acceptance is possible from these observations.
Automatic statistics monitoring could retrigger the known driver fault after boot;
this timing mechanism is plausible from source, not a captured new fault trace.
The prior software-reboot report must not be used to infer a Mac-only restriction.

The dashboard restart control depends on the unavailable native broker. A short
physical power-button press also depends on functioning event handling and must
not be promised to shut down this partially stalled system. No further power
cycle was requested. With no authenticated remote operating-system access and no
serial connection, activation of the staged repair and fresh blocked-task/kernel
capture remain blocked. I have already explained that serial access is
unavailable while the device is racked; repeated requests do not resolve that
constraint. Retain the unit's state rather than claiming another reset is a fix.

## Alternate-port reboot capture — 11 November, evening Eastern

I moved the Ethernet cable and power-cycled the affected NAS. Continuous
one-second ping and bounded SSH-greeting checks watched both known addresses.
Pinned SSH succeeded on the alternate port, and two authenticated reads confirmed
a new boot ID. The host alias/pinned key were preserved; no identity check was
bypassed. These results supersede the earlier remote-access blocker for this boot.

The previous boot's retained kernel journal contains another asynchronous external
abort at 11 November 08:07:22 UTC (03:07:22 Eastern). The affected root-owned `ip`
process faulted in `al_eth_mac_stats_get`; its call trace includes
`al_eth_get_stats64`, `dev_get_stats`, `rtnl_fill_stats` and `rtnl_dump_ifinfo`.
This independently confirms recurrence of the known Ethernet-statistics kernel
fault in the boot preceding the observed recovery. The precise failed register
condition and downstream retained-lock chain remain unproven. Moving ports does
not install or validate the staged software repair.

The initial fresh-boot snapshots show the original installed kernel, an active
native broker and console, active cooling/controller guard services, and a running
ten-second hardware watchdog reported by systemd. Data RAID5 has four of four
members and the OS mirror two of two, neither degraded. These membership snapshots
do not prove every file, parity correctness or physical cooling performance.

After the unclean shutdown, volume 1 completed journal recovery and mounted.
Volume 2's existing filesystem-check job was still running, with its mount queued
at the follow-up snapshot. No check or mount was restarted/submitted. The root
filesystem startup check logged device-busy/exit 8; it was not a successful offline
consistency check and must remain an open acceptance item. No new matching kernel
abort appeared in the captured current-boot fault search.

The LAN HTTPS service cannot bind its saved address on the newly selected port.
This is a separate address-binding problem, not proof that the native broker has
failed. No address, certificate, identity-provider or firewall setting was changed.
Raw boot IDs, paths, journals and network captures remain private. No disk layout,
recovery tuning, driver, service or notification configuration was modified.

### Follow-up after automatic journal recovery

A later authenticated read in the same boot confirms both data volumes mounted
and both arrays still fully populated/non-degraded, with no resync shown. The
volume-2 check/mount completed without manual intervention. Cached health monitoring
was 23 seconds old with no failed scopes. The sole active critical alert was the
configured LAN HTTPS endpoint being unavailable after the address/port change.
Cached cooling telemetry matched the current boot and reported full-speed level 7,
three fan RPM readings (approximately 8,300–8,700), CPU 41 C and disks 30–31 C; the
guard was ready. This verifies fresh reported telemetry, not a physical inspection.
No matching fault appeared in the new boot's kernel searches. Root offline
consistency acceptance and installation/testing of the driver candidate remain open.


## Subsequent focused repair

Remote serial recovery, fixed-image RAM boot/rollback and the separately approved
permanent Ethernet installation subsequently completed. The statistics callback
now avoids the faulting MAC-register read on this exact board. See the
[hardware validation report](REMOTE-UART-ETHERNET-VALIDATION-2026-11-11.md).
The observations above remain historical evidence; the exact downstream lock
chain and every possible cause of future outages are not claimed proven.
