# Remote dashboard preparation — 7 November 2026

Historical preparation record. I subsequently approved a dedicated DNS
hostname on existing port 443; see [completed activation](REMOTE-ACCESS-ACTIVATION-2026-11-07.md).

Status: private tunnel and private end-to-end proxy verified; public activation
and launcher switch are pending explicit approval after automatic review rejected
opening the additional public HTTPS port. This is not yet a usable off-LAN URL.

I requested an additional connection to their existing private hub and an
updated identity-provider launcher card. Inspection verified the existing hub and
peer allocations, the NAS's supported userspace WireGuard package and TUN device,
and the dedicated local HTTPS/console setup. No kernel change was needed.

A new NAS-specific key was generated on the NAS and its public key registered as
a distinct host-only peer on the hub. Other peers were not changed or reloaded.
The NAS route includes only the hub address; its original LAN default internet
route remains unchanged. The interface is boot-enabled with keepalive, the hub's
verified MTU and a dedicated input firewall. No home LAN forwarding was enabled.

The NAS web proxy binds only the private interface, allows only the hub source,
and forwards to the existing loopback console while removing claimed identity
headers. The isolated edge proxy currently binds localhost only and loads the
existing valid public certificate through systemd credentials. It runs with a
dynamic unprivileged account. Certificate renewal is checked hourly, with key
matching and expiry checks before a dedicated-proxy restart. No shared hub proxy
or identity service was restarted.

The NAS console was restarted once for the exact additional HTTPS origin. The
background broker retained its process identity, with iCloud connected, unpaused
and downloading afterward. The existing local callback remains selected while
public activation is pending. An exact strict future remote callback was added
to the existing provider; the original callback, client/issuer/subjects, linked
accounts, password hashes, roles and library permissions were preserved. The
launcher card has not been switched to an unreachable destination.

Retained preparation issues: two provider mutations refused incompatible model
representations and rolled back before changes; the installed data class and
concrete backing field were inspected before the successful narrow update. The
dedicated edge proxy initially could not traverse its newly created executable
directory. That directory contained only the new public executable, its mode was
corrected, and only the dedicated local proxy was restarted. Failure evidence and
unit history remain; unrelated services were not restarted.

End-to-end private acceptance used ordinary public-certificate validation and the
actual encrypted tunnel: dashboard and session status returned 200, unauthenticated
account and NAS status returned 401, and wrong-origin login returned 403. The
edge listener was confirmed localhost-only; the rejected public firewall change
was never executed. Current tunnel handshakes and the original internet route
were verified. Raw configurations and receipts remain private, outside Git.

Remaining: explicit approval for the exact public HTTPS listener; public/off-LAN
verification; coordinated remote callback and launcher update; real family/admin
SSO, media and phone PWA acceptance; restart/cold-start validation. No publication
of this repository or private history was performed.
