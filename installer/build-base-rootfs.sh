#!/bin/sh
# Local packaging from a prepared, signed-package Debian ARMhf base tree.
# This development recipe does not yet replace a clean public debootstrap build.
set -eu
umask 077
: "${FREEQNAP_SOURCE:?}"
: "${FREEQNAP_BOARD_SOURCE:?}"
: "${FREEQNAP_OUTPUT:?}"
: "${FREEQNAP_BASE_ROOT:?}"
case "$FREEQNAP_BASE_ROOT" in /build/freeqnap-base-*) ;; *) exit 1;; esac
[ ! -e "$FREEQNAP_BASE_ROOT" ]
[ -d "$FREEQNAP_OUTPUT" ]
root=$FREEQNAP_BASE_ROOT
mkdir -m 755 "$root"
# Device nodes belong to devtmpfs at runtime; never copy build-time devices.
archive=$root.source.tar
tar --numeric-owner --xattrs --acls --exclude='./dev/*' --exclude='./proc/*' \
 --exclude='./sys/*' --exclude='./run/*' -cf "$archive" -C /build/debian-rootfs .
tar --numeric-owner --xattrs --acls -xpf "$archive" -C "$root"
rm "$archive"
# Direct official updates must not depend on the administration Mac.
[ -s "$root/usr/share/keyrings/debian-archive-keyring.gpg" ]
mkdir -p "$root/etc/apt/sources.list.d"
cp "$FREEQNAP_SOURCE/target/debian.sources" "$root/etc/apt/sources.list.d/freeqnap-debian.sources"
chmod 644 "$root/etc/apt/sources.list.d/freeqnap-debian.sources"
printf '# Official main/updates/security sources are in freeqnap-debian.sources\n' > "$root/etc/apt/sources.list"
# Remove the development base's machine-specific identity and runtime state.
rm -rf "$root/root/.ssh" "$root/root/.bash_history" "$root/etc/ssh/ssh_host_"* \
 "$root/etc/machine-id" "$root/var/lib/dbus/machine-id" "$root/etc/eyeq-build-status" \
 "$root/etc/systemd/network/"* "$root/usr/lib/modules/"* "$root/var/lib/docker" \
 "$root/var/lib/containerd" "$root/var/lib/systemd/random-seed" "$root/var/lib/dhcp" \
 "$root/var/lib/NetworkManager" "$root/usr/bin/qemu-arm-static" "$root/usr/sbin/policy-rc.d"
find "$root/var/log" -mindepth 1 -delete
find "$root/tmp" "$root/var/tmp" "$root/run" -mindepth 1 -delete
: > "$root/etc/machine-id"
chmod 644 "$root/etc/machine-id"
printf '# Filled with this installation UUIDs by FreeQNAP.\n' > "$root/etc/fstab"
printf 'DEVICE /dev/sd*2\nHOMEHOST <ignore>\nAUTO -all\n' > "$root/etc/mdadm/mdadm.conf"
sed -i 's/^root:[^:]*:/root:!:/' "$root/etc/shadow"
printf 'freeqnap\n' > "$root/etc/hostname"
printf '127.0.0.1 localhost\n127.0.1.1 freeqnap\n' > "$root/etc/hosts"
printf 'qnap-ts431xeu-debian-armhf\n' > "$root/etc/eyeq-platform"
printf 'Unconfigured FreeQNAP base. No application or site configuration.\n' > "$root/etc/freeqnap-build-status"
mkdir -p "$root/etc/freeqnap" "$root/usr/local/lib/freeqnap" "$root/usr/local/share/eyeq" \
 "$root/etc/ssh/sshd_config.d" "$root/etc/systemd/system/ssh.service.d" \
 "$root/etc/systemd/system/serial-getty@ttyS0.service.d" "$root/usr/lib/systemd/system-shutdown"
cp "$FREEQNAP_SOURCE/target/credentials.py" "$root/usr/local/lib/freeqnap/"
cp "$FREEQNAP_SOURCE/target/freeqnap-first-login.service" "$root/etc/systemd/system/"
cp "$FREEQNAP_SOURCE/target/credentials-dependency.conf" "$root/etc/systemd/system/ssh.service.d/20-credentials.conf"
cp "$FREEQNAP_SOURCE/target/credentials-dependency.conf" "$root/etc/systemd/system/serial-getty@ttyS0.service.d/20-credentials.conf"
cat > "$root/etc/ssh/sshd_config.d/00-freeqnap.conf" <<'CFG'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
CFG
cat > "$root/etc/systemd/network/10-freeqnap-wired.network" <<'CFG'
[Match]
Type=ether

[Network]
DHCP=yes
IPv6AcceptRA=yes

[DHCPv4]
UseHostname=no
CFG
printf '{"power":"poweroff","reset":"reboot"}\n' > "$root/etc/eyeq-buttons.json"
# networkd runs as systemd-network, so its root-owned profile must be readable.
chmod 755 "$root/etc/systemd/network"
chmod 644 "$root/etc/systemd/network/10-freeqnap-wired.network" "$root/etc/eyeq-platform"
chmod 644 "$root/etc/systemd/system/freeqnap-first-login.service" \
 "$root/etc/systemd/system/ssh.service.d/20-credentials.conf" \
 "$root/etc/systemd/system/serial-getty@ttyS0.service.d/20-credentials.conf"
for name in eyeq-hwctl.py eyeq-buttons.py eyeq-disk-leds.py; do
 cp "$FREEQNAP_BOARD_SOURCE/$name" "$root/usr/local/share/eyeq/$name"
done
cp "$FREEQNAP_BOARD_SOURCE/eyeq-raid-event" "$root/usr/local/sbin/eyeq-raid-event"
chmod 755 "$root/usr/local/sbin/eyeq-raid-event"
for name in eyeq-cooling.service eyeq-drive-green.service eyeq-buttons.service eyeq-disk-leds.service; do
 cp "$FREEQNAP_BOARD_SOURCE/$name" "$root/etc/systemd/system/$name"
 chmod 644 "$root/etc/systemd/system/$name"
done
for name in mcu-safe-full eyeq-poweroff; do
 arm-linux-gnueabihf-gcc -Os -s -static "$FREEQNAP_BOARD_SOURCE/$name.c" -o "$root/usr/local/sbin/$name"
done
mv "$root/usr/local/sbin/mcu-safe-full" "$root/usr/local/sbin/eyeq-mcu-safe-full"
mv "$root/usr/local/sbin/eyeq-poweroff" "$root/usr/lib/systemd/system-shutdown/eyeq-poweroff"
cd /build/linux-6.12.114
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- INSTALL_MOD_PATH="$root" modules_install
version=$(cat include/config/kernel.release)
cp "$FREEQNAP_OUTPUT/modules/"*.ko "$root/usr/lib/modules/$version/"
rm -f "$root/usr/lib/modules/$version/build" "$root/usr/lib/modules/$version/source"
chroot "$root" /usr/sbin/depmod -a "$version"
chroot "$root" /usr/bin/systemctl --root=/ disable docker.service docker.socket containerd.service
chroot "$root" /usr/bin/systemctl --root=/ enable ssh.service serial-getty@ttyS0.service systemd-networkd.service \
 freeqnap-first-login.service eyeq-cooling.service eyeq-drive-green.service eyeq-buttons.service eyeq-disk-leds.service
# The install ID, authorized key, boot records, array UUIDs and password marker
# are written only after binding a concrete plan to the actual NAS and disks.
[ ! -e "$root/etc/freeqnap-install-id" ]
[ ! -e "$root/root/.ssh/authorized_keys" ]
[ ! -e "$root/etc/ssh/ssh_host_ed25519_key" ]
if grep -r -l '192\.168\.77\|192\.168\.1\.185\|eyeq-ts431-bench' "$root/etc"; then
 echo 'STOP: development identity remains in base'; exit 1
fi
tar --numeric-owner --xattrs --acls -czf "$FREEQNAP_OUTPUT/debian-armhf-base.tar.gz" -C "$root" .
python3 "$FREEQNAP_SOURCE/audit-base.py" "$FREEQNAP_OUTPUT/debian-armhf-base.tar.gz"
sha256sum "$FREEQNAP_OUTPUT/debian-armhf-base.tar.gz"
