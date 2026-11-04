# My Radio and interrupted-array API contracts

These functions use the authenticated administrator dashboard endpoint
`POST /api/nas/<operation>` with its normal session/CSRF checks, or the agent
`POST /api/agent/v1/operations/<operation>` with that exact grant. No arbitrary
shell or wildcard permission exists. Responses below describe their important
fields; invalid fields/values fail without granting broader access. IDs are
opaque. Secrets and private feed/download URLs must not be placed in public logs.

## Recovery

| Operation | Request | Response/behavior |
| --- | --- | --- |
| `raid.recovery-status` | `{}` | `arrays`: registered groups, state, volumes/mounted, available_actions, array progress, last_operation; no mutation |
| `raid.inspect-plan` | `{pool, mount_volumes?:true}` | Ten-minute `array-recovery` plan with exact snapshot, verified metadata_backup, risk, excluded operations and confirmation phrase; mode always readonly |
| `raid.resume-plan` | Same | Separate plan, mode resume; requires assembled read-only array |
| `raid.mount-plan` | Same | Mode mount; existing writable array only |
| `raid.inspect-apply` | `{plan_id,digest,confirmation,backup_acknowledged:true}` | Consumes its readonly plan, exact-member assembly, verified kernel read-only state; no mount/rebuild |
| `raid.resume-apply` | Same | Consumes only its resume plan, enables writes and optionally requests mounts; may return submitted/completed:false |
| `raid.mount-apply` | `{plan_id,digest,confirmation}` | Consumes only its mount plan; requests missing existing filesystems without duplicating pending jobs |
| `raid.backups` | `{}` | Complete archives with ID, size, group, creation time and protected flag |
| `raid.backup-read` | `{id,offset?:0,count?:524288}` | Bounded base64 data, filename, total_bytes, etag; sensitive export permission |
| `raid.backup-remove` | `{id,backup_copied:true,confirmation:"DELETE METADATA <exact-id>"}` | Deletes only an eligible older archive; latest per-array/current plan/latest-operation archives retained |
| `system.button-status` | `{}` | Installed held-button actions, accepted raw-input/pitched-output availability, disabled requested five-tap sequence and required validation |

Planning and applying are independent grants. A readonly apply grant cannot apply
a resume or mount plan. Plan references belong to the credential which made them.
A lost response requires state inspection, not a blind repeated mutation. Metadata
backup reads are sensitive; a successful download is not file-data protection.

## My Radio collections

| Operation | Request | Response/behavior |
| --- | --- | --- |
| `myradio.status` | `{}` | config, volume online, counts, pending downloads/uploads, scanner state, formats/privacy |
| `myradio.configure` | `{pool,scan_enabled?:true,folders?:{music:true,books:true,podcasts:true},musicbrainz?:false,openlibrary?:false,save_sidecars?:true,podcast_auto_refresh?:false}` | Initializes private identity-bound folders or changes options; retains an existing storage binding; use library.storage-plan/apply to relocate |
| `myradio.catalog` | `{category:"music"|"books"|"podcasts",query?,artist?,album?,genre?,sort?:"title"|"artist"|"album"|"newest"|"year",favorite?:false,archived?:false,limit?:60,offset?:0}` | items, total, facets; limit 1–120; book artist filter uses author |
| `myradio.item` | `{id}` | item metadata and saved progress |
| `myradio.read` | `{id,variant?:"original"|"cover",offset?:0,count?:524288}` | Identity-checked base64 bytes, filename, total_bytes and etag; count maximum 512 KiB |
| `myradio.book-text` | `{id,offset?:0,count?:64000}` | text, chapter offsets, total_characters, next_offset; maximum 64,000 characters/request; readable companions resolved |
| `myradio.upload-begin` | `{category,name,bytes}` | upload_id, offset, total_bytes; plain supported filename, 1 byte–128 GiB, maximum 16 incomplete uploads |
| `myradio.upload-chunk` | `{upload_id,offset,data_base64}` | Next offset; maximum 512 KiB decoded; existing bytes must match for resume; never overwrite mismatched partials |
| `myradio.upload-finish` | `{upload_id}` | Decodes/indexes completed original; item; exact post-rename reconciliation after interruption |
| `myradio.metadata` | `{id,metadata?:{...},favorite?:boolean,archived?:boolean}` | Updated item; originals retained; optional sidecar |
| `myradio.artwork` | `{id,data_base64}` | Locally decoded cover saved; maximum 1 MiB decoded input |
| `myradio.lookup` | `{id,title?,artist?}` | Reviewed provider results; enabled MusicBrainz/Open Library only; no automatic match application |
| `myradio.artwork-url` | `{id,url}` | Fetch/decode a selected HTTPS Cover Art Archive/Open Library cover |
| `myradio.progress` | `{id,position,kind?:"audio"|"text"}` | Saved finite, nonnegative audio seconds/text character offset |
| `myradio.scan` | `{}` | Queued job ID; enabled designated folders only |
| `myradio.import-folder` | `{category,share,path:""}` | Queued copy/index job, source unchanged, earlier completed imports retained; general file-access validation applies |
| `myradio.import-url` | `{category,name,url}` | Queued job_id/source_id; URL retained privately, job contains source ID only |
| `myradio.resume-download` | `{source}` | Explicit queued resume of a retryable source; verified partial/resume response required |

Editable metadata keys: `title`, `artist`, `album`, `album_artist`, `genre`, `year`,
`track`, `composer`, `author`, `narrator`, `publisher`, `description`, `isbn`,
`source_url`, and `companion_id`. Source links must be HTTP(S) without embedded
credentials. Companion editions must be other books and cannot form nested links.
Folders, paths and original-file identities are not editable metadata. The
`my-radio-reader` and `my-radio-editor` presets are explicit independent grants;
existing media/file tokens gain no personal-library access. Rights are NAS-wide
functions, not per-book or per-folder restrictions.

## Stations and podcasts

| Operation | Request | Response/behavior |
| --- | --- | --- |
| `myradio.stations` | `{query?,group?,country?,favorite?:false}` | Station metadata, last check, working/stale flags and group/country facets; no audio playback |
| `myradio.station-save` | `{id,favorite:boolean}` or `{name,url,group?,country:"US"|"CA"}` | Favorite update or verified public direct-stream addition |
| `myradio.station-check` | `{id}` | Bounded sample verification; unavailable station retained and marked not working |
| `myradio.station-source` | `{id}` | Public station URL/name for an authorized client; no private proxy access |
| `myradio.station-refresh` | `{group?:"",query?:"",country?:"US"|"CA"}` | Queued US/Canada-only directory search; up to 25 candidates per selected country; returned country codes rechecked; older entries retained |
| `myradio.podcasts` | `{feed?:id,query?:""}` | Regional subscriptions/searchable episodes plus unclassified_feeds requiring owner country confirmation; and saved asset IDs; private source URLs omitted |
| `myradio.podcast-add` | `{url,country:"US"|"CA"}` or `{id,country:"US"|"CA"}` | Saves/refreshes a regional RSS/Atom feed or classifies an existing subscription; maximum 50 subscriptions |
| `myradio.podcast-refresh` | `{id}` | Refreshes subscription listings; saved originals retained |
| `myradio.episode-download` | `{id}` | Queued episode save or already-downloaded item |

Browser-session-only streaming/download routes: `GET/HEAD /api/radio-file?id=...`
with `variant=original|cover`, `inline=1` or `download=1`; `GET/HEAD
/api/radio-stream?id=...`; and `GET/HEAD /api/raid-backup?id=...`. File and backup
routes support HTTP byte ranges and no-store. Agents use their bounded read
operations; their Bearer token does not authenticate browser endpoints. Never put
tokens in stream URLs. Station proxying requires a dashboard session and accepts
only public destinations; it is not a general URL proxy.

Country filters accept US/CA and their displayed names; other countries are rejected. Radio country follows directory metadata or an owner-declared custom service location, not network geofencing. Podcast country metadata persists through refresh; unclassified feeds cannot refresh or initiate new episode downloads. Existing saved originals are retained. Station-source/check refuse foreign or unclassified station IDs. Book voice/pitch/speed are client-local preferences, not a NAS speech or remote-audio API.


## Private library placement and USB imports

| Operation | Request | Response/behavior |
| --- | --- | --- |
| `library.storage-plan` | `{library:"radio"|"photos",pool,folder}` | Identity-bound reviewed `library-storage` plan; dedicated relative folder, writable registered volume; does not copy files |
| `library.storage-apply` | `{plan_id,digest,confirmation:"SET LIBRARY LOCATION"}` | Queues a consumed-plan operation; initializes or copies/verifies a private library and switches config/file identities atomically; retains previous archive and failed partial destinations |
| `photos.import-folder` | `{pool,folder?:""}` or `{share,folder?:""}` | Starts a background copy into configured archive; `share` accepts a share name, `pool:<registered-volume>` or `foreign:<owned-unlock-session>`; cannot supply both source forms |
| `myradio.import-folder` | `{category,share,path?:""}` | Queues supported-file copy; same share/pool/foreign source forms, source unchanged |

Placement and apply have separate exact agent grants and do not expand existing
presets/tokens. Plans retain principal ownership. Foreign import references must
belong to that agent, just like direct session reads. Folder imports may read a
registered read-only volume; the destination still must be writable. Status config
adds `location_selected`, visible `location_folder` and `previous_locations`
(pool/folder/filesystem UUID records). Before an explicitly chosen location the
browser shows setup instead of library use. Legacy configure calls retain their
original binding for compatibility; new location selection uses reviewed plans.
Music scanning/provider preferences remain on the library page. Library originals
remain protected from ordinary File Manager mutation; visible-folder transfers
require explicit import for cataloging. No credentials enter queued payloads.
