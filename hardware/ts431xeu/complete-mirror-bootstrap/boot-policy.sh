#!/bin/sh
# Small bootstrap policies. Disk metadata is data, never shell code.
internal_partition() {
 device=$1; number=$2; sysroot=${3:-/sys}; INTERNAL_PARENT=''
 printf '%s\n' "$device" | grep -Eq '^/dev/sd[a-z]+[12]$' || return 1
 part=${device##*/}; resolved=$(readlink -f "$sysroot/class/block/$part") || return 1
 [ -f "$resolved/partition" ] && [ "$(cat "$resolved/partition")" = "$number" ] || return 1
 case "$resolved" in */0000:00:09.0/ata[0-9]*/host*/target*/*/block/sd*/sd*) ;; *) return 1;; esac
 parent=$(basename "$(dirname "$resolved")")
 printf '%s\n' "$parent" | grep -Eq '^sd[a-z]+$' || return 1
 [ "$(readlink -f "$sysroot/class/block/$parent")/$part" = "$resolved" ] || return 1
 INTERNAL_PARENT=$parent
}
root_member_metadata() {
 metadata=$1; expected=$2; MEMBER_DEV_UUID=''; level=''; devices=''; array_uuid=''; seen=''
 [ -f "$metadata" ] && [ ! -L "$metadata" ] && [ "$(wc -c < "$metadata")" -le 16384 ] || return 1
 while IFS='=' read -r key value || [ -n "$key" ]; do
  case "$key" in MD_UUID|MD_LEVEL|MD_DEVICES|MD_DEV_UUID)
   case " $seen " in *" $key "*) return 1;; esac
   seen="$seen $key";; *) continue;; esac
  case "$key" in
   MD_UUID) array_uuid=$value;; MD_LEVEL) level=$value;; MD_DEVICES) devices=$value;; MD_DEV_UUID) MEMBER_DEV_UUID=$value;;
  esac
 done < "$metadata"
 [ "$level" = raid1 ] && [ "$devices" = 2 ] && [ "$array_uuid" = "$expected" ] || return 1
 printf '%s\n' "$MEMBER_DEV_UUID" | grep -Eq '^[0-9a-f]{8}(:[0-9a-f]{8}){3}$'
}
