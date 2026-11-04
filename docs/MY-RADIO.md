# My Radio: a private listening and reading library

My Radio is a main dashboard workspace and is available in the installed FreeQNAP
PWA. Music, Books, Podcasts and Internet Radio have their own views. The player
stays available while moving between dashboard pages. Nothing plays until you
choose Play; station checks read small samples without playing sound.

## Storage and privacy

Choose a mounted writable data volume on first setup. An encrypted volume must
be unlocked first; reconnecting removable storage requires the same recorded
volume identity. Locked/offline library storage is shown explicitly. FreeQNAP creates a private,
identity-marked `.freeqnap-myradio` directory with `music`, `books`, `podcasts` and
`incoming` children. These are separate from general shares, the movie/TV media
library and `.freeqnap-photos`. They are not automatically shared through SMB,
NFS, AFP or DLNA. Root-owned private modes protect them from file-sharing users;
the administrator and explicitly authorized agents can access their contents.
Changing the storage binding after setup requires a deliberate migration.

Upload files using **Add files**, copy a folder from an existing share, or enter a
public download URL and destination filename. Folder imports leave source files
unchanged. Interrupted uploads are retained: choose the same file again to compare
all already-uploaded bytes and resume. If transfer finished but decoding was
interrupted, use **Finish preparing**. Downloads retain verified partial files
and offer explicit Resume after failure. Restarting the broker does not silently
repeat imports or network downloads. Import failures may retain private `.partial`
files for inspection; these are not indexed as media and are not automatically
purged. Archive-original replacement is not implemented. Reviewed library relocation is available in Settings; the previous archive is retained.

## Music and metadata

Search titles, artists, albums or authors; filter artist/author and genre; sort
by title, artist/author, album, year or date added. Favorites are local. Embedded
music tags supply title, artist, album, genre, track, year and duration. Embedded
artwork is extracted when possible. **Details** edits metadata and accepts cover
art up to 1 MB. Owner edits and custom cover art survive rescans.

**Scanner & library settings** independently enables scanning for each collection.
A scan reads only the managed My Radio directories; it does not crawl other NAS
folders. Disabled scanning does not prevent an explicit upload/import from being
indexed. Activity shows queued scans/imports. The scanner reports its last state,
phase, file, indexed count and bounded errors. Refresh the workspace to obtain a
new scanner/download snapshot.

Optional MusicBrainz and Open Library searches are **off by default**. Enable the
provider, then choose **Find title metadata** on an item and review a match before
applying it. Titles and artist/author searches are sent to that provider only for
these explicit searches. MusicBrainz requests are serialized and rate limited.
Selected covers come from Cover Art Archive or Open Library. They are decoded
locally before being served. Providers can be unavailable or return wrong matches.

With sidecars enabled, portable `metadata.json` and `cover.jpg` live beside each
original. SQLite remains a searchable index and holds favorites, positions and
subscriptions. Sidecars do not replace a backup of the library and application
state. A future fresh-install index reconstruction from all sidecars still needs
separate acceptance; it is not advertised as a tested disaster-recovery procedure.

## Books and playback

| Format | Current behavior |
| --- | --- |
| MP3, M4A/M4B, AAC, FLAC, Ogg/Opus, WAV, AIFF, WMA | Original audio served with HTTP byte ranges; actual codec support depends on the browser |
| EPUB, TXT, DOCX | Bounded local text extraction; chapter/page navigation and device read-aloud |
| Text PDF | Optional Poppler text extraction; scanned/image PDFs need OCR first |
| DRM-free MOBI, AZW, AZW3 | Optional libmobi text extraction, up to 64 MB input; unsupported editions remain originals |
| KPF or DRM-protected editions | Original retained/downloadable; link a readable EPUB/TXT/PDF/DOCX or audiobook companion in Details |

There is no DRM-removal feature. A file extension alone does not guarantee the
file can be decoded. The NAS retains unsupported originals and explains the
reading limitation. For a linked audiobook edition, Play uses that audio file.

Audio supports seek, pause, previous/next, skip back/forward, speed, saved position
and browser Media Session controls where available. The text reader supports
chapters/pages, font size, local voice choice, read-aloud, pause and stop. Reading speed (0.5–2×) and pitch
(0.5–2, normal 1) are adjustable; voice URI, speed and pitch persist per browser.
Changing settings while paused does not start sound. Some device voices ignore
pitch or vary their behavior; intended-device listening is still required. Only
voices marked local by the browser are offered. The NAS has no dependency on a
paid speech service. Device voices, background speech, lock-screen controls and
PWA behavior need testing on your intended phone/browser. No transcoding, Cast,
AirPlay or automatic network-player control is implied by My Radio playback.

## Podcasts

Subscribe to public RSS/Atom feeds from United States or Canadian services,
choose their publisher/service country, refresh them, choose an episode, and save it
to the private podcast collection. Saved episodes remain even if the publisher
removes them. Optional six-hour subscription refresh updates listings only; it
does not automatically download every episode. Feed/enclosure URLs are stored
locally and are excluded from job payloads and subscription-list responses.
Existing unclassified subscriptions require country confirmation before episode
listing, refresh or new downloads; their saved originals remain retained. Country
is an owner declaration for podcasts, not an inference from CDN IP addresses.
Search filters subscribed episode titles, series and descriptions.
Descriptions are displayed as text. Subscription refresh is not a promise that a
publisher's paid or authenticated feeds will work.

## Internet Radio

The current regional seed directory contains 54 United States and Canadian
stations independently checked using bounded audio samples on 4 November 2026
(26 US, 29 Canadian). Other-country and unclassified stations are hidden, and
the stream endpoint refuses their IDs. Existing saved rows are retained. Country, genre/group, codec, bitrate, favorites
and last-check status are available. **Search online directory** searches station names on Radio Browser within US
and Canada, with optional genre and country filters; **Refresh results** retains
the selected filters and reloads the local results. It queries Radio Browser and checks each returned direct stream. Older entries remain; availability
can change. Checks older than seven days are clearly marked for rechecking. Add a
custom public direct audio URL using **Check & add station**. Playlist/webpage URLs
are rejected; codec compatibility remains a separate browser requirement.

Streams are proxied through the authenticated NAS origin, avoiding mixed-content
errors and disclosing no dashboard session to the station. Public requests pin
resolved public addresses and revalidate every redirect; local/private, reserved,
embedded-login and address-translation targets are denied. Four simultaneous
streams and six hours per connection are bounded. Reconnect to continue listening.
Station requests reveal the NAS's outbound IP to the provider. Refreshing the
station directory is opt-in; no account is required.

## Installation and validation

`sh deploy/install-myradio.sh` installs optional Debian `ffmpeg`, `poppler-utils`
and `libmobi-tools` decoders. It does not initialize storage, enable an online
provider or play audio. External decoders use read-only inputs, restricted network
namespaces, reduced privileges, resource limits and timeouts. Under the hardened
NAS service, PID 1 starts a separate unprivileged helper before applying its
set-ID syscall restrictions. The original broker protection remains enabled;
input is a read-only inherited file and derived output remains private. Book archives have
entry, directory, expansion and text-output limits. Originals are never executed.

Fixture tests cover archive traversal/entities/bombs, private targets, changed
originals, upload-byte comparison, interrupted downloads, post-rename restart
reconciliation and private storage isolation. Native ARMhf tests decoded synthetic
TXT/DOCX/EPUB/PDF/PalmDOC-MOBI and read tags from a silent MP3. These do not establish
all commercial ebook variants, codecs, station availability or mobile playback.


## Choose library locations and import USB folders

Before first use, choose a mounted writable volume and a dedicated folder on the
Music or Personal Photos & Videos page. The setup card links to **Settings →
Library locations**. Existing installations without an explicitly chosen visible
folder show the same prompt; their old originals remain intact. Internet Radio
streaming does not require local library storage.

Settings is the permanent place to change volume/folder. A reviewed background
operation copies the protected archive, verifies every copied file, refreshes
original-file identities and switches catalog/location together. The destination
must not already contain a private archive. The old archive is retained and its
location is shown in Settings; it still consumes space. Interrupted copies remain
for inspection and are never silently merged or overwritten. Refresh the location
card or check Activity after the operation. Do not select the same physical
storage as an independent backup.

The visible chosen folder appears as a named shortcut in File Manager's drive
list and sidebar. Its protected subfolder contains the indexed originals and
metadata and remains excluded from ordinary file manipulation/shares. Files
copied into the visible folder are **not indexed automatically**: use **Import
current folder…** or right-click a folder and choose an import action. Choose
Music, Books/Audiobooks, Podcasts, or Personal Photos & Videos. Supported files
and subfolders are copied into that library; source files are retained. Ordinary
copy/paste and drag/drop between writable registered locations remain available.

Attached USB volumes must be mounted (and unlocked when encrypted) first. Folder
imports support registered read-only USB sources and validated foreign read-only
unlock sessions without granting writes to them. Missing/disconnected/changed
sources stop or report an import failure rather than redirecting writes. An
unsupported/unmounted disk must first be made browsable in USB drives. Importing
an entire folder is explicit; there is no automatic USB ingestion.

Library bindings retain a stable owner ID across location changes. Currently that
owner is the local administrator; family PWA authentication and per-user brokers
are separate authorization work, not implied by a storage folder or SMB account.
File Manager refuses moving/deleting library container ancestors, including
retained old locations. Change library placement through Settings instead.
