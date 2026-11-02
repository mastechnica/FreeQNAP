# Agent API and network playback

FreeQNAP supports provider-neutral agents through local HTTPS. No model provider,
cloud service, shell, or separate agent runtime is required. The owner controls
credentials under **AI agent access** in the dashboard.

## Issue and revoke access

1. Sign in as the administrator and open **AI agent access**.
2. Name the agent, choose an expiry (1–365 days), and select its functions.
   Presets add explicit permissions; groups can be selected and cleared.
3. Create the token and save it in the agent's private secret store. It is shown
   once. Never put it in a URL, repository, screenshot, or shared conversation.
4. Revoke it from the agent list when access is no longer needed. To change its
   rights, issue a replacement with the new selection and revoke the old token.

**Rights are NAS-wide function permissions, not folder permissions.** A file
editor can modify shared folders across the NAS. A media editor can update all
indexed libraries. Do not grant file editing to an agent intended only to edit
metadata. File deletion, exports, network configuration, power controls and
storage creation are independent rights. New functions never silently expand
existing presets or tokens. Token management stays administrator-only.

Tokens contain 256 random bits; only SHA-256 hashes are stored. Credentials have
expiry and revocation checks on every request. The API limits each token to 120
requests per minute. Audit records retain operation, principal, time and outcome,
not request bodies, passwords or tokens. The last 10,000 records are retained.
Accepted means handed to the existing NAS handler, not verified physical success.
Queued work can continue after token revocation; inspect Activity before removing
access if a job is running. A change already executing cannot be undone by
revoking its credential.

## Discover and invoke operations

Use the NAS's trusted HTTPS address. Trust its private CA in the agent's HTTP
client; do not disable certificate verification. Send:

```http
Authorization: Bearer <private-token>
Content-Type: application/json
```

`GET /api/agent/v1` returns the exact operation IDs granted to this credential,
permission descriptions and capabilities. It does not disclose other tokens.
`POST /api/agent/v1/operations/<operation>` invokes one operation with its existing
JSON request body. Agent requests do not use browser cookies, CSRF headers or an
Origin header. Bearer credentials do not authenticate dashboard endpoints.

The checked-in [operation inventory](../freeqnap/agent_operations.json) covers
all fixed NAS broker functions, including status, disks, SMART, shares/users,
files, USB/encryption, backups/restores, media/scanner/metadata, downloads,
network/private LAN, VPN, DDNS, notifications, recovery and system controls.
Player operations below are additional gateway functions. Tests compare the
inventory against the real dispatch registry so new handlers require review.
There is no arbitrary command endpoint or wildcard grant.

Common request examples:

| Operation | JSON request | Result |
| --- | --- | --- |
| `health.alerts` | `{}` | Current health and alert state |
| `smart.status` | `{}` | Current disk health reports |
| `network.status` | `{}` | Ports and configured network state |
| `media.catalog` | `{"library":"movies","offset":0}` | Up to 200 entries, IDs, metadata and total count |
| `media.metadata` | `{"id":"<catalog-id>","metadata":{"title":"Example","year":"2026"},"save_sidecar":true}` | Updated metadata; optional portable sidecar |
| `media.scan` | `{"library":"movies"}` | Queued job ID |
| `files.list` | `{"share":"media","path":""}` | Directory listing |
| `files.mkdir` | `{"share":"media","path":"","name":"New folder"}` | Created directory |
| `downloads.add` | `{"url":"https://example.org/file.zip","name":"file.zip"}` | Added URL/torrent job |

Detailed request validation remains in the same handlers used by the dashboard;
this inventory is not an OpenAPI schema or a promise that arbitrary fields work.
File reads return bounded base64 chunks; uploads use begin/chunk/finish. Chunk
operations require their own grants. Reviewed operations still require a fresh
plan, its digest and exact confirmation; creating a plan does not authorize
applying it. Plans, upload handles, ZIP tickets and retryable jobs created through
the agent gateway belong to that credential. Another agent or browser's plan
cannot be applied through it. Failed operations are not automatically retried.

Errors use JSON: 403 for denied/expired/revoked credentials or permissions, 429
for the credential rate limit, 400 for invalid/failed operations, and 404 for
unknown endpoints. Broker and HTTP request sizes remain bounded. Do not blindly
retry a mutation after a lost response: inspect its job or system state first.

## Play the library on an approved network player

Network playback is **off by default**. It supports **UPnP MediaRenderer /
AVTransport**, original files and supported player codecs. It does not add
AirPlay, Cast, Roku-specific remote control, or transcoding. A DLNA browsing app
is not necessarily a remotely controllable renderer.

1. In **AI agent access**, enable network playback on a NAS LAN address and an
   unused media port (default 8091). This opens an optional HTTP stream listener.
   Keep it on a trusted LAN. **Never forward this port from the internet.**
2. Find network players, or enter a known device-description URL if multicast
   discovery cannot cross the local network. Discovery does not play audio.
3. Explicitly approve the identified player. Only the dashboard owner can approve
   it. Revoke it here independently of the agent's token.
4. Give the agent the **media playback** preset. Add media editing separately if
   desired. Discovery itself is a separate permission and never grants approval.
5. Read `media.catalog`, choose its entry ID and library, then invoke playback.

| Operation | JSON request |
| --- | --- |
| `media.players` | `{}` |
| `media.players-discover` | `{}` or `{"location":"http://<LAN-IP>/device.xml"}` |
| `media.play` | `{"player":"<approved-id>","library":"movies","id":"<catalog-id>","offset":0}` |
| `media.playback-status` | `{"player":"<approved-id>"}` |
| `media.playback-control` | `{"player":"<approved-id>","command":"pause"}` |
| `media.playback-control` | `{"player":"<approved-id>","command":"seek","position":"00:03:00"}` |

Controls support play, pause, stop, absolute seek, and forward/rewind skips.
For a skip, use `"command":"forward"` or `"command":"rewind"` with optional
`"seconds":30` (1–3600). Skips require the player to report its current playhead.
Continuous high-speed fast-forward is not assumed to be supported. The offset is the catalog page where
the selected item was returned, not a playback position. The playback endpoint
resolves that indexed item itself; arbitrary content URLs are not accepted.

Each playback creates a random, six-hour, single-item stream link, bound to the
approved player's IP and the issuing credential. Only its hash is retained.
The player's API never receives the agent token. Expiry, credential revocation,
player revocation, content changes or disabling playback block further reads;
a player may still play already buffered content. Streams support byte ranges.
Up to four concurrent stream requests and 64 unexpired stream tickets are allowed.
Playback rechecks the renderer descriptor and UDN; endpoint changes need fresh
approval. Descriptor and control URLs are restricted to the same observed RFC1918
IPv4 address, with bounded responses/timeouts, no redirects, and no XML entities.

Network identity is not cryptographic identity: hostile LAN spoofing and devices
behind shared addresses are outside this approval model. HTTP media is unencrypted
on the LAN. Use SMB/VPN for stronger access boundaries. A player must reach the
chosen NAS address and port; optional private-LAN firewall rules may need an
explicit media-port allowance. Success means the player accepted the commands;
actual output, codec compatibility and seeking require a real player test.

## Validation and limits

Automated tests cover credential expiry/revocation, default-deny rights, browser
separation, confirmation ownership, operation inventory parity, URL/XML safety,
player identity drift and stream-ticket revocation. Physical TV/speaker playback
has **not** been accepted. No test audio is sent automatically. Folder-specific
agent policies, custom reusable roles and a complete OpenAPI request schema are
not implemented; use the explicit per-function grants and shipped presets.


## USB encryption profile fields

`external.create-plan` accepts `encryption_profile` only when `encrypted:true`:
`aes256-xts` (default) or `aes128-xts`. The returned reviewed body includes
`encryption_profile` and `encryption_details` (LUKS2 format, cipher, total key bits,
Argon2id memory/parallelism/calibration). `external.create` applies the saved
profile and records its ID on the new pool. It still requires plan ID, digest,
exact confirmation and the in-memory `secret` object; never put credentials in
an agent's logs. Supplying a profile for an unencrypted create is rejected.

`external.eject` additionally returns a `flush` list per presented device, with
`id`, `method` and `device_cache_flush_supported`. Methods are `scsi-sync` or
`reported-write-through-no-sync-opcode`. The second is accepted only for a
specific unsupported command and a reported write-through cache, after Linux
buffer flushing; other failures remain errors. See [USB encryption](USB-ENCRYPTION.md).

## Cooling and watchdog status

`system.cooling-status` with `{}` returns configured mode, acceptance gate,
current fan/CPU/disk sample, controller/guard state and watchdog status. A stale
sample is reported unavailable. `system.watchdog-status` with `{}` reads identity,
active state, timeout, nowayout and `expected_enabled` (the managed policy file is present) without opening/arming the watchdog. A managed watchdog expected on but inactive/unavailable becomes a critical `watchdog` health incident.
`system.cooling-mode` accepts exactly `{"mode":"full"}` or `{"mode":"auto"}`.
Full-speed intent is saved before the checked hardware request and is retained if that request fails; the failure is reported rather than claimed applied. Automatic mode requires an
exact-install hardware acceptance receipt and is applied by the local controller;
a saved setting is not physical success. Inspect status afterward. New rights
must be granted explicitly; existing tokens and presets are unchanged. Raw speed,
MCU commands and watchdog arming are not exposed through these operations.

During local attended commissioning, the controller status may include
`attended_trial: true` while the saved mode is still `full`. This is a bounded
root-owned validation campaign, not an agent permission or permanent Auto grant.
Selecting Full speed cancels the trial before requesting full airflow. Agents
cannot create trial permissions or acceptance receipts through these operations.

`system.cooling-history` accepts `{}` or `{"limit":120}` (integer 1–240).
It returns sanitized `points`, `sample_interval_seconds:30` and `stale`.
Each point contains time, level, fault/attended-trial flags, CPU `temperature`,
`hottest_disk` and `fan0`/`fan1`/`fan2` RPM values; missing readings are null.
Boot/process/install identities and private file paths are excluded. History is
bounded/rotated locally and sampled, so it does not prove instantaneous RPM.
This is a separate explicit grant; existing tokens/presets are unchanged.

### Download recovery status

`downloads.status` job records can include `recovery_required: true` when the engine
reports damaged resume-control metadata. Such a job remains `state: "error"`, with
a fixed explanatory `engine_error`; private engine paths are not returned. It is
retained across restart and does not prevent later jobs from running.
`downloads.control` with `action: "resume"` rejects this condition instead of
repeatedly discarding/recreating the engine job. `action: "remove"` still retains
the downloaded files. Start a new job to use a fresh directory, or reconcile the
partial files manually; there is no automatic destructive marker repair.
