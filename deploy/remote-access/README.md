# Optional private-hub remote access

This optional deployment connects the NAS to an owner-controlled WireGuard hub.
It is separate from the selectable user VPN/gateway profile, and must not replace
that profile or install a default internet route. Generated keys, exact addresses,
hostnames and running configuration belong in ignored private evidence only.

Deployment components:

- A dedicated WireGuard interface with a host-only hub route, NAT keepalive and
  the hub's verified MTU. When kernel WireGuard is unavailable, the installed
  distribution wireguard-go implementation can provide the existing wg-quick
  interface. Never install an unverified binary or change the kernel implicitly.
- A dedicated firewall table accepting the hub web-proxy port and bounded ICMP
  diagnostics on this interface, with other incoming traffic dropped. Other VPN,
  private-LAN and default-route settings remain unchanged. No NAS SSH, SMB, NFS,
  private LAN forwarding, or other peer access is implied by dashboard access.
- A separate non-root NAS HTTP proxy bound only to the WireGuard address and
  allowing only the hub source. It forwards to the console's loopback listener,
  strips claimed user identities and asserts the exact configured public host
  and HTTPS scheme. The public edge terminates HTTPS with a valid certificate;
  WireGuard encrypts the entire private upstream transport.
- A dedicated unprivileged edge HTTPS proxy with narrowly loaded TLS credentials,
  isolated from shared identity/proxy services. Its certificate refresh helper
  checks validity and key match before restarting only that dedicated proxy when
  the existing public certificate changes. No certificate or private key is
  shipped in source.
- An exact additional console origin. Keep local origins and local passwords
  usable. Use the supported identity settings path for the new strict callback;
  preserve issuer, client credentials, immutable subjects, local mappings and
  family permissions. Keep the previous callback registered for rollback.
- The existing identity-provider launcher card is updated only after the remote
  URL is publicly reachable and authenticated browser acceptance is complete.
  Do not loosen card policies or enable automatic account provisioning.

Before any public activation, review the precise listener, firewall rule, login
surface and rollback. If publication/exposure is blocked by approval review, keep
the edge listener local-only and the launcher/local callback unchanged. Never
work around a rejection by opening another port or indirectly editing a firewall.

Validation should include a fresh tunnel handshake, unchanged original default
route, ongoing background downloads, exact origin/callback validation, HTTPS chain
verification, unauthorized account/NAS requests rejected, wrong-origin mutation
rejected, then a real authorized browser login and media/PWA access. Tunnel ping
alone does not prove the application. Preserve failed installation evidence and
verify restart persistence separately; do not label untested reboot/cold-start or
physical phone behavior accepted.

The deployed standard-port configuration uses a dedicated hostname in the existing
public Caddy instance, which manages its certificate automatically. The separate
manual-certificate edge proxy/helper was preparation only and is disabled there.
See the dated activation report for exact accepted behavior and remaining checks.
