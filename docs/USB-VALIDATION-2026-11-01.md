# Physical encrypted USB validation — 1 November 2026

The disposable 16 GB SanDisk flash drive completed the approved destructive
campaign on the physical TS-431XeU. Stable descriptor/serial/capacity, attachment,
partition/filesystem and internal-array identities were checked; private identities,
raw journals and plans are retained outside public source.

## Results

| Check | AES-256-XTS | AES-128-XTS |
| --- | --- | --- |
| Fresh LUKS2/ext4 creation | Passed, initial password | Passed, initial random key file |
| Add and verify alternate credential | 64-byte random key | Password |
| Incorrect password and incorrect key | Both refused, mapper remained closed | Both refused, mapper remained closed |
| File-manager folder/upload path | Unicode folder + 8 MiB random file | Unicode folder + 8 MiB random file |
| Four alternating password/key read/write remount cycles | Passed | Passed |
| Direct-read SHA-256 after remounts | Every proof matched | Every proof matched |
| Writes from every cycle survive later unlock | Passed | Passed |
| Normal unmount while a file is held open | Correctly refused | Correctly refused |
| Read-only unlock, proof read and attempted write | Read matched; write refused | Read matched; write refused |
| Final key-file reopen and normal lock | Passed | Passed |

The four read/write cycles per method total eight. Each method additionally had
read-only and final persistence reopens. Cipher and Argon2id metadata were checked
against the requested profile. Formatting, key addition, uploads, locking and
unlocking used the actual NAS implementations, not a loop-file substitute.

Observed successful read/write unlock workflows ranged **2.7–4.7 seconds**.
The 8 MiB uploaded proof took about **1.95 seconds** with either method. These are
small workflow observations, not sustained throughput benchmarks. Key-slot search,
calibration, storage and mounting contribute to the times; this is not evidence
that passwords or key files are inherently faster.

## Two product issues found before formatting

1. This flash drive rejects SCSI SYNCHRONIZE CACHE as an unsupported operation.
   It reports write-through caching, also supported by the read-only caching-page
   observation. Eject now accepts only that specific unsupported result with
   reported write-through, after normal unmount and Linux buffer flushing.
   Unit tests retain rejection for actual hardware errors, unknown policy and
   write-back caching. No device cache setting was changed.
2. Its valid capacity is aligned to 512-byte logical sectors but not to 4096
   bytes. The GPT planner had rejected it unnecessarily. Validation now uses the
   declared logical sector size; volume extents remain MiB-aligned. Header/CRC
   tests cover the non-4K-multiple geometry, and a read-only direct tail read
   succeeded on the physical drive before formatting.

Both stopped attempts were preserved and reconciled before a fresh plan was
executed. No format had started in those attempts. A test-harness null dependency
check was also corrected during read-only preflight. Consumed plans were not
reset or replayed, and no failed format was blindly retried.

## Cleanup and isolation

The completed campaign took about 129 seconds. Both temporary volumes were locked
and deregistered, test partition/filesystem signatures were removed, and the USB
was left blank, unmounted, with no crypto mapper. Temporary passwords were not
persisted; the temporary key files were removed. Only empty mountpoint directories
proven created by this campaign were removed afterward. This is not a physical
flash secure-erase claim.

The four-member internal data RAID and two-member OS mirror stayed non-degraded
and idle; internal-array membership and other storage configuration were preserved.
The TR-004 was excluded. The inspected campaign kernel log contained no matching
USB disconnect, DMA or block I/O failure; expected busy-unmount refusals were retained
in the private evidence. The two expected failed test-service statuses were cleared
only after their evidence was archived and the corrected campaign passed.

Regression verification passed **238 Python tests** (four platform-dependent
skips on the development host), all 14 JavaScript tests, and the 28 targeted native
profile/external/GPT tests. Package/link/source checks passed. The dashboard adds
explained security presets; choosing one does not format a drive without its
separate reviewed confirmation.

## Remaining limits

This accepts the tested USB/profile/credential workflows, not every enclosure,
flash controller, filesystem or failure mode. Abrupt power loss, physical unplug
while mounted, lost-header restoration, full-capacity endurance and external
platform interoperability remain separate acceptance work. Adaptive fan control
and watchdog expiration were not exercised by this campaign. See
[USB encryption](USB-ENCRYPTION.md) and the
[watchdog/cooling plan](WATCHDOG-COOLING-PLAN.md).


The final locally deployed broker produced correct non-applied plans for both
cipher profiles and safely ejected the blank drive using the reported write-through
path. The live dashboard was checked for recommended/balanced/separate-key
selection and help. The separate-key preset opened a key-file confirmation form
with password fields hidden; that preview was cancelled without another format.
Only local application services were restarted; no NAS reboot, watchdog arming or
fan-speed reduction was performed. The previous working release was retained.
