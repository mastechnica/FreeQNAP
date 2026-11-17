# Direct AuraView EyeQ Cloud connector — 12 November 2026

## Live acceptance — 12 November 2026

The direct connector is installed, paired to my existing EyeQ account,
and online. The enabled collections include Music, Books/audiobooks, downloaded
Podcasts, Personal Photos and Videos. I briefly excluded photos/videos,
then explicitly re-enabled both; the latest live configuration and authenticated
heartbeat confirm that they are enabled. The pairing credential was preserved.
No new pairing or original-media import was required.

Explicitly authorized real media checks passed bounded reads and seek checks for
music, books, photos and videos, JPEG thumbnail/preview decoding signatures and
readable-book text. In the signed-in EyeQ browser, Synthia discovered the NAS,
searched its music, started playback with an advancing player timeline and paused
it with a matching player state. Playback was stopped after testing. These are
browser playback checks, not external-speaker or physical device acceptance.

The source-name resolver now accepts a unique exact connector display name only
within the authenticated account. Narrow committed Cloud source deployments were
hash checked and backed up without replacing user databases or unrelated source.
An earlier deployment observation timed out during the service's normal websocket
drain and restored its files; the corrected bounded observation passed. Earlier
rejected media-read checks were superseded by explicit explicit authorization and
successful tests; they are retained as historical evidence.

Expanded dashboard sharing selectors, publisher-hosted radio/podcasts and reviewed
metadata/artwork editing are in local development. They are not claimed deployed
or accepted by the basic connector checks above. Raw diagnostics, credentials,
account identities and library content remain in ignored private evidence.

## Original preparation record (superseded deployment status)

The following sections record the earlier preparation scope. Their statements
about an unpaired installation, pending deployment and unavailable media testing
are historical; the live acceptance above supersedes those statements.

## Result

The optional connector runs directly on FreeQNAP. It connects outbound to EyeQ
Cloud using TLS websocket/HTTPS on port 443 and is independent of AVE40, Guessla,
Pulse and the Mac. EyeQ brands this media source AuraStore. The existing NAS
account/volume permissions remain authoritative; this app grants no remote NAS
administration or media writes.

The source and installer are in `apps/auraview-eyeq-connector/`. A matching
source-only distribution is maintained in EyeQ Cloud's
`deploy/eyeq/connectors/aurastore/`. The app is installed on the development NAS;
no Cloud credential was created, no account was linked, and no connector service
instance is enabled. Pairing remains an explicit per-account step.

## Supported collections

Existing indexed Music, Books/audiobooks, downloaded Podcasts, Personal Photos
and videos are browsable. Additional local media shares can be explicitly selected
at pairing for movie/TV/general-media folder browsing. The Cloud cannot select
paths, grant another user's library, unlock disks or initiate scans/imports.
Readable-book support depends on an existing native extracted-text edition;
original codecs/DRM remain limited by the playback browser. Internet radio and
publisher-hosted unsaved podcast episodes are outside this stored-media bridge.

Only bounded, allowlisted catalog metadata leaves the NAS when requested. No raw
paths, GPS/EXIF, private metadata fields, NAS identities or original files go to
Synthia. Original media is read in bounded chunks for EyeQ's authenticated player.
Permissions, disabled accounts and locked-volume ownership are rechecked per
request/chunk. Optional category restrictions cannot be bypassed with a known ID.

## Changes and validation

- Correct native photo `thumbnail` mapping and compatible full-photo previews.
- Add per-library selection, local username resolution and catalog-only readiness.
- Keep console settings/account reads in SQLite read-only mode, with no schema or
  journal-mode initialization. Retain native gateway/actor isolation.
- Report authenticated heartbeat status locally without credentials or private
  errors; stale state is explicit. Config/status files are private and durable.
- Expand folder media extensions for supported readable-book editions; keep
  explicit share roots, symlink exclusions and bounded pagination.
- Prepare Cloud artwork URLs only under its own authenticated media endpoint;
  never use an upstream-provided arbitrary artwork URL. Update photo display and
  readable-book selection without changing other device connectors.
- The first NAS readiness attempt caught a root-only Python environment caused by
  the caller's restrictive umask. The installer now sets an explicit public-code
  umask and repairs only dependency-tree readability; pairing files stay private.
  Earlier failed evidence remains retained.

Sixteen standalone connector tests pass. The complete isolated EyeQ regression
suite passed 245 tests; its media subset passed 25. Four browser-player regression
tests pass. These cover actual websocket request/reply/revocation, account/session
isolation, range handling, safe artwork routes and native account permissions.
Catalog-only checks on the real NAS successfully used the existing personal
account and found its indexed collections. Installed source/dependency, service
syntax and ARM fixture checks are recorded privately.

Automatic approval review rejected the proposed real-media byte-read check,
treating it as possible personal-media export. It did not run. Catalog checks do
not prove real file readability, decoding, audio output or end-to-end Cloud
playback. No new real-media playback or Cloud pairing is claimed.

## What EyeQ Cloud needs

1. Deploy the prepared `app/library_api.py`, `app/static/music-media.js` and rebuilt
   `app/static/connectors/aurastore-connector.tar.gz` through a narrow reviewed
   release. Back up/check the current live hashes first; other Cloud work may be
   pending, so do not deploy the entire working tree or overwrite newer changes.
2. Retain the existing account-authenticated `/api/aurastore/*` router and Synthia
   tools `search_music_media`, `play_music_media`, `control_music_media`. No new
   provider API key, MQTT user, NAS admin token or public NAS port is required.
3. Keep Cloud's existing single-worker websocket registry and sufficient websocket
   message limit (900,000 bytes). Preserve TLS/Upgrade forwarding and current
   account/session isolation. Do not widen CORS or proxy arbitrary NAS URLs.
4. Sign into the intended EyeQ account and create a one-use AuraStore code at
   Devices & data → Music & media connectors. A NAS administrator enters it in the
   connector's hidden prompt alongside the selected local NAS username/categories.
5. Start that one connector instance. Confirm Online in both places, browse the
   expected collections, verify denied categories/other accounts and revocation,
   and then perform explicitly authorized real playback/seek/image/book acceptance.
   The EyeQ browser must be open and permit playback; Synthia reports success only
   after its matching player receipt. AVE40/Display source integration remains a
   separate live-video feature; no AVE40 is required for this NAS library.

The Cloud changes are prepared locally, **not deployed or published** in this task.
See the app README for commands, per-family-user pairing, status and disconnect.
Keep raw diagnostics, accounts, credentials and library content out of Git.
