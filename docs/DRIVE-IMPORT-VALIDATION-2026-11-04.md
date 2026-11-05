# Destination-only drive imports and larger file windows — 4 November 2026

Whole-drive Import to… now asks only for the destination, then prepares the full accessible root contents in existing reviewed copy jobs. The shared destination picker can create/select a new folder in a writable parent. Folder controls, incoming notices and transfer details are compacted; windows are taller and detail expansion survives polling. No backend, permission or disk-layout change is required.

All 80 JavaScript checks passed, including 451 root items split into 200/200/51 plans, destination cancellation without reads/writes, exact plan bindings, ambiguous submission rejection, folder creation and read-only/path boundaries, deferred family-library paths and retained transfer-detail expansion. Package and showcase checks passed. Tests use fixtures; no real whole-drive copy or new user folder was submitted for validation. Console-only deployment preserves running copy and iCloud processes. No public push.

## Live verification

The signed-in family account's USB drive context action opened the destination picker directly. Selecting an existing writable personal location enabled New folder, and the name/create controls opened correctly. The check was canceled without creating any user folder, preparing a real import or submitting copy jobs. A populated mounted drive then displayed 345 root items with paging and approximately twelve rows visible in the current browser view, compared with the earlier five-row complaint. Screenshots are retained privately.

The initial live check exposed an interaction with the common button busy handler: New folder checked the button's temporary disabled state and returned before opening. The guard now checks actual destination permissions/state instead; the fixture uses the same busy-wrapper behavior and all 80 tests passed again. Console-only activations preserved the original background-worker PID. No disk, mount, RAID or notification changes were performed.
