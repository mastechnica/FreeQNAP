# Cloud identity, offline access and landing acceptance — 4 November 2026

Deployed the locally committed account/landing update to the second FreeQNAP NAS.
The owner's actual identity-provider connection was configured and exercised.
Private provider credentials, domains, user emails, exact subjects, account IDs and
raw evidence are excluded from this report and the source repository.

## Observed on the running system

- A dedicated confidential OIDC application uses RSA signing, a strict NAS HTTPS
  callback, immutable user-UUID subjects, Authorization Code with PKCE, and two
  explicitly allowed provider users. No existing application or signing private
  key was changed/exported. Other grants remain disabled.
- The owner applied both identity assignments through the NAS dashboard, with
  private local-administrator password confirmation. The original administrator
  profile, role and local-password hash match the encrypted pre-change snapshot.
  The second identity maps to a distinct enabled family profile, without NAS
  administration rights or a usable local password until its user opts in.
- Two real administrator Authentik browser round trips succeeded. The account
  page explicitly showed Authentik, the original NAS username/administrator role,
  and enabled separate offline sign-in. After the landing update, a new cloud
  login returned to Overview; the administrator setting is visibly fixed there.
- Photo Shared with me is visibly inside Personal Photos & Videos, accessible
  even before choosing the user's own library location. Radio/music/book sharing
  has its own My Radio tab. Existing grants/files were not moved.
- Provider settings are displayed as text until explicit editing. Administrator
  confirmation is separated from new-family fields, with the signed-in NAS
  administrator username, to avoid password-manager mislabeling.

## Validation and corrected issues

- Full local Python suite: 460 tests, four expected skips. JavaScript suite:
  31 tests passed, plus the separate Share Social dialog simulation.
- Native ARM account fixtures: 25 passed. Additional local/native HTTP checks
  proved that a family preference selects its allowed photo-sharing destination
  while local administrator login returns Overview. These are disposable private
  fixtures, not an actual family member's phone login.
- Tests cover signed OIDC state/nonce/audience/replay, explicit identity mapping,
  unchanged administrator profile, cloud-first/no-default-password creation,
  optional separate NAS passwords, recent-cloud reset and revocation races,
  offline local login with an unavailable provider, and isolated landing settings.
- An initial API preview used an unrecognized user-selection parameter and
  returned the caller for both previews. This was caught before assigning either
  NAS link. Corrected previews used `for_user`, verified each returned username
  and required distinct immutable subjects. Previous evidence remains private.
- The first live login exposed an empty provider grant list. Only Authorization
  Code was enabled; callback, credentials and subject mode remained unchanged.
  Subsequent browser logins passed.
- The encrypted portable configuration copy verified SQLite integrity and both
  links; live sessions, OIDC transactions and recent-authentication markers were
  excluded. An in-memory WAL-mode inspection was unsuitable; a private immutable
  file inspection verified the actual copy. No backup was restored onto the NAS.
- Exact provider secret/subjects are absent from all tracked source. Package,
  link and hardware inventory checks passed. No password was printed or saved in
  source, no test message/audio was sent, and the first EyeQ/Spectrum NAS was
  untouched. No NAS reboot, RAID mutation or notification change was needed.

## Remaining owner/family checks

The newly provisioned family member must test their own Authentik sign-in and may
choose Create Local Account with a different NAS password. That person's real
password creation/reset and chosen landing preference remain unaccepted on their
actual device. The NAS cannot compare a new NAS password with the undisclosed
provider password; a separate-password acknowledgement is required.

Phone PWA installation, certificate trust, provider round trips in installed-app
mode and offline-internet local sign-in still need actual-device acceptance.
Install from the NAS origin after login; LAN/private-VPN access remains necessary.
No public NAS exposure was configured. Provider group/back-channel logout behavior
is not a directory-sync implementation. See [the user guide](LOCAL-USERS-AND-AUTHENTIK.md).
