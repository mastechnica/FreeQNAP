# Personal photo workspace dependencies

The offline land outline in `web/photo-land.json` is Natural Earth 1:110m land
from the Natural Earth vector project. Natural Earth map data is public domain.

- Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson
- Terms: https://www.naturalearthdata.com/about/terms-of-use/
- SHA-256: `9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9`

The optional iCloud connector is installed separately from upstream source;
its code, credentials and cookies are not bundled in this repository.
The reviewed API target is upstream revision
`99a6e7cde77819e739ed293ef411e5468b34873f` of
https://github.com/icloud-photos-downloader/icloud_photos_downloader (MIT).
The archive SHA-256 is
`faec3c59d490d4317b358e7996f06a3c1de8d87ae52d8a56d64b2cdde12c085a`.
This revision includes ADP consent APIs absent from release v1.32.3; live account
compatibility still requires testing. It is an unofficial Apple web client.

ExifTool and FFmpeg are optional distribution packages used through bounded,
unprivileged subprocesses. Their original licenses and distribution notices
apply. This repository does not redistribute their binaries. Video browsing is
original/direct playback; this hardware is not advertised for 4K transcoding.
