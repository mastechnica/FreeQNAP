# Ethernet repair and LAN HTTPS recovery — 11 November 2026

## Final installation follow-up

The driver has now passed physical RAM boot/rollback and was installed under the
my exact first-slot authorization. Both the early-boot and disk-root copies
match the reviewed fix; an ordinary installed-image boot passed. The sections
below retain the earlier preparation chronology, not the current installation
status. See [the final hardware report](REMOTE-UART-ETHERNET-VALIDATION-2026-11-11.md)
for observation results and remaining limits. HTTPS remains certificate-verified
on the active LAN address and public endpoint.

## HTTPS restored

After I changed Ethernet ports, the LAN proxy retained its old bound
address. A new leaf certificate was issued for the currently assigned address
using the existing offline local certificate authority and the existing server
key. The previous address/name alternatives remain in the certificate. The CA
signing key stayed off the NAS. The proxy still binds one exact private address,
permits only the existing LAN client subnet and retains its Host restrictions,
TLS requirements and unprivileged service isolation.

The web console origin allowlist now includes the new LAN address while preserving
the former LAN/name and public cloud sign-in origins. The existing public route,
identity provider, account links and user permissions were not changed. The native
broker was not restarted; only the web console and LAN HTTPS proxy were restarted.
The private SSH alias now follows the active port with its strict pinned host key
and authentication identity preserved.

Private rollback copies were saved on the Mac and NAS. An initial syntax check
failed because the stopped service's runtime directory did not exist; validation
was moved into a separate staging runtime. The first activation probe failed and
rolled configuration back. Logs showed an overlapping service start still using
old credentials. The corrected activation stops the failed LAN proxy before file
replacement, then starts it and waits for a bounded certificate-verified response.
Earlier failed receipts remain retained; no failure was relabeled as success.

Independent checks from the Mac verified both the new LAN session endpoint using
the original CA and the public session endpoint using normal public trust. Neither
check disabled certificate verification. Current service state is active, cached
health monitoring is fresh and no active alerts remain in the checked snapshot.
This does not establish trust installation in every user's browser or complete an
end-to-end cloud sign-in on the newly assigned LAN address.

## Driver preparation; activation remains incomplete

The reviewed candidate was copied into a private maintenance staging directory,
not into the live module path. Its full checksum, matching kernel ABI and software
statistics marker were verified on the target. The original installed module was
backed up on both NAS and Mac with independent full-checksum agreement. The pinned
prior rollback image is retained and its local checksum rechecked. None of these
steps loaded the candidate, changed the running driver or wrote boot flash.

The accepted bootstrap loads Ethernet before switching to disk root. Replacing
only a disk module would not make the fix persistent. Both Ethernet ports share
this driver, so unloading it over SSH removes the working recovery connection.
The running kernel exposes neither its NAND flash interface nor a demonstrated
software path for safely testing the replacement image. UART and a reviewed RAM
boot/rollback session remain necessary before first hardware activation.

The isolated packager, `tools/build-safe-eth-ram.py`, preserves the accepted kernel
and bootstrap trees, checks pinned input identities, verifies all bootstrap entries
except the exact reviewed Ethernet module remain unchanged, checks the embedded
archive and emits an explicitly RAM-only, flash-prohibited manifest. The accepted
older bootstrap predates the current policy helper: that exact missing-file audit
limitation is recorded rather than adding unrelated bootstrap logic or claiming
current-policy acceptance. All other audit violations remain fatal. Failed build
outputs remain evidence and are not overwritten.

Build artifacts and raw journals, addresses, boot IDs, private keys and detailed
receipts stay outside public Git. No public publishing is part of this task.

## RAM package verification

The isolated build completed. The candidate's legacy ARM image header/payload CRCs,
manifest, size, all listed artifact hashes and exact unchanged kernel ABI passed
independent verification after copying the package to the Mac. Its embedded archive
was compared to the preserved bootstrap: only the reviewed Ethernet module differs.
The ordinary installer rejects the package; explicit RAM-only verification passes.
The fixed module's software-statistics marker was also checked on the NAS without
loading it. The rollback image remains pinned. This is build/package acceptance,
not a successful hardware boot, permanent driver installation or flash acceptance.

The first failed bootstrap audit and the build-environment startup timeout are
retained as evidence. No original build tree was overwritten. A fresh kernel
session still requires UART, an staffed recovery session and the existing
transfer helper serving only the exact candidate and pinned rollback. Leave the
NAS running until that session is prepared; no additional reboot has been sent.
