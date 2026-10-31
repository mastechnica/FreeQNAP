# Owner review and release gates

The owner approved the experimental source and showcase on 31 October 2026 for **mastechnica/FreeQNAP**, with Pages from `/docs`. Publish only the clean audited source snapshot. Other destinations, private development history and OS binaries are outside this approval. The binary installer and hardware acceptance gates below still apply.

## Review this candidate

- Read the README, installation walkthrough, storage/backup scope and acceptance ledger.
- Review the independent Git history, file inventory and proposed MIT/GPL license boundaries.
- Check the console in synthetic read-only mode; distinguish demo data from the real NAS.
- Inspect disk identity/ancestor protections, explicit destructive confirmations and first-slot-only write boundary.
- Confirm that defaults contain no administrator identity/password, application state, network site settings, share layout or data pool.
- Scan for credentials, private addresses/serials/MACs, personal paths, deployment logs, binaries, old history and proprietary code. Fixture addresses/identities must be synthetic and clearly test-only.

## Before calling this a public installer

- Finish a clean pinned build from documented source, package manifest, dependency/license inventory and complete corresponding source.
- Produce immutable normal-image/rootfs/module manifests and a reviewable signed release; no maintenance image accepted as a normal release.
- Combine the separate tools into a guided resumable state machine with target-generated proof. No forged acceptance JSON or raw command copy/paste required.
- Test interruption/reconciliation at every destructive boundary. Do not add automatic blind retry of disk/flash operations.
- The final installed-image physical cold start and subsequent native service/backup check passed. Resolve and retest the observed shutdown/RAID metadata ordering issue; do not equate successful recovery with clean shutdown. Preserve the remaining hardware gaps and excluded full-flash restore.
- Provide a maintained kernel/CVE review and RAM-before-flash update path with accepted rollback.

## Before calling this a complete NAS

The [current production-readiness checklist](PRODUCTION-READINESS.md) supersedes older implementation-status wording below; distinguish implemented source/fixtures from uncommissioned physical services.

- Commission data layout only after the owner selects redundancy and capacity; verify initialization and full resync.
- Add SMB/NFS defaults, users/groups, share permissions, client interoperability and mount-loss protection. No guest write or root-volume fallback.
- Add shared-file backup and independent off-NAS destination support with explicit credentials and restore drills.
- Validate degraded/rebuild/replacement, boot/service order, lost mounts, full disks and data recovery under interruption.
- Implement restore execution only after staged consistency/identity checks and an accepted disposable-target recovery test.

Current availability must remain honest. A source publication may be labeled experimental before all future NAS functions exist, but it must never present incomplete steps or unsafe defaults as a ready-to-run installer.
