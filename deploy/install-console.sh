#!/bin/sh
# Installs the local console and bounded diagnostic logs. No disk layout, flash, network or sharing changes.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run this on the NAS as root'; exit 1; }
[ "$(tr '\000' '\n' < /proc/device-tree/compatible | head -n 1)" = qnap,ts-431xeu ]
[ "$(dpkg --print-architecture)" = armhf ]
base=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 -m compileall -q "$base/freeqnap"
getent passwd freeqnap >/dev/null || adduser --system --group --home /var/lib/freeqnap --no-create-home freeqnap
install -d -m 700 -o freeqnap -g freeqnap /var/lib/freeqnap /var/backups/freeqnap
install -d -m 755 /opt/freeqnap/releases
# New, immutable source generation; previous generation is retained for rollback.
release=/opt/freeqnap/releases/$(date -u +%Y%m%dT%H%M%SZ)
[ ! -e "$release" ];install -d -m 755 "$release"
cp -R "$base/freeqnap" "$base/web" "$release/"
if [ -d "$base/docs" ];then cp -R "$base/docs" "$release/";fi
find "$release" -type d -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root "$release";find "$release" -type d -exec chmod 755 {} +;find "$release" -type f -exec chmod 644 {} +
ln -s "$release" /opt/freeqnap/current.next
mv -Tf /opt/freeqnap/current.next /opt/freeqnap/current
install -m 644 "$base/deploy/freeqnap.tmpfiles.conf" /etc/tmpfiles.d/freeqnap.conf
for name in freeqnap-console.service freeqnap-collect.service freeqnap-collect.timer;do
 install -m 644 "$base/deploy/$name" "/etc/systemd/system/$name"
done
systemd-tmpfiles --create /etc/tmpfiles.d/freeqnap.conf
# Keep crash evidence across resets without unbounded OS-volume growth.
install -d -m 755 /etc/systemd/journald.conf.d
install -m 644 "$base/deploy/freeqnap-journald.conf" /etc/systemd/journald.conf.d/70-freeqnap-retention.conf
install -d -m 2755 -o root -g systemd-journal /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal
systemctl restart systemd-journald
journalctl --flush
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/freeqnap-console.service /etc/systemd/system/freeqnap-collect.service /etc/systemd/system/freeqnap-collect.timer
systemctl start freeqnap-collect.service
systemctl enable --now freeqnap-collect.timer freeqnap-console.service
systemctl restart freeqnap-console.service
tls_restored=0
# Requires=console can stop an existing HTTPS proxy during console replacement.
# Bring it back explicitly rather than assuming a transient ActiveState is ready.
if [ -f /etc/freeqnap-https/public.json ] && systemctl is-enabled --quiet freeqnap-https.service;then
 systemctl start freeqnap-https.service
 PYTHONPATH="$release" python3 - <<'HTTPS'
import json,time
from pathlib import Path
from freeqnap.nas.management_tls import ManagementTLS,validate
config=validate(json.loads(Path('/etc/freeqnap-https/public.json').read_text()))
end=time.monotonic()+20
while time.monotonic()<end:
 if ManagementTLS(None).probe(config['address']):break
 time.sleep(.5)
else:raise SystemExit('Existing HTTPS did not recover; keep SSH access and inspect the retained generation')
HTTPS
 tls_restored=1
fi
if [ "$tls_restored" = 1 ];then
 printf 'Console updated; existing local HTTPS verified and administrator settings retained.\n'
else
 printf 'Console installed on loopback only; initialize its separate administrator password privately over SSH.\n'
fi
