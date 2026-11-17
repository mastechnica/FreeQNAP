# Places gallery and full-window viewer — 7 November 2026

Places selections now render in a responsive, vertically scrolling thumbnail grid.
The first batch is followed by additional pages as the user approaches the bottom;
a Load more fallback remains available. Selection changes ignore stale responses,
duplicate item IDs are suppressed, and thumbnail fetching remains lazy and bounded.
No fixed first-120-items cutoff remains in the selected location's gallery.

The map passes its own collection and albums into the photo viewer. Previously,
map selection was absent from the timeline's navigation array, so arrows were
missing. The map also had no timeline album list, which could throw before the
dialog opened; the viewer now uses the selected collection's album context with
an empty fallback. Regression coverage exercises that exact missing-list case.

Opening a location photo fills the browser viewport, with visible left/right
controls, a position counter, keyboard navigation and an optional details panel.
Next can load the following collection page; endpoint buttons disable when there
is no adjacent item. Native fullscreen targets the whole dialog so controls stay
available. Images retain contain sizing; originals, metadata, shares and account
permissions are unchanged.

Fourteen focused JavaScript tests passed, including actual map collection paging,
full-window navigation, preview loading/cancellation, thumbnail queue behavior,
map gestures and map privacy. Live signed-in family browser verification selected
a 159-item location, opened a photo full-window and advanced from item 1 to item 2
using the visible right arrow; the image loaded and fit without hiding controls.
An earlier nine-item selection was also displayed as thumbnail cards. Mobile CSS
is responsive, but physical phone acceptance remains with me.

Only two static assets were deployed with exact old hashes and private backups.
No NAS/service restart or photo-library mutation occurred. iCloud downloading
continued throughout. No personal photos, locations or runtime captures are added
to source or public history. No publication was performed.
