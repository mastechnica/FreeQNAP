# License scope and release gate

The proposed license for original FreeQNAP host/management code is MIT, subject to owner review before publication. Existing SPDX notices remain authoritative. The board device tree and Linux-derived patches are GPL-2.0-only; the root MIT license does not relicense them. Linux, external drivers, BusyBox and Debian packages retain their own terms.

No third-party source trees, OS/kernel images, signed vendor software or proprietary application code are included in this initial repository. A binary release is blocked until the complete corresponding source, original notices, build recipes and per-component obligations have been reviewed and packaged. See docs/SOURCES.md and docs/RELEASE-REVIEW.md.

## Showcase assets

FreeQNAP icons and the TS-431XeU vector illustration are original project assets.
Live dashboard screenshots use original pixels with documented privacy crops/masks;
no generated UI or third-party product photography is substituted. The two board
photographs were supplied by the owner and authorized for inclusion with identifier
masks; see `docs/tutorial/PHOTO-PROVENANCE.md`. Their inclusion/license remains part
of final owner review. The unused supplied product-reference PNG is retained
privately and excluded from this source tree. No remote fonts, icon library,
analytics or third-party JavaScript are bundled by the static showcase.
