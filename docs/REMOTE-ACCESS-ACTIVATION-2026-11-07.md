# Remote dashboard activation — 7 November 2026

Status: explicitly approved hostname active over standard public HTTPS; the existing
identity-provider launcher and exact callback now use that hostname. The earlier
private-only preparation is superseded by this activation.

After I created DNS, its answer was verified against the existing private
hub's public address. A distinct hostname route was added to the existing public
Caddy instance, candidate-validated and applied with a graceful reload. Ordinary
public certificate validation and hostname coverage passed. Caddy manages renewal.
No additional public firewall port was opened; the draft localhost-only edge
listener and its certificate timer were disabled. The NAS upstream port remains
bound only to the encrypted tunnel and restricted to its hub source.

The NAS console retains local HTTPS origins and accepts the exact approved remote
origin. Its supported identity-settings function selects the new strict callback.
The original local callback remains registered, the unused draft port callback was
removed, and the existing launcher card points to remote cloud sign-in. Issuer,
client credentials, immutable subjects, signing key and application access bindings
were preserved. NAS account links, password hashes, roles and library permissions
were verified unchanged. Local passwords still work offline; cloud sign-in returns
through the remote origin and requires internet. Existing cloud sessions may need
fresh login after the identity-setting change.

Acceptance used actual public DNS and normal HTTPS verification: dashboard,
session endpoint, PWA manifest and photo code returned 200; unauthenticated account
and NAS-status requests returned 401; wrong-origin login returned 403. OIDC start
returned the correct identity provider and exact public callback with S256 PKCE
and a Secure binding cookie. The existing local HTTPS endpoint still returned 200.
The private tunnel, private proxy and local HTTPS services were active, the NAS
internet route was unchanged, and the background broker retained its process
identity with iCloud connected, unpaused and downloading.

No NAS reboot, storage mutation, notification change, shared hub container restart,
account creation or password change occurred. Actual phone/family SSO, installed
PWA, external-network media playback and restart/cold-start behavior remain manual
acceptance checks. This report does not claim a completed browser token-exchange
round trip. Secrets, deployment addresses, raw provider records and private host
configuration remain outside this public-source documentation. No source/history
was pushed or published.
