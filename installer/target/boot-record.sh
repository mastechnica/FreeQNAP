#!/bin/sh
# Parse a restricted record as data. Never source/eval disk-supplied content.
parse_record() {
 record=$1; seen=''; fields=0
 FORMAT= MODEL= INSTALL_ID= UNIT_MAC= ROOT_MD_UUID= ROOT_FS_UUID=
 while IFS='=' read -r key value || [ -n "$key" ]; do
  case " $seen " in *" $key "*) return 1;; esac
  case "$key" in
   FORMAT) [ "$value" = 1 ] || return 1; FORMAT=$value;;
   MODEL) [ "$value" = TS-431XeU ] || return 1; MODEL=$value;;
   INSTALL_ID) printf '%s\n' "$value" | grep -Eq '^[0-9a-f]{32}$' || return 1; INSTALL_ID=$value;;
   UNIT_MAC) printf '%s\n' "$value" | grep -Eq '^[0-9a-f]{12}$' || return 1; UNIT_MAC=$value;;
   ROOT_MD_UUID) printf '%s\n' "$value" | grep -Eq '^[0-9a-f]{8}(:[0-9a-f]{8}){3}$' || return 1; ROOT_MD_UUID=$value;;
   ROOT_FS_UUID) printf '%s\n' "$value" | grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || return 1; ROOT_FS_UUID=$value;;
   *) return 1;;
  esac
  seen="$seen $key"; fields=$((fields+1))
 done < "$record"
 [ "$fields" = 6 ]
}
