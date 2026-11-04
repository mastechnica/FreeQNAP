# Metadata and sharing validation — 4 November 2026

The locally committed update is deployed to the second FreeQNAP NAS. Dashboard,
broker and trusted HTTPS are active. The browser retained its existing local
administrator session and displayed the new account/sharing navigation and the
required first-use library placement. No personal library location was chosen.

## Evidence

- Local Python regression suite: 448 tests, four expected skips. An additional
  restricted runner attempt could not open local HTTP test listeners; its failure
  log was retained and the complete suite passed with loopback access restored.
- Simulated JavaScript sharing workflow passed: privacy selected by default,
  preparation never invokes a sharing app, a separate user action opens sharing,
  neutral copy filename/timestamp, cancel cleanup, and no original fallback when
  cleaning fails. All dashboard JavaScript files pass syntax checks.
- Package inventory/private-path checks and forbidden-name scan passed.
- Native ARM fixtures: 13 account tests and 11 file-operation tests passed. The
  initial account fixture run hit the real free-space reserve on the temporary
  filesystem; its failure evidence was retained. The rerun used private OS-disk
  fixtures without weakening that reserve.
- Native metadata sidecar tests: three passed, including original preservation,
  stale/read-only denial, XMP retention and unsafe sidecar refusal.
- Native isolated cleaner: a generated tagged JPEG and H.264 MP4 each passed
  independent metadata inspection. GPS/title were absent, original SHA-256 stayed
  unchanged, the cleaned video decoded, and generated sharing copies were removed.
- The served sharing JavaScript checksum exactly matches the committed asset.
- Post-deployment data RAID: non-degraded and idle; OS mirror: non-degraded.
  Dashboard showed normal fan RPM/temperatures and an enabled hardware watchdog.
  No NAS reboot, RAID mutation, disk formatting or notification change occurred.

Raw logs and generated fixtures remain private and excluded from Git. No private
photo, real recipient, message, social upload, family account, cloud identity or
Apple login was used. The first EyeQ/Spectrum NAS was untouched.

## Remaining owner acceptance

Choose actual library volumes/folders, create desired family accounts and assign
their permissions. Optional Authentik and individual Apple connections require
private owner setup and end-to-end provider tests. On each target phone/PWA,
verify Share Social offers the desired apps, cancellation works and a chosen
recipient receives the intended privacy copy. Native sharing app availability and
delivery are not proven by the simulated browser tests. Large files and unusual
codecs may be unsupported; failed cleaning never silently shares the original.
See [privacy semantics and limits](METADATA-AND-SOCIAL-SHARING.md).
