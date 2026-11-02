# VPN, gateway, downloads and media-player approval

This is a local implementation and acceptance record, not a published binary release. No provider account, public VPN listener, router port forward, data-pool layout or download job is preconfigured. Administration uses the authenticated local console. Use SSH-protected loopback until trusted local HTTPS is commissioned.

## OpenVPN and WireGuard

The **VPN & gateway** workspace configures one outgoing client and one incoming server independently. Either role can use WireGuard or OpenVPN. Both client types use the same firewall, forwarding policy, route table and confirmation/rollback mechanism.

For an outgoing connection:

1. Obtain the provider's numeric endpoint IP, port, tunnel DNS and keys/certificates through a private channel. Hostnames are deliberately not resolved before the tunnel. WireGuard needs the assigned tunnel address, private key and provider public key, optionally a preshared key. OpenVPN uses inline CA/client certificates, private key and the exact expected server certificate name; optional provider login and tls-crypt are supported.
2. Select the directly connected management LAN and its exact private IPv4 CIDR. No LAN address, DHCP configuration or router setting is changed.
3. Select **Route all NAS internet traffic through this VPN** for NAS-wide full-tunnel routing. The default is enabled. Its persistent kill switch permits the explicitly retained LAN, loopback, VPN traffic and marked transport sockets. Ordinary IPv4, IPv6 and DNS fallback is blocked. A missing tunnel, failed handshake or stopped runtime does not restore normal WAN internet.
4. Optionally list LAN clients allowed to use the NAS as their gateway, using explicit IPv4 hosts/networks inside that LAN. Empty means no LAN forwarding. Only those sources may forward through the VPN, with NAT. Return traffic must belong to an initiated connection. Other forwarding is denied.
5. Review the redacted plan and type its confirmation. Confirm the local connection within 120 seconds. The independently supervised VPN runtime restores the previous configuration after timeout even if the browser or broker disappears. Local reachability confirmation is not proof of provider connectivity: verify handshake, DNS and external egress separately.

A VPN client interface is an **untrusted WAN**. Its input policy allows replies to NAS-initiated connections and rejects unsolicited traffic. No inbound port forwarding from a commercial VPN is enabled. The firewall changes only `inet freeqnap_vpn`; it never flushes the system ruleset.

Rules use a dedicated routing table, preserve explicitly declared directly connected management networks, and retain unreachable defaults to prevent policy-routing fallback. Tunnel DNS is assigned through systemd-resolved for NAS full-tunnel mode. The firewall blocks non-tunnel DNS even if a resolver tries another link. The early boot firewall unit runs before network setup, and networkd requires it; failures must be treated as unavailable protection, not green connectivity.

### Gateway clients

Set each selected client's IPv4 gateway to the NAS's LAN address. Configure DNS reachable through the tunnel. The NAS does not become a DHCP server, DNS proxy, transparent interceptor or LAN router automatically. Forwarding is explicitly IPv4-only in this milestone. A LAN client with a separate IPv6 route to another router can still use that route; configure that client/VLAN accordingly. NAS-originated IPv6 internet has no physical-WAN fallback when full-tunnel protection is enabled.

### Incoming server

Select a private, nonoverlapping /24–/28 server network, UDP port, external hostname/IP, allowed NAS TCP ports and optional LAN routes. Remote clients get only the declared NAS services and LAN destinations. Internet forwarding for remote peers requires the outgoing VPN; it does not use the ordinary WAN as fallback. No router UPnP/NAT-PMP mapping is requested. Arrange a manual port forward only if needed and deliberately approved for your own network.

For WireGuard, generate the private key on each client and register only that client's public key, name and unique address. The dashboard shows the server public key and exports a setup template; insert the client private key on that client only. Revocation removes its active key and saved peer entry. For OpenVPN, the NAS creates a private local CA and server certificate. Issue a uniquely named client profile and download it privately. The CA private key is never exported. Revocation updates the CRL and restarts the server to disconnect authenticated sessions as well as prevent new ones.

Private VPN configuration stays in root-only local files. Plans/status/activity exclude client private keys, certificates, provider login and passwords. No raw OpenVPN configuration, scripts, plugins, wg-quick hooks, arbitrary file paths, obsolete encryption, compression or TAP bridging are accepted. This is intentional; it is not universal provider-profile compatibility. Provider interoperability, remote device clients, MTU, sustained performance and real WAN interruptions still need acceptance.

Local emergency recovery, from UART/console as root: stop `freeqnap-vpn`, then run `python3 -m freeqnap.nas.vpn_runtime --disable` from the installed application directory. This explicitly returns ordinary WAN routing; it is never performed just because the tunnel fails.

## Download manager

Choose a mounted writable data pool and set concurrency, download/upload limits, seeding ratio and maximum seeding time. Downloads run as a separate unprivileged account with a private loopback RPC token, a read-only system view and a pinned writable data-directory bind. The service depends on the pool mount; a missing/locked or changed filesystem must stop it rather than write into an empty OS directory. Switching a pool does not silently move existing data/history.

Add HTTP/HTTPS URLs, BitTorrent magnet links or a torrent file up to 512 KiB. A URL can have an expected SHA-256. File/FTP URLs, embedded HTTP login, arbitrary engine options and shell callbacks are refused. Signed URLs are private queue data, not public activity text. Torrents upload while downloading, even when post-completion seeding is disabled. No external torrent or media test audio is generated automatically.

The root-owned queue is committed before submission. Each job has a persistent GID, so an ambiguous RPC reply is reconciled rather than blindly duplicated. The engine saves its session and partial-file control state frequently, supports HTTP Range resume, checks TLS certificates and retries interrupted transfers. Permanent failures remain visible and retryable; one failing item does not stop later jobs. Pause/resume intent survives process restart; restored engine tasks start paused until the durable desired state is reconciled. Reconciliation rotates in bounded batches and releases the storage lock between items. Removal stops the task and retains files, accessible in **Retained files**. File browsing/downloads reject symlinks, nested mounts and paths outside the recorded job and filesystem identity. Completed and partial files are not silently overwritten or deleted.

A completely full destination can damage aria2's partial-download control file.
When the engine reports that condition, FreeQNAP stops automatic retries for that
job and shows a fixed recovery message while preserving the job and partial files.
Other jobs continue. Resume is refused until manual reconciliation; alternatively
start a new download in its own fresh job directory. Removing the old job keeps
its files. No automatic deletion or reconstruction of damaged markers is claimed.

Downloads follow the NAS routing policy. To require VPN-only transfers, use and validate full-tunnel NAS routing and its kill switch. This milestone does not claim per-download VPN namespaces or IPv6 gateway service.

## DLNA approval

In **Media library**, select a designated media share, enable DLNA, and confirm enabling the approval policy. Until explicitly approved, a client receives neither catalog nor stream responses. Have the player search for media servers, refresh the requesting-client list, label the observed device and approve it. IPv4 and IPv6 addresses require separate explicit approval. Revocation applies to new and ongoing packet delivery; previously cached/downloaded content cannot be recalled.

Multicast announcements are suppressed, so approved players may need to rescan. The pending list comes from network requests, not a promise that arbitrary switched-LAN devices can be passively enumerated. The dedicated `inet freeqnap_dlna` rules protect the catalog port and all TCP/SSDP replies from the media-service UID, including a fallback HTTP port. The media service remains stopped if applying the policy fails, and is bound to broker availability.

Approval binds LAN interface, observed IP and Ethernet address. It is **not cryptographic authentication** and does not defeat a hostile LAN device spoofing another approved device. Use a trusted LAN/VLAN or authenticated encrypted SMB/HTTPS when that stronger identity is needed. DLNA remains direct-play: the actual player must support the content's codec.

## Acceptance and remaining work

Executed on the ARMhf NAS, using disposable network namespaces and generated local data, without modifying its live LAN routes:

- Default-deny DLNA IPv4/IPv6, pending-client observation, explicit approval, address separation, revocation and fallback-port denial.
- VPN unsolicited-input denial, NAS-initiated replies, preserved local administration, selected-client NAT/forwarding, denial of other gateway clients, and no physical IPv4/IPv6 fallback after simulated tunnel loss. Negative tests included a functioning fallback service.
- Actual encrypted WireGuard userspace peer traffic and handshake; OpenVPN mutual-TLS traffic and refusal of a revoked certificate.
- Real aria2 interruption/restart, saved partial-file state, nonzero HTTP Range resume, complete SHA-256 readback, rejection of unauthenticated RPC and unknown-GID response handling.
- Host tests for private redacted plans, configuration injection/scope refusal, stale runtime confirmation, ambiguous download admission, durable pause and failure isolation.

These are isolated native fixture tests, not external-provider/physical client acceptance. Full early-boot protection, systemd namespace/mount-loss behavior, runtime rollback under abrupt service interruption, external torrent-peer interoperability and complete full-destination torrent recovery still need acceptance, as do intended client applications. Later RAM-kernel and local-peer results are recorded separately in the dated validation reports. The native control services are installed and verified with unconfigured defaults. Real data pools and external VPN/media/download use remain uncommissioned until the relevant gates and a reviewed owner-selected storage plan are complete. Do not present this source checkpoint as a turnkey public release.

Primary references: [WireGuard routing](https://www.wireguard.com/netns/), [WireGuard userspace implementation](https://github.com/WireGuard/wireguard-go), [OpenVPN 2.6 manual](https://openvpn.net/community-docs/community-articles/openvpn-2-6-manual/), [aria2 manual](https://aria2.github.io/manual/en/html/aria2c.html), [nftables manual](https://netfilter.org/projects/nftables/manpage.html).
