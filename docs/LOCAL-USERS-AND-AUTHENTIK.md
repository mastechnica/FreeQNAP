# Local users and optional Authentik

FreeQNAP has local PWA/dashboard accounts independently of the NAS file-sharing
accounts. **Settings → Local users & Authentik** creates family accounts, resets
temporary passwords, changes display names/permissions, disables accounts and
revokes sessions. New/reset passwords require a change at next local login.
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
members cannot browse all NAS volume roots or attach their own arbitrary USB
session. An administrator can copy USB files into an assigned/personal folder.

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
6. Save/enable. Each user signs in **locally first**, opens **My account**, chooses
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
