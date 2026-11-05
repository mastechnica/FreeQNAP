# Private unlocked volumes, user reports and Activity

## Encrypted volumes belong to the unlocking identity

A dashboard user who unlocks a registered encrypted volume, or an imported LUKS,
APFS or BitLocker session, owns that unlock. The ownership record survives service
restarts and is tied to the volume identity. Passwords and key bytes are not saved.
Another family account, another administrator, or a different agent credential
cannot browse, stream, edit, import or copy its files through FreeQNAP. Cached
personal-library metadata follows this restriction too. Sharing a personal library
does not override the source volume's private unlock.

Administrators can inspect capacity, mount state and accounting, without a dashboard
content override. A successful lock followed by an unlock with another account's
valid disk password/key transfers the unlock ownership. Knowing the password permits
that later unlock; ownership is not a substitute for keeping encryption keys private.
Existing encrypted sessions whose owner is unknown fail closed: safely close/eject
the old session and unlock again. They are never silently assigned to the administrator.
Unencrypted external volumes retain their existing shared-folder permissions.

Family file readers can browse shared mounted unencrypted USB media. Family accounts
need the explicit **Unlock and use their own encrypted external volumes** permission
under **Settings → Users** to mount/import existing volumes or unlock encrypted media. Adding this permission does not
silently grant it to existing family accounts. Formatting and enclosure-wide eject
remain administrator functions. The File Manager lists accessible private volumes;
other people's private unlocks cannot be selected for browsing.

Private encrypted volumes are excluded from SMB/NFS/AFP and DLNA exports. These
protocol services do not authenticate as a dashboard user, so their existing access
lists cannot safely represent this ownership. An agent owns its own unlock under
its credential identity; it does not inherit the issuing administrator's unlock.
Owner checks are repeated when streaming and while queued file work accesses data.
Plans and queued work retain their requester identity. Different users cannot apply
one another's plans or retry an attributed operation under a new identity.

The operating-system root account remains trusted: encryption cannot hide an already
decrypted filesystem from a host administrator with root/SSH access. This feature is
a FreeQNAP application/API/service boundary, not protection against a compromised
kernel or root account. Do not roll back to an older release that lacks these checks
while private encrypted volumes remain unlocked.

## Administrator reports

**Settings → Users** shows each account's enabled state, recent activity, current
unexpired session count and last recorded successful login. “Active recently” means
an authenticated request within five minutes, not proof the person is at a screen.

Select **Refresh storage report** to run bounded background accounting. It breaks
personal storage into Personal Photos & Videos, My Radio and personal files,
including retained previous library locations. Image/video/audio/book/other file
sizes are summarized. Configured Media Library folders are listed separately as
shared storage rather than charging every person who has access.

Reports open directory components without following symbolic links, reject nested
filesystems and verify the configured filesystem identity. File contents are not
read for accounting. Hard links count once per personal scan, and once across shared
media scans. Logical file size differs from allocated space, array parity and total
volume usage. Shared/personal views may overlap if an administrator configured them
to overlap; do not add these figures as an exact appliance-wide total. Recycle data
outside personal roots, filesystem metadata, system files and unassigned folders
are not attributed to a person. These are reports, not enforced quotas.

Unavailable/locked/changed locations are marked unavailable. Limits, permission
errors and races produce partial results; they are never labeled a complete zero.
Reports are on demand with a timestamp, not continuous live metering. Long or failed
scans preserve the last saved report and expose an error.

## Activity

The administrator's Activity page contains all dashboard/API user actions, account
security events and attributed job outcomes. Family users see only their own events.
Everyone also sees sanitized hardware/service health notices, recorded NAS power
requests and a notice when a new system boot is observed. System notices do not
reveal the other user's identity, filename, library title or request body.

The latest page has **Older**, **Newer** and **Latest** controls, plus an administrator
person filter. Automatic session/status polling is hidden by default to keep human
actions readable; **Include automatic status checks** shows those retained events. New sign-in/security
events enter the same durable paginated ledger. A separate security-history panel
also exposes up to 100 older account events recorded before this update. Worker
outcomes and shared system notices have separate recent panels (100 events each).
HTTP “accepted” means the handler accepted a request, not that a queued operation
completed. Check its worker outcome. A denied operation remains visible to its
requester and the administrator.

Events store an allowlisted operation name, stable actor identity, timestamp,
outcome, severity and response-size count. Request bodies, passwords, tokens,
credentials, file contents and URL query strings are not recorded. Response sizes
are not proof of bytes delivered to a client and are not storage-space charges.
If an event cannot be saved, Activity shows a logging warning; it does not silently
claim a complete audit.

Coverage begins when this release is installed. This is not a forensic reconstruction
of earlier activity and is not a complete per-user audit of root/SSH commands or
SMB/NFS/AFP file operations. Shared system notices are derived from existing health
incidents and known power/boot events, not unrestricted journal text. Native protocol
identity unification and comprehensive protocol-file auditing remain future work.

## Local APIs

Existing cookie/CSRF rules and exact agent function grants remain in force.

- `GET /api/activity?before=<event-id>&limit=50&include_polls=0`: own events for members; all events
  for administrators. Administrator-only `user=<stable-id>` filters one person.
  `events` contains private/self or shared-system DTOs; `next_before` is the next
  cursor or null. Set `include_polls=1` for retained automatic status requests. `security`, `system`, `jobs`, `coverage` and `logging_warning`
  explain retained security history, recent supplementary events and coverage.
- `GET /api/users`: administrator-only. Each user gains `last_seen`, `online`,
  `active_sessions` and `last_login`.
- `GET /api/users/usage`: administrator-only cached storage report. Add `?refresh=1`
  to request an asynchronous bounded scan. Returns `running`, `snapshot` and `scope`.
  Snapshot rows identify the user, section, completion state, logical `bytes`,
  `allocated_bytes`, file count and media-type byte totals. Shared media is separate.
- NAS pool/session status gains `private` and `content_access`; status visibility
  is not permission to open files. Trusted ownership envelopes are internal only,
  cannot be supplied through raw dashboard routes and are absent from agent grants.

No family permission, agent grant, external publication or disk layout changes are
implicitly applied by this update.

See [connection feedback and folder browsing](PHOTOS-USB-AND-BROWSING.md) for the
shared plaintext USB behavior, interactive picker and new read-only interface fields.

## Private artwork cache

Derived photo previews, thumbnails and recognized cover artwork use private, revalidated HTTP caching. Validators are scoped to the signed-in account and any library-sharing grant. The server performs the authorized media read before returning 304; a revoked grant cannot receive a cache-validation success. Logout requests browser cache clearing. Ordinary originals and downloads remain no-store. Local map background geometry is public static data; map tiles use the provider's normal browser cache rules.
