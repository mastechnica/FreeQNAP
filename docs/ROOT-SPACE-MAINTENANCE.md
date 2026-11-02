# OS-space maintenance plan

Read-only review on 1 November 2026 found approximately 983 MB available on the
8 GB OS filesystem. Its existing warning remains active; no alert threshold,
notification preference or backup was changed to hide it.

The largest reviewed consumers were approximately 2.35 GB of retained source-review
staging, 1.35 GB of application release generations and 371 MB of system cache.
These are apparent directory totals, not guaranteed reclaim estimates: shared
hardlinks, open files and filesystem reserved space affect actual recovery.
Public reports omit private staging names and device identities.

## Safe cleanup order

1. Inventory every candidate and its ownership, inode, device, size and hash.
   Identify references from active services, current/rollback symlinks, installer
   sessions, pending validation and backup manifests before proposing removal.
2. Archive historical source-review staging privately on the owner's host. Verify
   both the transferred archive and every member against a pinned manifest, with
   enough host space. A copy command alone does not establish a good archive.
3. Retain the active application generation, a tested immediate rollback, installed
   and candidate module sets, original flash backups and accepted encrypted recovery
   archives. Do not treat old timestamps or a name containing “test” as permission
   to delete.
4. Present a path-specific cleanup plan and reclaim estimate. Delete only reviewed
   archived candidates after confirmation, then recheck services, free space,
   backup readability and active health state. Do not broadly prune releases.
5. Establish a bounded staging/release retention process for future updates, using
   immutable hardlinks for identical source files. It must never remove the last
   accepted rollback or backup while an update/recovery campaign is incomplete.

The initial review performed no cleanup. The owner subsequently authorized the
bounded archive-and-remove operation recorded below. Increasing data capacity does
not increase the separate OS filesystem; moving private keys/configuration or
logs to arbitrary data shares is not an appropriate shortcut.

## Completed bounded cleanup — 1 November 2026

The owner authorized space cleanup. Only the historical source-review staging
directory was removed, after checking for live references and privately archiving
it on the owner's host. Active/recent rollback application releases, all kernel
module sets, original flash backups, validation records and accepted encrypted
recovery archives were retained. No cache or broad release pruning was performed.

The archive was independently reread and all **18,752 entries**, including
**17,503 regular-file hashes**, were verified against the original inventory, with
owner/group and permissions checks. Before deletion, every source path, device,
inode, size, timestamp and content hash was rechecked, along with process/service
references, healthy arrays and the unchanged active release. A partial-operation
journal prevents an automatic retry. No archive contents or raw manifests are
in the public source tree.

Measured reclaim was **2,351,005,696 bytes** (2.35 GB / 2.19 GiB). Available OS space
increased from about **0.98 GB to 3.33 GB** (3.10 GiB). The retained encrypted
recovery archives had identical hashes afterward. The NAS was not rebooted and
application services were not restarted.

The next normal inventory and health observations were both newer than cleanup.
The capacity warning resolved naturally, with **no active alerts**. Both arrays
remained non-degraded/idle, both data volumes mounted, HTTPS certificate-verified,
full cooling fault-free and the ten-second watchdog active. No service was failed.
No notification preference, threshold or acknowledgment was changed.
