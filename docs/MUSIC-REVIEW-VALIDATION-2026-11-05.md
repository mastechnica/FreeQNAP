# Music review and M4B replacement — 5 November 2026

This maintenance uses exact private library and volume identities, a reviewed per-file inventory, an independent private catalog backup and descriptor-relative file operations. It does not format volumes, change RAID membership, interrupt the photo transfer or restart the storage worker. Raw file lists, checksums, identities and media stay outside Git.

The source collection contains 7,958 audio files (about 76 GB of audio). Embedded artist/album/title tags, corroborated same-folder values and existing artwork are reviewed locally. Uncertain filenames and all release-note NFOs are preserved. Identity-bound music sidecars supply scanner metadata; same-volume hard links avoid duplicating the full audio collection. Prepared metadata rescans recheck the exact original identity before using their cache.

Ten M4B replacements are matched to the existing audiobooks by title, author and duration. Local ten-second decoding samples passed. New NAS originals must pass complete checksums before their existing catalog IDs are updated and the exact old AAX originals/staging copies are removed. Favorites, progress and other books are preserved.

Synology cache deletion is restricted to the inventoried `@eaDir` subtrees, with complete per-file identities, no links or mount crossings, and bounded cache-file sizes. Useful per-track cover derivatives are extracted before cleanup. No other source files are deleted or renamed. Final physical results are recorded after application and scan completion.


## Completed device results

Ten M4B replacements (3,943,311,477 bytes) passed full checksums after transfer and after catalog registration. Existing book IDs, favorites and progress were retained; embedded cover images were normalized. All twenty approved old NAS AAX originals/temporary copies were removed only after replacement verification. Source files on the owner's computer were preserved. Local ten-second decode samples passed; this does not prove every browser supports every codec or every second of content.

The music audit found 7,958 audio files totaling 75,984,725,009 bytes. Complete or corroborated artist/album/title identification was available for 7,365; 593 are labeled Needs identification. Existing usable artwork was found for 5,722 tracks. All 43 release-note NFO files were preserved, and no source audio filenames were renamed. Identity-bound sidecars and verified same-volume hard links registered the collection without a second full-sized data copy.

Cleanup removed only 708 inventoried Synology cache roots containing 11,136 cache files (326,239,533 bytes), after useful track-cover extraction. Fourteen initial probe errors were resolved with the bounded format-aware local readers. The final physical scan indexed 7,968 assets: 7,958 music tracks and ten books, with zero errors and a complete receipt. Both internal arrays were healthy and idle. The original storage worker and ongoing photo transfer were preserved.

Album grouping and the new listening overview are separately checked in the radio-hub validation report. Unidentified titles/artwork are not claimed as identified, and sample playback checks do not prove every format is browser-playable.
