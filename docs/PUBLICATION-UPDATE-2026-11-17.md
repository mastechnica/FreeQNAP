# Public source update — 17 November 2026

This update documents and includes the live configuration-backup repair, its
regression tests, and the current green-light result. See the complete
[backup repair record](BACKUP-REPAIR-2026-11-17.md) for the two original failures,
the refused verification attempt, the SQLite access setting explicitly approved
for this installation, and verification of the accepted replacement archive.

Personal observations and development decisions are now written in my voice
throughout the README, showcase/tutorial and engineering notes. Publication
approval boilerplate has been removed from the README and release overview.
Technical account, filesystem and controller-process ownership terminology retains
its meaning. Hardware evidence and unfinished acceptance limits are unchanged.

The public update uses a clean snapshot of committed source plus these reviewed
changes. It includes committed work since the previous public update, including
Ethernet repair, recovery snapshot bounds and the optional direct EyeQ connector.
Unfinished connector-sharing/metadata work and the duplicate application file in
the local working folder are excluded. No private development Git history is
imported into the public repository.

## Publication validation

- Application suite: 738 tests completed successfully, with 16 expected
  platform/dependency skips.
- Installer suite: all 52 tests passed, including local transfer/socket fixtures.
- Browser behavior: all 94 JavaScript tests passed.
- Optional direct connector: all 16 tests passed.
- JavaScript syntax: all 23 application/showcase files passed.
- Source inventory, Markdown links, static HTML links/anchors, screenshot hashes,
  dimensions and PNG metadata checks passed.
- Gitleaks found no secrets in the clean publishable source snapshot.
- The targeted recovery/encryption/health suite separately passed all 35 tests.

The encrypted NAS configuration archive, its password, independent Mac copy,
rollback files, runtime captures and private verification receipts remain outside
public source. The published source manifest describes the snapshot, not private
Git history or OS binaries. No live NAS mutation is needed for this documentation
publication. Configuration recovery does not establish a media-original backup
or a complete disaster-restore test.
