# Storage and backup scope

FreeQNAP carries forward the tested storage/backup behavior as independent NAS code. It does not include the former application stack or import its accounts, databases or configuration. The source separation is complete; feature acceptance is tracked below.

| Function | Current FreeQNAP implementation | Acceptance / next work |
| --- | --- | --- |
| Disk identity and capacity | lsblk serial/WWN/capacity and mounted filesystem capacity | Native collector passed with all four SATA disks |
| OS mirror | Existing two-member ext4/md root, exact installation record | Real second-unit NAND boots passed with healthy mirror |
| RAID status | State, members, degraded count and sync action | Reporting only; no broad array auto-assembly |
| SMART health | Fixed read-only command; no wake/self-test/config writes; serial comparison | All four SMART health reads passed; failures are reported independently |
| CPU/drive temperatures | Native thermal and SMART readings | Calibration and adaptive cooling acceptance remain open |
| Pool creation | Fresh reviewable plans for mirror, RAID5/6/10; protects root ancestry and changed identities | Reviewed native create/import exists, including explicit OS free-tail regions; physical pool commissioning is pending; ARM32 ext4 size guard applies |
| Configuration backup | Private atomic archives, consistent online SQLite snapshot, session exclusion, SHA-256 per member/archive | Failure/integrity tests pass; includes FreeQNAP state only |
| Retention | Default seven fully verified archives; failed/partial diagnostics retained | Old good copies are not pruned before a verified replacement |
| Daily backup | Opt-in persisted policy, coalesces missed intervals into one job | Console worker must be running; no boot-time replay flood |
| Second local copy | Explicit path plus filesystem UUID; verified copy and independent retention | Missing/changed mount fails; no fallback into OS root |
| Backup verification | Managed regular archive; type/path/duplicate/size checks plus hashes | Hashes detect corruption, not malicious replacement of archive and receipt together |
| Restore preview | Console configuration restore remains preview-only; shared files have Restic staged verified restore and separately reviewed recovery publication | No complete system/bare-metal restore accepted; no silent overwrite of live writers |
| Local operations | Durable job history, isolated failures, explicit retry | Interrupted work becomes retryable and is never assumed successful |
| SMB/NFS shares, users, quotas | Not commissioned | Separate reviewed defaults, permission and mount-loss tests needed |
| Shared-file/off-NAS backup | Native encrypted Restic local or pinned-SFTP repositories, manual jobs, checks, staged restore and reviewed pruning | File-backed tests passed; no real repository configured; recurring shared-file scheduling and physical restore acceptance remain open |
| Disk replacement, reshape and degraded boot | Not accepted | Disposable-disk failure/rebuild test required |

The current native broker supports reviewed data-pool formatting and staged shared-file restore. This does not authorize automatic formatting, blind retry after interruption or overwriting live data. Its storage functions contain no video reserve, recording directory or former application-specific database/TLS paths.

## Configure backups locally

Run from the installed source directory as the `freeqnap` service account. The console must run for queued/scheduled jobs to execute:

```sh
python3 -m freeqnap.cli backup-policy --daily on --keep 7
python3 -m freeqnap.cli backup-enqueue
```

To enable a second copy, supply an existing writable destination under the intended mounted data filesystem and its actual filesystem UUID:

```sh
python3 -m freeqnap.cli backup-policy --daily on --keep 7 --mirror-path /srv/freeqnap/volumes/data/private-backups --mirror-uuid YOUR_FILESYSTEM_UUID
```

There is no default data UUID. A missing or changed UUID fails the mirror operation while retaining the verified system copy. The job remains retryable, later jobs continue, and its failure must be checked. A mirror copy inside the NAS is not an independent disaster backup. Mount identity is checked before/after transfer; hostile concurrent privileged mount changes are outside this initial acceptance.

`backup-create --source ... --destination ...` is a synchronous administrator CLI tool. Its default source is the console state directory. The privileged NAS broker stores separate settings/secrets; those are not covered by the default console archive. It is not a live file-server backup utility and does not include `/etc`, SSH identity, share data, the OS or flash. Non-SQLite binary database files are listed as excluded; runtime sessions are removed from SQLite snapshots. Backups may still contain administrator password hashes and sensitive settings: keep them private. No encryption or off-device transfer is claimed.

Use `backup-verify ARCHIVE` and `restore-preview ARCHIVE` for an existing managed archive. The companion receipt must accompany it. Preview never extracts over a running service. A future restore workflow must map destinations, stop writers, stage and validate files, preserve identity, and prove rollback on a disposable installation before it is enabled.

## Data layout decision remains explicit

The installer protects OS disks from whole-disk pool plans. A blank data disk can be planned only with a fresh complete inventory, serial and WWN. Using spare capacity on OS disks has a separate explicit `free-tail` region-aware plan that preserves the known OS partitions. Single-filesystem plans refuse capacity above the ARM32 ext4 limit; reviewed two-filesystem arrays are supported as described below. Capacity estimates exclude filesystem/metadata overhead and are not promises of available space.

For this four-bay platform, choose the data redundancy/usable-capacity policy during commissioning. Do not automatically create a multi-day parity array merely because four disks are present. Acceptance must include full initial synchronization, checksum data, member failure, replacement/rebuild, reboot and mount-loss behavior before important data is stored.

## Production sign-off

See [production readiness](PRODUCTION-READINESS.md) for current live checks and the ordered physical acceptance gates. The daily console configuration-backup policy is separate from shared-file backup: reviewed recurring Restic schedules and selected encrypted NAS recovery exports are implemented. Fresh-system recovery remains unaccepted.


## Two filesystems on one large internal array

The internal creation review can select two equal filesystems. It reserves metadata/alignment space, pins an explicit component size, creates one MD array and two distinct GPT partition UUIDs, and validates the exact array/partition parent, extent and UUID before formatting. OS boot/root partitions remain protected; only reviewed unused tails are allocated. Each filesystem stays below the ARM32 16 TiB page-cache addressability limit. ext4's on-disk `64bit` feature does not remove that kernel limit, and no existing filesystem is converted by this workflow.

Four nominal 10 TB disks in RAID5 provide about 30 TB decimal / 27.3 TiB before filesystem metadata, split into roughly 15 TB / 13.6 TiB volumes. Both volumes share one RAID failure domain; splitting does not add redundancy or create an independent backup. Initial synchronization and controlled failure/rebuild acceptance are mandatory before relying on it. Native file-backed RAID5/GPT/ext4/remount tests passed. The owner subsequently approved the exact four physical disks; creation, mounting and bounded fsynced/direct-read checks passed on both filesystems. Full initial synchronization and physical recovery are still pending. Metadata data offset is explicitly pinned to 128 MiB within the reserved component margin. Kernel partition registration accepts an already registered partition only when its exact reviewed extent matches; a generic partx error never becomes inferred success.

Selected encrypted NAS configuration capture, local password-encrypted downloads and optional Restic schedules are described in [configuration recovery](CONFIGURATION-RECOVERY.md). They do not automatically restore a live system or enable external backups.


### Large-array backup GPT acceptance note

On the physical approximately 30 TB MD device, the kernel partition probe reported that the alternate GPT was invalid and used the primary. A later independent O_DIRECT read of both the primary and end-of-array metadata regions matched the reviewed generated images byte for byte, and both filesystems mounted and passed direct-read file checks. The warning must not be silently treated as metadata corruption or erased with a format retry. ARM32 buffered block-device addressability is a candidate explanation; the exact probe/recovery behavior still needs acceptance. Validate primary-loss recovery with compatible direct-I/O tools before calling large-array partition recovery complete. Full physical recovery remains unaccepted.


## Shared-storage backup safeguards and real-volume file campaign

Manual and recurring backups now compare known filesystem, MD-array, storage-group, USB-enclosure and member-disk identities. Two filesystems or separate arrays on shared disks cannot bypass the shared-storage acknowledgment merely by having different pool names. Scheduled bindings pin those known boundaries, so changed storage mapping requires a new review. The historical API acknowledgment field/string retains its `same_pool` / `SAME POOL repository-name` spelling for compatibility; the dashboard explains the broader shared-storage meaning. No local copy is presented as an accepted independent disaster backup.

A bounded campaign on the two actual commissioned internal ext4 filesystems passed 4 MiB chunked upload and direct-read hashes, cross-filesystem staged copy, atomic rename/collision refusal, recycle recovery, ZIP creation and both extraction modes, authenticated streamed multi-file ZIP download, and authenticated media byte ranges with unauthenticated denial. A Restic snapshot/full-data check and staged restore matched file bytes, modes, ACLs and extended attributes; the modified live source remained unchanged. Reviewed atomic promotion, wrong-password denial and retained last-good repository checks passed. Every disposable test file/repository was cleaned after verification; production NAS configuration, RAID membership, boot and flash remained unchanged.

The two test filesystems share one RAID5, so this is bounded real-filesystem integration evidence, not an independent backup, bare-metal restore, sustained-load, real SMB/NFS/AFP client, failure/rebuild or power-loss acceptance. Cleanup took longer under concurrent initial RAID recovery, with repeated journal commits; recovery continued and no new kernel controller/filesystem error was observed. Do not infer idle performance from that campaign. Full synchronization and later soak/recovery tests remain required.
