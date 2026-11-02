# Encrypted USB storage

New encrypted USB volumes use **LUKS2 with an ext4 filesystem**. In **USB drives**,
open the drive's settings and choose **Format drive…** to prepare a reviewed
layout. Formatting erases the selected drive. Existing encrypted drives use
**Unlock**; unlocking never reformats them.

## Encryption choices

| Choice | Data cipher | Total XTS key | Password protection |
| --- | --- | --- | --- |
| AES-256-XTS (default) | `aes-xts-plain64` | 512 bits, two AES-256 keys | Argon2id |
| AES-128-XTS | `aes-xts-plain64` | 256 bits, two AES-128 keys | Argon2id |

Both choices accept a password or an uploaded binary key file. The credential
choice does not change the data cipher. Argon2id uses at most 128 MiB and two
parallel lanes with a two-second calibration target; total unlock time also
includes device checks, key-slot work and mounting. Changing the cipher requires
a new format; there is no automatic in-place conversion.

The options are deliberately bounded; arbitrary cipher parameters, plain dm-crypt,
legacy LUKS1 creation and device-vendor encryption commands are not offered.
The exact parameters appear in the confirmation plan. Existing volumes retain
their original encryption when imported. See the
[cryptsetup LUKS format reference](https://manpages.debian.org/trixie/cryptsetup-bin/cryptsetup-luksFormat.8.en.html)
and [upstream FAQ](https://gitlab.com/cryptsetup/cryptsetup/-/blob/master/FAQ.md).

## Plain-language security presets

| Preset | Choose it when | What to keep safe |
| --- | --- | --- |
| Recommended · AES-256 + passphrase | Most private-file storage; strongest AES choice offered here | A long unique passphrase and independent recovery material |
| Performance balance · AES-128 + passphrase | You want strong encryption with lower cipher CPU cost | An equally strong passphrase; faster transfers are not guaranteed |
| Separate-key protection · AES-256 + key file | You can reliably keep a random key separately from the NAS | The key file and a separate backup; possession of the key unlocks the disk |
| Custom | You understand the cipher and credential choices | Whatever accepted password/key you choose |
| Unencrypted ext4 | You explicitly do not need lost-drive confidentiality | No unlock secret is required; drive contents are readable without one |

AES-128 is strong encryption, not an intentionally weak mode. AES-256 provides a
larger data-key strength; the password and its handling still matter. A random
key file is not inherently two-factor authentication. Adding both a password
slot and a key-file slot means **either** credential can unlock the same disk.
The key-file preset selects that input in the confirmation dialog and offers
upload/generation; it does not secretly store a key on the NAS.

Encryption protects the locked drive if it is lost or stolen. Once mounted,
normal NAS, sharing and agent permissions apply. Lost credentials are not
recoverable through an administrator backdoor. Keep an independent recovery copy
before storing valuable files.

## Passwords and key files

New passwords require at least 12 characters. Existing-drive unlock accepts the
existing password, including shorter passwords. New uploaded key files contain
32–4096 bytes; use random bytes, not a document or a memorable text string.
The dashboard's key generator creates a download for you to keep independently.

Passwords and key contents travel only in the authenticated HTTPS request and
private broker memory; they are not put in job payloads or activity logs. Key
addition uses sealed memory descriptors. The NAS does not retain an automatic
unlock password or key file. A key file stored beside the encrypted data on the
same drive is not a useful independent recovery copy.

An additional password/key can be added through the reviewed key-management
operation. It verifies the existing credential, adds and verifies the new slot,
and preserves existing slots. Keep a separate accepted recovery credential and
header backup before entrusting important data to encryption.

## Mounting and disconnecting

- **Unlock** opens the encrypted container and mounts its exact registered ext4
  filesystem. It checks the LUKS identity, filesystem UUID and USB attachment.
- **Lock** unmounts it normally and closes its mapper. A busy filesystem must not
  be forcibly or lazily detached; close its users and try again after inspection.
- A read-only import stays read-only. Choose read/write explicitly where supported.
- **Safely eject** unmounts registered volumes, closes encryption, flushes Linux's
  buffers and requests the device's cache flush. It never powers off or changes
  enclosure RAID settings.

Some flash drives reject SCSI SYNCHRONIZE CACHE. Only the specific unsupported
opcode result (sg3_utils status 9), combined with a kernel-reported **write-through**
cache, is accepted after successful unmount and Linux buffer flushing. Real flush
errors, unknown policy and write-back caching still fail closed. No cache policy
is changed to make eject succeed. The response reports the flush method. This is
not power-loss certification of the flash controller. References:
[sg3_utils statuses](https://sg.danny.cz/sg/sg3_utils.html) and
[Linux block queue ABI](https://docs.kernel.org/admin-guide/abi-stable.html).

## Validation procedure

`tools/native-usb-crypto-validation.py` is an explicit destructive acceptance tool,
not an installer or a device autodetector. It requires a private, fresh,
identity-bound owner-approved plan. Default invocation performs preflight only;
`--apply` consumes the plan before the first mutation. Never replay a consumed
plan after interruption. The tool pins the USB serial/descriptor, capacity,
attachment sequence and stable path, and checks healthy internal-array identities.

For each cipher it creates a real USB volume, adds the alternate credential,
uploads an 8 MiB random proof through the file-manager implementation, checks
wrong-password/key rejection and busy-unmount refusal, and repeats password/key
mount cycles with direct-read hashes. It also tests a read-only mount, verifies
writes survived remounting, and removes only its approved test layout. A failure
retains its phase and private evidence instead of blindly formatting again.

XTS encryption protects confidentiality; it does not authenticate every data block.
The acceptance tool's hashes verify its test payloads, not all future user data.
Independent backups and physical power-loss/reconnect tests remain separate.
