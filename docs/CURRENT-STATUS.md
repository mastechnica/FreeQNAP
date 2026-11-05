# Accepted personal media maintenance — 5 November 2026

Music reconciliation is applied and verified: 5,487 corrections, 7,958 originals
preserved, 706 album cards and 7,270 main tracks with expandable alternative files.
No originals were renamed or deleted. Forty-eight unusable originals and 154
identification flags remain visible; 523 albums have existing cover art. This is
not a claim of pristine/full-content acceptance. See [reconciliation evidence](MUSIC-RECONCILIATION-2026-11-05.md).

Eighteen personal iCloud albums imported successfully, using additive retention.
The accepted pass linked 260 archived memberships and retained 614 pending ones;
subsequently downloaded originals attach automatically. No Apple session or native
storage-worker restart occurred. Shared/Smart Album and nested-folder replication
remain excluded. See [personal photo behavior and acceptance](PERSONAL-PHOTOS.md).

Books contains ten retained audiobooks and three distinct public-domain eBooks:
Meditations (TXT), The Time Machine (EPUB3) and We (AZW3). All thirteen items have
title, author, genre, synopsis and cover art. The three new originals passed
SHA-256, native text-reader and artwork checks; the live family interface and
metadata editor were verified. See [book import acceptance](BOOK-IMPORT-VALIDATION-2026-11-05.md).

Both internal arrays remained non-degraded and idle. The original long-running
native worker and active photo work remain intact; optimized full scans still
need an idle native-worker adoption after transfers finish. Local regression:
653 Python tests (16 optional/environment skips), 90 JavaScript checks and
package/showcase checks passed. Source changes and sanitized reports are committed
locally only; nothing was pushed or published.

# Album-based music and personal listening hub — 5 November 2026

Music now opens as cover-art albums with ordered track/details views. My Radio opens on a personal Overview with honest recent/explore rows and listening statistics starting from actual new playback. Books gains series, reading order and collections. All card editors offer explicit matching searches against enabled metadata providers; none is silently enabled.

Physical maintenance completed: ten checksum-verified M4B replacements, 7,958 music tracks indexed, 5,722 tracks with existing artwork, 593 needing identification, zero final scan errors. Source filenames and 43 release-note NFOs were retained. Only the approved Synology cache trees and replaced NAS AAX copies were removed. See [music maintenance results](MUSIC-REVIEW-VALIDATION-2026-11-05.md).

The active photo copy and original storage worker are preserved. Full-library routine rescans remain gated until a safe optimized-worker reload; the isolated updated scanner already completed the requested indexing. No NAS reboot, new provider disclosure or public push is part of this update. 634 Python tests (sixteen optional/environment skips), ninety JavaScript checks and package/showcase checks passed. Twenty-three focused tests also passed on the NAS. Final live album reads took about 4–5 seconds during the ongoing copy. See [album/hub validation](MY-RADIO-HUB-VALIDATION-2026-11-05.md) for browser acceptance and remaining limits.

# Show-first podcast browser — 4 November 2026

4 November: Show-first podcast browsing deployed; all 13 publisher covers fetched and 3,044 currently indexed episodes available. Personal three-dot card editing is deployed. Ten AAX audiobook originals and their covers/metadata were imported and checksum-verified in the personal catalog; active transfers remain running. Native pagination/AAX upload acceptance awaits a safe storage-worker reload.

Podcasts now opens as a compact show-cover grid. A show opens its own episode view, with Back to shows and an explicit saved-episode play button. Search spans show names, publishers, episode titles and notes. Genre/publisher filters, rolling publish-date filters, downloaded/not-downloaded filters and chronological/title/duration sorting are available. Both views offer 25, 50, 100, 500 or All, with First/Previous/page numbers/Next/Last. Browsing, expanding a show and loading artwork never start audio. Subscription management stays collapsed.

Publisher covers are fetched through a public-address-pinned, bounded local proxy and privately cached. RSS header reads stop before episode bodies; remote SVG/HTML is rejected. Account and library-share authorization is repeated before serving artwork or 304. Client artwork loading is limited to two concurrent images; missing images retain deterministic colorful fallback covers. Original feed URLs are not returned by the browser API.

The console browser works with the already-running broker by gathering its authorized per-show windows; it labels those legacy windows explicitly. Native retained-history pagination is also implemented and byte-budgeted for the existing two-MiB broker frame, but requires a safe broker reload after active copies/imports finish. All means all episodes available in the current view, not every historical episode ever published. No active worker is restarted for this UI update.

Local verification: 594 Python tests with 16 optional/environment skips, 85 JavaScript checks and package/showcase checks passed. Coverage includes real date ordering, genre/search/download filters, every page size, modern cursor following, legacy-window labeling, cache reauthorization, revoked artwork access and Unicode response budgets. Native/live acceptance is recorded after deployment; no public push.

# Watched library folders and verified podcast subscriptions — 4 November 2026

The family music destination is enrolled for automatic source import and is waiting for existing file copies. Multiple source folders, category switches, browse controls and saved-library shortcuts are live in My Radio, Personal Photos and Library Settings. Required source folders were prepared through existing scoped file operations.

The requested ten technology and three cybersecurity subscriptions were populated and verified through the family account's listing, without audio downloads or preference changes. Oversized RSS feeds required the new bounded reader in an isolated metadata import; the ongoing broker still needs an idle reload before its own large-feed refresh handler gains that fix. Active transfer/iCloud workers were preserved.

Final local regression: 582 Python tests (16 optional/environment skips), 82 JavaScript checks, package and showcase checks passed. Real music import/artwork acceptance awaits the running copy's completion. Updates are committed locally only.

# Watched library folders and music-copy enrollment — 4 November 2026

Added persistent account-scoped source folders for My Radio and Personal Photos, separate from the primary private catalog location. Each collection can watch multiple accessible folders, with per-folder enable/category controls, a schedule and manual scan. Saved library locations populate source shortcuts. Successful library-location saves prepare required visible source folders through the existing authorized file service; existing spelling/case is reused. Personal Files already creates its selected folder during its reviewed save.

The existing My Radio global and category scan switches remain authoritative. Automatic source imports wait for the account's queued/running file transfers; photo folder imports also wait for current photo/iCloud work. The music destination is enrolled using its exact existing folder spelling without moving, renaming or restarting its transfer. Metadata from local tags and embedded covers is read on import. Internet providers remain unchanged and opt-in; this update does not claim automatic online enrichment.

The source coordinator runs in the console and uses the existing broker's per-account authorization and import jobs, so no broker restart is needed. It retains receipts, stops on failed/unknown jobs or ambiguous submission and does not blindly resubmit after a restart. Originals stay in place; importing into the private catalog consumes additional storage. Radio trees containing only subdirectories at their root are split into child-folder jobs. The existing native importer retains its 10,000-file per-job limit; unusually large mixed or single-child trees need narrower sources.

Validation: 576 Python tests passed (16 optional/environment skips), 82 JavaScript tests passed, and package/showcase checks passed. Tests cover source permissions, shared-library denial, path bounds, existing lowercase folders, transfer waiting, positive receipts, retained failures, unknown submissions, source splitting and photo-busy waiting. End-to-end music catalog acceptance remains pending completion of the ongoing USB transfer and the first source scan. Raw evidence is private. No public push, NAS reboot, broker restart, RAID changes or notification changes.

# Destination-only drive imports and larger file windows — 4 November 2026

Whole-drive Import to… now asks only for the destination, then prepares the full accessible root contents in existing reviewed copy jobs. The shared destination picker can create/select a new folder in a writable parent. Folder controls, incoming notices and transfer details are compacted; windows are taller and detail expansion survives polling. No backend, permission or disk-layout change is required.

All 80 JavaScript checks passed, including 451 root items split into 200/200/51 plans, destination cancellation without reads/writes, exact plan bindings, ambiguous submission rejection, folder creation and read-only/path boundaries, deferred family-library paths and retained transfer-detail expansion. Package and showcase checks passed. Tests use fixtures; no real whole-drive copy or new user folder was submitted for validation. Console-only deployment preserves running copy and iCloud processes. No public push.

# File browsing, map navigation and visible iCloud progress — 4 November 2026

Implemented per-window page sizes, All Files with bounded enumeration, separate row highlighting/checking and Import to… with source/destination folder pickers. The Files heading is separate from its toolbar. Added private revalidated artwork caching and a four-request thumbnail queue. Places now uses clustered canvas rendering, fine continuous navigation and offline land behind delayed street tiles. Both photo entry points show the same download progress, with unknown totals labeled honestly.

Local regression: 565 Python tests passed (16 optional/environment skips), and 72 JavaScript tests passed. Conditional HTTP tests exercise authorization before 304 and denial after revoked access. Map tests exercise anchored zoom, drag/pinch and no tile requests before a stable 2.1-second view. These are automated checks, not physical hardware acceptance.

Console-only deployment preserves the existing broker, live USB copy and iCloud session. Connector inventory-counter improvements are staged for the next safe broker update; the currently running downloader does not expose a complete expected total. No invented percentage or completion claim is made. Private evidence and screenshots stay ignored; no public push is performed.

# USB layout and visible transfer destinations — 4 November 2026

USB Storage uses one compact aligned row per physical device, with volume controls
and usage together. The File Manager selector/sidebar no longer repeat a personal
library under both its share name and shortcut name, or a mounted drive as a second
disabled attachment. Distinct shared folders and volume roots remain distinct.

Transfer cards open their logical destination. The matching folder window shows
an Incoming copy notice until whole-folder verification/publication completes.
This does not expose private staging as a normal file location or change the copy's
atomic publication rule. At inspection the copy was still running, had checked
about 5.98 GB of 105.81 GB, and had published no selected folders. No copy restart,
mount/unmount, source changes or storage layout changes are part of this UI update.

# Independent USB mounts and retained-copy continuation — 4 November 2026

Deployed per-volume copy protection and dashboard typed confirmations using only
CONFIRM. Exact plan/disk binding remains enforced internally. Busy/wait/error
feedback now appears inside the confirmation dialog rather than only behind it.

The owner-approved worker cutover retained all 8,143 staged files (about 8.8 GB)
and their identities. Three sample hashes matched both original and staged files.
The same stage is continuing under a fresh identity-matched plan, with no source
or published destination overwrite. At verification it had rechecked/reused over
2.1 GB. Counters recount retained files during verification; completion of the
105.8 GB copy remains pending. No NAS reboot or disk formatting occurred.

The unrelated 500 GB music drive mounted read-only with the same previously
approved identity/options in 2.45 seconds while the continuation ran. It is
browsable as usb-storage2. Both busy source/destination lease checks refused,
while the unrelated music volume's lease was available. This was not a forced
unmount or physical disconnect test of an in-use volume. Source data, interrupted
attempt evidence and private state backups are retained. Changes are committed
locally and have not been publicly published.

# Family system Overview and USB access — 4 November 2026

Family Overview now displays allowlisted read-only system health: CPU, memory,
temperature, network history, RAID state, each attached disk's temperature/SMART,
and mounted capacity. Missing/stale telemetry remains explicit. Private library
paths, credentials, device serials and other account configuration are omitted.
Administrator settings and storage mutation rights are unchanged.

USB Storage routing now uses the same permission-aware route list as its menu,
fixing the redirect to Overview. Existing mounting/unlocking permission checks
and private encrypted-volume ownership remain in force. The additional 500 GB
Samsung USB drive was detected with an ext4 filesystem; it has not been formatted
or automatically mounted. The previous verified USB copy remains running.

# Transfer paths and readable history — 4 November 2026

Deployed source and final destination paths on file-transfer cards. The read-only
inventory collector observes paired source/output descriptors without restarting
the copy worker. Full nested paths include an observation timestamp; ambiguous or
stale observations fall back to selected folders and the reported filename.
Only broker-authorized transfer rows receive path context. Previous transfers
retains expansion and scroll position during live progress refreshes.

The active copy continued through deployment, with more than 4,300 files verified
at inspection. The entire selected folder remains staged until verification ends.
Completion is not claimed. No storage layout, user grants, Apple authentication,
notification preferences or RAID settings changed. Changes are committed locally;
no public push was performed.

# USB copy progress and refresh — 4 November 2026

Fixed ordinary-folder creation under existing hardening and the personal worker's
separate checkpoint ID. Deployed private live copy/verification counters, speed,
ETA, reviewed retries, coalesced folder refresh and accessible library shortcuts.
The original failed copy was revalidated and submitted once with unchanged source
and destination identities and no overwrite. It is actively copying 45,608 files
(about 105.8 GB). At the recorded check, 1,101 files/1.45 GB were verified; ETA was
about 9.8 hours and remains an estimate. Destination listing stayed responsive.
The selected folder appears after complete verification. iCloud also remains
connected/downloading. Whole-copy and archive completion are not claimed.
See [dated validation](FILE-TRANSFERS-VALIDATION-2026-11-04.md) and
[user/API guide](FILE-TRANSFERS.md). Updates are local, not publicly published.

# Photo viewer responsiveness — 4 November 2026

Preview reads no longer wait behind network ingestion. The viewer shows a thumbnail
while generating the large image, with loading feedback, bounded retries, manual
Retry image and cancellation when closed. All 83 photo tests and 45 JavaScript
tests passed; targeted concurrency/identity tests passed on ARM. Three live large
previews loaded during active iCloud ingestion. New previews took about six seconds;
a cached preview took about 0.1 seconds. The archive continued with 502 files and
no reported download errors at inspection. The owner confirmed images now load; subsequent proportional-fit sizing was
deployed and checked with synthetic desktop/mobile layouts. No reboot or storage-layout change was performed. Changes are local.
See [dated validation](PHOTOS-USB-UX-VALIDATION-2026-11-04.md).

# Full-image previews and location maps — 4 November 2026

Complete primary-image HEIC decoding and versioned previews are deployed. Real
read-only native comparisons passed both decoder isolation paths, and the broker
served a corrected thumbnail. GPS details now include an online city-scale map or
an offline fallback, with a per-profile privacy setting in Library locations and
Import & iCloud. The requested online setting is enabled for existing profiles.
The Settings interface was checked live; the owner confirmed corrected images
and the location map both look correct.
The archive download resumed after the controlled update, with 236 files and no
reported download errors at inspection. Data RAID remains healthy/idle; no reboot
or storage-layout change occurred. Source and evidence remain local.
See [dated validation](PHOTOS-USB-UX-VALIDATION-2026-11-04.md).

# iCloud archive downloading — 4 November 2026

Following owner review of Apple account prompts, real photo access is connected
and downloading. Consecutive checks showed growth from 17 to 27 archived originals,
with zero reported errors. Three bounded original-file identity/checksum reads
passed. Initial live ingestion is accepted; the first full library pass and later
scheduled/session-renewal checks remain pending. Downloads were left running.
See [dated evidence](PHOTOS-USB-UX-VALIDATION-2026-11-04.md).

# Apple account review required — 4 November 2026

The latest real login reports an Apple terms-review requirement before web photo
access. The dashboard now identifies this account action explicitly; the owner
must review Apple prompts personally at iCloud.com. The account-action release
passed 71 photo tests locally and on ARM and is deployed. Actual photo access
and archive download are still unaccepted. RAID remained healthy/idle, with
full cooling and watchdog unchanged. See the
[dated follow-up](PHOTOS-USB-UX-VALIDATION-2026-11-04.md).

# Photos, USB access and visual browsing — 4 November 2026

Deployed clearer Apple sign-in/download states, family USB mount/unlock access,
shared plaintext versus private encrypted USB content, expandable folder trees,
and station logos with generated artwork alternatives. Actual folder browsing and
radio artwork were verified in the running dashboard. Local regression passed
492 Python tests (four expected skips) and 38 JavaScript tests; native ARM checks
also passed. Data RAID is non-degraded/idle, OS mirror healthy, full cooling and
watchdog active. Fresh owner Apple sign-in and actual archive download acceptance
remain pending; no download success is claimed. No reboot or disk operation occurred.
See [dated results](PHOTOS-USB-UX-VALIDATION-2026-11-04.md) and
[behavior guide](PHOTOS-USB-AND-BROWSING.md). Updates are committed locally only.

# Private volumes and user Activity — 4 November 2026

Deployed owner-bound encrypted storage, account/session summaries, bounded per-user
storage reports and private Activity. The administrator sees all application activity;
family users see only their own actions plus sanitized shared system notices.
Local regression: 477 Python tests (four expected skips), JavaScript checks and 17
native privacy tests passed. Live reports and the administrator interface were verified.
RAID is non-degraded/idle; current health has no active incidents. Cooling remains
full speed and watchdog active. No NAS reboot or disk-layout change was performed.
See [dated acceptance](USER-PRIVACY-VALIDATION-2026-11-04.md) and
[behavior and API guide](USER-PRIVACY-AND-ACTIVITY.md). Physical two-user encrypted
media and phone/family acceptance remain pending; protocol/root audit limits are explicit.

# Cloud identity, offline access and landing pages — 4 November 2026

Deployed and validated the optional provider connection. The owner manually linked
the existing administrator and a separate family profile through the dashboard.
Actual administrator Authentik round trips succeeded, retaining the original
profile/password; new administrator sign-ins land on Overview. Family users can
choose permitted landing pages in My account, with personal Overview as default.
Optional Create Local Account/reset keeps one profile with separate NAS credentials.
Photo sharing is nested in Photos; music/book sharing is nested in My Radio.
Local suite: 460 Python tests (four expected skips), 31 JavaScript tests and
25 native account tests passed. Family-member and phone/PWA acceptance remain
pending. See [dated results](OIDC-AND-OFFLINE-VALIDATION-2026-11-04.md) and
[manual setup and account guide](LOCAL-USERS-AND-AUTHENTIK.md).

# Viewer metadata and sharing — 4 November 2026

Metadata/GPS editing now uses non-destructive XMP sidecars and updates the Photos
map/timeline. Share Social prepares bounded, metadata-cleaned private copies before
the native share sheet; download fallback is available. Independent reader checks
fail closed. The update is deployed. Local regression and native synthetic photo/video
cleaning, original preservation and metadata sidecar checks passed. See the
[dated validation](SHARING-VALIDATION-2026-11-04.md).
Actual phone/PWA app availability and delivery require owner testing. No real
external shares were sent. See [privacy and sharing](METADATA-AND-SOCIAL-SHARING.md).

# Local family accounts and File Manager follow-up — 4 November 2026

Implemented local family/admin roles and permissions, isolated personal libraries
and iCloud settings, administrator-assigned folders, optional Authentik setup/linking,
and distinct read-only scoped sharing. File Manager gains numbered pages,
Copy/Move-to pickers, drag/drop choice and folder-wide fullscreen media arrows.
The account/features checkpoint is deployed. Native private account and file-operation fixtures passed; no real family account or provider was created. Real family accounts, Authentik/Apple
logins and mobile sharing acceptance require owner setup; none are seeded.
See [accounts](LOCAL-USERS-AND-AUTHENTIK.md) and [Files](FILE-MANAGER.md).

# Explicit private library locations — 4 November 2026

Music and Personal Photos & Videos now require a selected volume and dedicated
folder in the browser before use. Settings → Library locations handles later
changes through a reviewed, verified copy; previous archives remain retained.
File Manager offers named shortcuts and explicit source-preserving folder imports
from mounted USB volumes, including validated read-only unlock sessions. Copies
placed in visible folders require import to appear in the library catalog.
Owner selection of the actual production locations remains pending; deployment
does not choose them or migrate personal content automatically.
See [the workflow](MY-RADIO.md#choose-library-locations-and-import-usb-folders).

# Regional radio and book voices — 4 November 2026

Locally deployed: searchable US/Canada Internet Radio with online directory
search, regional podcast subscriptions and episode search, plus selectable local
book-reading voices with speed/pitch controls saved per browser. The starter list
contains 55 sampled stations; the live installation retains 57 regional entries.
Actual listening, phone/PWA speech behavior and device-specific pitch support
remain owner acceptance items. No sound was played and no publication was made.
See [validation](MY-RADIO-VALIDATION-2026-11-04.md#uscanada-discovery-and-book-voice-follow-up--4-november-2026).

# Interrupted data RAID recovery completed — 4 November 2026

The original four-member data RAID5 is non-degraded and idle. Both mounted data
volumes passed final exact-filesystem/partition/extent/path/inode/size direct-read
SHA-256 verification of their original 8 MiB proof files. No recovery mutation
was repeated. The OS mirror is non-degraded; its queued consistency check is now
running and remains an ordinary maintenance warning. Cooling/guard/watchdog and
trusted HTTPS are healthy, with no new completion-interval kernel errors.

The completion monitor is stopped. Whole-content/parity integrity, physical
replacement, recovery cold starts and the original lockup root cause remain
unaccepted. Notification preferences were unchanged; external delivery remains
disabled. See [the incident completion record](LOCKUP-RECOVERY-2026-11-03.md#recovery-completed-and-final-proofs-verified--4-november-2026).
Earlier in-progress percentages and ETAs below are historical checkpoints.

# Dashboard, private libraries and recovery controls — 4 November 2026

Locally deployed: **My Radio** (Music, Books, Podcasts, Internet Radio), separate
private collection storage, cover art/metadata, retained transfers, optional title
lookups and exact agent permissions. Settings now groups connections, access,
VPN, DDNS, backup and installation help. Storage & RAID joins volumes/encryption
and recovery. Existing bookmarks remain valid.

Interrupted-array recovery now has separate reviewed read-only inspection,
writable rebuild resume, mounting and private metadata backup controls. The
running array was not failed, re-added, force-assembled or otherwise disturbed to
test these controls. Mount planning passed during live recovery without applying
the plan. Forced recovery execution paths have fixture/failure-injection coverage;
physical failure/replacement acceptance is unchanged.

The hardened broker's set-ID restriction exposed a decoder integration fault.
A separate unprivileged, network-disabled helper fixes it without relaxing the
broker. Native tests verified read-only input, denied writes/network/root
escalation, hidden NAS paths, unchanged originals and real book/music/cover output.

At the browser checkpoint data recovery was approximately 93.5%, both data volumes
were mounted and the OS mirror was healthy. This is a dated observation, not a
live ETA or completed recovery. Full-speed cooling and the watchdog were retained.
The original lockup cause remains unknown; kernel update/rollback and the other
recorded hardware/recovery acceptance limits remain separate work.

Five quick power-button presses and the requested pitched melody remain disabled:
the accepted MCU exposes a held-button event and fixed beep only. The exact tune
is retained for a future proven input/output path. No sound, shutdown or reboot
was tested in this work. Phone/PWA playback and real personal media/feed/provider
acceptance still require intended-device testing. KPF/protected Kindle originals
need a readable or audiobook companion.

See [validation](MY-RADIO-VALIDATION-2026-11-04.md), [My Radio](MY-RADIO.md),
[recovery](INTERRUPTED-RAID-RECOVERY.md), [API contracts](MY-RADIO-AND-RECOVERY-API.md)
and [button limits](FRONT-BUTTON.md). Changes are committed locally; this task
has not published or pushed a new public snapshot.

# Latest incident checkpoint — 3 November 2026

After a management stall and owner hard reset, the OS mirror is healthy but the
initial data RAID5 did not automatically resume: it refused dirty/degraded
assembly with its fourth member about 90.86% rebuilt. Exact-member forced
read-only recovery was explicitly approved and completed after independent
metadata backups. Both original 8 MiB initialization proof files match, but this
does not accept all content or parity integrity. The separately approved writable
resume has now restarted recovery near its saved checkpoint. Both data volumes are mounted
and their original direct-read proofs match after journal recovery. The data array remains non-redundant,
around 91% rebuilt. Do not present the older sync ETA as current.

The dashboard loading fix is deployed. Bounded persistent logs are enabled.
The original management-stall cause remains unknown. See the
[dated incident record](LOCKUP-RECOVERY-2026-11-03.md).

# Current status — 2 November 2026

## Personal Photos & Videos

The private timeline, albums, favorites, original downloads, metadata viewer and offline GPS map are locally deployed. The optional iCloud connector is installed, disabled and signed out; no real Apple account or archive is configured. Downloaded originals are retained independently of later cloud deletion. Native synthetic and permission/streaming regressions passed; real Apple sign-in and first-library acceptance still require owner setup. See [Personal Photos](PERSONAL-PHOTOS.md).

## Current physical expansion checkpoint — 2 November 2026

The approved physical operation has progressed beyond the historical preparation
and imaging-gate entries below. Thirteen encrypted recovery images were verified
before layout writes. The initial mixed-member image mismatch was reconciled to
54 unallocated filesystem blocks; a separate member-bound image passed exact
independent full rereads and decryption. Original evidence was retained.

Both OS member partitions are now 128 GiB. Root MD/filesystem UUIDs and all 12,132
critical manifest entries were preserved; the two-member root mirror is non-degraded.
Its scheduled consistency check is currently queued behind data recovery. One redundant writable-state request returned busy on an already writable
array; the error was retained and a separately checked continuation performed only
the required growth. No force-clean operation was used.

The new four-member internal RAID5 has been created under the approved plan and
initial recovery is running. The two approximately 14.794 TB unencrypted ext4 data
filesystems were created with the 64bit feature disabled. Registration, normal boot
and exact-identity post-boot proof checks passed. The OS filesystem reports about
126 GiB, with 116 GiB free at the first check. Strict trusted HTTPS returned 200;
saved full cooling and the ten-second hardware watchdog are active. USB devices
and installed flash were untouched by that OS operation. See [the physical report](OS-EXPANSION-VALIDATION-2026-11-02.md).
Early recovery ETA is unstable while filesystem creation competes for I/O; do not
present it as a guaranteed completion time. Synchronization completion and physical
cold-start/full-replacement recovery remain separate acceptance gates.


FreeQNAP is a locally managed Debian ARMhf NAS for the TS-431XeU/AL314. The
personal `mastechnica/FreeQNAP` source/showcase release is experimental. Public
source availability does not certify every hardware feature or a turnkey binary
installer. Raw identities, credentials, firmware and device evidence remain private.

## Current completion supervision

The queued scheduled OS consistency check exposed an overly strict idle-only
monitor assertion. The corrected read-only verifier passed eight policy tests
and its native preflight/service run. Original fault evidence remains private.
It records queued/running checks and still requires both arrays idle and
non-degraded before final direct-read proof acceptance. It never changes MD
recovery or maintenance settings.

## Historical RAM-only maintenance checkpoint

The owner-approved OS expansion is in its offline imaging stage. The NAS is
running a separate RAM maintenance image; the existing OS mirror is assembled
read-only, and the data array is not assembled. Installed NAS services and the
dashboard are intentionally offline. No partition changes, data-array erasure
or OS growth have occurred.

The first encrypted full-OS image passes decryption/integrity and exact-size
checks, but its initial independent native checksum comparison failed. The
write gate remains closed while bounded read-only chunk comparisons investigate
the discrepancy. The image, its private key material and failure receipts are
preserved. This is not a verified recovery image yet, and the failure must not
be bypassed by restarting the destructive plan.

See [the OS expansion plan](OS-EXPANSION-128G.md). The normal-system observations
below are historical checkpoints, not a claim that services run in maintenance.

## Last normal-system baseline

- Autonomous NAND boot, ordinary warm/cold starts, four SATA bays, both RJ45
  interfaces, enclosure indicators, buttons and orderly chassis power-off have
  bounded physical evidence. Later boot-discovery ordering was fixed without
  relaxing volume identity checks.
- The synchronized four-disk RAID5 provides two mounted **unencrypted** ext4 data
  volumes, about 14.97 TB each after filesystem overhead. The separate two-member
  OS mirror is healthy. Each ext4 filesystem stays below the ARM32 16 TiB limit.
- The approved real data-member logical failure/removal and same-member re-add
  passed. Independent direct reads verified both original proof files and the
  degraded-write proof again after the cooling workloads. No member mutation was
  repeated. At that checkpoint both arrays were non-degraded/idle and both data
  volumes were mounted.
- The final normal-system checkpoint after bounded archival cleanup had no failed
  system services or active capacity alert; thresholds were not lowered.

See [the data recovery record](VALIDATION-2026-11-01.md),
[shutdown follow-up](SHUTDOWN-FOLLOWUP.md) and
[production-readiness boundaries](PRODUCTION-READINESS.md).

## Cooling and watchdog checkpoint

Four covered-chassis ten-minute runs passed:

| Run | Peak CPU | Peak disk | Result |
| --- | ---: | ---: | --- |
| Lighter full-speed load | 57°C | 45°C | Passed |
| Reviewed heavy full-speed load | 67°C | 37°C | Passed |
| High-airflow adaptive idle/read load | 53°C | 35°C | Passed; approximately 580 seconds of observed high-speed sample intervals |
| Adaptive heavy load | 66°C | 34°C | Passed; high airflow changed to full at a sampled CPU temperature of 60°C |

All three fan counters responded and the owner confirmed normal visible rotation.
The earlier 65°C commissioning stops and interrupted guard-restart run remain
recorded. A reviewed 70°C load stop is below the unchanged 80°C kernel bench trip;
the retained stock board configuration's 105°C trip is not a silicon-rating or
physical thermal-protection claim. No thermal trip was exercised.

The permanent local controller, independent guard, full/automatic controls,
read-only status and bounded history are implemented. **The bounded high/full automatic profile is now accepted and enabled** after the final attended stale-input and stopped-controller checks. Stale readings restored full mode in 0.950 seconds; stopped-controller recovery took 3.747 seconds and retained its fault latch after restart. The owner confirmed all three fans stayed normal through both. Temporary trial permission expires on owner death,
cancellation or deadline. Only the tested high-airflow levels 6/7 are implemented;
no fan-stop, low-speed or arbitrary PWM setting is adopted.

Three ten-second SP805 expiry resets and explicit disarm observations passed in
diskless RAM. The **installed watchdog is active under systemd PID 1 at ten seconds**. Advancing heartbeats and one owner handle were observed across multiple timeout periods, including a short CPU load. Maintenance disarm stayed inactive without a late reset for 24 seconds, then re-enable passed. An ordinary restart of the installed kernel restored active watchdog supervision and permanent Auto without intervention; both arrays and mounts returned healthy and all direct proof hashes matched. The owner confirmed all fans and four bay indicators normal. Reboot/kexec watchdog timers remain disabled; no expiry was induced on mounted storage.

See [cooling controls](COOLING.md), [physical cooling record](COOLING-VALIDATION-2026-11-01.md),
[watchdog record](WATCHDOG-VALIDATION-2026-11-01.md) and
[remaining cooling/watchdog plan](WATCHDOG-COOLING-PLAN.md).

## Kernel maintenance

The installed kernel is **6.12.114**. The 1 November authoritative release check
reported maintained 6.12 LTS **6.12.115** available. A security-only FreeQNAP6 candidate preserving the exact accepted complete-mirror bootstrap, nine matching ARM modules and the independently pinned original installed-image rollback bundle passed artifact checks. The transfer helper can serve both exact images
without granting flash authority. **The newer kernel passed an initial RAM boot, healthy-array/mount checks and all three direct-read proof hashes; it remains uninstalled.** The independently pinned original image also passed RAM rollback, healthy-array/mount checks and all three direct-read proofs. Automatic cooling and watchdog supervision were restored afterward. A final normal boot from unchanged NAND restored both safety policies and healthy arrays/mounts without intervention. Broader driver regression and permanent installation remain pending. Board/shutdown source hashes and carried-forward Ethernet ordering
fixes were reviewed; those checks do not replace hardware regression or a complete
CVE review of external drivers. See [kernel maintenance](KERNEL-SECURITY.md) and
[restricted recovery candidate](BOOT-RECOVERY-CANDIDATE.md).

## USB and encrypted media

The exact-board EJ188 MRRS-128 workaround passed bounded normal-kernel flash-drive
and TR-004 write/readback tests, including a 1 GiB enclosure regression and offsets
beyond 16 TiB. The owner-approved TR-004 layout is now two approximately 15 TB
unencrypted ext4 volumes, mounted read/write. Three mounted cycles per volume
passed 3 GiB of writes and 6 GiB of direct verification, cache flushes, remounts
and both offline filesystem checks. Safe eject and owner-assisted physical USB
reconnection and a clean enclosure-only power cycle passed. Software reauthorization exceeded its readiness deadline
before returning; that limitation and remaining NAS-cold-boot/power-loss/controller-health
limits are retained in [the dated enclosure report](TR004-VALIDATION-2026-11-02.md).
Original interrupted operations were preserved, not blindly replayed.

The physical disposable USB passed LUKS2/ext4 AES-256/AES-128 password/key-file
checks, eight writable cycles, direct hashes and read-only/busy refusal. Temporary
volumes/secrets were removed. Experimental encrypted APFS read-only browsing/media
was observed; APFS writes, universal Mac encryption compatibility and complete
BitLocker browsing are not accepted. See [USB/TR-004](USB-TR004.md),
[USB validation](USB-VALIDATION-2026-11-01.md) and [encryption guidance](USB-ENCRYPTION.md).

## Application capabilities and commissioning

The compact local console covers storage/encryption, SMB/NFS/AFP controls, file
desktop, backups/restores, media/scanner/metadata, approved DLNA clients, USB,
network/private LAN, OpenVPN/WireGuard, DDNS, downloads/torrents, recovery,
health/rules and activity. Function-scoped expiring/revocable agent credentials and
optional approved-player UPnP controls are implemented. Existing agent grants do
not grow automatically when a function is added.

Optional services require their own configuration and intended-client acceptance.
Real NFS/AFP file operations, media renderer/codec interoperability, VPN/provider
and physical gateway clients, live DDNS, real torrent exchange and enabled external
notification receipt remain open. Fixture/protocol tests are not those results.
Email, push and buzzer preferences are unchanged; no test sound/message was sent.
Local private-CA HTTPS, signed package-update reachability and valid time sync have
prior evidence; phone PWA installation/push receipt remain owner tests.

Bounded file backup/staged restore and encrypted local configuration capture/download
passed. Fresh-install/system restoration and operational independent data backup
remain separate; the owner deferred an external destination. RAID/recycle bins and
same-pool copies are not independent disaster backups.

## Remaining release and hardware boundaries

Physical hot-unplug, distinct replacement-disk rebuild, degraded OS boot,
post-write/degraded cold-start and abrupt-power recovery, long mixed-workload soak,
10GbE/SFP+, broader USB SuperSpeed/fault testing and wake behavior remain unaccepted.
Host/MCU electrical failure, fan stall and actual overtemperature-trip behavior are
not inferred from the bounded cooling results. Full-chip/SPI restoration is
**excluded by owner decision**.

A turnkey binary release still needs a clean pinned build, complete corresponding
source/dependency/license review, signed immutable artifacts and independently
repeated installation/interruption/update recovery. Keep the accepted installed
image and private UART/TFTP recovery evidence while progressing through those gates.

### Hardening follow-up

Unprivileged eBPF is now disabled persistently on the installed baseline; a real
unprivileged creation attempt was denied. A separate 6.12.115 FreeQNAP7 hardening
candidate compiled with strict memory protections, strong stack/user-copy/bounds
checks and a boot W+X verifier; all nine module versions passed artifact review.
It passed a physical RAM boot, the positive boot W+X check and two bidirectional restart cycles on each RJ45. A ten-minute full-fan CPU/four-disk read run passed at peak CPU 64°C/disk 33°C, followed by all three direct proof hashes. Cold-start/final rollback and permanent installation remain pending. The firmware IBE warning remains open,
independently of potentially optimistic CPU vulnerability sysfs reporting.

See [the attended kernel validation record](KERNEL-VALIDATION-2026-11-01.md) for the current acceptance matrix.

### Remote maintenance checkpoint

With the owner away, further experimental RAM boots and cold-start checks are
deferred. UART capture is passive so an unexpected restart can use the retained
installed boot path. Full cooling and the PID-1 watchdog remain active.

Local HTTPS was restored on the actually connected RJ45 using a new leaf under
the unchanged private CA, the same LAN restrictions and retained private rollback
files. Strict response checks passed on both NAS and Mac; the real HTTPS alert
resolved without suppression. Only the existing OS-space warning remains.

The hardening-policy recovery capture is deployed. A fresh password-encrypted
configuration export passed independent Mac download, decryption and every member
hash check, including the managed BPF policy. Accepted older backups remain.
The TR-004 passed 512 MiB of repeated direct reads including beyond 16 TiB and near
its end; it remains read-only pending fresh initialization approval. This does
not accept mounted write/flush/reconnect behavior or controller RAID health.

## Additional unattended service checks

The hardened RAM kernel passed both isolated VPN/firewall/DLNA campaigns (25
userspace and 26 native-WireGuard checks). The approved two-volume bounded file
campaign also passed uploads, archives, authenticated media/downloads and encrypted
restic staged restore with metadata preservation and wrong-password denial. These
are local same-array recovery checks; independent disaster recovery and physical
media-player compatibility remain separate acceptance work. No reboot, flash write
or TR-004 formatting was performed.

The isolated native download campaign also passed partial HTTP resume after engine
restart, durable paused restoration, final checksum and unauthenticated RPC denial.
Torrent-peer exchange, reboot interruption and disk-full acceptance remain open.
The production-readiness plan has been reconciled with the dated records rather
than retaining completed synchronization/cooling/watchdog work as pending.

## Unattended failure-handling checkpoint

Real RAM-confined Restic tests passed full/interrupted/unavailable destination
failure with last-good restore, and fixture-only retention. A 2 MiB local two-peer
torrent transfer passed its checksum. A full-destination test exposed damaged
resume metadata; the deployed manager now preserves and flags that job instead
of blindly retrying, while later work continues. Automatic marker repair remains
unaccepted. Backup acceptance now also rechecks source directory device/inode
identity. Installer status reports recorded flash writes and incomplete mutations.

See [the dated report](UNATTENDED-VALIDATION-2026-11-01.md) for exact test counts,
negative results and limits, and [OS-space review](ROOT-SPACE-MAINTENANCE.md) for the
non-destructive cleanup plan. No NAS reboot, TR-004 formatting or cleanup occurred.

## OS-space cleanup checkpoint

After owner authorization and independent private archival verification, historical
source-review staging was removed with fresh identity/content and live-reference
checks. This reclaimed 2.35 GB and left 3.33 GB available on the OS filesystem.
The next normal inventory/health sample resolved the capacity warning naturally;
no active alerts or failed services remained. Both arrays/data mounts, HTTPS, full
cooling and watchdog supervision remained healthy. Releases, modules, flash backups
and encrypted recovery archives were retained. No reboot or service restart occurred.
See [the maintenance record](ROOT-SPACE-MAINTENANCE.md).

## Owner-requested OS expansion preparation

A disk-specific proposal now covers a 128 GiB OS mirror and destructive recreation
of the internal RAID5 as two approximately 14.794 TB unencrypted data filesystems
before overhead. Fresh encrypted configuration backup verification and an owned-loop
offline-resize rehearsal passed. The owner confirmed the exact plan. The physical layout remains unchanged; the
privileged transfer-helper restart, verified RAM maintenance and a consistent
offline OS image remain pre-write requirements. See [the expansion plan](OS-EXPANSION-128G.md).
