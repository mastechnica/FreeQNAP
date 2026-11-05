# Photos, USB browsing and radio artwork acceptance — 4 November 2026

The deployed application is `b88dc0b`. This update and its evidence remain local;
no public push was performed.

## Verified

- Local regression: 492 Python tests, four expected skips, and 38 JavaScript tests
  passed, alongside the social-sharing check. Package/showcase checks passed.
- Native ARM checks passed: 69 photo tests, 27 account tests, 17 privacy tests and
  four artwork tests. Two additional native checks verified shared-USB import
  boundaries and per-user folder selection. These are fixture checks, not a real
  Apple account download acceptance.
- The signed-in dashboard shows an enabled Browse drives & folders button before
  a location is selected. Its expandable tree listed actual child folders on the
  already mounted read-only NTFS USB drive. No drive was mounted or changed.
- Live Internet Radio cards displayed station-owned artwork for three visible
  stations and colorful locally generated alternatives. Two independently requested
  real station icons were decoded successfully through the installed broker.
  Artwork loading did not play audio or perform stream tests.
- The existing family profile received only its requested external mount/unlock
  permission; its member role and other accounts were preserved. The existing
  permission-update mechanism revoked that profile's sessions, requiring a new
  NAS sign-in. Formatting and enclosure-wide eject remain administrator-only.
- Tests enforce plaintext USB sharing, encrypted owner-only data, private personal
  folder restrictions and identical import-source restrictions. A real two-person
  encrypted-drive acceptance remains separate and pending.
- Data RAID was non-degraded and idle; the OS mirror was non-degraded. Console,
  broker, HTTPS and cooling services were active. Current health had no incidents;
  full fan speed remained selected and the hardware watchdog was active.

## iCloud acceptance still requires the owner

The configured family account's saved session requires a fresh sign-in. At the last
check no download was running and no completed archive pass or files were recorded.
The revised interface states this, disables downloading until access is verified,
and exposes code verification, trusted-device web-access approval, inventory access,
background progress and safe failure messages separately. The owner has been asked
to complete Apple authentication privately. Actual Apple sign-in and file download
are not claimed accepted until that step and an archive pass succeed.

The earlier generic status did not preserve enough detail to establish the original
Apple failure cause. Advanced Data Protection can require a separate trusted-device
web-access approval after the code. The implementation now surfaces that stage and
provides a saved-session check without repeating the connector's session-trust call.

## Corrections and preserved evidence

The first native ingestion fixtures correctly failed the free-space reserve on the
RAM-backed temporary filesystem. Only the test scratch location was moved to private
OS storage; the production reserve was not weakened. Original failure evidence was
retained. Live station decoding also exposed an insufficient memory allowance;
384 MiB succeeded on the actual ARM decoder and its isolated helper. The final
release uses that bounded allowance and a new derived-cache version.

Consistent private application snapshots were encrypted before deployment. Raw
account state, logs, screenshots and receipts remain in the ignored validation folder.
No reboot, disk-layout change, volume unlock/eject, RAID operation, notification
change or first-NAS operation was performed. Existing Apple settings and sessions
were preserved; no account password was changed.

See [behavior and API guide](PHOTOS-USB-AND-BROWSING.md).

## Follow-up: Apple account gating

A subsequent saved-token diagnostic successfully logged in, but Apple rejected
`requestWebAccessState` with authentication-required code 421. The same account
response explicitly reported `termsUpdateNeeded: true`, no verification challenge,
and no completed web-session token. The owner was asked to review Apple prompts
personally. This is an observed account-state gate, not an accepted photo download.
The connector now blocks consent/download before terms/account-repair review and
the dashboard provides a direct account-action explanation. All 71 photo regression
tests passed, including both account-action flags; JavaScript syntax checks passed.

The account-action release `59b5d38` also passed all 71 photo tests on the ARM NAS
in 49 seconds before activation. Broker, console and both cooling services were
active afterward; data RAID was idle/non-degraded and the OS mirror non-degraded.
No public publication or NAS reboot was performed. Owner Apple review remains pending.

## Live download acceptance

After the owner completed Apple's account prompts, the real account reached
`connected` with no connection problem and an active download. Two consecutive
checks showed the archive growing from 17 to 27 indexed originals, approximately
46 MB at the latter check, with zero reported download errors. Three bounded
originals totaling approximately 5.2 MB were opened through exact saved file identity
checks and independently rehashed; all matched their recorded SHA-256 identities.
Only aggregate results were retained in this report; private evidence contains no
account identifier, original filename, photo metadata or credential.

This accepts real sign-in, photo access and initial verified ingestion. The first
full inventory/download pass is still in progress; completeness of the entire Apple
library, subsequent scheduled passes and long-running session renewal remain
unaccepted. Downloads were left running; no service restart or pause was performed.

## HEIC and location-map follow-up

Actual downloaded HEIC preview comparisons showed the existing decode path losing
image detail/content; the new primary-image decode produced the complete image.
The original was 5712 × 4284; corrected thumbnail and viewer preview were 384 × 288
and 1600 × 1200. Read-only native tests passed in both standalone unprivileged and
production service-manager isolation. Originals and old derived evidence were retained.
Local regression passed 503 tests (16 environment/dependency skips), and all 38
existing JavaScript tests plus three new online/offline/polar map tests passed.
Private map preferences were tested independently from landing-page preferences
and other users. The owner explicitly approved OpenStreetMap coordinate/map-area
requests and requested online maps enabled with a retained offline setting.

The deployed broker served a corrected version-2 thumbnail from a real archived
HEIC. Downloads were deliberately paused at a durable checkpoint for the broker
update, then resumed using the preserved Apple session without another password.
The first continuation encountered the broker socket before startup completed;
no download request was submitted at that point. A subsequent readiness check
confirmed the socket, saved-session photo access was verified and ingestion resumed.
The latest inspected archive count was 236, connected/downloading with zero
reported download errors. The console-only embedding-policy follow-up did not
restart the download broker. Both arrays remained non-degraded, data RAID idle,
and cooling services active. The approved online setting was enabled for existing
profiles while new profiles retain the offline default. The real administrator
Settings page showed the enabled checkbox; the private setting-isolation test
also passed on ARM. Owner photo-viewer/map visual acceptance is still requested.
No private photo previews, coordinates or raw account state were added to Git.

## Owner visual acceptance

The owner refreshed Personal Photos & Videos and confirmed that the corrected
images and the location map both look correct. This closes the requested visual
acceptance for the complete-image previews and GPS viewer map. Whole-library
archive completion and future session renewal remain separate acceptance items.

## Viewer responsiveness during downloads

The owner subsequently reported intermittent full-image loading while details and
map appeared. Review found that photo reads used the same serialization lock held
across network ingestion. Completed immutable originals and preview caches now use
identity-checked read-only descriptors independently of that long-running lock.
Decoder admission remains bounded, checks for a cache published while waiting,
and publishes each derived file atomically.

All 83 photo tests passed locally. Three targeted ARM tests proved that a thumbnail
read finishes during deliberately stalled ingestion, concurrent full-preview reads
decode once, and changed original identities remain rejected. All 45 JavaScript
tests passed, including progressive thumbnail loading, explicit retry/error states,
bounded busy retries, cancellation and late-response handling. Package/showcase
checks passed.

The deployed release is `d2d744c`. The existing archive job was paused at its saved
checkpoint for activation, encrypted application snapshots were retained, and the
job resumed with the preserved Apple session. Three actual full previews were
served successfully while downloading: two new renders took approximately six
seconds each and a cached render about 0.1 seconds. The inspected archive had 502
files, connected/downloading, with zero reported download errors. Both arrays
remained non-degraded, data RAID idle and cooling services active. No reboot,
disk-layout change, map-setting change or notification change occurred.
Owner confirmation of reliability across additional images remains requested.

## Fit viewer media to available space

The owner confirmed images now load, then requested larger automatic fitting.
The viewer now explicitly sizes image/video boxes to the available media cell
with proportional containment. Toolbar and details remain separate grid regions,
with bounded toolbar overflow and scrollable details. Synthetic desktop and
390-pixel mobile layout checks showed the complete image and unobscured controls;
no private media were used in those screenshots. The CSS-only console release
`0c95677` was activated without restarting the download broker, and the served CSS
matched the reviewed local source byte-for-byte. Owner confirmation on additional
real images remains distinct from these synthetic layout checks.
