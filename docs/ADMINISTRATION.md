# Local administration

There is no cloud enrollment, remote telemetry, shared password or imported application configuration. OS access and the console administrator are separate credentials.

## Console installation on converted Debian

The installer below only adds the FreeQNAP console and read-only collector. It does not format disks, change flash, assign network addresses or enable file shares. Review the source first. Run on a matching armhf TS-431XeU with Python 3, smartmontools, util-linux and systemd available:

```sh
sudo sh deploy/install-console.sh
```

The root-owned collector refreshes an inventory file readable by the `freeqnap` group. The web service runs as the unprivileged `freeqnap` system account with a read-only application tree, no device access and no capabilities. Old code generations remain under `/opt/freeqnap/releases`; reinstalling does not replace private state or select a data layout.

Initialize a console password privately in a real SSH terminal:

```sh
cd /opt/freeqnap/current
sudo -u freeqnap python3 -m freeqnap.cli init-admin
```

This prompts twice without echo and refuses to overwrite an existing administrator. No password goes into chat, arguments, Git or the release image. The initial console displays a setup-required screen until completed. OS root can remain locked with key-only SSH; use `passwd` independently when desired.

Forward the console from your own computer, substituting the actual NAS address and administrator account:

```sh
ssh -N -L 8080:127.0.0.1:8080 YOUR_ADMIN@YOUR_NAS
```

Open <http://127.0.0.1:8080>. The SSH channel protects transport. The console deliberately binds only to NAS loopback and does not accept forwarded-identity headers. Cookie sessions are private, expire after twelve hours and require same-origin JSON plus a CSRF token for operations. Optional LAN HTTPS can be commissioned with a private local CA; see [local HTTPS](LOCAL-HTTPS.md). It preserves this SSH endpoint. No public Internet endpoint is configured. Close the tunnel when finished.

## Health and backup checks

```sh
systemctl status freeqnap-console freeqnap-collect.timer
journalctl -u freeqnap-collect -u freeqnap-console
```

Inventory older than two minutes is visibly stale. Missing SMART data is unavailable, not a pass. A healthy OS mirror is not proof that a data pool exists or that recovery works. The activity list retains retryable backup failures. Daily scheduling is off until the owner chooses a policy; see [backups](STORAGE-BACKUPS.md).

## VPN, gateway, downloads and media approval

See [the local network/download guide](VPN-DOWNLOADS-MEDIA-ACCESS.md) for controls, isolation tests and remaining commissioning gates.

## Kernel maintenance

See [the dated kernel/security review](KERNEL-SECURITY.md) for current-series verification, package updates and the uninstalled native VPN candidate.

Debian package updates do not automatically rebuild or replace this custom NAND kernel. Linux 6.12.114 is the tested source base, not a perpetual “all CVEs fixed” claim. Review the maintained upstream branch, Alpine drivers and configuration for each update, build matching modules, validate in RAM, retain original backups and prove rollback before offering a public update mechanism. No automatic kernel flash updater is provided.

The currently accepted cooling mode is fixed full speed. Do not disable cooling services or substitute an untested curve to reduce noise. Watchdog expiry, wake, SuperSpeed, 10GbE and complete restoration retain the limits in the acceptance ledger.


Local health, optional encrypted email, installable PWA and browser push are described in [Health & notifications](HEALTH-NOTIFICATIONS.md). Optional provider profiles are under [Dynamic DNS](DYNAMIC-DNS.md). Both outbound features remain disabled until explicitly configured; no firewall exposure is implied.

## TS-431XeU USB write workaround

The tested Etron EJ188 controller needs a 128-byte PCIe maximum read-request limit on this board. Native NAS provisioning installs `freeqnap-usb-pcie.service`; the separately callable installer is `deploy/install-usb-pcie.sh`. The helper refuses other boards, PCI functions/revisions/classes and unreviewed settings, preserves unrelated bits and verifies readback. Check `systemctl status freeqnap-usb-pcie.service` and its current-boot journal before writable USB use. After a manual PCI-function reset, restart this service before writing; reset may restore the failing default. The helper neither resets a controller nor formats/mounts a disk.

Disabling the unit does not undo an already programmed volatile register; a later reset/boot returns the hardware default and can reintroduce the write fault. Preserve read-only quarantine during rollback/testing. See [physical test evidence and limits](USB-TR004.md).
