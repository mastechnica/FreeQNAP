# Photo connection feedback, shared USB and browsable folders

## iCloud connection steps

The six-digit verification code verifies an Apple sign-in. It does not by itself
prove access to an Advanced Data Protection photo library. FreeQNAP now separates
sign-in, verification, saved-session checks, trusted-device web approval, photo-access
verification and the download itself. The installed connector already establishes
session trust during code verification; FreeQNAP does not repeat that trust request.

Open **Personal Photos & Videos → Import & iCloud**. The connection card provides
persistent status and safe error/next-step messages. **Download new items now** is
disabled until photo access is verified and storage is online, and changes to a busy
state during a download/import. The page shows a download request immediately,
then inventory checks, processed files, errors, per-file bytes and last-pass outcome.
It explicitly says if no iCloud pass has completed. Refresh failures show that the
last status may be stale instead of silently leaving a misleading connected state.

Use **Check saved sign-in** to retry existing local Apple session cookies without
re-entering the password. If the session is missing/expired, enter the password
privately in the NAS page and complete Apple's verification. With Advanced Data
Protection, watch the trusted iPhone for a separate request to approve photo web
access. FreeQNAP checks that the photo inventory can be accessed before calling
this connection ready. Scheduled downloads remain an independent setting.

Apple documents the trusted-device approval and web-access setting in its
[web-access guide](https://support.apple.com/en-us/102630). Depending on OS version,
the setting is called Allow Data Access or Access iCloud Data on the Web. FreeQNAP
does not disable Advanced Data Protection or change an Apple setting for you.
Actual Apple acceptance remains account/device-specific; passing fixture tests does
not prove that an owner has approved a real iPhone prompt.

The NAS retains downloaded originals if they disappear from iCloud. It does not
request remote deletion. Passwords, codes, signed URLs and upstream exception text
are never put into the connection-error record. Only fixed safe classifications and
instructions are saved. Cookies remain private in the owning account's namespace.

## USB storage for family users

Family accounts with file-browsing rights see **USB Storage**, attached-device status,
shared mounted unencrypted USB volumes and read-only foreign filesystem sessions.
They can browse/copy that plain USB content even when someone else mounted it.
This does not grant access to other family members' private NAS library folders.

The explicit **Unlock and use their own encrypted external volumes** permission
also permits mounting/importing existing external filesystems and unlocking them.
No formatting or enclosure-wide eject permission is implied. Existing-volume import
retains the reviewed, device-specific plan and filesystem identity checks. Permission
changes use the existing revocation policy and require a fresh NAS sign-in.

An encrypted volume remains visible as an attached device, but its unlocked content
is available only to the unlocking user/credential. Another account cannot browse,
stream or copy it by guessing a pool/session ID or a direct file URL. Plain storage
sharing and encrypted unlock ownership are intentionally distinct. OS root remains
trusted, and private encrypted pools stay out of protocol exports without mapped
user authentication. See [private-volume rules](USER-PRIVACY-AND-ACTIVITY.md).

## Directory selection

The shared **Browse folders…** dialog provides an expandable tree of available
NAS folders, mounted USB volumes, foreign read-only sessions and unavailable drives.
Locked, offline and inaccessible choices stay disabled, with a link to USB Storage.

File Manager has **Browse drives & folders…** per window. **Copy to…** and **Move to…**
use the same tree before the existing reviewed transfer plan. Personal library/files
locations and photo/music import sources also have Browse controls. Library location
selection can append a new folder name; the picker itself creates nothing. Normal
library setup performs its existing reviewed operation afterward.

Family library-location browsing stays inside that user's reserved personal area,
even when choosing a different volume. It does not list another family's folders or
turn an internal data-volume root into shared storage. Source import selection can
use an accessible USB drive, including read-only sources. Remote SFTP repository
paths, new filenames, encryption key uploads and generated private staging locations
are not local NAS folder-selection controls and retain their respective interfaces.

## Internet radio artwork

Every station card and player cover uses a same-origin artwork URL. When the station
directory provides a favicon, the NAS fetches it without browser cookies, validates
public network targets and redirects, bounds input size, and decodes supported raster
images using the isolated helper. Normalized thumbnails are cached privately.

Missing, broken, unsupported or temporarily busy logos receive deterministic local
vector artwork with station initials, colors, genre and a live-radio motif. Remote SVG
is never passed through. Negative caching and bounded decoding protect this ARM NAS;
visible cards make a small bounded number of retries so available logos can replace
the initial fallback. Artwork loading never starts audio playback.

## Interface additions

All existing session/CSRF and exact agent grants remain in force; new operations do
not silently expand previously issued tokens.

- `photos.icloud-check {}`: starts a saved-session/photo-access check. It requires the
  owning user's iCloud permission and is excluded from agent token grants like the
  other interactive Apple credential-management operations.
- `photos.icloud-status`: adds `authenticating`, `download_running`, `can_download`,
  `connection_problem` and `session_check_available`. A connection problem contains
  only a fixed `code`, `stage`, `message` and timestamp. Existing fields are retained.
- `library.folders {pool,path,offset,limit}`: directory metadata for the location
  picker. Family calls are prefixed by the server-owned user namespace; the browser
  never supplies an owner ID. A missing personal root returns `not_created:true`;
  no directory is created by browsing. Existing storage-choice rights apply.
- `myradio.station-artwork {id}`: returns a supported MIME type, bounded base64 artwork
  and `station_icon`. Existing radio-read rights apply; shared music/book grants
  do not grant access to unrelated station collections.
- `GET /api/radio-station-art?id=<station-id>`: authenticated same-origin image bytes,
  with nosniff, same-origin resource policy and restrictive SVG CSP. Preview mode
  cannot fetch internet artwork. There is no arbitrary-URL proxy parameter.

These changes preserve plain/encrypted distinction at backend file/stream/import
checks, not only in navigation or dropdowns.

Connection failures also expose a fixed `connection_problem.error_kind` category and
`step` for diagnosis. These contain no upstream exception text, response bodies,
account identifiers, passwords or tokens. A photo-access failure does not imply
that a new-device approval or verification code was requested.

### Apple account actions

If Apple returns `termsUpdateNeeded` or `isRepairNeeded`, the connection shows
`account-action-required` with `apple-terms-required` or
`apple-account-action-required`. No web-approval or download request proceeds.
The owner must open iCloud.com personally, review any terms or account prompts,
and confirm Photos opens, then sign in again on the NAS. The application never
accepts legal agreements for the owner. A valid password or trusted-device session
does not by itself prove a usable iCloud Photos session.

## Full-image HEIC previews and location maps

HEIF/HEIC previews use the complete primary image through libheif rather than an
individual video stream/tile. An isolated read-only helper assembles image grids,
applies image transforms and produces a bounded image before JPEG encoding.
The optional photo installer includes the HEVC/AV1 decoder plugins. Original media
remain unchanged. Preview cache version 2 prevents reuse of older incorrect images;
old derived cache files are retained and are not mistaken for originals.

A photo/video with embedded GPS has a location map below its viewer details.
Settings → Library locations and Photos → Import & iCloud expose the per-user
**Use OpenStreetMap city and street maps** preference. It defaults off. When on,
the external map receives the displayed map bounds and pin coordinates, but not
the photo, Apple credentials or other metadata. When off, only bundled offline
land data are used. Offline maps have less detail and no city/street labels.
Polar coordinates fall back to the offline view. No reverse geocoding is performed.

Authenticated `GET /api/account` includes `photo_maps: {online: boolean}` for the
current user. `POST /api/account/preferences` accepts `photo_online_maps: boolean`
independently of the existing `landing_page` choice; unknown fields, owner IDs and
non-booleans are rejected. The preference change is audited and cannot change
another user's setting. New-device browser testing remains separate from unit tests.

### Viewer loading during imports

Completed originals are immutable and retained during placement changes. Preview
reads validate exact file identities and use opened directory/file descriptors
instead of waiting on the lock held by a network download. Preview generation
remains bounded to one decoder per library, waits briefly for admission, and checks
the cache again before decoding. Derived images are published atomically.

The viewer keeps a thumbnail visible while the full preview loads, states when it
is loading or busy, retries temporary busy/server responses at most twice, and
offers **Retry image** after failure. Authentication errors ask for sign-in rather
than repeatedly retrying. Closing the viewer cancels the pending transfer; originals
and the independent iCloud archive job are unaffected by viewer cancellation.

The popup fits each image/video proportionally into its reserved media area,
including upscaling small previews. The toolbar and details occupy separate grid
regions; the image is not cropped to fill them. Details remain scrollable on small
screens, and fullscreen fits the media to the whole screen.

### Recognizing Apple approval requests

The NAS status identifies **FreeQNAP** while requesting iCloud Photos access and
explains that approval may appear on a trusted Mac or iPhone. Apple's popup itself
is generated by Apple. The installed connector provides no supported device-name
field for its web-access approval workflow; a FreeQNAP name in that popup is not
promised. The application does not alter authentication headers or reconnect an
active session just to experiment with popup branding. Saved NAS settings/session
files persist; Apple's temporary authorization may still require renewal.
