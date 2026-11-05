# File browsing, map navigation and visible iCloud progress — 4 November 2026

Implemented per-window page sizes, All Files with bounded enumeration, separate row highlighting/checking and Import to… with source/destination folder pickers. The Files heading is separate from its toolbar. Added private revalidated artwork caching and a four-request thumbnail queue. Places now uses clustered canvas rendering, fine continuous navigation and offline land behind delayed street tiles. Both photo entry points show the same download progress, with unknown totals labeled honestly.

Local regression: 565 Python tests passed (16 optional/environment skips), and 70 JavaScript tests passed. Conditional HTTP tests exercise authorization before 304 and denial after revoked access. Map tests exercise anchored zoom, drag/pinch and no tile requests before a stable 2.1-second view. These are automated checks, not physical hardware acceptance.

Console-only deployment preserves the existing broker, live USB copy and iCloud session. Connector inventory-counter improvements are staged for the next safe broker update; the currently running downloader does not expose a complete expected total. No invented percentage or completion claim is made. Private evidence and screenshots stay ignored; no public push is performed.

## Live activation

Release `3f27800` passed all 10 media HTTP and two cache tests on the ARM NAS. The dashboard was activated without changing the broker process. Both MD arrays remained fully populated, non-degraded and idle. The signed-in family gallery showed an active iCloud progress bar and increasing processed totals; the Files view showed the separate heading, selection controls and page-size selector. The existing USB copy continued past 27 GB verified of approximately 106 GB; it was not complete. The running iCloud pass reported 16 failures needing follow-up; no complete-account acceptance is claimed.

A source-package check initially flagged a synthetic fixture directory's capitalized users component as a private host path. Renaming only that fixture resolved the check without weakening the scanner. Package and showcase checks passed. Raw screenshots remain private.

Live Import & iCloud also showed both identical activity bars and current-file byte progress. A byte-only observation exposed the old connector's missing counters; the browser now keeps observed counters per account during the running pass and says Waiting for item counts when none have arrived. The final 72 JavaScript checks include both cases. Places gesture/delay acceptance remains automated; no owner visual acceptance of the new map is claimed.
