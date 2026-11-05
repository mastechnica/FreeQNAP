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

Library bindings retain a stable owner ID across location changes. Family dashboard accounts have separate library owners and existing per-user authorization; storage-folder or SMB access alone does not grant library access.
File Manager refuses moving/deleting library container ancestors, including
retained old locations. Change library placement through Settings instead.

Album and station artwork uses account-scoped private HTTP caching with authorization revalidation on each request, reducing repeat image transfers while keeping account and sharing boundaries.

## Scan folders and File Manager imports

The primary library location holds the private catalog; it is separate from a list of watched source folders. Open **Library storage, scanner & metadata settings** in My Radio, **Import & iCloud** in Personal Photos, or **Settings → Library locations**. Add one or more folders using the browser or the saved-library shortcuts, select each collection/category, enable automatic imports if wanted and save. Local audio tags and embedded artwork are read on import. Online title/cover lookups remain a separate opt-in action.

My Radio prepares Music, Books and Podcasts folders; Personal Photos prepares Imports. Existing case variants are reused. A primary location's reviewed save creates the visible base folder; ordinary Personal Files creates its selected folder too. File Manager can copy into those folders. Only saved/enabled scan sources are imported; creating an arbitrary folder alone does not enroll it.

The source scanner waits for your active file transfers to finish, then copies supported originals into the private catalog while retaining the source. This uses additional space. Photo sources wait for existing iCloud/photo imports. Per-folder and global scan switches can disable work. Status distinguishes scheduled, waiting, active, complete and needs-attention states, and Activity retains the native import jobs. Large radio trees are split where possible; a single native import still has a 10,000-file limit. No source deletion propagates to the catalog.

The optional [technology and security podcast starter list](TECHNOLOGY-PODCASTS.md) contains verified publisher feeds. Subscribing loads metadata; saving an episode is a separate audio-download action. The larger-feed reader is available in current source, with the live legacy-worker activation limit documented alongside that list.

## Podcast shows and episodes

The Podcasts landing page lists subscribed shows with publisher artwork, genres and latest episode dates. Choose a show to expand its episode browser. Use Back to shows to return. Search covers shows, publishers, titles and notes; filters select genres, publishers, publication age and downloaded state. Sort by newest/oldest, title, publisher or episode count, and by duration within a show. Choose 25, 50, 100, 500 or All and navigate using the page controls.

Cover images are served through the NAS and privately revalidated in the browser cache. A colorful fallback appears if publisher artwork is unavailable. Show expansion does not play audio. Play saved episode is explicit; Save episode queues an audio download. Manage subscriptions stays collapsed below the library. Refresh library refreshes the local listing; Check for new episodes explicitly refreshes the publisher feed. Legacy workers can expose only their recent per-show window; that limitation is displayed, and All covers the currently available view. Native full retained-history paging is available after its safe idle activation.

### Edit your collection cards

Open the three-dot menu at the top right of Music, Books, podcast-show and Internet Radio covers to edit details and cover art. Books and music retain their existing metadata/sidecar editor, optional title lookups and original-download action. Shows and stations have personal title, creator/publisher, genres, description and website overrides, plus JPEG/PNG/WebP cover uploads below 1 MB. These display changes do not change stream or feed destinations. Shared libraries remain read-only. Custom cover responses require current account/library access even when cached.

AAX files are retained as audiobook originals with embedded tags and covers when available. They are explicitly labeled as needing a compatible authorized player; importing does not remove DRM or establish browser playback. A DRM-free audio companion may be linked from Details. Subject genre and audiobook classification are separate. Native AAX upload acceptance becomes active on a safe storage-worker reload; the current UI update does not restart active transfers.

### Existing music collections

Local embedded tags are preferred. A missing tag may use unanimous values from at least two tagged tracks in the same album folder; conflicting values remain unresolved. Existing structured album NFOs can supply declared album fields, while plain release notes remain unchanged. Missing identification is labeled **Needs identification** and can be edited from the three-dot menu. Original music filenames and playlists need not be renamed for scanning.

A reviewed music folder can receive per-track `.metadata.json` sidecars (bounded hashed names for exceptionally long filenames). They are tied to the original filename, inode, size and modification time, and are ignored if stale, malformed or linked. Normal folder import consumes valid sidecars. The private catalog also keeps its usual metadata sidecars and prepared-file identity, so rescans verify unchanged files without repeatedly decoding an entire collection.

Same-volume catalog hard links retain the reviewed original audio without a second full-sized data copy. They share the underlying bytes: modifying an original also modifies its linked catalog original, and identity checks reject changed files until rescanned. Removing a source name does not remove the catalog link. This is not a backup. Existing embedded/front-cover images are preferred over guesses; unresolved art stays a placeholder. `@eaDir` folders are excluded from future imports. The optional maintenance tag/art decoder uses Debian's `python3-mutagen` and `python3-pil`, with descriptor-only input, an unprivileged network namespace and resource limits. See [Mutagen file-object documentation](https://mutagen.readthedocs.io/en/latest/user/filelike.html).


## Your listening overview

My Radio opens on Overview. Compact cover rows show recent listening in Music, Audiobooks, Podcasts, Internet Radio and Books. Until you play something, each row is explicitly labeled Explore your collection. Browsing never starts playback. Your own listening card shows hours, category time, genre percentages, top tracks and top stations. Tracking starts with your next actual play; earlier listening is not reconstructed. Browser-reported heartbeats are bounded by server time, pause time is excluded, seeking adds no listening time, and missed/offline heartbeats can undercount. Shared-item history is rechecked against current access before displaying titles.

## Browse music by album

Music opens a cover-art album grid, not thousands of individual songs. Search albums, artists or song titles, filter artists/genres, and choose 25, 50, 100, 500 or All albums. Open a cover to see album details and its ordered disc/track list. Play album is explicit. Each track retains its own Details editor. Existing embedded/local cover art is preferred; unresolved covers use a colorful placeholder instead of an invented match. Common compilation titles and unidentified folders stay separated using reviewed source-folder evidence.

Edit album details changes only fields you actually alter across that album's tracks; individual song titles and performers remain intact. Uploaded album artwork is an account-scoped display override. Album edits can partially succeed if storage stops responding: the error reports how many track writes completed so you can inspect before retrying. Shared collections are read-only.

## Books, series and collections

Books supports author, genre, format, series and collection filters. Details includes series name, reading-order number and multiple collections. Series ordering uses the numeric reading order where available. These organization fields are retained in the local account configuration; the original book file is unchanged. Existing core metadata sidecars remain in the private catalog. Include both library content and configuration in backups.

## Find matching metadata

Every music/book/show/station editor includes Search enabled metadata providers. Searches are explicit: enable MusicBrainz for music, Open Library for books, or the optional Apple Podcasts title directory and Radio Browser in Library settings. No provider is silently enabled. Only the entered title/creator search is sent; originals and playback history are not uploaded. Review a result before applying metadata or optional cover art. Search results expire after ten minutes and are bound to the account, requester and exact item.

Podcast matching is limited to already-enrolled feeds whose declared region matches the selected United States/Canada region. Radio search results are restricted to that selected country. Publisher RSS supplies podcast artwork; store promotional artwork is not imported. Applying display metadata never changes a subscription feed or station stream. External cover access is validated and raster-only; inaccessible covers can be replaced by an upload. No transcoding is introduced.

## Prepared music while existing copies run

A reviewed large collection can be indexed by the isolated updated scanner while the older storage worker continues an unrelated photo copy. Browsing works immediately. The UI pauses full-library rechecks until that worker can safely reload its optimized scanner; this avoids interrupting an existing copy or re-decoding the entire collection. A completed maintenance scan is distinct from this pending routine-worker activation.

The album index is cached privately to keep large libraries responsive. Each use rechecks native access and the current item count. Known edits invalidate it. After ten minutes an unchanged index can be served while it refreshes in the background; an index older than a day or with a changed count must rebuild. Refresh albums explicitly rebuilds it. Permission revocation is enforced before cached reads; media playback still reauthorizes the selected original. Source album grouping does not split compilations by individual song years.

## Reconcile fragmented albums

Album identity follows reviewed album/album-artist evidence across source folders. Case, accents, punctuation and song release years do not independently split a known album. Reviewed assignments are bound to the current album metadata, so changing a track's album can move it. Unrelated unidentified or generic compilation folders remain separate unless reviewed. Disc and track order remain distinct from album identity. Original artist/guest credits are preserved separately from the album artist.

Verified byte-identical originals appear as retained identical copies below the selected track. Other files with matching intended title, performer, disc/track and near-equal duration appear as other copies/versions; that label does not claim their audio bytes or performances are identical. The preferred playable file is used in the normal queue, with every alternative still available. Live/remix titles and materially different durations stay separate. Album edits include the retained alternatives. No original is deleted by grouping.

Music has All album statuses, Needs identification and Audio unavailable filters. A source with no decodable audio remains visible with an explanation and no normal Play control; adding a title does not repair it. An existing valid file for the same clearly identified album track takes precedence, with its unavailable source copy retained separately. Metadata and local sidecars are updated without rewriting encoded audio. Missing/corrupt originals and genuinely unidentified recordings require better source material or further review.
