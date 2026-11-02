#!/bin/sh
# Install the controller at fixed full speed. Never creates acceptance receipts.
set -eu
[ "$(id -u)" = 0 ]
[ "$(tr '\000' '\n' < /proc/device-tree/compatible | head -n 1)" = qnap,ts-431xeu ]
base=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
[ -x /usr/local/sbin/eyeq-mcu-safe-full ]
[ -f /opt/freeqnap/current/freeqnap/cooling.py ]
/usr/local/sbin/eyeq-mcu-safe-full
install -d -m 750 -o root -g freeqnap /var/lib/freeqnap-cooling /run/freeqnap-cooling
if [ ! -e /etc/freeqnap/cooling.json ];then
 python3 - <<'PY'
import json,os,secrets
p='/etc/freeqnap/cooling.json'
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o640)
with os.fdopen(fd,'w') as f:json.dump({'mode':'full','generation':secrets.token_hex(16)},f);f.flush();os.fsync(f.fileno())
PY
fi
for name in freeqnap-cooling.service freeqnap-cooling-guard.service;do
 install -m 644 "$base/deploy/$name" /etc/systemd/system/
done
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/freeqnap-cooling.service /etc/systemd/system/freeqnap-cooling-guard.service
systemctl enable --now freeqnap-cooling-guard.service freeqnap-cooling.service
