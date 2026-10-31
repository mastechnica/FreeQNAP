#!/bin/sh
# Expand the clean Debian tools in RAM; start only a key-authenticated setup SSH.
# No disk mount, partition, application service, DHCP or flash command is issued.
set -eu
umask 077
[ "$#" = 4 ]
url=$1 digest=$2 address=$3 fingerprint=$4
printf '%s\n' "$digest" | grep -Eq '^[0-9a-f]{64}$'
printf '%s\n' "$fingerprint" | grep -Eq '^[0-9a-f]{64}$'
printf '%s\n' "$address" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'
case "$url" in http://*/debian-armhf-base.tar.gz) ;; *) exit 1;; esac
[ -f /run/freeqnap-cooling-ack ] && [ -f /run/freeqnap-macs-verified ]
[ ! -f /run/freeqnap-root-validation-failed ]
[ -s /tmp/freeqnap-administrator.pub ]
grep -Eq '^ssh-ed25519 [A-Za-z0-9+/=]+( |$)' /tmp/freeqnap-administrator.pub
[ "$(wc -l < /tmp/freeqnap-administrator.pub)" = 1 ]
[ ! -e /tmp/freeqnap-debian ]
wget -q -T 30 -O /tmp/freeqnap-base.tar.gz "$url"
printf '%s  %s\n' "$digest" /tmp/freeqnap-base.tar.gz | sha256sum -c -
mkdir /tmp/freeqnap-debian
mount -t tmpfs -o size=1100m,mode=755 tmpfs /tmp/freeqnap-debian
tar -xzf /tmp/freeqnap-base.tar.gz -C /tmp/freeqnap-debian
root=/tmp/freeqnap-debian
for path in dev proc sys run; do mount --bind /$path "$root/$path"; done
# A plain /dev bind does not include nested mounts. SSH needs devpts inside
# this chroot before it can allocate the private password-entry terminal.
mkdir -p "$root/dev/pts"
mount -t devpts -o gid=5,mode=620,ptmxmode=666 devpts "$root/dev/pts"
mkdir -p "$root/root/.ssh" "$root/run/sshd"
chmod 700 "$root/root/.ssh"
cp /tmp/freeqnap-administrator.pub "$root/root/.ssh/authorized_keys"
chmod 600 "$root/root/.ssh/authorized_keys"
printf '%s\n' "$fingerprint" > "$root/run/freeqnap-ram-installer"
chroot "$root" /usr/bin/ssh-keygen -A
cat > "$root/run/freeqnap-setup-sshd.conf" <<CFG
Port 22222
ListenAddress $address
HostKey /etc/ssh/ssh_host_ed25519_key
PidFile /run/freeqnap-setup-sshd.pid
AuthorizedKeysFile .ssh/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin prohibit-password
UsePAM yes
AllowUsers root
LogLevel ERROR
CFG
chroot "$root" /usr/sbin/sshd -t -f /run/freeqnap-setup-sshd.conf
chroot "$root" /usr/sbin/sshd -f /run/freeqnap-setup-sshd.conf -E /run/freeqnap-setup-sshd.log
printf 'FREEQNAP_SETUP_HOST_KEY: '
cat "$root/etc/ssh/ssh_host_ed25519_key.pub"
echo 'FREEQNAP_DEBIAN_TOOLS_READY: RAM only; setup SSH uses port 22222.'
