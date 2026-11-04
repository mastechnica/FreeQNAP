#!/bin/sh
# Optional, distribution-provided decoders. No account, scan, playback or storage creation.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run on the NAS as root.' >&2; exit 1; }
[ "$(dpkg --print-architecture)" = armhf ] || { echo 'This installer targets Debian ARMhf.' >&2; exit 1; }
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg poppler-utils libmobi-tools
printf 'Optional book and music decoders installed. Choose My Radio storage in the dashboard.
'
