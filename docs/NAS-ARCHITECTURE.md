# Full NAS implementation

The owner authorized the NAS expansion on 29 October 2026: SMB, NFS and AFP, shared-file backup/restore, encrypted volumes, media indexing/scraping/discovery, a complete manual dashboard and a guided installer. GitHub publication remains review-gated. This document is the implementation contract, not a declaration that every item is operational.

## Native services

- Samba for authenticated SMB3, Apple-compatible extended attributes and optional Time Machine shares.
- NFS-Ganesha VFS for explicit NFSv4 exports. The current board kernel has export handles but no NFSD module; the userspace server avoids changing the accepted boot kernel merely to serve NFS. Client networks and access mapping must be explicit.
- Netatalk for optional AFP/DHX2 and Bonjour discovery. AFP and AUTH_SYS NFS do not provide encrypted file transport; enable only for explicitly chosen trusted clients. SMB3 encrypted transport is the preferred default.
- cryptsetup/LUKS2 over a data MD array, ext4 inside. Password/key unlock is manual by default. Unlock secrets never enter durable job payloads, Git, logs or shell arguments. Key/header backup and loss consequences must be visible.
- Restic for encrypted, versioned shared-file backups, repository checks and staged restore. A partially readable backup is unsuccessful, never a verified complete snapshot. Retention requires a verified replacement; pruning is explicit.
- Gerbera for UPnP/DLNA and direct media playback, plus a FreeQNAP media library/index and authenticated HTTP/SMB access. External metadata lookup is opt-in. Existing local NFO/artwork is usable without cloud credentials. Client codec/protocol support must be tested; no ARM transcoding performance is promised.

Debian ARMhf packages are used where available. Current Jellyfin releases dropped ARM32 support; do not ship an old unsupported release to obtain a media UI. Current OpenMediaVault also dropped ARM32 through its Salt dependency; FreeQNAP remains independent native Debian administration.

## Privilege boundary

The browser talks only to the authenticated unprivileged FreeQNAP web service. A root-owned Unix-socket broker accepts a fixed operation schema from that service's UID using peer credentials. It has no raw shell, arbitrary service, arbitrary path or generic block-write endpoint. The broker independently validates all device, mount, account, plan and secret inputs.

All state-changing storage work uses a fresh root-owned review plan, immutable disk/partition/array/filesystem identities, an exact confirmation and a durable operation ledger. Interrupted destructive work is never automatically retried or inferred complete. OS partitions and ancestors remain protected; allocating a new free-tail data partition on an OS disk is a distinct region-aware plan, never a whole-disk erase.

Mount identities are checked before use. Unmounted volume underlays are root-owned and inaccessible to file-service users. Service reconciliation removes unavailable/locked shares, and volume locks stop dependent services before unmount/close. Missing mounts must not redirect writes to root. Tests must include real mount-loss behavior.

The dashboard must expose operation results, failures and retry/reconciliation states. No disabled control may masquerade as a working feature. Secrets are entered privately through SSH-protected loopback or trusted local HTTPS. An optional first-run enrollment token permits private browser administrator setup without a default password.

## Manual dashboard workspaces

Overview; disks/SMART; pools/RAID/create/import/replace/check; encryption unlock/lock/recovery key/header; shares and users/permissions; files and staged restore; backup repositories/jobs/retention/checks; media libraries/scan/metadata/discovery; local settings/security; service/activity/recovery logs; installation and recovery tutorial.

Hardware failure/rebuild and full backup/restore drills remain owner-coordinated acceptance. The existing final-poweroff metadata issue must remain visible until fixed and physically retested. No original board photo may be published without redaction review, and no UART pinout may be inferred from appearance or another model.

## Primary references

- [Debian Netatalk ARMhf](https://packages.debian.org/en/trixie/armhf/netatalk)
- [NFS-Ganesha VFS](https://github.com/nfs-ganesha/nfs-ganesha/wiki/VFS)
- [Gerbera Debian ARMhf](https://packages.debian.org/trixie/armhf/gerbera)
- [Restic restore](https://restic.readthedocs.io/en/v0.18.0/050_restore.html)
- [Jellyfin ARM32 removal](https://jellyfin.org/posts/jellyfin-release-10.11.0/)
- [OpenMediaVault supported platforms decision](https://github.com/openmediavault/openmediavault/issues/1996)

## Host mount visibility without weakening broker isolation

The broker retains ProtectSystem, ProtectHome and PrivateTmp. Automatic approval review rejected a proposal to remove those restrictions, so that proposal was not applied. Mount/unmount requests instead use standard systemd transient mount units through PID1 (`systemd-mount`), restricted by the broker to exact registered devices and fixed FreeQNAP mountpoints. This makes host-visible mounts without moving an unconfined custom helper outside the broker or disabling its filesystem restrictions. A disposable loop fixture has now verified the mount UUID and file readback inside a service with the retained broker restrictions and on the host. Identical propagated mount aliases are deduplicated; different source/root/options still fail closed. Native mount-loss and real data-pool commissioning remain separate gates.

The owner additionally requires explicit per-client DLNA approval. Unapproved clients must not receive the media catalog or streams; a pending/approved/revoked device list and network enforcement are required. DLNA's weak device identity must not be presented as password-authenticated access. This supersedes the earlier open-LAN DLNA description.

## VPN and downloads expansion

The owner also authorized OpenVPN and WireGuard client/server roles, explicit LAN-to-VPN gateway forwarding, untrusted-WAN filtering, full-tunnel kill switches and a resumable URL/torrent manager. These remain local NAS features, without remote fleet management. See [network/download implementation and acceptance](VPN-DOWNLOADS-MEDIA-ACCESS.md) and [kernel currency](KERNEL-SECURITY.md).

File-manager and network-control implementation: [file operations and recycle policy](FILE-MANAGER.md), [physical ports/private LAN and timed rollback](NETWORK-CONTROL.md). The private DHCP account has a separate configuration directory/group and cannot access the privileged broker socket. Network rollback runs independently of the web process and storage jobs. Private LAN remains opt-in.
