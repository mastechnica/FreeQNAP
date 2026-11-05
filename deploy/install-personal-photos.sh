#!/bin/sh
# Optional photo dependencies only; never signs in or starts an archive.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root on Debian.' >&2; exit 1; }
[ "${1:-}" = '--with-icloud' ] || { echo 'Usage: install-personal-photos.sh --with-icloud [verified-source.tar.gz]' >&2; exit 1; }
photo_revision=99a6e7cde77819e739ed293ef411e5468b34873f
photo_sha=faec3c59d490d4317b358e7996f06a3c1de8d87ae52d8a56d64b2cdde12c085a
photo_archive=${2:-/var/tmp/freeqnap-icloud-source.tar.gz}
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-venv libimage-exiftool-perl ffmpeg libheif1 libheif-plugin-libde265 libheif-plugin-dav1d
if [ ! -f "$photo_archive" ]; then
 python3 - "$photo_archive" "$photo_revision" <<'PY'
import sys,urllib.request
from pathlib import Path
path=Path(sys.argv[1]);url='https://codeload.github.com/icloud-photos-downloader/icloud_photos_downloader/tar.gz/'+sys.argv[2]
with urllib.request.urlopen(url,timeout=60) as source,path.open('xb') as target:
 while chunk:=source.read(1024**2):target.write(chunk)
PY
fi
printf '%s  %s\n' "$photo_sha" "$photo_archive" | sha256sum -c -
photo_venv=/opt/freeqnap/photos-venv
if [ -e "$photo_venv" ]; then echo 'Existing photo environment retained; inspect before replacing.' >&2; exit 1; fi
install -d -m 700 -o nobody -g nogroup "$photo_venv"
chmod 644 "$photo_archive"
runuser -u nobody -- python3 -m venv --system-site-packages "$photo_venv"
runuser -u nobody -- "$photo_venv/bin/python3" -m pip install --no-cache-dir "$photo_archive"
"$photo_venv/bin/python3" -m pip check
"$photo_venv/bin/python3" - <<'PY'
from pyicloud_ipd.base import PyiCloudService
for method in ('validate_2fa_code','trust_session','trigger_push_notification','request_pcs_consent'):
 if not hasattr(PyiCloudService,method):raise SystemExit('Required iCloud authentication API is unavailable: '+method)
print('Optional iCloud connector API checks passed; no Apple connection was made.')
PY
chown -R root:root "$photo_venv"
chmod 755 "$photo_venv"
printf '%s\n' "$photo_revision" > "$photo_venv/freeqnap-upstream-revision"
photo_deploy=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -m 644 "$photo_deploy/freeqnap-icloud-albums.service" "$photo_deploy/freeqnap-icloud-albums.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now freeqnap-icloud-albums.timer
echo 'Dependencies prepared. Broker interpreter adoption is a separate deployment step.'
