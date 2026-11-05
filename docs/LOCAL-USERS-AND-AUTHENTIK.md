# Local users and optional Authentik

FreeQNAP has local PWA/dashboard accounts independently of the NAS file-sharing
accounts. **Settings → Local users & Authentik** creates family accounts, resets
temporary passwords, changes display names/permissions, disables accounts and
revokes sessions. New/reset administrator-issued passwords require a change at next local login. Verified Authentik sign-in remains available for an explicitly linked user, including to reset their local NAS password.
Accounts are retained when disabled; disabling does not delete personal files.
The original local administrator stays enabled for recovery.

## Access and personal storage

- **NAS administrator** can manage the entire appliance: RAID, disks, NAS shares,
  networking, users, backups and other system services. This is a trusted role.
- **Family member** has no RAID, system, network, recovery-backup, agent-management
  or arbitrary-disk access. The administrator selects My Radio read/write, Photos
  read/write, own iCloud management, own files read/write, choosing personal storage
  and sharing personal libraries. Authorization is enforced in the server/broker,
  not just by hiding menus.

Each family member has isolated catalogs, jobs, albums, reading positions and
Apple settings/session directories. New private locations stay below
`Users/<stable-local-user-id>/` on an explicitly selected mounted volume. The
ordinary **Personal files** folder is separate from the private Music/Photos
archives. Settings exposes all three choices. Changing the ordinary files folder
keeps the previous folder in place; use File Manager to copy its contents.
Changing Music/Photos storage performs a reviewed verified archive copy and
retains the previous archive. No location is chosen automatically.

Administrators can assign additional existing NAS shared folders to a local user
with read-only or read/write access. Assignments pin the share path, pool and
filesystem identity; repointing a share does not silently authorize a new target.
Removing an assignment retains files. These grants affect dashboard access, not
SMB/NFS credentials; configure those separately under Shares & users. Family
members cannot browse arbitrary NAS volume roots. When explicitly granted external
storage unlocking and file access, a family member can use the dashboard USB
controls. Mounted unencrypted USB storage follows the shared-volume access rules;
encrypted storage content belongs only to the account that unlocked it. An
administrator can also copy USB files into an assigned/personal folder.

## Optional cloud login

Local login always works independently of Authentik availability. The same local
account, permissions and stable file ownership are used for both login methods.
There is no automatic email matching, automatic user creation or cloud claim that
promotes someone to NAS administrator.

1. Optionally install the official Debian dependencies with
   `sudo sh deploy/install-identity.sh` from the installed source directory.
2. In **your own Authentik**, create an Application with an OAuth2/OpenID Connect
   provider, a **Confidential** client and an RSA signing key (**RS256**, at least
   2048 bits). Configure the users/groups permitted to access that application.
3. In FreeQNAP settings enter the provider's application **Issuer URL**, **Client
   ID**, **Client secret** and the exact trusted NAS HTTPS origin followed by
   `/auth/oidc/callback`. Add that same callback as a **Strict** redirect URI in
   Authentik. Select the `openid`, `profile` and `email` scope mappings.
4. Both browser and NAS must reach the provider over certificate-verified HTTPS.
   For a private CA, install its public certificate in the NAS system trust store;
   certificate validation cannot be disabled. Discovery and token/JWKS endpoints
   must use the configured issuer origin. No ports or firewall rules are opened.
5. Optionally require an exact group. Configure an Authentik claim mapping that
   includes a `groups` array in ID tokens. This restricts sign-in; it does not
   grant roles. Choose a cloud-session lifetime of 15–240 minutes (default 60).
6. Save/enable. A user who already has a local password opens **My account**, chooses
   **Link my Authentik login**, confirms the local password and completes provider
   sign-in. The signed issuer/subject pair links explicitly to that local user.
7. Sign out and test **Sign in with Authentik**. An unlinked identity is denied.
   Keep a known working local administrator and test local login during an outage.

Authorization code + PKCE S256, a browser-bound one-use state and nonce, pinned
issuer/endpoints, signed RS256 ID tokens, audience/authorized-party and lifetime
checks protect the exchange. Provider tokens are not retained. Client secrets
remain in the private console database and never appear in settings responses or
activity. Disabling the provider revokes cloud sessions and retains local users,
links and files. Local role/disable/password changes revoke sessions. Provider
changes are checked at login; existing cloud sessions are bounded by the selected
lifetime. Back-channel logout/group synchronization is not implemented.

To recover a forgotten local password through authorized SSH, run the console as
its service account from the installed source directory:

```sh
sudo -u freeqnap python3 -m freeqnap.cli reset-local-password --username admin
```

The terminal prompts privately twice; no password belongs in the command or chat.
The user must change the temporary password at next sign-in.

## Private sharing and individual iCloud accounts

**Shared with me** is separate from each person's own collections. Owners can
share an entire Music/Books/Podcasts collection, an entire Photos & Videos library,
selected albums or selected photo/video items with enabled local users. Shares
are authenticated, read-only and revocable; they are not public links or DLNA
exports. Album membership is live: later additions/removals affect that album
share. An individual-item share does not include its unselected Live Photo/video
companions. Map, timeline, album counts and byte reads all use the same selection.
Downloads already received cannot be revoked or erased remotely.

Each user's **Import & iCloud** page connects their own Apple Account and controls
their own downloads. Apple settings, passwords, session cookies and sync controls
are not shared with album recipients. Photos remain retained after cloud deletion.
Account/permission changes can pause personal background work; disabled-user jobs
remain retained. Re-enabling an account does not silently sign it back into Apple.

## Recovery and acceptance

Encrypted NAS recovery captures now include consistent console identities,
permission/share assignments and per-user catalog databases, excluding login
sessions, pending OIDC/enrollment transactions and Apple session cookies. Original
media files still need their own backup. Restoration remains a separately reviewed
staging/reconciliation process, not automatic replacement of live accounts or
pending jobs. Stable IDs must be preserved/reconciled; do not recreate users with
new IDs and assume their existing libraries changed owners.

Fixture coverage includes cross-user reads/writes, iCloud configuration isolation,
revocation, selected album/item maps/content, signed OIDC/nonce/audience/state,
local fallback and existing administrator/session compatibility. An actual owner
Authentik instance, family phones/PWA and Apple sign-ins still need owner
acceptance. No real family accounts, cloud links or Apple logins are seeded by
installation. NAS-wide agent credentials remain administrator-managed; this is
not an implementation of family-issued agent tokens or cloud directory sync.


## Cloud-first users and optional offline sign-in

An administrator can use **Settings → Local users & Authentik → Link an Authentik
user** to map the exact immutable Subject (`sub`) from the provider's verified
user preview. Select an existing NAS account to preserve its role, password,
permissions and stable ownership. Or choose **New family member · Authentik first**
to create a non-administrator profile without a local password. Choose **Review identity link**, then confirm the local
administrator password in the separate administrator-only dialog. Never save
that confirmation password as the new family member’s password. Existing provider identities are never
silently reassigned. Enable the Authorization Code grant explicitly; a newly API-created provider may
otherwise have an empty grant list. No implicit/password/client-credentials grant
is needed. Use an immutable UUID-based provider subject; email matching
is not an enrollment mechanism. Only explicitly linked accounts can sign in.

A cloud-first profile has no usable local password until its user chooses one.
After Authentik sign-in, an optional **Create Local Account** prompt explains how
to keep access when internet or the provider is unavailable. **My account** offers
the same option later. Despite the button's familiar wording, this adds a separate
NAS login credential to the same existing profile; it never duplicates libraries
or moves file ownership. The NAS username is shown before setup.

The user enters and confirms a new NAS password (at least 12 characters) and must
acknowledge choosing a password different from Authentik. FreeQNAP does not obtain
or store the Authentik password and cannot independently compare the two. It never
asks for both passwords together or submits the NAS password to the provider.
Local passwords are salted/hardened hashes. Authentik-only profiles store an
explicit disabled-password marker, never a shared/default/random known password.

Setting/resetting the NAS password through Authentik requires a verified NAS
cloud-login session authenticated within five minutes. Otherwise sign in through
Authentik again first. Saved user IDs, permissions and files are retained. Other
sessions are revoked; the successful setup receives a replacement session. A
locally signed-in user changes their password by supplying the current NAS
password. A NAS administrator can issue a temporary local password from the user
card; the next local login requires changing it. There is no anonymous email reset.

If Authentik becomes unavailable, users who enabled local sign-in can use the NAS
username/password directly over its trusted LAN HTTPS address. A profile that
skipped local setup needs a NAS administrator's local recovery/reset assistance.
No provider outage automatically weakens authentication. Independent configuration
and content backups remain necessary if the NAS itself is lost.

## PWA after cloud login

Authentik redirects back to the NAS. Install FreeQNAP from the NAS HTTPS origin,
not the Authentik portal: Safari → Share → Add to Home Screen on iPhone/iPad, or
the browser's Install app / Add to Home screen on Android. Trust the NAS public CA
on each device first, or configure another valid certificate; do not bypass a
browser warning. The PWA uses the same profile and authorization as the dashboard.
LAN/private-VPN reachability is still needed; cloud login does not expose the NAS
publicly. Use local sign-in when the internet is unavailable. Native phone install
and Authentik round-trip behavior still require testing on the actual device.

## Session-only API additions

- `POST /api/identity/assign`: administrator password reauthentication, exact
  `subject`, and either an existing `user_id` or new `username`, `label`, personal
  `permissions`. New profiles are always family members. Issuer comes from the
  configured and verified provider, never from an untrusted request.
- `GET /api/account` includes `authentication`, `recent_oidc` and
  `user.local_password_enabled`; no hashes or provider secrets are returned.
- `POST /api/account/local-password`: `password`, `confirm_password`, and
  `different_password_ack:true`. A recent verified OIDC session and normal
  same-origin CSRF checks are required. Returns profile/session state without
  any password. These operations are unavailable to NAS agent tokens.

Photo **Shared with me** is inside Personal Photos & Videos. My Radio has its own
Shared with me tab for music, books and podcasts. Existing links remain readable;
no files or grants are moved by this navigation change.


When verifying subjects through the Authentik API, use the provider preview's
`for_user=<numeric-user-id>` parameter. Omitting it or using an unrecognized
parameter can preview the authenticated API caller instead. Verify the returned
`preferred_username` and distinct immutable subjects before assigning identities.
A preview is preparation evidence, not proof of a successful browser login.


## Landing pages

Every new administrator login lands on **Overview**, through either local or
Authentik sign-in. This is enforced by the server and is not configurable.
Family members choose **My account → Landing page** from the pages their current
permissions allow: their personal Overview, Photos, shared photos, My Radio
collections, Files or My account. With no preference, or if access to a selected
page is later removed, the default is Overview. Family Overview contains personal
library/file links and their own photo counts; it does not expose RAID, hardware
monitoring or system administration. Preferences stay with the same stable NAS
profile across local/cloud logins and configuration backups.

The PWA root launch uses the same preference when a session is still valid.
Reloading a page already open preserves that page; the landing policy applies
at a new sign-in or root app launch. Local temporary-password requirements still
open My account first when a password change is required.

`POST /api/account/preferences` accepts only `{landing_page:<allowed key>}` for
the current authenticated user. `GET /api/account` returns the permitted `landing`
choices; login/session responses include the canonical `landing_page`. External
URLs, arbitrary admin paths and another user's ID are rejected. These session-only
preferences do not grant additional permissions or expose a generic redirect.

## Private disks, storage reporting and Activity

See [private unlocked volumes and audit reports](USER-PRIVACY-AND-ACTIVITY.md) for
owner-only encrypted storage, the explicit family unlock permission, administrator
account/storage summaries, and private per-user Activity. Cloud and local sign-in
use the same stable NAS user identity for these restrictions.

## Family system status and USB storage

Every signed-in family account can read appliance status on Overview: CPU and
memory load, temperature and network history, physical disk/SMART health, RAID
state and aggregate mounted capacity. Stale or unavailable measurements are
labelled. This response omits account settings, credentials, device serials,
private file paths and detailed alert payloads. It grants no administrator actions.
Administrators retain the detailed diagnosis and settings pages.

USB Storage is available to accounts allowed file browsing or external-volume
unlocking. The same route permission rules govern both its menu and its page.
Mounting/unlocking still requires the administrator-granted storage permission;
plain mounted media is shared, and encrypted content remains private to its
unlocking account. Erase/format and appliance-management controls stay restricted.
Copying holds leases on its source and destination volumes, rather than a long
NAS-wide lock. Unrelated drives can mount while a copy runs. Unmount/lock/eject
checks refuse a volume that an active copy is using. A short metadata lock still
serializes configuration changes.
