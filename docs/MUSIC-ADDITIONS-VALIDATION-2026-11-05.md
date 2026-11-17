# Additional music and album reconciliation — 5 November 2026

The completed second copy introduced 5,395 additional audio originals. This review
covers the complete 13,353-file source collection across 1,310 audio-containing
folders, retaining the previously reviewed collection and all encoded originals.

## Identification and album organization

The review reads embedded tags/art, existing artwork, cue sheets, playlists,
release notes and other inert metadata. Cached, rate-limited MusicBrainz release
queries compare titles, performers, disc positions, track sequences and durations.
Anonymous numbered rips require whole-sequence corroboration. Artist/label
references resolve selected uncommon recordings. Provider failures remain recorded
as failures; a candidate search result alone is not an accepted identification.

Album artist is separate from each track performer. Corroborated multi-disc
aliases are unified, preserving disc order, bonus tracks, regional editions and
source gaps. Mixed concert recordings remain labeled as source collections rather
than falsely presented as one official release. Exact-copy claims require full
hash evidence; other same-song originals remain selectable versions. No missing
track is fabricated or downloaded to make an incomplete album appear complete.

Artwork comes first from embedded/existing source images, then from Cover Art
Archive for verified releases. Artwork is decoded into bounded local JPEGs and
shared only within the identified album. Original cover copyrights remain with
their owners; private library artwork is not included in the public repository.

## Original preservation and scanner correction

A private plan pins the library, filesystem, source directory, every original
file identity and existing catalog metadata. Independent metadata backups and
per-file sidecar preimages are retained. New private catalog originals use
same-filesystem hard links; original audio names and bytes are unchanged.
Identity-bound source sidecars and private catalog metadata are updated together.
Favorites and listening positions remain intact. There is no whole-database
rollback over newly imported photos or other intervening activity.

Music scanning/import and account-scoped album browsing now accept audio formats
only. Text release notes and ebook documents no longer appear as songs. Legacy
supporting-document catalog entries are archived, with their bytes retained.
Books continue accepting both readable documents and audiobook audio. Watched
folder expansion also ignores music companion documents when choosing scan tasks.

The running storage worker and existing photo import are preserved. Updated
native scanner source is exercised by a separate maintenance scan; already loaded
native broker code is deliberately not restarted during the active photo import.
The console/catalog adopts its filtering update independently. Future safe native
worker adoption remains required for automatic-import filtering in that process.

## Verification and remaining limits

Final application, scanner and live account-scoped browser counts are recorded
below after completion. Full decoding/listening of every original is not claimed.
Empty/unusable originals are preserved and marked unavailable; metadata cannot
repair missing audio. Uncertain credits, editions and titles remain visibly marked
for review. The independent copy-verification/photo-import campaign continues
separately; this review does not claim its final checksums have completed.

Validation includes 722 repository tests (16 environment-specific skips), focused
scanner/catalog regression coverage, syntax compilation, original identity checks,
and live personal-library authorization. Raw filenames, account identities,
checksums, paths, catalog backups and artwork stay in ignored private evidence.
No public publication is part of this task.

## References

- [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API) and
  [rate limits](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting).
- [Cover Art Archive API](https://musicbrainz.org/doc/Cover_Art_Archive/API).
- [Sleep artist release](https://sleep-band.bandcamp.com/album/sleeps-holy-mountain).

## Current checkpoint: network interruption, not acceptance

The researched plan covers all 13,353 audio originals, including 5,395 additions.
It identifies 1,174 intended album groups and plans artwork for 10,897 originals.
These are **plan counts**, not final live acceptance counts. The delayed, bounded
retry recovered 67 temporary provider failures; individual failed attempts remain
retained. Another 30 overlooked local images passed bounded decoding and visual
review. A separately prepared supplement improves 178 track metadata records and
provides 790 additional per-track cover assignments.

The guarded main operation passed its original-identity/catalog preflight and
retained a private catalog backup and per-file metadata/artwork preimages. The
last reachable checkpoint recorded 2,900 of 13,353 registrations. The NAS then
stopped answering network checks while the router and switch remained reachable.
The supervised operation was not stopped or restarted; its current progress and
outcome cannot be established remotely. Its current state must be inspected
before any continuation, rather than blindly replaying it.

I have been asked to check the powered-on NAS and reconnect its verified
serial console. No NAS reset, reboot, RAID mutation, source-audio rename/deletion
or first-NAS intervention was performed. Both internal arrays were non-degraded
at the last reachable check, but current health is unverified during the outage.

Final source identity checks, the supplemental corrections/artwork, final scanner
run, refreshed private index and live Music acceptance remain pending. The
prepared final live check accounts for every original through main tracks,
identical copies, other versions and retained unavailable copies. Fifteen added
originals are empty; the reviewed collection contains 63 unavailable originals in
total, 295 identification flags, 11 unknown performer fields and 43 unknown album
fields. These review counts must be checked again after application completes.

### Physically confirmed power interruption

I subsequently confirmed accidental power loss/power cycling. After the
reported restart, pinned remote access remains unavailable and an address check
did not find the known NAS identity elsewhere on the LAN. Boot/serial inspection
is still needed. This explains the disconnect, but does not establish successful
boot, filesystem consistency or completed metadata/import work. Any continuation
must reconcile individual catalog/link/sidecar states against the retained plan
and preimages; it must not restart the original one-shot application or replay
already successful file-copy jobs.

### Serial recovery and post-power-loss reconciliation

Serial inspection found the NAS stopped at its bootloader prompt. The saved boot
command matched the accepted installed setup; invoking it without changing the
environment started Debian. Capture began after the failed starts, so the reason
automatic startup stopped is not established. An unexpected buffered control
character is consistent with serial interference, but is not proof of its cause.
Repeated unattended startup still requires separate acceptance after recovery.

The connected Ethernet interface obtained a different lease. Returning the cable
to the prior interface restored the existing service address and HTTPS listener,
without changing network settings, certificates or sign-in destinations. No
flash write or kernel replacement was performed.

Both data filesystems mounted after their startup checks. Both original 8 MiB
initialization proofs passed exact filesystem/partition UUID, partition extent,
path, inode, size and direct-read SHA-256 checks. All four data RAID members are
present and the OS mirror is non-degraded; the kernel automatically started data
consistency resync after the unclean power loss. This is not a completed parity or
whole-content acceptance. Boot also reported invalid backup GPT metadata while
using the valid primary table; no partition-table repair was attempted.

A fresh read-only audit verified all 13,353 source-original identities, finding
zero unexpected file or catalog changes. It classified 8,987 catalog records with
planned metadata, 279 original metadata records and 4,087 not-yet-registered
originals; 7,290 source sidecars already match the plan. These counts overlap by
purpose and are not a completed final scanner count. The new continuation must
finish only the verified remaining work; the original one-shot application and
succeeded copy jobs must not be replayed. Both successful music transfer receipts
remain succeeded. The interrupted photo import retains its completed-source ledger
and iCloud pause checkpoint.

Preparation stopped safely on a missing helper import path and then on a lost
maintenance gate, before any continuation writes. Failure evidence is retained.
The gate was restored only after checking that no music jobs were active. The
background scanner now preserves explicit maintenance holds when startup volumes
are unavailable, including a hold established while a request is in flight.
The source fix is staged without a service restart. Regression passed 724 tests,
with 16 environment-specific skips. Final continuation/scanner/UI evidence remains
pending below.


### Durable continuation and explicitly approved organization

I authorized confident source-file renames and moves. A separate organizer
is prepared to place verified tracks under Artist / Album / Disc / numbered title,
using one canonical spelling per reviewed album and retaining distinct editions.
It never overwrites an existing destination. Before removing an old directory
entry, it verifies the same inode/size/time and full SHA-256 at the new path, saves
a durable old-to-new proof and metadata preimage, and flushes the new link and
sidecar. Managed library identities, favorites and history remain unchanged.
Uncertain/unavailable originals, missing naming fields and files linked by cue
sheets or playlists retain their original source paths. Missing tracks are not
invented. This is the approved method; completed move counts remain pending.

A bounded metadata-only batch helper flushes the verified data filesystem before
committing its SQLite catalog transaction. Flush failure rolls back catalog rows;
staged links and metadata remain for an explicit identity audit, never blind
replay. A two-original physical fixture verified real Linux flushing, transaction
order, failure rollback and unchanged original bytes/inodes. Repository regression
passes 729 tests, with 16 environment-specific skips.

The first batch stopped at a long companion-metadata filename. Its transaction
rolled back without changing audio. Temporary metadata names now have a fixed
bounded length, covered by a maximum-filename regression. The failed evidence is
retained. A second complete read-only audit again verified all 13,353 originals,
including 27 safely retained unregistered links from the rolled-back batch.
A fresh pending-action plan retained 9,137 completed entries and identified 4,216
remaining metadata actions; its one-shot continuation is running.

The already loaded older watched-folder loop could replace a maintenance message
when a status request timed out. Its exact source settings were therefore retained
verbatim in a private temporary hold, excluding that source from scheduling without
restarting services. The completion supervisor restores those exact settings after
successful organization and scanner verification. Prior failures are not erased.

A separately researched 252-track refinement resolves misfiled boxed-set tracks
and numbered classical movements using source titles, disc order, durations,
supplied label scans and primary catalog evidence. Verified release-group artwork
replaces misleading inherited covers. Three unverified live recordings remain
unattributed and lose misleading inherited artwork. These are prepared corrections,
not final live acceptance counts.

The supervisor runs each remaining stage once and stops on failure. Original copy
jobs are not replayed. The independent whole-copy verifier must account for the
new durable path ledger before any future run; its old destination paths must not
be treated as current. The interrupted photo import and iCloud pause remain
retained for their separate continuation. Final organization, scanner and live
account-scoped album acceptance are still pending at this checkpoint.

Additional identification references:

- [Gramola / Naxos exact piano-sonata catalog](https://www.naxos.com/CatalogueDetail/?id=Gramola98742-50).
- [Artist's original boxed-set release notice](https://www.ledzeppelin.com/event/april-26-1993).


### Metadata accepted; physical organization still running

The main continuation completed all 13,353 registrations/identity checks, skipping
9,137 already completed records and finishing only the 4,216 audited actions.
The supplement completed 807 updates, followed by two final live-track corrections,
13 additional representative local covers and all 252 deep-review corrections.
Current catalog totals are 13,353 audio originals and 11,062 per-track artwork
assignments. There remain 148 identification flags, 63 unavailable originals,
14 blank performer fields and 43 blank album fields. Removing unsupported
attributions can increase blank fields; uncertainty is not concealed.

The immutable organization plan selects 5,877 confidently named originals. The
other 7,476 keep their source paths because of cue/playlist references, uncertain
or unavailable audio, or insufficient naming fields. All originals remain in the
managed library. The first organizer was deliberately interrupted when its full
checksum reads were found to hold a catalog write transaction. Its original
supervisor failure and ledger are retained. No service restart was used.

A separate continuation audited all 5,877 planned path pairs and independently
verified 525 already completed moves against their durable full-hash proofs. It
continues only the 5,352 pending moves, including any safe prelinked entries, with
**no catalog write transaction during audio hashing**. It flushes new paths and
sidecars after syncing the path ledger and before unlinking old paths. Both the
original and continuation ledgers are needed for future mapped copy verification.
The final scanner, original source-settings restoration and live account-scoped
check are supervised one-shot stages; they remain pending at this checkpoint.
A separate native visibility scan is verifying prepared metadata without releasing
the source scheduling hold.

Automatic data resynchronization has finished. Both internal arrays are idle and
non-degraded, both data volumes remain mounted, and the core dashboard/storage/
cooling services remain active. No new kernel I/O/hung-task fault was found in
the checked interval. These observations do not prove all file contents or parity.
HTTPS and unauthenticated session requests respond normally. The saved Firefox
family credential was rejected; private sign-in is needed for final visual review.
I was asked without interrupting the ongoing music work.


### Signed-in visibility acceptance during organization

The native visibility scan completed 13,366 library entries (13,353 music originals
plus 13 books), with zero errors and the existing storage worker preserved.
I signed in privately as the family member. The live Music page shows
1,160 albums, 12,307 main tracks and all 13,353 retained files; 936 album cards
have artwork. Search, pagination, album covers and the corrected four-disc boxed-set
view were checked without starting audio playback. Multi-disc views now explicitly
label each disc so repeated track numbers are understandable; JavaScript syntax
and all four existing Music UI tests pass. The two static UI assets were deployed
without restarting services, after verifying and privately backing up their exact
prior versions.

The account-scoped verifier confirms the exact expected set of 13,353 original IDs
through main tracks, 110 identical copies and 936 other versions, with all 13 book
entries preserved. Its first private attempt expected full tracks on compact album
cards and failed on that response-shape mismatch. It was corrected to validate
cards against the same authorized album inventory and to exercise the actual detail
handler for three corrected boxed sets. No media mutation or copy replay resulted
from that verifier error. Those counts precede the organizer's final hash/group
refresh and must be checked again after completion.

Physical file organization has passed 3,250 checksum-proven moves at this later
checkpoint. Its remaining moves, final native scan, exact watched-folder settings
restoration and completion health checks remain supervised and unfinished.


## Completed organization and final acceptance

The one-shot supervisor completed successfully while the maintenance host was
temporarily away from the NAS LAN. No job was replayed after access returned.
All **5,877 planned moves** completed with the same inode/size/modification time
and full SHA-256 verification before and after creating each new location.
The **7,476 retained source locations** preserve uncertain/unavailable originals,
incomplete naming fields and cue/playlist references. All encoded originals and
managed IDs, favorites and listening history were retained.

A fresh independent read-only check reconciled both durable ledgers: 5,885 rows
represent 5,877 unique moves, with eight overlapping staged proofs agreeing exactly.
It checked all 13,353 current source and managed file identities, absence of the
old entry for every completed move, every identity-bound source metadata sidecar,
11,062 existing bounded JPEG artwork files and all 252 deep-review corrections.
The exact expected original-ID set also passed the account-scoped catalog check.
The saved full before/after checksums were validated against the plans and current
identities; a third full rehash of the whole audio collection was not performed.
No fresh decoding/listening of every recording is claimed.

Final native scanning indexed **13,366 entries** (13,353 music originals and 13
books), with zero errors. Final authorized browsing and the signed-in Firefox
album grid confirm:

- 1,160 albums and 12,307 main tracks, retaining all 13,353 original files.
- 147 proven identical copies and 899 other retained versions, all still selectable.
- 936 albums with artwork; 11,062 per-track artwork assignments.
- All 13 books preserved, with corrected boxed-set detail handlers verified.
- Clear multi-disc headings, search, page navigation and loaded cover images;
  no audible playback test was sent.

The final hash evidence reclassified 37 previously retained versions as identical
copies; it did not delete or merge their files. Remaining quality limits are 148
catalog identification flags (145 on main displayed tracks), 63 unusable originals,
14 blank performer fields and 43 blank album fields. Naming and metadata cannot
restore missing audio or establish an unverified performance attribution.

The original watched-folder configuration was restored **byte-for-byte**, and the
private maintenance hold was removed. Normal configured source scanning has resumed;
a waiting background scan job is distinct from the completed maintenance scan.
No independent scan/import was resubmitted during final verification.

Both internal RAID arrays are non-degraded and idle, and both original data
filesystems are mounted read/write with their expected UUIDs. Storage, dashboard,
HTTPS, cooling and its independent guard are active. The enabled runtime watchdog
reports a ten-second timeout and a live countdown. All three cooling RPM readings
are present, with full-speed mode retained and no cooling fault; the checked CPU
sample is 46°C. No new kernel fault appeared in the final checked interval.
No restart, RAID tuning or notification change was performed for acceptance.

Raw receipts, identities, filenames, account-scoped results and artwork remain
private. Documentation is committed locally only. The completed music monitor is
removed. The interrupted local photo import and deliberate iCloud pause remain a
**separate unfinished campaign**. Its old full-copy verifier must use both new
path ledgers before any future run. Neither independent whole-copy/photo completion
nor parity, whole-library decode, unattended cold-start or complete hardware
acceptance is implied by this music acceptance.
