# User privacy and Activity acceptance — 4 November 2026

The installed application release is `7a8998d`. Later documentation/test commits do
not change its product code. Everything in this report was kept local; no public
publication was performed for this update.

## Accepted evidence

- Full local Python regression: 477 tests, four expected skips. The focused 17-test
  privacy suite also passed on the ARM NAS against the installed application.
  A further local/native assertion verified that a signed-in family member with
  a valid CSRF token cannot submit a forged administrator ownership envelope.
- JavaScript tests and social-sharing checks passed. Source/package and showcase
  checks passed; the final reviewed source snapshot had no secret-scan findings.
- Fixture/native checks cover persistent encrypted-volume ownership, changed/unknown
  identities, other-user/administrator/agent denials, metadata-versus-content access,
  foreign encrypted sessions, actor-bound plans/jobs/retries, scoped Activity paging,
  administrator-only reports, account login logging and sanitized system notices.
- Directory accounting checks verify hard-link deduplication, symbolic-link exclusion
  and honest partial results at scan limits. This performs no content reads.
- The actual signed-in administrator user page showed both existing accounts,
  their session/presence status and the new storage report. The actual Activity page
  showed the person filter, paging, optional automatic-status records and shared
  component health notices. Supplementary job history does not duplicate shared notices.
- Live report generation completed for both accounts without error. Their personal
  storage locations are not configured and were reported as such, not as measured
  empty libraries. There were no configured shared Media Library folders to meter.
- Data RAID was non-degraded and idle; the separate OS mirror was non-degraded.
  Broker, console, HTTPS, cooling controller and cooling guard were active. Full fan
  speed remained selected, all three RPM readings were present, CPU was about 45°C
  and disk readings were 32–33°C. The hardware watchdog remained active at ten seconds.
- Current health monitoring was fresh with zero active incidents. Retained failed
  historical jobs remain visible and are not erased or reclassified as current
  hardware faults. No new critical kernel journal errors appeared after deployment.
  Uptime confirmed this was a service update, not a NAS restart.

## Preservation and deployment

Private consistent application database snapshots were encrypted before deployment.
The release source checksum and native results were verified before activation;
updates were withheld if an application operation was active. Schema changes are
additive. Existing administrator/password/provider identities, family permissions,
shares, notification settings and storage layouts were preserved. The first NAS
was not contacted. No disks were formatted, mounted, unlocked, locked or ejected.

No encrypted physical volume was mounted at deployment. Unknown legacy encrypted
unlock owners fail closed rather than being silently adopted. Protocol exports of
private encrypted volumes are blocked because those services lack a verified
mapping to dashboard identities. OS root remains a trusted administrator boundary.

## Remaining owner acceptance and coverage limits

1. With a disposable encrypted USB drive, sign in as two real users and verify
   owner-only selectors, browsing, media, upload/copy/import, direct links, lock and
   a later unlock by the other account. Fixture/native access checks do not replace
   a physical LUKS/APFS/BitLocker handoff test; no such disk was modified this phase.
2. Complete the family member's actual Authentik login, optional independent local
   password, personal location selection and phone/PWA round trip. No family password
   or real user session was created for testing.
3. Activity covers application/API actions and attributed job outcomes from this
   update, with retained older account history and sanitized health/power/boot notices.
   It does not reconstruct old missing actions or provide complete per-user SSH,
   SMB/NFS/AFP file auditing. Those protocol identities remain separate.
4. Accounting is bounded and on demand. Shared/unattributed folders, OS files,
   filesystem overhead and recycle data outside personal roots are not private-user
   charges; logical sizes are not quotas or exact appliance-wide used space.
5. Rollback to code without ownership enforcement requires first safely locking
   private encrypted volumes. Never assume older code preserves this new boundary.

See [behavior, trust boundaries and APIs](USER-PRIVACY-AND-ACTIVITY.md).

## Family Overview and USB navigation follow-up

Verified in an existing signed-in family browser session that USB Storage opens
without redirecting to Overview, lists all three attached USB devices, and offers
Mount volume for the new ext4 music drive. No mount, unlock, format, grant change
or copy restart was performed. A visible notice explains that mount operations
can wait for an existing verified copy's global storage-operation lock.

The family Overview visibly displayed CPU, memory, temperature, receive/send and
load graphs, both healthy/idle RAID arrays, all seven physical disks, internal
SMART results and temperatures, mounted capacity and current health. The four
internal disks passed SMART and reported 32–33°C at that check. Display follow-ups
deduplicate repeated mounts of the same filesystem and label occupied bays without
exposing device identities. Collector staleness and unavailable metrics remain
explicit; this does not grant appliance-management actions.

The full Python suite ran 520 tests with 16 optional/environment skips. Subsequent
targeted account/HTTP checks passed 28 tests with 12 environment skips, and all
51 JavaScript tests passed. Three telemetry-projection tests passed, including
private-data exclusion, mount deduplication and unavailable-status reporting.
Authenticated HTTP fixtures confirm family users still cannot read raw health
alerts or front-panel endpoints, users or provider configuration. The dedicated
summary permits only allowlisted read-only fields.

Native console-UID validation received seven disks, two arrays, 2,856 historical
measurements and fresh front-panel telemetry with no active health alerts.
Deployment restarted only console/proxy; the running broker PID was unchanged.
Screenshots remain in ignored private evidence. Changes are local, not published.
