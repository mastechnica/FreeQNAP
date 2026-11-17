# Optional AuraView EyeQ Connector App

I authorized this optional integration on 11 November 2026. EyeQ labels
this NAS **AuraStore**; FreeQNAP retains its own product identity locally.

The app lives in `apps/auraview-eyeq-connector/`. See its README for installation,
per-user pairing, service instances, permissions, revocation and rollback.
It shares already indexed media and explicitly selected media shares through an
outbound authenticated TLS connection. It does not import the EyeQ cloud app,
fleet management, telemetry collection or storage administration into FreeQNAP.

Each pairing fixes an existing local NAS account. Every request uses the native
permission gateway; disabled accounts and revoked permissions block access.
Remote requests cannot select another account, arbitrary file paths, shell
commands, URLs, scans or writes. Credentials are mode 600, never committed.
Cloud originals are not retained; media is streamed to the authenticated user.
Synthia receives only metadata from searches the user requests.

Run `python3 -m unittest discover -s apps/auraview-eyeq-connector -v`.
Five standalone tests cover sanitized results, opaque folder references, excluded
symlinks/non-media files, unsupported operations, atomic private configuration,
and account checks between chunks. EyeQ additionally tests native permission
routing, account isolation, pairing, revocation, websocket RPC, and HTTP ranges.

Hardware acceptance remains pending: both the established LAN SSH route and the
existing AuraView private route timed out before authentication on 11 November.
No NAS install, service restart or storage operation was performed. Do not
confuse the passing fixtures with a live NAS streaming test.

The distribution copy in the AuraView repository is
`deploy/eyeq/connectors/aurastore/`; its deterministic source archive is offered
from Devices & data. Keep source copies identical when releasing.
