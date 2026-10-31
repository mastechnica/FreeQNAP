#!/bin/sh
# Install locally built, reviewed exact-kernel artifacts; no reboot or flash write.
set -eu
[ "$#" = 2 ] || { echo 'Usage: install-poweroff.sh MATCHING_MODULE.ko STATIC_SHUTDOWN_HELPER';exit 2; }
[ "$(id -u)" = 0 ]
[ "$(tr '\000' '\n' < /proc/device-tree/compatible | head -n 1)" = qnap,ts-431xeu ]
module=$1
helper=$2
[ -f "$module" ] && [ ! -L "$module" ] && [ -x "$helper" ] && [ ! -L "$helper" ]
case $(modinfo -F vermagic "$module") in "$(uname -r) "*) ;; *) echo 'Module ABI differs; refusing';exit 1;; esac
[ "$(modinfo -F name "$module")" = freeqnap_poweroff ]
"$helper" --check
backup=/var/lib/freeqnap-system/shutdown-original
install -d -m 700 "$backup"
if [ ! -e "$backup/eyeq-poweroff" ];then cp -p /usr/lib/systemd/system-shutdown/eyeq-poweroff "$backup/eyeq-poweroff";fi
install -d /lib/modules/"$(uname -r)"/updates/freeqnap
install -m 644 "$module" /lib/modules/"$(uname -r)"/updates/freeqnap/freeqnap_poweroff.ko
depmod -a
modprobe freeqnap_poweroff
[ "$(cat /sys/module/freeqnap_poweroff/parameters/ready)" = Y ]
"$helper" --check
install -m 700 "$helper" /usr/lib/systemd/system-shutdown/eyeq-poweroff
printf '%s\n' freeqnap_poweroff > /etc/modules-load.d/freeqnap-poweroff.conf
printf 'Final kernel callback registered without a UART write. Physical shutdown/cold-start acceptance is still required.\n'
