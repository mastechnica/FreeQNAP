# Ethernet statistics fault and installed repair

The previous boot journal records an asynchronous external abort in `al_eth_mac_stats_get` on the TS-431XeU at 2026-11-09 01:49:13 UTC, or 8 November at 8:49 p.m. Eastern. The affected `ip` process was serving a route-netlink link dump. Its trace passed through `al_eth_get_stats64`, `dev_get_stats` and `rtnl_fill_stats`. This predates the reported Mac Ethernet change. Subsequent SSH logs show unfinished startup connections accumulating and `Maxstartups` rejections. The exact retained-lock chain and original hardware-register failure condition were not captured; the driver fault is the strongest underlying-cause evidence for the partial outage.

## Repair design

The source patch changes `ndo_get_stats64` only on the exact `qnap,ts-431xeu` board compatible. That callback returns the driver's existing per-queue software packet, byte and allocation/mapping-drop counters, read through the existing `u64_stats_sync` synchronization. It returns before calling the faulting MAC MMIO statistics function. Other boards retain their prior callback behavior. Down interfaces retain the existing no-read behavior. No transmit, receive, PHY configuration, flash or storage code is changed.

These are software traffic counters, not MAC wire counters. Hardware-only error, pause, multicast and similar statistics are not populated on this board by the replacement callback. Avoid interpreting unpopulated fields as proof of zero hardware errors. The change removes the recorded statistics-read path; it is not a claim to fix every possible Ethernet failure.

## Reproduce the candidate

In an isolated ARM cross-build environment with the previously reviewed source trees:

```sh
python3 tools/build-safe-eth-stats.py \
  --source /build/al_eth-standalone/src \
  --kernel /build/linux-6.12.114 \
  --output /build/new-safe-statistics-candidate
```

The tool refuses existing output, checks the original and patched main-source hashes, requires the exact prepared `6.12.114-eyeq-ts431xeu-freeqnap1` ABI, applies the source patch without fuzz, runs a fixture against the actual patched callback, and compiles a separate ARM module. It records the module hash and explicitly marks physical validation and installation false. It performs no installation, module loading, reboot or flash operation. The standalone validator can also be run with `tools/validate-safe-eth-stats.py --source PATH_TO_PATCHED_al_eth_main.c`.

Two isolated builds passed on 10 November. The callback fixture verifies multi-queue sums, 64-bit totals, down-state handling, other-board behavior and no hardware-statistics call on the exact board. The compiled module reports the matching ABI and `freeqnap_stats=software-queues-v1`. These are compilation and fixture results, not physical hardware acceptance. The private build directories and module binaries remain outside public Git.

## Hardware activation and permanent installation

The selected remote UART recovery path was verified before activation.
Fixed-image RAM boot, original-image RAM rollback and a second fixed RAM boot
passed on the physical NAS. The second fixed RAM observation lasted 601 seconds.
Following explicit approval of the exact first-slot write plan, the independently
backed-up first NAND boot slot was programmed once and readback verified. The
matching disk-root module was installed without unloading the active driver.
An ordinary restart then booted the installed image without UART interception or
network loading. No SPI bootloader, second slot, data partition or USB disk was
changed. See [hardware acceptance and limits](REMOTE-UART-ETHERNET-VALIDATION-2026-11-11.md).

The installed kernel retains the accepted 6.12.114 ABI. This focused repair does
not complete the separate hardened-kernel update. The preserved older bootstrap's
missing newer policy helper remains an explicit acceptance limitation. The RAM
source package stays flash-prohibited; only the separately reviewed, identical
accepted artifact was promoted for the approved installation.

## Changes already deployed

Guessla's media bridge uses one authenticated SSH control master for catalog and artwork/source requests, with a 30-second reconnection cooldown after failure. This reduces connection load but does not repair the kernel fault. FreeQNAP's separate Apple approval recovery control is deployed; see [Restore Apple web access](ICLOUD-ACCESS-RECOVERY.md).

## RAM-only packaging

`tools/build-safe-eth-ram.py` creates a separate kernel/bootstrap build from the
hash-pinned accepted baseline. Supply the exact kernel tree, generic bootstrap,
baseline release directory, reviewed module and a new output directory. It never
connects to a NAS, loads a module or writes flash. It verifies that only the
Ethernet module differs in the embedded bootstrap and records the legacy baseline's
missing newer policy-helper limitation. Its manifest requires explicit RAM-only
verification and is rejected by ordinary installation. The later hardware acceptance and separately approved installation are recorded
in the linked validation report.
