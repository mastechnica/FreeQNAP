# Original photographs and redaction

The owner supplied the two original HEIC photographs of this TS-431XeU and authorized their inclusion with identifying serials removed. On 29 October 2026 the owner explicitly selected deterministic redaction masks after a generative preview changed small board details. That preview is rejected and is not in this repository or tutorial.

The included PNGs use the original oriented pixels with opaque masks covering identifying stickers and unrelated drive-label regions. Every pixel outside the recorded masks is unchanged. Fresh PNG export excludes EXIF/GPS/thumbnails and all source metadata. Per-image redaction receipts record the mask coordinates and output hashes; the originals remain private and outside this repository.

`tools/redact-photos.py` reproduces these masks with Pillow. It refuses to overwrite reviewed output and verifies unchanged pixels outside its masks. The rectangles are conservative; the owner must review the final photographs before GitHub publication. The original board and connector geometry have not been generated or reconstructed.

The owner confirmed the four-pin CN2/UART0_DEBUG connector and far-right GND with the lettering upright. The separate SVG clearly marks the other positions as related-model references, not measured acceptance on this board. Do not turn those labels into an unqualified wiring instruction until they and the voltage are verified.
