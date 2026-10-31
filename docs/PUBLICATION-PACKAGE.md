# GitHub source-review package

**Publication authorized on 31 October 2026.** The owner approved the reviewed
source and showcase for the personal **mastechnica/FreeQNAP** repository, with
GitHub Pages served from `/docs`. Use only the personal account and a clean source
snapshot. Do not import private development history or use an organization or a
separate commercial project's documentation repository.

## What the owner is reviewing

- Root README: the GitHub repository's main page, feature matrix, real screenshots,
  local preview instructions and acceptance boundaries.
- `docs/index.html`: full static showcase intended for a future GitHub Pages root
  served from `/docs`. It includes a keyboard-accessible screenshot gallery,
  complete feature tour, hardware photographs, installer stages and readiness.
- `docs/tutorial/`: the illustrated technical guide, original-pixel motherboard
  and UART photographs with opaque identifier masks, and qualified pinout diagram.
- Source: application, installer stages, board integration, tests, deployment and
  review tools, license notices and engineering documentation.

The optional trailer field is portable metadata; the app does not automatically
search/download trailers. Browser picture-in-picture is capability-dependent.
No universal USB crypto, automatic 4K transcoding, full-chip recovery, compatible
related-model installation or fully accepted public binary installer is promised.

## Preview

From the repository root:

```sh
python3 -m http.server 8767 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8767/`. The page is static and contains no dashboard session,
remote fonts, analytics, trackers, live NAS connection or external script dependency.
It uses sanitized screenshots of the real application. Guide links remain local.
Opening external documentation/source links is a separate browser action.

## Checks and packaging

```sh
python3 tools/check-package.py
python3 tools/check-showcase.py
python3 -m unittest discover -s installer/tests -q
python3 -m unittest discover -s tests -q
node --check web/app.js
node --check docs/showcase.js
```

Commit the reviewed sources, then create the archive:

```sh
python3 tools/package-review.py --output dist/github-review
```

The reproducible ZIP contains the exact committed source tree and a SHA-256 member
manifest. Its sibling checksum file identifies the ZIP. The tool verifies every
ZIP member against its manifest and refuses a dirty working tree, symlinks,
private/generated directories and excluded OS/key/database/log artifacts. Generated
archives remain Git-ignored. The package is a **source snapshot**, not a binary
installer, verified disk image or copy of the developer's local Git history.

Private originals, runtime state, SSH material, certificates/keys, source-build
caches, flash dumps and device configuration stay outside the ZIP. No NAS root or
data backup is included. Screenshot receipts verify deterministic crops/masks and
no changed pixels outside masks; their original captures remain private.

## Publication boundaries

Review README, the full showcase and three screenshots, installation safety,
acceptance wording and MIT/GPL boundaries. Review original photo masks/pinout
qualifications and any remaining real identifiers. Source checks are not a
comprehensive secret or legal audit. The local history was not included in the
review ZIP and is excluded from the initial public repository. Publication
approval does not cover unrelated local history or private assets.

The owner approved the exact personal destination and requested Pages. Publish
only the clean reviewed snapshot and enable Pages from `/docs`. Future changes
must retain the same private-data and source/license boundaries.
Do not mark the installer turnkey or upload OS binaries until clean-source,
corresponding-source/license, signatures, interruption/recovery and update gates
are met. Preserve all original notices. See [license scope](../licenses/README.md)
and [current status](CURRENT-STATUS.md).

## This review's verification

- 43 installer fixture tests passed on the Mac.
- 222 application fixture tests passed with four platform-specific skips.
- Showcase/app JavaScript syntax checks and the existing Node view tests passed.
- Public source-inventory/hash/private-path checks and static HTML local-link,
  anchor, screenshot-hash/dimension/metadata checks passed.
- The static page returned HTTP 200 on localhost. Desktop hero, screenshot gallery
  and keyboard tab switching were checked in the browser. Mobile breakpoints are
  implemented but not physically accepted on every device.
- The review ZIP is verified member-by-member and can be checked from a clean
  extraction without developer-private files. Its external manifest/checksum record
  gives the exact committed source revision; no local history is bundled.
