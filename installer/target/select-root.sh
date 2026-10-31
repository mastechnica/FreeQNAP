#!/bin/sh
# Candidate bootstrap: exact internal SATA mirror, including one surviving member.
# RAM/physical failure acceptance is required before replacing installed images.
set -eu
. /freeqnap/boot-record.sh
. /freeqnap/boot-policy.sh
mkdir -p /run/freeqnap /newroot /dev/md
: > /run/freeqnap/boot-records
selected=''; record_count=0; temporary_mount=''
trap '[ -z "$temporary_mount" ] || umount "$temporary_mount"' EXIT
for device in /dev/sd*1; do
 internal_partition "$device" 1 || continue
 [ "$(/usr/sbin/blkid -s PARTLABEL -o value "$device" 2>/dev/null)" = FREEQNAP_BOOT ] || continue
 mountpoint=/run/freeqnap/boot-$(basename "$device")
 mkdir -p "$mountpoint"
 mount -t ext4 -o ro,noload "$device" "$mountpoint" || exit 1
 temporary_mount=$mountpoint
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
 record_count=$((record_count+1)); [ "$record_count" -le 2 ] || { echo 'Ambiguous extra boot record'; exit 1; }
 printf '%s\n' "$device" >> /run/freeqnap/boot-records
 umount "$mountpoint"; temporary_mount=''
done
[ -n "$selected" ] || exit 42
parse_record /run/freeqnap/selected.conf || exit 1
set --; seen_members=''
for device in /dev/sd*2; do
 internal_partition "$device" 2 || continue
 metadata=/run/freeqnap/member-$(basename "$device")
 /usr/sbin/mdadm --examine --export "$device" > "$metadata" 2>/dev/null || continue
 root_member_metadata "$metadata" "$ROOT_MD_UUID" || continue
 case " $seen_members " in *" $MEMBER_DEV_UUID "*) echo 'Duplicate cloned root member'; exit 1;; esac
 seen_members="$seen_members $MEMBER_DEV_UUID"; set -- "$@" "$device"
done
[ "$#" -ge 1 ] && [ "$#" -le 2 ] || { echo 'Missing or ambiguous root mirror members'; exit 1; }
printf 'DEVICE' > /etc/mdadm/mdadm.conf
printf ' %s' "$@" >> /etc/mdadm/mdadm.conf
printf '\nHOMEHOST <ignore>\nAUTO -all\nARRAY /dev/md/freeqnap-root UUID=%s\n' "$ROOT_MD_UUID" >> /etc/mdadm/mdadm.conf
# One exact surviving RAID1 member is allowed; mdadm still decides freshness.
# No scan, forced assembly, fabricated clean state or unrelated array activation.
/usr/sbin/mdadm --assemble --run --readonly /dev/md/freeqnap-root --uuid="$ROOT_MD_UUID" --config=/etc/mdadm/mdadm.conf "$@"
array=$(basename "$(readlink -f /dev/md/freeqnap-root)")
[ "$(cat "/sys/class/block/$array/md/level")" = raid1 ] || exit 1
[ "$(cat "/sys/class/block/$array/md/raid_disks")" = 2 ] || exit 1
degraded=$(cat "/sys/class/block/$array/md/degraded")
case "$degraded" in 0) ;; 1) echo 'FreeQNAP: root mirror has one verified surviving member; degraded boot requires operator attention';; *) exit 1;; esac
[ "$(/usr/sbin/blkid -s UUID -o value /dev/md/freeqnap-root)" = "$ROOT_FS_UUID" ] || exit 1
mount -t ext4 -o ro,noload /dev/md/freeqnap-root /newroot
[ -f /newroot/etc/freeqnap-install-id ] && [ ! -L /newroot/etc/freeqnap-install-id ] && [ "$(cat /newroot/etc/freeqnap-install-id)" = "$INSTALL_ID" ] || exit 1
umount /newroot
/usr/sbin/mdadm --readwrite /dev/md/freeqnap-root
set +e
/usr/sbin/e2fsck -p /dev/md/freeqnap-root
result=$?
set -e
[ "$result" -le 1 ] || exit 1
mount -t ext4 -o ro /dev/md/freeqnap-root /newroot
printf '%s\n' "$degraded" > /run/freeqnap/root-boot-degraded
# PID1 performs the handoff; this helper never invokes switch_root.
touch /run/freeqnap-root-ready
