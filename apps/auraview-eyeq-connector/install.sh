#!/bin/sh
# Install application files only. No disk, firewall or NAS configuration changes.
set -eu
umask 022
[ "$(id -u)" = 0 ] || { echo 'Run as the NAS administrator (root).'; exit 1; }
getent passwd freeqnap >/dev/null
[ -d /opt/freeqnap/current/freeqnap ] || { echo 'Supported AuraStore/FreeQNAP installation required.'; exit 1; }
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -d -m 0755 /opt/auraview-eyeq-connector
install -m 0644 "$HERE/connector.py" /opt/auraview-eyeq-connector/connector.py
python3 -m venv /opt/auraview-eyeq-connector/venv
/opt/auraview-eyeq-connector/venv/bin/pip install 'websockets==15.0.1'
# Dependencies contain no user state; repair prior restrictive caller umasks.
chmod -R a+rX /opt/auraview-eyeq-connector/venv
install -d -m 0700 -o freeqnap -g freeqnap /var/lib/auraview-eyeq-connector
install -m 0644 "$HERE/auraview-eyeq-connector@.service" /etc/systemd/system/
systemctl daemon-reload
echo 'Installed. Pair a local NAS account before starting its service; see README.md.'
