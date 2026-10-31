# Kernel and security maintenance

## Check recorded 30 October 2026

The installed base is **Linux 6.12.114**, released upstream on **21 October 2026**. Kernel.org now lists **6.12.115**, released **30 October 2026**, as the newest maintained **6.12 LTS** release. The running NAS is therefore one stable update behind. A separate candidate has compiled and passed artifact checks; it has not replaced the installed image. The 6.12 branch remains maintained; a higher major/minor version is not required merely to receive its backported stable fixes.

Release comparison establishes version currency only, **not** a complete configuration-specific CVE applicability audit, proof that every fix exists in external Alpine drivers, or a claim of no unknown vulnerabilities. Future releases must be reviewed. The Linux kernel security guidance recommends complete stable updates rather than selecting only individually numbered CVE patches.

The local read-only check is:

```sh
python3 tools/check-kernel.py --kernel YOUR_RUNNING_KERNEL_VERSION
```

It reads the maintained release list over verified HTTPS, reports the running base, current release and whether the series is active, and fails explicitly if verification is unavailable. It does not flash an image or pronounce the system CVE-free. Debian `apt` updates do not replace this custom NAND kernel.

Direct verified HTTPS access and Debian main, trixie-updates and trixie-security metadata refresh were rechecked after the owner restored upstream connectivity. The signed package simulation reported zero pending upgrades. `deploy/configure-security-updates.sh` records this guarded conversion, retaining the old source configuration privately and refusing unknown/repeated replacements; it does not upgrade packages or reboot. No Mac package mirror is required for subsequent direct updates.

The earlier native NAS package update campaign also applied the available Debian security/point updates for OpenSSL and its providers, Expat, liblzma, PCRE2, Brotli and CA certificates, plus timezone data. The affected long-lived services and systemd manager were then refreshed. A fresh process-map scan found no remaining process using the replaced security libraries. SSH/LAN access returned, no systemd unit was failed, and the OS mirror remained healthy. No chassis reboot or kernel flash was needed for this userspace update. This does not imply that the uninstalled VPN kernel candidate has passed RAM-boot or physical acceptance.

## VPN-capable candidate

The accepted installed kernel lacks TUN and native WireGuard. A matching TUN module was built and tested in memory, without forcing version compatibility or changing flash. Official Debian WireGuard userspace and OpenVPN packages passed encrypted traffic tests in isolated namespaces.

A separate **6.12.114 FreeQNAP native VPN candidate** has also been built with TUN and WireGuard built in and matching Ethernet, thermal and optional loop modules. Its image and checksums remain private local artifacts, explicitly marked **not installed / RAM boot not yet tested**. Existing installed NAND and U-Boot settings are unchanged. The board feature fragment records the added options, not physical acceptance of the candidate.

`tools/build-native-kernel.sh` documents this separate build from the already reviewed prepared source tree. It refuses an existing output directory and keeps the accepted build separate. This is not yet the clean-source, pinned public release builder. Complete corresponding source/license packaging, source authenticity verification, immutable manifests and release signing remain publication gates.

For any future update: check active upstream release and security announcements; audit upstream changes plus board/external-driver patches; build matching modules and root artifacts; validate the image in RAM with recovery UART available; repeat networking/restart/SATA/USB/cooling/LED/button/storage checks; prove rollback and original-flash backup availability; only then review permanent installation. Never force-load a mismatched module or flash an untested candidate to avoid an optional driver dependency.

Sources: [current kernel releases](https://www.kernel.org/), [release JSON](https://www.kernel.org/releases.json), [maintained branches](https://www.kernel.org/category/releases.html), [kernel CVE process and applicability](https://www.kernel.org/doc/html/latest/process/cve.html).

The optional private-LAN firewall also needs nftables' `limit` expression. A matching `nft_limit` module was built from the accepted upstream tree and verified against the running kernel's vermagic before loading. This adds rate-limited ICMP without a flash write or kernel reboot; it is not a kernel security-version update. `tools/build-optional-module.sh` records the build path, and the NAS feature fragment includes it for subsequent full builds.

## Stable-update and root-survivor candidate

The 6.12.114 → 6.12.115 incremental source archive matched kernel.org's cryptographically verified signed checksum list. The checksum autosigner public key was obtained through kernel.org's HTTPS Web Key Directory in a temporary isolated keyring, fingerprint `B8868C80BA62A1FFFAF5FDA9632D3A06589DA6B1`. The archive SHA-256 is `aedeff550cf0d1f062310369e4dae908b46bccb0b8e9bb2d9b69c5c5f83d2a75`. This authenticates that incremental archive; it does not turn the existing prepared development tree into the still-pending clean public source build.

The entire increment applied to a separate copy with zero fuzz and no offsets. The accepted board device-tree source hash was preserved; the failed USB noncoherency experiment is excluded. Matching Ethernet, thermal, final power-off and optional modules were rebuilt together. The 6.12.115 FreeQNAP5 candidate passed legacy ARM image/header/checksum validation, all nine module version checks, and module dependency-index checks. Ordinary installer verification rejected it as required. The external Ethernet/HAL build still emits fallthrough, missing-prototype and stack-frame warnings; compilation is not an external-driver security audit. The candidate also embeds the restricted root-survivor selector described in [boot recovery](BOOT-RECOVERY-CANDIDATE.md). Its manifest explicitly permits RAM diagnosis only and prohibits flash installation. Compilation, checksums and disposable loop tests do not establish physical board acceptance or resolve the TR-004 controller fault. The installed 6.12.114 image remains in place while the new data RAID synchronizes.

Source verification follows [kernel.org's signature guidance](https://www.kernel.org/signature.html). Review the [complete stable changelog](https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.12.115), not just selected CVE numbers; configuration-specific and external-driver review remains open.
