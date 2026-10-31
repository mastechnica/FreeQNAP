# Shutdown metadata follow-up

Observed on the second TS-431XeU during the final installed-image cold-start test, 29 October 2026. This is an open engineering issue, not a failed disk or a completed fix.

## Evidence

The shutdown trace showed filesystem synchronization, root remounted read-only, and all filesystems reported unmounted before the late MCU chassis-power-off request. Systemd also reported that one MD device could not be finalized. The owner confirmed the fans stopped, waited, and powered the chassis on normally.

The next autonomous NAND boot identified all four disks and assembled both members of the OS mirror. The kernel reported `not clean -- starting background reconstruction`, followed by `resync done`. It uses an internal write-intent bitmap. By the post-boot checks, the mirror was clean, non-degraded and idle, all four SMART health checks passed, and no service was failed. A new configuration backup verified successfully.

This supports successful cold-boot recovery. It does **not** support a claim that the late power-cut hook leaves clean RAID metadata on every normal shutdown. The current hook synchronizes filesystems before MCU power removal; ordering relative to the kernel's final MD shutdown/metadata flush is a candidate cause, not yet proven.

## Investigation and acceptance

1. Compare the root array's persisted member metadata before shutdown and at the next RAM-only inspection, with no application writers. Keep exact evidence private.
2. Review the Linux MD shutdown path and the systemd late-hook ordering against the precise kernel build. See the upstream [MD sysfs/state documentation](https://docs.kernel.org/admin-guide/md.html).
3. Implement the smallest guarded finalization change. Preserve filesystem read-only and board/PID1 checks, and reject unexpected or busy state. Never use `--assume-clean`, recreate an array, discard a bitmap or write fabricated clean metadata to suppress the symptom.
4. Test on the disposable unit: normal idle shutdown, shutdown after real writes, reboot and physical power-on. Verify data checksums, member events, no recovery required after clean shutdown, no failed services and preserved backup history.
5. Keep interrupted-power recovery distinct: a repair must not disable genuine recovery after an unclean power loss. Degraded/rebuild and abrupt-power tests remain separate acceptance work.

No code or array metadata change was applied as part of the cold-start check. The NAS was left running with its synchronized mirror and local services healthy.

## Guarded candidate prepared 30 October 2026

Inspection of the exact 6.12.114 source explains the ordering risk: `md_notify_reboot()` flushes bitmap/superblock state through the normal kernel shutdown notifier. The original userspace hook can remove chassis power before the reboot syscall reaches that notifier. Stopping the mounted root through the normal MD stop/read-only ioctl is not a safe shortcut: the kernel's opener checks can reject it while the root filesystem still holds the device. No array state, superblock or bitmap was fabricated or reset during this investigation.

`hardware/ts431xeu/freeqnap-poweroff.c` registers a **final kernel power-off callback**, after MD notifiers, device shutdown and syscore shutdown. It locks support to the exact board, UART1 physical resource, register width/shift and 375 MHz clock. Registration/unload performs no UART write. At actual final power-off it sends only the already accepted SPEC3 power frame using bounded atomic polling. This follows the upstream QNAP final-UART handoff approach, with this board's different MCU protocol. It is not a restart callback.

The existing static shutdown helper now delegates when this registered kernel callback reports ready. Its board, final-PID1 and read-only-root guards remain. Without the module it retains the legacy compatibility path; that path has not acquired clean-MD acceptance merely because the source changed.

A matching module and static helper have been built and installed **on the spare only**, with the original helper retained privately. Native dry-run checks observed the kernel-ready flag change from absent to ready without a power command, and local services stayed healthy. A deterministic test-file checksum and member metadata were saved. **Physical shutdown/cold-start verification is pending the owner's availability. This is a candidate, not a proven fix.** No NAND, SPI, boot command, data layout or RAID metadata was changed by installation.

The optional module builder accepts `freeqnap_poweroff`. On the target, `deploy/install-poweroff.sh` checks exact vermagic/model and installs reviewed local module/helper artifacts without rebooting. The helper can be compiled statically from the included C source with the matching armhf toolchain. Retain the prior helper and module state for rollback; never force-load a different ABI. This does not complete the public clean-build installer.

References: [kernel shutdown ordering](https://github.com/torvalds/linux/blob/v6.12/kernel/reboot.c), [MD shutdown and opener checks](https://github.com/torvalds/linux/blob/v6.12/drivers/md/md.c), [upstream QNAP final-UART power-off](https://github.com/torvalds/linux/blob/v6.12/drivers/power/reset/qnap-poweroff.c).

## First candidate physical cycle: passed 30 October 2026

The owner-authorized idle shutdown reached the kernel's final callback **after all four SATA disks synchronized caches and stopped**, followed by the Ethernet shutdown and kernel power-down messages. The owner confirmed the fans stopped, waited, and powered on normally. The next autonomous installed-image boot had a new boot ID, all four SATA links/disks, an unchanged fsynced 16 MiB test-file SHA-256, a healthy `[UU]` OS mirror and no failed services. Neither the boot journal nor captured cold-boot trace contained the previous unclean-array/background-reconstruction report. All four internal SMART short self-tests had completed without error before shutdown.

This accepts that first idle cycle of the guarded callback. Repeat post-write shutdown, normal reboot, physical data-array shutdown/reassembly and interrupted-power cases remain separate tests. Do not generalize one clean root-mirror cycle into complete storage/power-loss acceptance. The compatibility fallback without the matching module remains unaccepted for clean metadata ordering.
