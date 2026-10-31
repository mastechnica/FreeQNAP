# Local network control panel

Network controls physical Ethernet ports with explicit port/MAC identities. It supports a DHCP client or manual IPv4 address/prefix, default gateway, DNS servers, MTU, route metric, static IPv4 routes and automatic/disabled IPv6. Only explicitly managed ports receive a generated profile; other installed profiles remain available. The first matching networkd profile actually in use is checked before accepting application.

A change has a separate confirmation step. After the independent network agent applies it, reconnect if necessary and confirm successful administration within 120 seconds. Failure, expiry or an interrupted agent restores the previous configuration and its owned profile files. Dashboard/broker connectivity is not required for the rollback timer. Keep a local console available for commissioning; rollback cannot repair a physically disconnected cable or an external router change.

## Optional private LAN

Private LAN is **disabled by default**. No DHCP server is enabled on a physical port by installation. Select a dedicated port connected only to an isolated cable or switch segment before enabling it. Do not attach its DHCP server to an existing home/business LAN.

Configure the NAS's private address, DHCP range and lease duration, upstream DNS, allowed NAS TCP ports and client internet policy. Overlapping live/configured networks, duplicate reservations, invalid gateways and changed physical identities are rejected. The private port is IPv4-only in this milestone. Ordinary port profiles may retain automatic IPv6.

Internet policies are NAS access only, a selected physical uplink, or VPN only. NAS access only advertises no default gateway. VPN-only forwarding uses the existing OpenVPN/WireGuard client and its no-fallback policy; losing the tunnel must not move clients onto the ordinary uplink. Direct-uplink routing is refused while a VPN client is configured. The physical uplink remains the existing management LAN, not a replacement for a separately hardened public-WAN router.

The firewall blocks unlisted access to the NAS and unsolicited inbound routed connections from private clients. DHCP, DNS and rate-limited ping have explicit rules. Other routed traffic is denied except the separately authorized VPN paths. Disabling the private LAN does not leave general physical-port forwarding open. Rules are confined to FreeQNAP's own table; no global firewall flush is used.

## Clients

The client list combines DHCP leases, neighbor observations and saved records. Give a client a hostname, notes, reserved IPv4 address and block/unblock policy. Changes are reviewed and use the same confirmation mechanism. Blocked MACs are denied before established-connection allowances; observed/reserved blocked IPs also block return traffic. DNS/DHCP runs under its own account and has no access to the privileged broker group.

MAC/IP controls are not device authentication. A client can spoof an identity. This firewall controls NAS and routed access; it cannot isolate two peers exchanging traffic directly through an external switch. Use switch port isolation/VLANs or separate physical segments where that isolation is required. Historical leases may appear after a device disconnects; observation is not proof of present reachability.

Implementation references: [systemd network profiles](https://www.freedesktop.org/software/systemd/man/latest/systemd.network.html), [dnsmasq's official manual](https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html). Physical-port changes, DHCP clients and VPN gateway behavior need separate acceptance from parser/rendering tests.

## Recorded validation

The native ARMhf campaign passed 17 isolated packet cases, including real DHCP DISCOVER/OFFER/REQUEST/ACK with a reserved address under the unprivileged service account, no DHCP on the uplink, blocked renewal, allowed/denied NAS services, block/unblock, selected-uplink NAT, combined VPN policies and tunnel-loss denial of physical-WAN fallback. These tests used virtual links; they did not enable DHCP on a physical port.

A separate test applied a temporary manual address only to an unplugged LAN2 port. With no confirmation, the independent controller removed that address and its owned profile after 120 seconds, restored the prior settings and retained management access on LAN1. Private DHCP remained inactive. Parser/state tests additionally cover failed application, interrupted changes, cross-boot recovery and a confirmed change surviving restart before pending-file cleanup. Real private-LAN client/switch commissioning remains outstanding.
