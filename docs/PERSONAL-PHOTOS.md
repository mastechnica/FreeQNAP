# Personal Photos & Videos

Local deployment checkpoint: the workspace and optional connector are installed.
Synthetic verification passed; no Apple account has been connected and no personal
library has been imported yet.

The dedicated workspace provides a familiar photo timeline, Years/Months views,
manual albums, favorites, captions, original downloads, still previews, video
playback and a GPS map. Live Photo image/motion components share a group; original
and available edited versions remain independently retained. It does not provide
face recognition, Apple's Memories/People models or 4K transcoding.

## Archive retention

Select a mounted, writable data volume and a library name. The app creates a
private `.freeqnap-photos-…` folder, bound to that volume's filesystem UUID and a
library marker. It never writes into the OS mountpoint when storage is missing.
General file operations exclude this protected namespace. Personal-photo agent
permissions are separate and opt-in; existing media/file presets do not expand.

Originals are stored by SHA-256 without overwriting older versions. Partial
files survive interrupted transfers and are resumed only against a matching
remote version and validated range response. Verification and metadata sidecars
precede a successful source record. No cloud-deletion, local pruning, expiration
or bidirectional synchronization operation is offered. Local-folder import copies
supported media without deleting or moving source files.

An image deleted from iCloud before any successful NAS download cannot be saved
by this feature. Keep iCloud until the selected library scopes have completed,
all errors are reconciled and an independent backup has been verified. RAID is
not an independent backup, and the internal array may still be initializing.

## Metadata and map privacy

Capture dates, camera/lens details and GPS are read from embedded metadata;
iCloud's capture date is a fallback where available. Missing dates remain
Undated; missing GPS is never invented. Favorites/captions are saved separately
from immutable originals. Metadata sidecars make the archive inspectable without
relying solely on the SQLite catalog.

The public-domain Natural Earth land outline is served locally. The map clusters
locations on the NAS and supports pan, zoom and selection without sending photo
coordinates to a third-party map provider. It does not include street tiles or
external reverse geocoding. Decoder subprocesses have reduced privileges,
resource/time limits and a local-descriptor-only FFmpeg protocol allowlist.

## iCloud account access

The optional connector uses an unofficial Apple web client, separately pinned
and installed. Apple may change the web interface or expire authorization.
Sign in privately through trusted local HTTPS, then enter Apple's verification
code. Passwords/codes stay out of persistent operation payloads and are not saved;
authentication cookies remain private to the NAS. Apple does not provide this
integration with a separate photo-read-only token; the app's adapter only lists
and downloads assets, and never invokes deletion APIs.

Advanced Data Protection support requires enabling Apple web data access and
approving a trusted-device consent prompt. The pinned upstream revision includes
an API not present in the v1.32.3 release; actual account compatibility remains
unaccepted until tested. Security-key and older two-step accounts are not yet
accepted by this dashboard flow.

Choose whether to include Hidden items and iCloud Shared Photo Library. Imported
Hidden items appear in this private gallery; they do not retain Apple's separate
Hidden-album authentication. Legacy Shared Albums and exact Apple album/folder
hierarchy migration are not currently provided. The last-run report records the
chosen scopes; an incomplete listing or failed download is not reported healthy.
An explicit pause survives scheduled checks. Previously archived files remain
available when Apple authentication expires or the cloud is unavailable.

## API/privacy boundary

Administrator-session endpoints use `/api/nas/photos.*`; original/preview
streaming uses authenticated `/api/photo-file?id=…&variant=…`. Original HTTP ranges
remain supported. Apple sign-in/MFA endpoints require the trusted HTTPS proxy
and are excluded from agent token grants. The new `personal-photo-reader` and
`personal-photo-editor` presets are explicit grants and can expose private media
or GPS; they are not included in old media/file presets. No photos are exported
to SMB, NFS, AFP, DLNA or public URLs automatically.

Original media is data, not a configuration backup. Keep an independent archive
copy, including its metadata sidecars, before deleting your only other copy.
Optional connector sessions require private reauthentication after disaster
recovery; no Apple password is embedded in a project or public package.

### Native synthetic checkpoint

The isolated ARM environment passed all 54 staged photo/agent tests. Separate
synthetic JPEG, HEIC and silent QuickTime files passed native capture-date/GPS
extraction, retained-original hashes, bounded JPEG preview generation, Live Photo
component grouping and GPS map totals. The decoder ran as an unprivileged user
in a network namespace with only read-only inherited input descriptors.
No personal media, Apple sign-in or production archive configuration was used.

Verified-prefix checkpoints additionally retain an uncommitted tail separately
after a crash; they never append to an unverified partial as though those bytes
were known-good cloud content. Normal power controls refuse while photo activity
is running. Live Apple account access and browser workflow acceptance remain
separate checks.


### Local deployment checkpoint — 2 November 2026

The section is deployed on the local ARMhf NAS in an immutable source generation,
with its previous generation retained. The broker uses an isolated, revision-pinned
connector environment; the existing trusted HTTPS service recovered and was probed
successfully. Neither disks, RAID settings, notification preferences nor boot images
were changed. The connector is installed but disabled and signed out. No production
archive directory or Apple account has been configured.

Final verification: 378 host tests passed (four skips); 74 targeted photo, agent
permission and authenticated streaming tests passed on ARMhf. Native synthetic
JPEG/HEIC/QuickTime extraction and previews also passed. A synthetic browser session
verified the compact gallery, location clustering, cluster-to-filmstrip selection and
photo viewer. Map dragging originally intercepted pin clicks; this was corrected and
selection was verified again. These checks do not establish live Apple compatibility.

The owner must sign in privately, choose archive storage and connect Apple with MFA.
Real-account inventory completeness, authentication renewal, actual download throughput
and representative personal-library playback remain unaccepted until that session.
The map is an offline geographic overview, not a street-level mapping service. There
is no facial recognition or automatic semantic image classification in this release.


## Family identities and sharing

Each local user has independent catalogs, storage and iCloud settings/session
files. See [local users, optional Authentik and scoped sharing](LOCAL-USERS-AND-AUTHENTIK.md).
Whole libraries, albums or selected photos/videos can be shared read-only with
other local users, separately from their own collections. Sharing includes selected
content metadata and locations, never Apple credentials or session cookies.

## Responsive places and download feedback

Places uses a local canvas with clustered points, continuous drag/pinch navigation, cursor-anchored wheel zoom and quarter-step zoom buttons. The bundled Natural Earth background remains visible while street tiles load. With online maps enabled, a view must remain unchanged for 2.1 seconds before missing visible OpenStreetMap tiles are requested. Panning or zooming restarts the delay; already cached tiles can still display. No tile prefetch or offline tile pack is downloaded. Photo-details maps follow the same delay. Online maps remain a per-user choice. See the [tile service policy](https://operations.osmfoundation.org/policies/tiles/).

Both the gallery header and Import & iCloud show archive download activity, checked items, processed files and errors. A moving bar explicitly means activity when the inventory total is unknown. When available, current-file bytes and the inventoried-item total are displayed separately; an inventory total may grow as additional collections are inspected and is not a promised full-account total. The connector preserves inventory counters during file-byte updates. Already-running connector versions may not supply totals until their next safe service update; do not restart a live download just to populate a bar.

Private thumbnails and previews can be reused from the browser cache after authorization and validation on every request. Originals retain no-store handling. Loading is limited to four concurrent thumbnail requests, with a bounded timeout so a stalled image does not block the queue.

## Scan folders and File Manager imports

The primary library location holds the private catalog; it is separate from a list of watched source folders. Open **Library storage, scanner & metadata settings** in My Radio, **Import & iCloud** in Personal Photos, or **Settings → Library locations**. Add one or more folders using the browser or the saved-library shortcuts, select each collection/category, enable automatic imports if wanted and save. Local audio tags and embedded artwork are read on import. Online title/cover lookups remain a separate opt-in action.

My Radio prepares Music, Books and Podcasts folders; Personal Photos prepares Imports. Existing case variants are reused. A primary location's reviewed save creates the visible base folder; ordinary Personal Files creates its selected folder too. File Manager can copy into those folders. Only saved/enabled scan sources are imported; creating an arbitrary folder alone does not enroll it.

The source scanner waits for your active file transfers to finish, then copies supported originals into the private catalog while retaining the source. This uses additional space. Photo sources wait for existing iCloud/photo imports. Per-folder and global scan switches can disable work. Status distinguishes scheduled, waiting, active, complete and needs-attention states, and Activity retains the native import jobs. Large radio trees are split where possible; a single native import still has a 10,000-file limit. No source deletion propagates to the catalog.

### iCloud album import

Import & iCloud has a separate, opt-in **iCloud albums** panel. Enable it and
choose **Import albums now**, or check every 1–24 hours (default six). Each NAS
account uses only its own saved Apple sign-in and selected archive. Photo and
iCloud management permissions are required. This is optional, including when
photo downloads are already enabled.

Personal iCloud album names and membership are imported using stable Apple album
identifiers. Identically named albums remain separate. Downloaded originals join
the matching album; membership awaiting a download is retained and attached on
later passes. Renames update the imported title. Existing local albums, archived
originals and previously imported membership are never removed by remote deletion.
This deliberately preserves an archive rather than an exact live mirror. Smart
Albums, nested folder layout, legacy Shared Albums and Shared Photo Library album
membership are outside this implementation.

The optional `freeqnap-icloud-albums.timer` runs a bounded album-only companion.
It copies saved session files into a private temporary directory, without writing
the active downloader's cookie directory. Passwords and verification codes are
not requested by this worker. If Apple requires renewed authentication, use the
existing private sign-in controls and then retry album import. Progress reports
album counts, linked archived memberships and memberships waiting for originals.
A failed album does not discard successful albums or delete existing membership.

The isolated worker retains `PrivateDevices=yes`. After first selecting or changing
archive volumes, run `python3 tools/configure-icloud-albums.py` as root from the
installed source directory. It verifies mounted filesystem and block-device
identities and exposes only those device node paths read-only for identity checks.
It does not allow raw device I/O, mount or unlock storage. Missing/offline/changed
volume identities fail closed. This preparation is needed before the first album
import on a new archive volume; the dashboard reports an unavailable archive
rather than bypassing its identity check.

### Physical acceptance — 5 November 2026

The owner's existing saved session successfully listed eighteen personal albums.
The final pass processed 946 distinct Apple asset references into 874 unique
album/master memberships, with zero failed albums. At that snapshot 260 memberships
linked to archived originals and 614 awaited downloads. Counts are memberships,
not a claim about unique photos across the entire account. The two-minute local
companion pass attaches subsequently archived photos without needing another
remote inventory. The remote album inventory is configured for six-hour checks
on the requested account only; other accounts remain opt-in.

A live variant case exposed multiple distinct Apple asset records sharing one
original master. The importer now deduplicates masters for membership while
validating asset-reference uniqueness and both initial/final remote counts.
Repeated asset records still fail completeness checks. Both cases have regression
coverage. Existing downloader sessions and the long-running native worker stayed
intact. PrivateDevices remains enabled and raw block-device I/O remains denied.

The physical run proves the current personal album interface and available
memberships, not every future Apple API change. Pending originals still require
successful archive downloads; a membership entry cannot recover a photo deleted
before it downloads. Nested iCloud folder layout, Smart Albums and shared-library
album replication remain outside this acceptance.
