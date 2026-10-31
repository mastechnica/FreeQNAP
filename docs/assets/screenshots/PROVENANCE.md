# Live dashboard screenshots

Captured on 31 October 2026 from the running, authenticated FreeQNAP application
on the physical TS-431XeU. These are not synthetic preview fixtures, rendered
mockups or AI-generated interface images.

- **Overview:** real front-panel visualization, incomplete RAID protection alert
  during initial synchronization, CPU/RAM/temperature history. The critical state
  was retained; nothing was changed to make the system appear healthy.
- **Files:** two actual tiled folder windows showing existing folders and a silent
  test WAV on the disposable unlocked LUKS/ext4 USB drive. Viewing these files did
  not create, move or delete data. No audio was played. Four partial serial labels
  were masked.
- **Network:** actual connected/disconnected physical ports, current traffic,
  charts and aggregate coverage. The private IPv4/IPv6 address row was masked.
  Unknown negotiated speed and short history coverage remain visible.

Browser tabs, address bar and browser profile controls were cropped away. Opaque
rectangles cover identifiers. All other retained pixels are unchanged from the
original captures. No health state, count, filename, chart or metric was invented
or retouched. PNG exports contain no EXIF/GPS/source filename metadata.

[Redaction receipts](receipts.json) record source/output SHA-256, crop coordinates
and mask rectangles. [Preparation tool](../../../tools/prepare-screenshots.py)
reproduces the outputs from private originals and verifies pixel equality outside
masks. Original unredacted captures are private and excluded from distribution.
The owner should review the images once more before public publication.
