# Security and maintenance status

FreeQNAP is experimental and has not received an independent security audit. Its
custom board kernel is not updated by normal Debian package upgrades. Review the
dated kernel-security record; no permanent or comprehensive CVE coverage is promised.

The console defaults to NAS loopback with authenticated SSH forwarding. Optional
LAN HTTPS uses an explicitly configured local certificate and source restrictions.
It has separate private administrator enrollment, session/CSRF checks and no
default administrator password or trusted proxy-user login header. Root SSH is
key-only by default. The web process is unprivileged; the local broker exposes
fixed checked operations, not arbitrary shell commands. Root inventory collection
is separate. Disk identity/ancestor and confirmation checks remain required.

Legacy console-only snapshots are private and unencrypted. Downloadable complete
NAS configuration exports use password encryption; Restic repositories are encrypted.
These have different coverage, and neither is a bootable OS/flash backup. SHA-256
receipts alone detect accidental corruption; they do not authenticate a package
against an attacker who can replace both package and receipt. Keep independent,
verified backups and recovery secrets outside the NAS.

Optional VPN/private LAN/firewall and service settings need real deployment tests.
DLNA client approval by network identity does not authenticate a person or provide
per-user folder isolation. Do not expose management services publicly by default.
Browser push relays and selected providers are external systems; their acceptance
does not prove receipt or privacy beyond the documented protocol.

Report suspected issues privately to the maintainer through the eventual personal
repository's private reporting facility if available. No reporting endpoint is
promised before publication. Do not include credentials, raw device dumps or
private files in a public issue. This review source package is not a signed
binary appliance release or a guarantee of secure recovery under all failures.
