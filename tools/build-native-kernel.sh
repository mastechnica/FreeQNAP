#!/bin/sh
# Build a separate RAM-only candidate from a reviewed prepared board tree.
# This is NOT the still-pending clean-source turnkey release builder.
set -eu
umask 077
project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
boot_source=${FREEQNAP_BOOTSTRAP_SOURCE:-$project/installer/target}
expected=${FREEQNAP_EXPECTED_KERNEL_VERSION:-6.12.114}
suffix=${FREEQNAP_LOCALVERSION:--eyeq-ts431xeu-freeqnap4}
depmod_command=${FREEQNAP_DEPMOD:-depmod}
case "$expected:$suffix" in 6.12.114:-eyeq-ts431xeu-freeqnap4|6.12.115:-eyeq-ts431xeu-freeqnap5) ;; *) echo "Unreviewed kernel/version combination";exit 1;; esac
command -v "$depmod_command" >/dev/null || { echo "Install kmod/depmod in the builder before compiling";exit 1; }
: "${FREEQNAP_KERNEL_SOURCE:?Reviewed prepared kernel tree required}"
: "${FREEQNAP_ETH_SOURCE:?Reviewed standalone Ethernet source required}"
: "${FREEQNAP_THERMAL_SOURCE:?Reviewed standalone thermal source required}"
: "${FREEQNAP_INITRAMFS_SOURCE:?Accepted generic initramfs root required}"
: "${FREEQNAP_KERNEL_BUILD:?New isolated build directory required}"
[ ! -e "$FREEQNAP_KERNEL_BUILD" ] || { echo 'Refusing existing build directory';exit 1; }
[ "$(make -s -C "$FREEQNAP_KERNEL_SOURCE" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- kernelversion)" = "$expected" ]
mkdir -p "$FREEQNAP_KERNEL_BUILD"
cp -a "$FREEQNAP_KERNEL_SOURCE" "$FREEQNAP_KERNEL_BUILD/kernel"
cp -a "$FREEQNAP_ETH_SOURCE" "$FREEQNAP_KERNEL_BUILD/ethernet"
cp -a "$FREEQNAP_THERMAL_SOURCE" "$FREEQNAP_KERNEL_BUILD/thermal"
cp -a "$FREEQNAP_INITRAMFS_SOURCE" "$FREEQNAP_KERNEL_BUILD/initramfs"
mkdir -p "$FREEQNAP_KERNEL_BUILD/output" "$FREEQNAP_KERNEL_BUILD/poweroff" "$FREEQNAP_KERNEL_BUILD/initramfs/freeqnap"
for file in boot-record.sh boot-policy.sh select-root.sh;do
 [ -f "$boot_source/$file" ];cp "$boot_source/$file" "$FREEQNAP_KERNEL_BUILD/initramfs/freeqnap/"
done
[ -f "$project/installer/audit-initramfs.py" ]
python3 "$project/installer/audit-initramfs.py" "$FREEQNAP_KERNEL_BUILD/initramfs"
[ -f "$project/hardware/ts431xeu/freeqnap-poweroff.c" ]
cp "$project/hardware/ts431xeu/freeqnap-poweroff.c" "$FREEQNAP_KERNEL_BUILD/poweroff/"
printf 'obj-m += freeqnap-poweroff.o\n' > "$FREEQNAP_KERNEL_BUILD/poweroff/Makefile"
# Reject the earlier unaccepted noncoherent DMA experiment before compilation.
[ "$(sha256sum "$FREEQNAP_KERNEL_BUILD/kernel/arch/arm/boot/dts/amazon/alpine-qnap-ts431xeu.dts" | cut -d ' ' -f 1)" = 613b1df6b4fb5da3342e45a58848ac686f6b43b07aabeeb500460dd3c5e4d63e ]
cd "$FREEQNAP_KERNEL_BUILD/kernel"
scripts/config --enable TUN --enable WIREGUARD --enable BLK_DEV --module BLK_DEV_LOOP --module NFT_LIMIT --module FUSE_FS --module CRYPTO_USER_API_SKCIPHER --module DM_ZERO --set-val BLK_DEV_LOOP_MIN_COUNT 0
scripts/config --set-str LOCALVERSION "$suffix" --disable LOCALVERSION_AUTO --set-str INITRAMFS_SOURCE "$FREEQNAP_KERNEL_BUILD/initramfs"
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig
for feature in TUN WIREGUARD DST_CACHE GRO_CELLS NF_TABLES NFT_CT NFT_NAT NFT_MASQ;do grep -qx "CONFIG_$feature=y" .config;done
make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- zImage amazon/alpine-qnap-ts431xeu.dtb modules
for source in "$FREEQNAP_KERNEL_BUILD/ethernet/src" "$FREEQNAP_KERNEL_BUILD/thermal/src";do
 make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- M="$source" modules
done
make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- M="$FREEQNAP_KERNEL_BUILD/poweroff" modules
cp "$FREEQNAP_KERNEL_BUILD/ethernet/src/al_eth.ko" "$FREEQNAP_KERNEL_BUILD/thermal/src/al_thermal.ko" "$FREEQNAP_KERNEL_BUILD/initramfs/lib/modules/"
make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- zImage
python3 "$project/installer/audit-initramfs.py" --cpio usr/initramfs_data.cpio
output=$FREEQNAP_KERNEL_BUILD/output
cp arch/arm/boot/zImage "$output/zImage"
cp arch/arm/boot/dts/amazon/alpine-qnap-ts431xeu.dtb "$output/board.dtb"
cat "$output/zImage" "$output/board.dtb" > "$output/zImage-dtb"
mkimage -A arm -O linux -T kernel -C none -a 0x8000 -e 0x8000 -n "FreeQNAP $expected RAM candidate" -d "$output/zImage-dtb" "$output/uImage"
cp .config "$output/kernel.config"
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- INSTALL_MOD_PATH="$output/modules-root" DEPMOD="$depmod_command" modules_install
version=$(cat include/config/kernel.release)
mkdir -p "$output/modules-root/lib/modules/$version/extra"
cp "$FREEQNAP_KERNEL_BUILD/initramfs/lib/modules/"*.ko "$output/modules-root/lib/modules/$version/extra/"
mkdir -p "$output/modules-root/lib/modules/$version/updates/freeqnap"
cp "$FREEQNAP_KERNEL_BUILD/poweroff/freeqnap-poweroff.ko" "$output/modules-root/lib/modules/$version/updates/freeqnap/freeqnap_poweroff.ko"
"$depmod_command" -ae -F System.map -b "$output/modules-root" "$version"
python3 - "$output" "$version" <<'MANIFEST'
from pathlib import Path
import hashlib,json,sys,zlib
root=Path(sys.argv[1]);files={}
for name in ('uImage','zImage','board.dtb','kernel.config'):
 data=(root/name).read_bytes();files[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 if name=='uImage':files[name]['crc32']=f'{zlib.crc32(data):08x}'
manifest={'schema':1,'model':'TS-431XeU','architecture':'armhf','kernel_release':sys.argv[2],'ram_only':True,'flash_allowed':False,'root_survivor_physical_boot_accepted':False,'artifacts':files,'review':'Uninstalled RAM-only candidate. Exact internal SATA discovery and one-member RAID1 policy have source/owned-loop tests; physical boot and full hardware regression remain required.'}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
MANIFEST
sha256sum "$output/uImage" "$output/zImage" "$output/board.dtb" "$output/kernel.config" > "$output/SHA256SUMS"
printf 'CANDIDATE ONLY: RAM boot + physical hardware regression required before flash installation.\n'
