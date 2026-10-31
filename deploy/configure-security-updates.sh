#!/bin/sh
# Enable direct official signed Debian sources; preserve the old configuration.
set -eu
[ "$(id -u)" = 0 ]
[ "$(tr '\000' '\n' < /proc/device-tree/compatible | head -n 1)" = qnap,ts-431xeu ]
[ "$(dpkg --print-architecture)" = armhf ]
. /etc/os-release
[ "$VERSION_CODENAME" = trixie ]
[ -s /usr/share/keyrings/debian-archive-keyring.gpg ]
backup=/var/lib/freeqnap-system/apt-sources-before-direct-security
[ ! -e "$backup" ] || { echo 'Existing source backup: review before repeating configuration';exit 1; }
[ ! -e /etc/apt/sources.list.d/freeqnap-debian.sources ] || { echo "Existing FreeQNAP source file: review before replacing";exit 1; }
install -d -m 700 "$backup"
if [ -f /etc/apt/sources.list ];then cp -p /etc/apt/sources.list "$backup/sources.list";fi
cp -a /etc/apt/sources.list.d "$backup/sources.list.d"
cat > /etc/apt/sources.list.d/freeqnap-debian.sources <<'EOF'
Types: deb
URIs: https://deb.debian.org/debian
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://security.debian.org/debian-security
Suites: trixie-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
chmod 644 /etc/apt/sources.list.d/freeqnap-debian.sources
# This converted installation's original list contained only the same main suite.
# Keep unknown additional repositories for explicit review rather than replacing them.
if [ -f /etc/apt/sources.list ];then
 if ! cmp -s /etc/apt/sources.list /dev/null;then
  if [ "$(sed '/^[[:space:]]*#/d;/^[[:space:]]*$/d' /etc/apt/sources.list)" != 'deb https://deb.debian.org/debian trixie main' ];then
   rm /etc/apt/sources.list.d/freeqnap-debian.sources
   echo 'Unexpected existing sources; retained untouched, review the private backup';exit 1
  fi
 fi
 printf '# Official main/updates/security sources are in freeqnap-debian.sources\n' > /etc/apt/sources.list
fi
apt-get -o Acquire::https::Timeout=30 -o Acquire::Retries=1 update
printf 'Signed package metadata refreshed directly. No package upgrade or reboot was performed.\n'
