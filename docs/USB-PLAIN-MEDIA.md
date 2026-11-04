# Existing NTFS, exFAT and FAT USB media

USB drives offers **Mount read-only** for existing unencrypted NTFS, exFAT and
FAT partitions. It uses a fresh exact-device plan and a root-private, read-only
nodev/nosuid/noexec session. NTFS uses ntfs-3g with norecover; it does not repair
or replay an unsafe volume. The action formats nothing and stores no password.
An active session appears in File Manager and can be a library import source.
Use Lock volume / safe eject before unplugging. Automatic mounting is not enabled
by this change. A dirty/hibernated or unsupported volume may be refused.

Fixture tests confirm plain NTFS mounts without cryptsetup or password handling.
Physical acceptance is recorded separately; fixture coverage is not disk testing.
