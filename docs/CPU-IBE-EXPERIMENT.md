# Cortex-A15 IBE investigation

Status: **separate unbooted RAM-only experiment**, not an accepted firmware fix or
permanent release. The running FreeQNAP7 hardening candidate still reports IBE
warnings on all four cores. No bootloader/SPI or CPU experiment has been applied
to that running image.

## Why investigate a kernel-side path

Arm documents ACTLR bit 0 as enabling branch-target-buffer invalidation on
Cortex-A15. Non-secure writes are restricted; a firmware-controlled system can
ignore the requested bit. An original Linux ARM discussion proposes requesting it
during matched A15/B15 CPU setup, which can help platforms that release CPUs into
secure mode directly. That historical proposal is **not evidence of an accepted
upstream fix or of this NAS's security state**.

References: [Arm Cortex-A15 ACTLR/NSACR reference](https://documentation-service.arm.com/static/5e8e312bfd977155116a812f),
[original kernel proposal](https://lists.openwall.net/linux-kernel/2018/06/07/1280),
[discussion of direct secure CPU startup](https://lists.openwall.net/linux-kernel/2018/08/22/537).

## Experimental implementation

The separate FreeQNAP8 recipe requires `arm-hardening-ibe-v1`, the complete-mirror
bootstrap and exact unmodified hashes of both affected source files. Its small
GPL kernel patch adds a default-off `FREEQNAP_CA15_IBE` option, dependent on
Alpine, SMP and branch-predictor hardening. Other build profiles explicitly disable
it; the memory-only hardening profile refuses a patched input CPU tree.

Only matched A15/B15 setup supplies bit 0 to the existing ACTLR read/modify/write
operation. Existing bits are preserved; A7/A12 skip the experiment, A17 retains
its original path, and the normal per-CPU IBE readback, vulnerability warnings and
mitigation installation logic are unchanged. Actual assembly was reviewed for
these branches and the single-bit request. The patch does not make arbitrary
register access available to the dashboard or to agents.

The build passed zero-fuzz source patching, actual CPIO helper/driver checks, all
nine matching ARM module checks and legacy image checks. Its manifest explicitly
marks the CPU experiment and retains RAM-only / flash-prohibited flags. Six
negative/profile tests confirm it cannot silently enter another candidate.
None of those checks proves the register is writable or the mitigation effective
on the physical NAS.

## Physical acceptance still required

Use an attended RAM session with full cooling, verified UART and the pinned old
rollback image. Record every core's actual mitigation/readback messages and keep
warning evidence if the write is ignored. A positive sysfs summary alone is
insufficient. Recheck all cores online, boot W+X evidence, exact data proofs,
networking, thermal/load behavior and rollback. Any fault stops the campaign;
there is no automatic flash adoption, forced reset of mounted storage or claim
that all speculative-execution vulnerabilities are solved.

The read-only checker supports `--require-cpu-ibe`. It requires all four CPUs
online, positive per-core ICIALLU installation messages and no IBE warning. Partial
core evidence, contradictory warnings and a sysfs-only mitigation summary fail.
Combine it with `--require-memory-hardening`; confirming this one CPU path is not
a complete speculative-execution or CVE-free certification.
