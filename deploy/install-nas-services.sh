#!/bin/sh
# Provision already installed native NAS dependencies. No pool/share is created.
set -eu
[ "$(id -u)" = 0 ]
[ "$(tr '\000' '\n' < /proc/device-tree/compatible | head -n 1)" = qnap,ts-431xeu ]
base=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Disable only unprivileged BPF; preserve privileged firewall/VPN use.
python3 "$base/deploy/configure-hardening.py" --apply
for command in smbd testparm netatalk ganesha.nfsd cryptsetup restic gpg tdbbackup gerbera ffprobe mdadm sfdisk sgdisk partx blockdev findmnt lsblk wipefs udevadm nft openvpn wg wireguard-go aria2c sg_sync dnsmasq networkctl;do
 command -v "$command" >/dev/null || { echo "Missing NAS dependency: $command";exit 1; }
done
python3 -c 'import ctypes.util; assert ctypes.util.find_library("archive"), "Install libarchive13t64 for archive extraction"'
mask_stock_unit() {
 unit=$1
 [ "$(readlink "/etc/systemd/system/$unit" 2>/dev/null || true)" = /dev/null ] && return 0
 systemctl disable --now "$unit" 2>/dev/null || true
 systemctl mask "$unit"
}
for unit in smbd nmbd netatalk nfs-ganesha gerbera avahi-daemon;do
 mask_stock_unit "$unit.service"
done
# The accepted kernel serves NFS through Ganesha, without kernel NFS client plumbing.
for unit in nfs-client.target run-rpc_pipefs.mount rpc-gssd.service rpcbind.service rpcbind.socket;do
 mask_stock_unit "$unit"
done
modinfo nft_limit >/dev/null || { echo 'Install the matching nft_limit module for the private-LAN firewall first';exit 1; }
modprobe nft_limit
printf '%s\n' nft_limit > /etc/modules-load.d/freeqnap-firewall.conf
modinfo tun >/dev/null || { echo 'Install a matching persistent TUN driver or use the tested native VPN kernel first';exit 1; }
getent group dnsmasq >/dev/null || groupadd --system dnsmasq
getent passwd dnsmasq >/dev/null || useradd --gid dnsmasq --system --home-dir /var/lib/freeqnap-dhcp --shell /usr/sbin/nologin dnsmasq
install -d -m 750 -o root -g dnsmasq /etc/freeqnap-dhcp
# Optional DDNS updates run as a separate account through fixed transient units.
if command -v ddclient >/dev/null;then
 systemctl mask --now ddclient.service
 getent passwd freeqnap-ddns >/dev/null || useradd --system --user-group --home-dir /var/lib/freeqnap-ddns --no-create-home --shell /usr/sbin/nologin freeqnap-ddns
 install -d -m 700 -o freeqnap-ddns -g freeqnap-ddns /var/lib/freeqnap-ddns
fi
getent passwd freeqnap-downloads >/dev/null || useradd --system --home-dir /var/lib/freeqnap-downloads --shell /usr/sbin/nologin freeqnap-downloads
install -d -m 755 /srv/freeqnap/download-work
install -d -m 750 -o root -g freeqnap /etc/freeqnap /run/freeqnap
install -d -m 755 /srv/freeqnap /srv/freeqnap/volumes /etc/avahi/services
install -d -m 700 /var/lib/freeqnap-system
install -d -m 700 -o gerbera -g gerbera /var/lib/freeqnap-media
cat > /etc/freeqnap/avahi-daemon.conf <<'CFG'
[server]
allow-interfaces=enp0s1
use-ipv4=yes
use-ipv6=yes
[wide-area]
enable-wide-area=no
[publish]
publish-addresses=yes
publish-workstation=no
[reflector]
enable-reflector=no
CFG
chmod 644 /etc/freeqnap/avahi-daemon.conf
for file in "$base"/deploy/freeqnap-broker.service "$base"/deploy/freeqnap-smb.service "$base"/deploy/freeqnap-nfs.service "$base"/deploy/freeqnap-afp.service "$base"/deploy/freeqnap-dlna.service "$base"/deploy/freeqnap-discovery.service "$base"/deploy/freeqnap-vpn-firewall.service "$base"/deploy/freeqnap-vpn.service "$base"/deploy/freeqnap-downloads.service "$base"/deploy/freeqnap-network.service "$base"/deploy/freeqnap-dhcp.service;do
 install -m 644 "$file" /etc/systemd/system/
done
# LAN1 is the default uplink. Disconnected optional ports must not fail network-online.
install -d -m 755 /etc/systemd/system/systemd-networkd-wait-online.service.d
cat > /etc/systemd/system/systemd-networkd-wait-online.service.d/freeqnap.conf <<'CFG'
[Service]
ExecStart=
ExecStart=/usr/lib/systemd/systemd-networkd-wait-online --any --ipv4 --timeout=30
CFG
# Fail closed at boot if the early VPN firewall cannot load.
install -d -m 755 /etc/systemd/system/systemd-networkd.service.d
cat > /etc/systemd/system/systemd-networkd.service.d/freeqnap-vpn.conf <<'CFG'
[Unit]
Requires=freeqnap-vpn-firewall.service
After=freeqnap-vpn-firewall.service
Requires=freeqnap-network.service
After=freeqnap-network.service
CFG
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/freeqnap-broker.service /etc/systemd/system/freeqnap-smb.service /etc/systemd/system/freeqnap-nfs.service /etc/systemd/system/freeqnap-afp.service /etc/systemd/system/freeqnap-dlna.service /etc/systemd/system/freeqnap-discovery.service
systemctl enable --now freeqnap-vpn-firewall.service freeqnap-vpn.service freeqnap-network.service
sh "$base/deploy/install-usb-pcie.sh"
systemctl enable --now freeqnap-broker.service freeqnap-discovery.service
if [ -f /opt/freeqnap/current/freeqnap/cooling.py ];then sh "$base/deploy/install-cooling.sh";fi
if [ -f "$base/tools/configure-smartd.py" ];then python3 "$base/tools/configure-smartd.py" --apply;fi
printf 'Native broker configured. No data pool, user, share or media library was created.\n'
