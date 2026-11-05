# File Manager transfers and media viewing

Choose a drive, assigned shared folder or personal folder in a window. Open a
second window for another location. First/Previous/numbered pages/Next/Last support
large folders. Copy to… and Move to… in the toolbar/right-click menu open a
browsable destination picker. Internal drag/drop asks Move / Copy / Cancel before
reviewing the transfer. Read-only sources can only be copied.

Copies stage and hash-verify before publication and never overwrite an existing
target. Same-volume moves rename atomically. Cross-volume moves verify the copy,
then retain the original in its source Recycle bin, under the configured retention
policy. A failed/partial transfer retains its completed destinations and remaining
source/partial evidence; inspect Activity instead of blindly repeating it. Recycle
retention consumes source space until originals expire or are explicitly purged.
Mounted read-only foreign USB sessions can be copy/import sources. Identity changes
or a disconnection stop access; no formatting, repair or source write is implied.

The image/video/audio viewer offers previous/next media across the whole filtered
folder, not only its current page. The same viewer remains open for browser
fullscreen navigation. Files open paused. Browser codecs and native fullscreen
behavior still determine playback; original files are unchanged.

Personal library containers and retained archive parents cannot be renamed or
deleted through ordinary File Manager actions. Copy files into a visible import
folder, then use Import current folder… or the right-click import actions to
catalog them. Ordinary personal storage and administrator-assigned shared folders
remain separate from these protected archives.


Viewer-only [metadata editing and Share Social](METADATA-AND-SOCIAL-SHARING.md) preserve originals and offer privacy-cleaned sharing copies.

## Larger folders and clear selection

Each window offers 100, 500, 1000 or All Files. All Files reads bounded pages, renders rows progressively and refreshes less frequently; it stops with an explicit error above 200,000 entries or if the folder changes during enumeration. First/Previous/page numbers/Next/Last remain available for paged views. Select all and Deselect all apply to the loaded view. Ctrl/Command and Shift highlight rows; Select highlighted checks those rows for operations. Existing operation limits still apply.

Right-click a drive or shared location and choose Import to… to browse a source folder and a writable destination. The operation uses the normal reviewed copy plan; selecting folders does not start a copy. The Files title appears above the toolbar.

## Whole-drive imports and destination folders — 4 November 2026

Right-click a drive and choose Import to… to copy all accessible root contents, including subfolders, directly into a destination. The picker asks only for that destination; it does not ask for a source selection. A selected subfolder still imports that folder. FreeQNAP private system entries and symbolic links are excluded; unsupported/unreadable data stops its affected job without source deletion. Existing destination names are never overwritten or silently merged.

Whole-drive imports prepare all immutable copy plans before confirmation, in groups of at most 200 top-level items. One CONFIRM queues the reviewed jobs; each appears in Files and Activity. All source/destination authorization and identity checks still run in the existing service. Above 10,000 root items, import folders separately. If a submission fails, confirmed receipts remain visible and the interface refuses blind retries because the last request might have reached the NAS. Cancel stops further submissions; already queued jobs continue. This is a grouped copy, not an all-or-nothing volume snapshot. Files added after inventory are not included.

Writable destination pickers include New folder. Select the parent, enter one name, and choose Create folder; the new folder is created and selected without closing the picker. Read-only/locked locations cannot create folders. Library setup retains its reviewed-save behavior: Use new folder proposes a location that is created when saved, rather than writing outside a family's private area.

Folder windows now start taller, with a single initial window using the workspace width. Compact controls and rows reserve more height for filenames. Active transfer metrics remain visible; paths and explanatory notes expand under Paths & transfer details and stay expanded across refreshes.

## Scan folders and File Manager imports

The primary library location holds the private catalog; it is separate from a list of watched source folders. Open **Library storage, scanner & metadata settings** in My Radio, **Import & iCloud** in Personal Photos, or **Settings → Library locations**. Add one or more folders using the browser or the saved-library shortcuts, select each collection/category, enable automatic imports if wanted and save. Local audio tags and embedded artwork are read on import. Online title/cover lookups remain a separate opt-in action.

My Radio prepares Music, Books and Podcasts folders; Personal Photos prepares Imports. Existing case variants are reused. A primary location's reviewed save creates the visible base folder; ordinary Personal Files creates its selected folder too. File Manager can copy into those folders. Only saved/enabled scan sources are imported; creating an arbitrary folder alone does not enroll it.

The source scanner waits for your active file transfers to finish, then copies supported originals into the private catalog while retaining the source. This uses additional space. Photo sources wait for existing iCloud/photo imports. Per-folder and global scan switches can disable work. Status distinguishes scheduled, waiting, active, complete and needs-attention states, and Activity retains the native import jobs. Large radio trees are split where possible; a single native import still has a 10,000-file limit. No source deletion propagates to the catalog.
