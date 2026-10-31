# Password unlocking external encrypted disks

The USB workspace offers two separate paths:

- **Registered NAS volumes:** existing LUKS2/ext4 volumes use the manual password/key unlock already provided in Storage. Writable access follows their explicitly reviewed import policy. Newly created encrypted NAS volumes retain the stronger new-password policy.
- **Foreign encrypted disks:** select a detected USB partition, review **UNLOCK USB READ ONLY**, then enter its existing password/recovery password or applicable uploaded key privately. These sessions support browsing, original-file downloads and explicit lock/unmount. They never become writable storage pools, shares, backup targets or automatic boot mounts.

There is no universal encrypted-disk reader. Detection, protector support, the inner filesystem, kernel drivers and the particular format version all matter. The panel reports installed-reader availability separately from physical acceptance.

| Format | Reader path | Scope / restrictions |
|---|---|---|
| LUKS1 / LUKS2 | cryptsetup `--type luks --readonly` | Password or uploaded key; ext4, NTFS and FAT/exFAT only when the matching reader exists. Unsupported inner filesystems are rejected. Existing LUKS1 is not converted. |
| BitLocker / BitLocker To Go | cryptsetup `--type bitlk --readonly`, ntfs-3g | Password or recovery password; supported protectors only. TPM-only and hardware-dependent unlock, incomplete/damaged encryption and every legacy cipher combination are not promised. Uploaded startup-key compatibility is driver-dependent. |
| FileVault APFS | Pinned, locally built APFS FUSE reader with FUSE3 | **Experimental read-only**, software-encrypted APFS using a password or personal recovery key. Choose the APFS volume index if the container contains several volumes. Hardware-bound T2/Apple silicon encryption is unsupported. Not every APFS feature or compression variant is accepted. |
| Other encryption / filesystem combinations | Unavailable | Never silently format, repair, guess credentials or advertise compatibility. |

`cryptsetup --type fvault2` describes a separate older FileVault2/CoreStorage path; it must not be mistaken for an APFS driver. APFS is handled by its filesystem reader. Unsupported hardware encryption cannot be bypassed merely by entering a password on the NAS.

## Safeguards and secrets

USB sessions require the same stable serial-numbered USB identity and protected-root checks as managed external storage. A fresh reviewed plan pins the selected partition, UUID/partition UUID, attachment sequence and enclosure identity. Mounted/mapped/swapped partitions and already registered volumes are refused. Unlock rechecks the plan, and every browse/read validates the attachment and read-only mount source. Symlinks and nested filesystems are not followed. Only the explicitly selected direct USB disk/partition is unlocked; no broad assembly, formatting, repair or RAID-mode change occurs.

Foreign passwords may be short because they already exist; this does not weaken new encrypted-volume password requirements. Passwords are not placed in process arguments, operation history, Git, logs or permanent settings. cryptsetup receives credentials on standard input. The APFS reader has a narrowly scoped source adjustment allowing standard-input passwords instead of command-line secrets. Its root-only launcher consumes and deletes a mode-0600 secret handoff in `/run` **only after verifying tmpfs**. The password is therefore briefly present in volatile private memory-backed storage. It is not retained for reconnect or reboot; ordinary runtime/system memory security still applies.

The decrypted block mapping is read-only. A root-owned mode-0700 mount parent blocks direct access by unrelated local users even if a filesystem reader exposes permissive root modes. ext4 adds `noload` and NTFS uses `norecover`; the application does not replay a foreign journal. Mounts require `ro,nodev,nosuid,noexec`. Lock refuses a busy unmount rather than forcing or lazily detaching it. An interrupted mapping retains a non-secret intent record and can be explicitly closed through the panel. A disconnected session is not automatically reopened.

## Local optional-reader build

Use maintained signed Debian packages for cryptsetup, ntfs-3g, fuse3 and libarchive13t64. FUSE and the userspace skcipher interface and `dm-zero` target must match the exact kernel. The optional module helper builds upstream `fuse`, `algif_skcipher`, `dm-zero` and `loop` against a prepared matching tree; verify the target vermagic and dependencies before loading. Never force a module with a different ABI. Loop support is for explicitly owned test images; the dashboard never selects loop devices as USB storage.

`tools/build-apfs-reader.sh` requires a fresh upstream apfs-fuse checkout at commit `66b86bd525e8cb90f9012543be89b1f092b75cf3` and its declared lzfse submodule at `e634ca58b4821d9f3d560cdc6df5dec02ffc93fd`. Native build dependencies are git, make, CMake, a C/C++ compiler, libfuse3-dev, zlib1g-dev and libbz2-dev. Build with FUSE3 on ARM32. The helper applies the documented stdin adjustment and refuses already patched input. Preserve the patched source, both projects' licenses and build provenance with any binary distribution. No reader or kernel binaries are included in this source package. Install a reviewed private build as `/usr/local/libexec/freeqnap-apfs-fuse`; missing readers are visibly unavailable.

## Validation boundaries

`tools/foreign-unlock-smoke.py --confirm-loop-fixture` creates owned file-backed disks for LUKS1/ext4, LUKS2/ext4 and LUKS2/NTFS, seeds data, unlocks read-only, verifies reads, checks that writes fail and locks them. `tools/foreign-reader-fixture.py` accepts only root-owned private images below `/var/lib/freeqnap-validation` for APFS and BitLocker tests. These explicit root-only fixture tools do not grant the dashboard an arbitrary block-device path.

Physical USB encrypted-disk acceptance, unplug while reading, every protector/cipher/filesystem combination, long-duration/large-volume reads, damaged-media recovery and Windows/macOS client interoperability remain separate. The TR-004 SuperSpeed write failure remains unresolved and quarantined; successful software-encryption fixtures do not clear that gate.

## Primary references

- [cryptsetup open and supported encryption types](https://manpages.debian.org/trixie/cryptsetup-bin/cryptsetup-open.8.en.html)
- [APFS FUSE upstream features, limitations and license](https://github.com/sgan81/apfs-fuse)
- [Official cryptsetup BitLocker compatibility tests and fixtures](https://github.com/mbroz/cryptsetup/blob/master/tests/bitlk-compat-test)
- [Apple platform security and hardware-bound encryption](https://help.apple.com/pdf/security/en_US/apple-platform-security-guide.pdf)

The pinned APFS FUSE build exposes a synthetic metadata parent. FreeQNAP presents its `root` directory as the user-visible folder tree; it does not expose the driver’s private metadata directory in the file browser.

## Dated test evidence (October 30, 2026 UTC)

- The full local application suite passed **103 tests** on the Mac; the same **103 tests passed natively on the ARMhf NAS** in the final source deployment.
- Native owned-loop tests passed LUKS1/ext4, LUKS2/ext4 and LUKS2/NTFS unlock/read/write-denial/lock. These seeded NTFS data offline; an attempted writable NTFS fixture seed mount failed, and writable foreign NTFS is not offered.
- A software-encrypted APFS image created by macOS passed wrong-password rejection, correct-password unlock, known-file content verification, write denial and clean lock through the transient APFS service on ARMhf. The password handoff and application state contained no retained unlock secret after completion.
- Two official AES-XTS-128 crypto vectors (BitLocker and BitLocker To Go) rejected the wrong password, unlocked read-only and produced the **exact complete decrypted SHA-256 values from the upstream fixture metadata** after loading `dm-zero`. Their NTFS metadata was rejected by the filesystem reader, so these results prove the crypto path and **do not prove complete BitLocker file browsing**. `--crypto-only` records that distinction explicitly. A complete clean BitLocker filesystem/physical USB test remains required; no repair or write-mode retry was performed.

No physical encrypted USB device has passed this campaign. The format panel therefore retains `physical_acceptance: false` for every reader. No universal-format, writable APFS or hardware-encryption bypass claim is made.

The future full-kernel recipe now selects these reader modules under a distinct candidate ABI name (`freeqnap3`). That full candidate has not been built/boot-accepted by this increment. The running/installed kernel remains the accepted `freeqnap1` with verified matching optional modules; no NAND update was performed.

## Physical APFS session follow-up — 31 October 2026

A macOS-encrypted SanDisk partition was selected and unlocked through the live dashboard with the owner entering the password privately. The reader service and read-only FUSE mount started, but the dashboard broker could not access them: FUSE checked the mounter group (root) against the broker group (freeqnap) and denied access. The UI misleadingly showed the mounted session as disconnected. No browsing/playback acceptance is claimed from that attempt.

The transient APFS service now inherits the broker's effective primary group explicitly. This preserves FUSE's default per-user/group restriction and the private parent directory; no `allow_other`, writable mount or retained password is added. All 194 native application tests passed after the change. The original session was normally locked and the owner-requested flash-drive detach completed after no-use/write-through/flush checks, with RAID recovery continuing. A fresh owner password entry and dashboard browsing/media checks remain required before physical APFS acceptance.

## Physical APFS dashboard/media validation — 31 October 2026

After the reader-group correction, the owner reconnected a software-encrypted APFS flash drive and entered its password privately through the live dashboard. The session showed **Unlocked · read-only** and the dashboard listed its files. WebP and JPEG images rendered in the popup; an H.264/AAC MP4 played through its approximately eleven-second duration; fullscreen entered/exited successfully; an M4A audio sample advanced in the native browser player. These observations were made in Brave on the owner's Mac, with the filesystem still `ro,nodev,nosuid,noexec` and internal RAID recovery continuing. No upload, folder creation, filesystem repair or write was attempted on APFS.

The previously download-only foreign-volume browser now offers Play/View controls using the same authenticated session-bound file endpoint, inline media type checks, HTTP range support and existing fullscreen/download controls. Unsupported playback no longer misleadingly asks the user to press a disabled Play button: autoplay denial and unsupported codec/container failures have distinct guidance. A tested Motion JPEG video in MKV did not play in Brave; original downloads remain available and there is no transcoding promise. No change to NAS authentication, mount protections or writable-format scope was made.

All six desktop/PWA Node checks and JavaScript syntax checks passed. The preceding reader-group deployment passed all 194 native application tests. Physical results establish this drive's unlock/browse and the observed media formats only, not every APFS feature, Mac hardware encryption, every browser/codec, long-duration playback or damaged-media recovery. Owner filenames, passwords and screenshots remain private and are excluded from the public source package.

### Existing Linux passwords

Registered LUKS2/ext4 volumes support an explicitly reviewed read/write import without formatting. Unlock accepts existing passwords shorter than 12 characters; the 12-character minimum remains required when creating new encryption passwords. Passwords are not saved. Read-only foreign inspection remains a separate option. Physical read/write media acceptance must be recorded after the owner unlocks the imported volume.
