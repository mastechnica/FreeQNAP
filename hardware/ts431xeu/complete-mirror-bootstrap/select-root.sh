#!/bin/sh
# Generic bootstrap. Only this installation's explicitly identified array is opened.
set -eu
. /freeqnap/boot-record.sh
mkdir -p /run/freeqnap /newroot /dev/md
: > /run/freeqnap/boot-records
selected=''
for device in $(/usr/sbin/blkid -t PARTLABEL=FREEQNAP_BOOT -o device); do
 mountpoint=/run/freeqnap/boot-$(basename "$device")
 mkdir -p "$mountpoint"
 mount -t ext4 -o ro,noload "$device" "$mountpoint" || exit 1
 record=$mountpoint/freeqnap/installation.conf
 [ -f "$record" ] && [ ! -L "$record" ] && [ "$(wc -c < "$record")" -le 1024 ] || exit 1
 parse_record "$record" || exit 1
 matched=no
 for address in /sys/class/net/*/address; do
  [ "$(tr -d ':' < "$address")" != "$UNIT_MAC" ] || matched=yes
 done
 [ "$matched" = yes ] || { echo 'Boot record belongs to a different NAS'; exit 1; }
 if [ -z "$selected" ]; then
  cp "$record" /run/freeqnap/selected.conf; selected=$device
 else
  cmp -s "$record" /run/freeqnap/selected.conf || { echo 'Conflicting mirrored boot records'; exit 1; }
 fi
 printf '%s\n' "$device" >> /run/freeqnap/boot-records
 umount "$mountpoint"
done
[ -n "$selected" ] || exit 42
parse_record /run/freeqnap/selected.conf || exit 1
printf 'DEVICE /dev/sd*2\nHOMEHOST <ignore>\nAUTO -all\nARRAY /dev/md/freeqnap-root UUID=%s\n' "$ROOT_MD_UUID" > /etc/mdadm/mdadm.conf
# No broad scan/automatic QTS array assembly and no degraded acceptance here.
/usr/sbin/mdadm --assemble --run --readonly /dev/md/freeqnap-root --config=/etc/mdadm/mdadm.conf
array=$(basename "$(readlink -f /dev/md/freeqnap-root)")
[ "$(cat "/sys/class/block/$array/md/degraded")" = 0 ] || exit 1
[ "$(/usr/sbin/blkid -s UUID -o value /dev/md/freeqnap-root)" = "$ROOT_FS_UUID" ] || exit 1
mount -t ext4 -o ro,noload /dev/md/freeqnap-root /newroot
[ -f /newroot/etc/freeqnap-install-id ] && [ "$(cat /newroot/etc/freeqnap-install-id)" = "$INSTALL_ID" ] || exit 1
umount /newroot
/usr/sbin/mdadm --readwrite /dev/md/freeqnap-root
set +e
/usr/sbin/e2fsck -p /dev/md/freeqnap-root
result=$?
set -e
[ "$result" -le 1 ] || exit 1
mount -t ext4 -o ro /dev/md/freeqnap-root /newroot
# The caller is PID1. Leave a checked, mounted root for that process to perform
# switch_root; a helper child must never attempt the PID1-only handoff itself.
touch /run/freeqnap-root-ready
