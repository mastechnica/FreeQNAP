#!/bin/sh
# Read-only serial inventory. Base64 protects field delimiters and untrusted disk strings.
set -eu
field() { printf '__FREEQNAP_FIELD__|%s|' "$1"; shift; "$@" | base64 | tr -d '\n'; printf '\n'; }
flag() { if [ -f "$1" ]; then printf 1; else printf 0; fi; }
hex() { od -An -v -tx1 "$1" | tr -d ' \n'; }
field kernel uname -r
field board cat /proc/device-tree/model
field compatible cat /proc/device-tree/compatible
field cpu cat /proc/cpuinfo
field memory cat /proc/meminfo
field mounts cat /proc/mounts
field mdstat cat /proc/mdstat
field swaps cat /proc/swaps
field cooling_ack flag /run/freeqnap-cooling-ack
field factory_macs_verified flag /run/freeqnap-macs-verified
field existing_root_failed flag /run/freeqnap-root-validation-failed
field disks /usr/bin/lsblk --json --bytes -o NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,HCTL,RO,FSTYPE,UUID,MOUNTPOINTS
for file in /sys/class/net/*/address; do
 interface=$(basename "$(dirname "$file")")
 field "mac.$interface" cat "$file"
done
for file in /sys/class/thermal/thermal_zone*/temp; do
 [ -f "$file" ] || continue
 zone=$(basename "$(dirname "$file")")
 field "thermal.$zone" cat "$file"
done

for device in /sys/class/block/sd[a-z]; do
 [ -e "$device/device" ] || continue
 field "disk.$(basename "$device").sysfs" readlink -f "$device/device"
 [ ! -r "$device/device/vpd_pg80" ] || field "disk.$(basename "$device").vpd80" hex "$device/device/vpd_pg80"
 [ ! -r "$device/device/wwid" ] || field "disk.$(basename "$device").wwid" cat "$device/device/wwid"
done
