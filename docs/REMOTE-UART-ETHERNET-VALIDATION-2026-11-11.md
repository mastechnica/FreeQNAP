# Remote UART and Ethernet repair validation — 11 November 2026

## Recovery access

I selected a Pulse-managed balenaOS host with an FTDI USB UART. Its device
identity was checked against authenticated Pulse inventory. Because the standard
Pulse SSH gateway was unavailable, the device host key was obtained through the
certificate-verified, authenticated Pulse tunnel to the exact selected device,
then pinned for local SSH. The supported Pulse administrator identity worked;
root login was not enabled and no new SSH keys or fleet settings were installed.
The local hardware address and host-reported device identity also matched.

After I corrected TX/RX, a console marker sent by the NAS was received
exactly, and three harmless carriage returns increased the NAS UART receive count
by three without new framing errors. A Python capture opened the UART without
acquiring a controlling terminal and obtained the expected NAS login prompt.
The shell-based background reader had missed prompts; it was not proof of broken
wiring after the marker/counter checks passed. All final control uses the existing
exclusive capture and its private local Unix socket.

Only private temporary helpers were added to an existing runtime. No application
release, display service, account permissions, notification settings or fleet
configuration was changed. The boot-transfer helper binds only the chosen LAN
address, serves exactly the pinned candidate and rollback images to the selected
NAS, drops privileges and refuses uploads. Both complete payloads were streamed
into NAS memory and independently hash-verified before the restart.

## Fresh configuration backup

The first capture failed while SQLite needed filesystem access unavailable inside
the live broker's read-only namespace. Its durable failed job/stage remains.
An independent temporary SQLite backup outside that namespace passed integrity
checking. A separate full-capture attempt then correctly refused the personal
media database because it had grown beyond the former per-file snapshot limit;
that failure/stage also remains retained.

The reviewed source now separates the unchanged 64 MiB ordinary-file bound from
a 128 MiB SQLite bound and a 256 MiB aggregate capture bound. Hashing and archive
member verification stream bounded chunks. SQLite copying checks its page count,
aggregate size and a deadline; database errors become structured capture failures
while incomplete evidence and older accepted backups remain retained. Nineteen
recovery/encryption regression tests pass, including larger personal database
retention, streamed hashing, cap failure isolation and structured SQLite failure.

These source changes were used only by an isolated SSH capture process; the live
broker was not hot-patched or restarted. Its namespace limitation is not claimed
fixed. The fresh encrypted capture includes 339 files. Its independent Mac copy
passed the complete encrypted-file checksum and length check. Credentials and
backup passwords remain private. Media originals are not included in this
configuration archive. No failed job was relabeled as successful.

## First fixed-driver RAM boot

A normal software restart reached the verified remote bootloader capture. Fresh
board/flash geometry, saved boot path and acceptable temperature were checked.
The exact candidate was loaded into RAM; byte length, CRC and legacy image header
passed before boot. This bootloader has no full SHA command; complete SHA checks
were performed on the serving artifacts and the prior full NAS-memory transfers.
No boot environment was saved and no NAND erase/write operation occurred.

The new boot's loaded Ethernet module source identity matched the fixed candidate.
Two hundred link dumps and 1,200 physical-interface counter reads completed, then
three native NAS status requests returned in under one second with fresh health
monitoring. No matching new kernel fault appeared. Both data volumes mounted.
The two original 8 MiB initialization proofs passed direct-read hashes with exact
filesystem/partition extent, path, inode and size checks. An initial verifier had
used the approved relative proof path without its volume prefix; that path error
was retained and corrected before any data proof was claimed. Bidirectional 8 MiB
SSH transfers also passed complete hashes without creating NAS data files.

This was the first RAM checkpoint. The subsequent rollback, repeated fixed-image
acceptance and separately approved installation are recorded below. Short checks
are not long-term stability or whole-content/parity acceptance.

## Private boot-slot backup authorization

Automatic approval review initially refused transfer of the existing first 32 MiB
NAND slot because the exact potentially sensitive payload and private destinations
needed explicit authorization. No rejected operation was executed. I then
explicitly approved that slot read to the selected host's private recovery folder
and the Mac's ignored private backup folder. No public destination was used.

The subsequent read-only preflight found no NAND bad blocks and the first-slot
CRC matched the retained original image plus erased padding. The bootloader's
upload command ignored its alternate destination-port setting and reached the
separate download-only helper, which correctly refused it. A dedicated exact-file,
exact-size, one-client receiver is used sequentially on the required port; the
RAM helper's no-upload restriction is not weakened. Backup acceptance requires the
actual file, independent copies and full checksums, never just a returned prompt.


## Completed rollback and permanent installation

The original-image RAM rollback returned the expected original driver and exact
root/data identities. Both arrays were idle and non-degraded. A second fixed RAM
boot passed 601 seconds of observation: 55 samples, 550 link dumps and 330 software
counter reads, stable required-service processes, fresh native status/cooling and
no matching new kernel fault. Its SSH launch client timed out while systemd kept
the one-shot monitor running normally; it was not restarted or mislabeled failed.

The full original 32 MiB boot slot was accepted only after complete size/hash/CRC
checks and a second private persistent-host copy. A receiver's broad diagnostic
match initially rejected a completed transfer after a legacy bootloader warning;
the actual retained bytes were independently verified without replaying the upload.
The configuration archive was also independently decrypted on the Mac: all 339
members and their hashes passed without extracting plaintext files. It contains
configuration, not media originals.

Following my fresh exact first-slot authorization, the controller erased
only that slot, wrote the page-padded accepted image once and verified full-slot
and image-prefix readback. Its durable receipt and offline refusal/no-retry tests
were retained. The SPI bootloader, second slot, data partitions and USB drives were
excluded. The reviewed module was installed atomically on disk, preserving its
original and dependency-index backups; the active NIC was never unloaded.

The first installed boot and a second ordinary restart both loaded the fixed
module. The second restart's serial-log delta confirms normal NAND/Linux startup
without autoboot interception or TFTP loading. Matching early-boot and disk-root
module identities were verified. Both original 8 MiB initialization proofs passed
exact filesystem/partition extent, path, inode, size and direct-read hash checks;
bidirectional 8 MiB memory-only network transfers passed full hashes in this boot.

## Installed-image observation result

The final ordinary-boot observation passed for **601.21 seconds**, with 55 samples,
550 link dumps and 330 software-counter reads. Required service PIDs stayed stable,
native health/cooling stayed fresh and no matching new kernel fault appeared.
An independent post-observation read reconfirmed the same boot and loaded/on-disk
module, idle/non-degraded arrays, mounted volume identities and fresh native health.
This monitor performs no flash writes; the earlier approved installation is a
separate operation with its own verified readback receipt.

## Operational state and remaining limits

Both arrays are fully populated, non-degraded and idle; both expected data volumes
are mounted. Full-speed cooling, fresh guard telemetry and the ten-second system
watchdog are enabled. CPU readings were approximately 46–48 C and disk readings
32–33 C. LAN and public HTTPS endpoints pass independent certificate verification.
Firefox reaches the secure sign-in page; a new authenticated dashboard session
was not established during final acceptance.

Two warnings from the earlier failed backup attempts remain visible and retained.
The larger-catalog backup fixes were used in an isolated capture, not deployed as
a live broker namespace repair. Routine dashboard backup reliability therefore
still needs that separate repair; the fresh complete encrypted backup is verified.
The temporary boot-transfer listener is closed; remote UART remains passive and
disarmed, with capture/backups retained privately on both recovery hosts.

This is focused active-port acceptance, not a physical test of the other RJ45 or
SFP+ link, a cold power cycle, or proof of every file/parity block. Root offline
consistency checking previously reported device-busy and is not claimed passed.
The kernel remains the accepted 6.12.114 ABI; the separate hardened-kernel update
and the older bootstrap's missing newer policy-helper limitation remain open.
Unpopulated hardware-only NIC counters do not demonstrate zero wire errors.
Removing the recorded faulting statistics path does not prove every possible
future outage is eliminated. No private firmware, credentials or captures are
committed or published.
