#!/bin/sh
set -eu
[ "$(id -u)" = 0 ]
base=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 -B "$base/tools/usb-pcie-workaround.py"
install -d -m 755 /usr/local/libexec
install -m 700 "$base/tools/usb-pcie-workaround.py" /usr/local/libexec/freeqnap-usb-pcie
install -m 644 "$base/deploy/freeqnap-usb-pcie.service" /etc/systemd/system/freeqnap-usb-pcie.service
systemd-analyze verify /etc/systemd/system/freeqnap-usb-pcie.service
systemctl daemon-reload
systemctl enable --now freeqnap-usb-pcie.service
