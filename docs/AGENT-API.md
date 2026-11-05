# Agent API and network playback

FreeQNAP supports provider-neutral agents through local HTTPS. No model provider,
cloud service, shell, or separate agent runtime is required. The owner controls
credentials under **Settings → AI agent access** in the dashboard.

## Issue and revoke access

1. Sign in as the administrator and open **Settings → AI agent access**.
2. Name the agent, choose an expiry (1–365 days), and select its functions.
   Presets add explicit permissions; groups can be selected and cleared.
3. Create the token and save it in the agent's private secret store. It is shown
   once. Never put it in a URL, repository, screenshot, or shared conversation.
4. Revoke it from the agent list when access is no longer needed. To change its
   rights, issue a replacement with the new selection and revoke the old token.

**Rights are NAS-wide function permissions, not folder permissions.** Private
encrypted unlock ownership is an additional boundary: each credential owns its own
unlock and cannot inherit another account’s or credential’s decrypted files.
Private encrypted sources are excluded from DLNA/anonymous network exports. See
[private-volume and activity rules](USER-PRIVACY-AND-ACTIVITY.md).

 A file
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

## Personal-photo access

New photo operations do not expand existing token grants. The explicit
`personal-photo-reader` preset permits catalog/status, GPS clusters, related
versions and original/preview reads; it exposes private media/location data.
`personal-photo-editor` permits captions/favorites and manual album membership.
Apple account settings, sign-in and verification codes are administrator-only
and cannot be granted to agents. Generic file operations cannot enter the
protected personal-photo namespace. See [Personal Photos](PERSONAL-PHOTOS.md).

## Personal audio, books and interrupted RAID recovery

Separate exact grants and request contracts are documented in [My Radio and recovery](MY-RADIO-AND-RECOVERY-API.md). Existing credentials gain no access automatically. Recovery is never part of a media preset.


## Local people and optional identity providers

See [local users and Authentik](LOCAL-USERS-AND-AUTHENTIK.md). Local account,
provider and sharing administration uses authenticated same-origin session/CSRF
routes; family members cannot issue NAS agent credentials. Existing agent tokens
retain their explicit grants and do not gain per-user catalogs automatically.
New exact NAS operations: `library.files-status` (read-only),
`library.files-plan` `{pool,folder}`, `library.files-apply`
`{plan_id,digest,confirmation}` and `files.media-neighbors`
`{share,path?:"",name,query?:""}` returning previous/next file descriptors, position
and total. Copy/move results add `recycled_sources`; cross-volume moves verify
before recycling originals. Foreign-session sources require ownership of that
agent's session reference. Internal `personal.*` envelopes are unavailable through
HTTP/agent operation dispatch and are never owner selectors supplied by a client.


## Photo/video metadata sidecars

`files.metadata-read` takes `{share,path}`; `photos.metadata-read` takes `{id}`.
Results include editable `metadata`, an `etag`, technical information and storage
semantics. Changes use `*.metadata-plan` with the same identity plus `etag` and
`metadata`; review and apply through `*.metadata-apply` with `plan_id`, `digest`
and exact `confirmation`. Stale identities/sidecars and read-only targets fail.
Fields: title, description, creator, copyright, tags, taken (ISO date/time),
latitude/longitude (both numbers or both null), altitude, make, camera and lens.
GPS ranges and timestamps are validated. Edits write XMP sidecars, preserve the
original and update Personal Photos' catalog/map; embedded EXIF is not rewritten.
These six operations require explicit individual token grants and do not expand
existing tokens. Browser-family metadata editing additionally requires
`metadata.edit` and the corresponding file/photo write right. External native-app
sharing is session-only and never automatically sends content. See
[privacy and sharing](METADATA-AND-SOCIAL-SHARING.md).

## Station artwork and folder browsing

`myradio.station-artwork` and `library.folders` are separately selectable operations.
They do not expand existing credentials. The interactive `photos.icloud-check` action
is not available to agent tokens. See [interface fields and owner rules](PHOTOS-USB-AND-BROWSING.md).

File copy telemetry and freshly reviewed retries are documented in
[File transfers](FILE-TRANSFERS.md). `files.transfers` is read-only and filters by
the authenticated principal; `files.transfer-retry-plan` prepares a new review,
not an automatic retry. Existing tokens require explicit grants for new operations.

### Photo progress and media cache response additions

`photos.status.operation` may include `expected_items` alongside `seen`, `completed`, `failed`, and per-file `bytes`/`total_bytes`. The expected count covers the inventory discovered so far and may grow across collections; absence means unknown, not zero. File-byte updates preserve inventory counters; terminal/new-operation states clear obsolete per-file fields. These additive connector fields take effect after a safe broker update. Existing running downloads are not restarted for UI changes.

Authorized thumbnail/preview and recognized artwork HTTP reads support private conditional caching with account/grant-scoped ETags and `If-None-Match`/304. Authorization is checked before conditional responses. Originals keep no-store and range behavior. This does not grant agents new permissions or expand media access.

### Account scan-folder endpoints

The authenticated dashboard exposes POST `/api/nas/library.sources-status`, `library.sources-save` and `library.sources-scan`. These are session-scoped endpoints, not bearer-agent operations in the current token catalog; existing token grants/presets are unchanged. Shared libraries cannot configure sources. Read requires `myradio.read` or `photos.read`; saving/scanning requires the corresponding `.write`, with normal file-read/write and source authorization independently enforced by existing handlers. Administrators can use the existing managed-account selector. Owner IDs cannot be supplied in the body.

All three take `kind: "radio" | "photos"`. Save also accepts `enabled` (boolean), `interval_minutes` (integer 5–1440) and `sources` (up to 32 entries). An entry has `share`, relative `path`, `enabled`, optional display `label`, and radio `category` (`music`, `books`, `podcasts`); photo category is fixed. Returned source IDs are bookkeeping only. Paths must stay inside accessible sources; no permission is granted by saving a path.

Status returns `config`, `run`, `suggestions`, `library_location`, `folder_setup`, `catalog_counts`, `current_scanner`, `copy_into_private_catalog` and an `online_metadata` explanation. Internal expanded task inventories are not returned. Run states include scheduled, waiting-transfers, waiting-photos, waiting-job, waiting-photo, complete, disabled, failed and uncertain. Scan requests schedule saved sources rather than synchronously importing. Failed/unknown receipts and ambiguous submissions block automatic retries; inspect Activity before operator reconciliation. Automatic imports never enable online metadata lookups.

### Session podcast browser and artwork

POST `/api/nas/myradio.podcast-browser` is a session-scoped read interface that reuses authorized `myradio.podcasts` reads. It is not added to bearer-agent presets or grants. Shared access must be an authorized podcast-library share; managed-account access remains administrator-only. The request accepts `view` (`shows` or `episodes`), `feed`, `query` (up to 255 characters), `genre`, `publisher`, `age` (empty, 7/30/90/365, older or undated), `saved` (empty/yes/no), `sort` (newest/oldest/title/publisher/episodes/duration), `offset`, `limit` (25/50/100/500 or all) and optional boolean `refresh`. Search/filtering happens before paging.

Responses include `items`, `total`, `offset`, `limit`, optional selected `show`, genre/publisher `options`, authorized `show_count`, `indexed_episodes`, and `recent_window`. Show items include title, publisher, description, genres, safe website, artwork availability, episode/matching/saved counts and latest timestamp. Episode items contain opaque ID, title, plain notes, publication date/timestamp, duration and any saved asset reference. No feed/enclosure URL or owner-selecting payload field is exposed. Unknown/cross-account feed references are denied.

GET `/api/podcast-art?id=…` requires the same session/account/share authorization before image cache reads or conditional 304. It returns only bounded JPEG/PNG/WebP, private revalidation headers and a scoped ETag. Remote XML/SVG/HTML is not served as artwork. Cached derived artwork is bounded and evicted independently of originals.

Native `myradio.podcasts` additionally supports offset and numeric limits up to 1000 or all, returning total/next_offset/pagination. Responses obey the broker byte budget, so clients must follow actual next_offset even when all is requested. The running legacy broker may not expose this capability until its next safe reload; the console compatibility layer reports recent_window rather than claiming older retained records are available. Existing bearer-token rights remain unchanged.

#### Personal card edits (browser session)

`POST /api/nas/myradio.card-save` accepts `kind` (`podcast` or `station`), `id`, optional `metadata` (`title`, `author`, `genre`, `description`, `website`), optional base64 `artwork` and boolean `reset_artwork`. Text limits are respectively 500, 500, 200, 10000 and 2000 characters. Genres use comma-separated text. A supplied title cannot be blank. Website URLs must resolve to public HTTP(S) destinations. Artwork is raster JPEG/PNG/WebP, at most 1 MiB; active SVG/HTML is rejected. Returns `{saved:true,revision}`. The current session must have `myradio.write`; shared libraries cannot be edited, and managed-account edits require an administrator. The target must already be in that account’s authorized library. Source URLs, region, approval and playback destinations cannot be edited here.

`GET /api/library-card-art?kind=podcast|station&id=…` returns a private custom raster cover, with session/account authorization before 200 or conditional 304. Missing/inaccessible artwork returns 404; no session returns 401. These console endpoints do not add bearer-agent capabilities. Existing book/music metadata and artwork operations keep their current authorization. Native `myradio.metadata` additionally accepts `book_type` (`audiobook`, `ebook`, `other`) after the safe worker reload.

#### Prepared local music metadata

Music item metadata can include `identification_status` (`complete` or `needs-review`) and `metadata_sources`, mapping tag fields to `embedded`, `folder-consensus`, `existing-album-nfo` or `filename-needs-review`. These report local evidence, not an online fingerprint match. They add no permissions or external metadata transmission. Unknown identification leaves the original filename unchanged. Internal prepared-file identity checks are omitted from newly loaded native public DTOs. Browser-compatible M4B editions use normal audiobook playback; legacy AAX/APE/WMA originals retain compatible-player guidance. No automatic transcoding is introduced.

`myradio.status` includes `prepared_scanning:true` when the native worker has loaded identity-verified fast rescans. The console may report `optimized_scan_pending:true` for a prepared large library while an older worker remains active for an existing transfer. In that state `myradio.scan` is rejected before enqueueing; current browsing/playback and unrelated transfers remain available. Planned per-account music maintenance temporarily rejects new media writes/scans, with an explanatory response, and holds automatic folder imports. These holds add no new permissions and do not silently replay uncertain jobs.


### Session album browser, listening overview and metadata matching

The following POST `/api/nas/` operations are authenticated, CSRF-protected dashboard-session adapters. They do not add bearer-agent grants or presets. Native account, collection and managed-user authorization is reapplied; shared collections remain read-only. Owner IDs cannot be supplied in payloads.

| Operation | Request | Response / rights |
| --- | --- | --- |
| `myradio.music-browser` | Optional `album` ID, `query`, `artist`, `genre`, `sort` (title/artist/newest/year), `offset`, `limit` (25/50/100/500/all), boolean `refresh` | Authorized album summaries, facets, totals, paging; selected album includes tracks in disc/track order. Requires native My Radio reads. |
| `myradio.books-browser` | `query`, `artist`, `genre`, `series`, `collection`, `format` (empty/audiobook/ebook), `sort`, `offset`, `limit`, boolean `favorite`/`archived` | Authorized items, facets and paging. Title, author, newest, year and numeric series ordering; normal book access. |
| `myradio.album-save` | `album`, optional `metadata` containing album/album_artist/genre/year, optional base64 raster `artwork` at most 1 MiB | `updated` track count and `cover_saved`. Requires `myradio.write`, denied on shares. Explicit changed fields apply to all album tracks (maximum 1,000). A partial failure reports completed writes; inspect before retry. |
| `myradio.overview` | Empty object | Own `sections`, `recent`, `stats`, `counts`, `measurement`. Managed-account impersonation is denied. |
| `myradio.listen` | Start: `event:start`, `id`, `kind` (music/audiobooks/books/podcasts/radio). Tick/stop: `event`, opaque `session`, boolean `playing` | Start returns session/tracking_since; updates return saved/seconds/ended. Listener is always the signed-in account, never a payload owner. Current item/share access rechecked. |
| `myradio.providers` | Empty object | Enabled flags and transmission disclosure. Native MusicBrainz/OpenLibrary flags plus per-account podcasts/radio flags. |
| `myradio.providers-save` | Optional boolean `podcasts`, `radio` | Updated enabled flags. Requires write permission; shared collections denied. Native provider flags remain in normal My Radio configuration. |
| `myradio.metadata-search` | `kind` (asset/album/podcast/station), exact `id`, `title`, optional `artist`, `country` (US/CA) | Explicit enabled-provider search results with opaque ticket, public metadata, optional has_cover; disabled providers return an explanation without searching. Requires write/current target access. |
| `myradio.metadata-apply` | `ticket`, boolean `cover` | Applies the selected metadata and optionally artwork; returns saved/warning. Ticket is owner/requester/target-bound for ten minutes, provider enablement and authorization rechecked. Feed and stream destinations are unchanged. |

Album summaries include opaque ID, title, artist, year, genres, track_count, duration, needs_review, optional cover_item/custom_artwork/revision and source folder label for unidentified albums. Internal filesystem paths/identities are not exposed. Source evidence prevents unrelated unidentified/compilation folders from merging. Private inventory caching repeats native authorization before each cache read.

`myradio.metadata` supports book `series` (200 characters), `series_number` (40 characters) and `collections` (up to twenty names, 160 characters each). Organization is account-scoped local configuration; the original file is unchanged. Native core metadata/sidecar writes keep existing authorization. Catalog/item responses overlay these book fields. Personal album artwork is a console display override rather than replacement of every track's embedded art.

Listening stats contain total_seconds, sessions, tracking_since, by_kind, genres (name/seconds/percent), top_tracks and top_stations. Only actual browser playback starts sessions; updates account previous playing state by server wall time, cap each interval at sixty seconds, reject concurrent stale writes and exclude pauses. Missing/offline reports may undercount. No history is reconstructed. Recent and top item details are reauthorized before display. High-frequency successful ticks do not flood Activity; start/stop and failed requests remain auditable.

GET `/api/album-art?id=…` and `/api/metadata-match-art?ticket=…` require current session/account/share/provider authorization before either 200 or conditional 304. Only bounded JPEG/PNG/WebP is returned with private revalidation, ETag, Vary:Cookie and nosniff. Missing/inaccessible art returns 404; unauthenticated requests return 401. Search queries go only to enabled providers on explicit request; no originals or listening history are transmitted. Podcast results must match enrolled region-declared US/Canadian feeds, and radio results must match the selected country. Provider artwork requests are validated through the existing public-HTTP boundary. No new renderer-control rights are granted.

The private album inventory may persist across console restarts. Native authorization and item count are checked before cache use; known metadata edits invalidate it. Unchanged snapshots older than ten minutes refresh in the background, with a one-day maximum. Explicit refresh rebuilds synchronously. Cached display metadata can lag out-of-band edits during that window; original reads always enforce current authorization. Catalog lookup indexes accelerate the exact title and facet expressions without changing media.

### Reviewed album identity and retained alternatives

Session `myradio.music-browser` accepts optional `attention` (empty, `identification`, `audio`). Album responses additionally expose `file_count`, `identical_copies`, `other_versions`, `retained_unavailable_copies` and `unavailable_tracks`. `track_count` counts the main intended-track rows; `file_count` counts retained originals. Main track rows may have nested `alternate_copies` (verified identical content), `other_versions` (metadata/duration grouping, not a byte-identity claim) and `unavailable_copies` (unavailable sources with a matching playable intended track). Each retained item keeps normal account authorization. `album-save` applies to all retained files, including nested alternatives; its 1,000-file limit counts them too. These fields grant no new file access or bearer scopes.

Music metadata provenance can additionally identify `reviewed-folder`, `reviewed-online` or `reviewed-artwork`. Prepared metadata may report `audio_status:unavailable` and a short `audio_warning`; such items retain `playable:original-only` with a specific explanation that the source did not contain decodable audio. Identification and audio availability are separate facts. A successful header read is not complete-file integrity acceptance. Native `disc` metadata editing is supported in current source after the storage worker's safe reload; the running older worker's editor does not advertise that new field. Source music sidecars retain disc order but continue to exclude active URL fields.

The session-only personal photo controls `photos.icloud-albums-status`,
`photos.icloud-albums-configure` (`enabled`, `interval_hours` 1–24) and
`photos.icloud-albums-sync` (empty request) operate only on the signed-in account,
or an explicitly managed administrator target. They are not bearer-agent
operations. Status requires photo access; changes require photo and iCloud write
rights. Archive location and Apple account must be configured before enabling or
requesting an import. Shared-library sessions cannot change these controls.
