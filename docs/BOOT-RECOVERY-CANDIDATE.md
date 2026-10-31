# Restricted root-mirror survivor boot candidate

This is uninstalled recovery work, not physical degraded-boot acceptance. The installed bootstrap still requires the original complete root mirror. Retain UART/TFTP recovery and the accepted image until the candidate passes the campaign below.

## Selection boundaries

The candidate probes only partition 1 and partition 2 on disks directly below the board's internal SATA controller (`0000:00:09.0`). USB partitions, device-mapper paths, arbitrary labels on external disks and unrelated MD arrays cannot become root candidates. It reads bounded regular boot records as data, checks the unit MAC binding, and requires mirrored records to agree. Ambiguous additional or cloned members fail closed.

Root assembly uses explicit candidate devices and the exact recorded MD UUID, RAID1 level and two-member geometry. One surviving member is allowed; two conflicting/stale members remain subject to mdadm's normal freshness decisions. There is no scan, forced assembly or fabricated clean flag. Assembly starts read-only; the recorded filesystem UUID and installation identity must match before normal preen filesystem checking and the root handoff. A degraded boot emits a warning and runtime marker. Successful degraded operation requires prompt operator reconciliation and does not provide redundancy.

`installer/target/boot-policy.sh` holds the bounded metadata and internal-path rules; `select-root.sh` applies them. Source tests cover wrong USB/controller paths, wrong partition numbers, array UUID/level/geometry, duplicate fields, symlinks, oversized metadata and shell injection. `tools/native-root-survivor-smoke.py --confirm-loop-fixture` runs only owned disposable loop images: either member survived exact-UUID read-only assembly, filesystem/install-ID/hash checks and normal filesystem checking. No physical array was removed, marked failed or rebuilt by this validation.

## Before installation

Wait for initial data RAID synchronization to finish. Preserve independent configuration and disposable-file proof copies, ensure the recovery UART and accepted RAM image are ready, and verify the exact disks and array identities again. Then RAM-boot the candidate first with both root members. Validate matching modules, network restart, SATA warm reboot, cooling, buttons, LEDs, shutdown and existing data mounts.

A separate reviewed physical campaign must test each root-member survivor, dirty/stale and conflicting identities, bounded refusal cases, original-image recovery, identity-bound replacement/rebuild, and post-rebuild data hashes. Data RAID5 failure/rebuild is another campaign; its acceptance cannot be inferred from the root RAID1 fixture. Do not change the installed boot image merely because the candidate compiles or the loop tests pass. Full-chip/SPI restoration remains excluded by owner decision.

The normal installer rejects RAM-only/flash-prohibited manifests. Do not remove those restrictions to promote a diagnostic image. A permanent release requires its own complete acceptance and rollback review.
