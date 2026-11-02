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
