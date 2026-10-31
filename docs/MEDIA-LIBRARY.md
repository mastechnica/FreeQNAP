# Media library

FreeQNAP scans only explicitly configured shared folders. The Media scanner panel shows global enablement, per-folder switches, current folder, indexed count and last progress. Disabling scanning stops a running scan at the next directory boundary; queued scans reject disabled folders. Excluded paths are relative subfolders, one per line. Disabling scanning does not delete an existing catalog or disable DLNA playback. DLNA retains its separate client approval policy.

## Naming and portable metadata

Use `Movie Title (2024)/Movie Title (2024).mp4` for movies, and `Show Name/Season 01/Show Name - S01E02 - Episode Title.mkv` for television. Names are organizational guidance; automatic episode recognition/matching is not implemented. Home movies benefit from descriptive names and dates, with manually edited details.

The scanner reads embedded tags and local NFO (`matching-name.nfo`, `movie.nfo`, `tvshow.nfo`). Covers can be `matching-name.jpg`, `poster.jpg`, `folder.jpg`, or `cover.jpg`. The local SQLite index is a browsing cache; portable companion files remain next to the media. Metadata edits can save matching-name NFO files. Existing companions are retained as `.backup-<random>` files before replacement. Backups currently require manual housekeeping.

The title viewer exposes title, type, synopsis, year, genre, actors/roles, director, producer, studio, rating and other text fields. Only supplied/imported information appears; missing credits are not invented. JPEG/PNG cover uploads are decoded and normalized to JPEG, with a 1 MiB upload limit. Video covers default to 180 seconds, accept an explicit timestamp, or use the player time. This extracts a video frame at that timestamp; it is not a literal screenshot of browser overlays. Short/unsupported videos may require another timestamp. Direct playback depends on browser codec support; there is no streaming transcode service.

## Online sources

TVmaze supports manual TV search; OMDb supports explicit movie/TV title lookup with an owner-supplied API key. The OMDb key is stored in private NAS state, is never returned by the status API, and is sent only to the fixed OMDb HTTPS endpoint. Redirects are disabled and errors are sanitized. Owner-entered searches go to its fixed HTTPS endpoint; local scans do not automatically send filenames online. Preserve its returned attribution. Arbitrary websites cannot be added as scrapers. Additional arbitrary provider connectors and automatic movie/episode matching remain outstanding; no placeholder is represented as operational. See https://omdbapi.com/ for provider account and usage terms.

## Validation limits

Fixture tests cover sidecar roundtrip, prior-file backup, scanner disable, exclusions, invalid cast and invalid capture timestamp. Native regression and UI verification are recorded separately. Physical media cover extraction, uploaded-cover decoding, full metadata roundtrip and long-running scan cancellation require acceptance on real media before production claims. Provider outages and process interruption must not be mistaken for complete scans.

## DLNA compatibility and folder privacy

Playback & folder access offers default and per-observed-device presets for generic players, Apple TV, Roku, Fire TV, smart TVs and audio players. These are saved compatibility recommendations, not codec conversion or a claimed hardware certification. They do not change device approval. The installed Gerbera 2.4.1 setup publishes all DLNA libraries to every approved player. Per-user and per-device DLNA folder restrictions are unavailable; the UI says so. Use authenticated SMB share permissions for private folders, and leave DLNA disabled for them. Never infer access enforcement from a hidden catalog item alone: direct media URLs and previously discovered IDs must also be denied before per-device folder acceptance.

Live audio/video transcoding is visibly unavailable and cannot be enabled through the API. This ARMv7 NAS has no accepted hardware video encoder or transcoding benchmark. Presets recommend direct play and conversion of a copy elsewhere when necessary. Future transcoding needs bounded concurrent jobs, resource limits, cancellation, seek/codec validation and real-player tests. Future DLNA folder scoping needs an enforced server boundary or a reviewed newer server implementation; no cosmetic library selector substitutes for it.

References: https://docs.gerbera.io/en/stable/config-clients.html and https://docs.gerbera.io/en/stable/config-transcode.html describe newer Gerbera capabilities; those docs do not establish support in the installed version.
