# Metadata editing and Share Social

Open a photo or video in Files, Media Library or Personal Photos & Videos.
The **Metadata / EXIF** button opens the editor only while viewing an item.
Edit its title, caption, photographer, tags, capture time or location. Paste GPS
coordinates or select a location on the offline map. Save the reviewed changes.

Edits use a standard adjacent `filename.ext.xmp` sidecar. Original bytes and
embedded EXIF remain unchanged. Existing sidecars are retained before replacement;
unknown XMP fields are preserved. Personal Photos updates its catalog, timeline
and map. Copy both original and sidecar to preserve edits outside this NAS.
Read-only sources require copying to writable storage before editing.

## Sharing to apps on a phone or computer

Choose **Share Social** in a viewer. **Remove metadata and GPS before sharing**
is selected by default. Choose **Prepare copy**, wait for preparation and integrity
verification, then press **Share…**. The operating system offers supported installed
apps, including email, messaging and social apps. You choose the recipient and send
there. FreeQNAP cannot prove delivery. It never sends a message automatically.

If file sharing is unavailable in a browser, choose **Download copy** and attach
that file in the desired app. Native file sharing requires trusted HTTPS and a
browser/OS that implements file sharing. Phone/PWA share-sheet acceptance requires
an owner test on each intended device; desktop fixtures cannot prove it.

Privacy copies have neutral filenames and do not include XMP sidecars. Photos
become flattened JPEGs up to 4096 pixels wide: original format, transparency and
animation are not retained in the copy. Supported H.264/HEVC videos are remuxed to
fragmented MP4 without transcoding, with at most the first supported AAC audio
track. Chapters, subtitles, data tracks, descriptive container tags and video SEI
metadata are omitted. HDR/Dolby Vision information may be lost. Required technical
codec/duration/dimension information remains. Visible faces, text, landmarks,
speech and information encoded in the actual content are not anonymized.

The isolated cleaner has no network access or original write access. JPEG APP
and comment blocks are removed; MP4 structures are restricted and descriptive
metadata boxes removed. A separate isolated metadata reader then checks the
copy; unsupported/unverifiable files fail closed. They are never silently shared
as originals. Limits: one cleaner at a time, 128 MiB input/output per item, two
active copies per user, eight overall, 20-minute expiry. Close/Cancel removes the
server copy; expired generated files are swept by the worker. Copies already
handed to a device or another app cannot be revoked. Memory/browser limitations
may prevent large items from sharing even below the limit.

Deselecting the privacy option deliberately shares the original, including its
embedded metadata. Sidecar-only edits are not embedded into that original.

## Permissions and API

Administrators grant family members `metadata.edit` and `social.share`
independently of read/write library rights. Editing also requires the appropriate
library/file write permission. Sharing requires read access, including rechecking
scoped family grants while reading a prepared copy. No anonymous/public URL is
created. Disabling an account or revoking its source grant prevents subsequent
NAS reads; already downloaded copies remain with the recipient.

Session-only, same-origin CSRF-protected routes:

- `POST /api/social/prepare`: `{source:{type:"files",share,path}}` or
  `{source:{type:"photos",id}}`; optional `shared` identifies an existing grant.
  Returns opaque `id`, expiry, bytes, MIME, neutral filename and SHA-256 `etag`.
- `POST /api/social/read`: same source/grant plus `id`, `offset`, `count`
  (1–524288). Returns the copy metadata and `data_base64`. Identity, permission,
  original source and recipient are checked on each request.
- `POST /api/social/discard`: same source/grant and `id`; deletes that user's copy.

These are browser-session routes, not token agent operations. Internal broker
operations are not exposed as arbitrary HTTP or agent calls. Metadata operations
are individually selectable in the agent catalog; see [agent API](AGENT-API.md).
