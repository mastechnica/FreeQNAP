#!/bin/sh
# Run in a pinned ARM cross-builder; no host mount is needed by this recipe.
set -eu
umask 077
: "${FREEQNAP_SOURCE:?Set the installer source directory}"
: "${FREEQNAP_OUTPUT:?Set a new output directory}"
: "${FREEQNAP_BOARD_SOURCE:?Set the reviewed board source directory}"
[ ! -e "$FREEQNAP_OUTPUT" ] || { echo 'Output already exists; choose a new generation'; exit 1; }
root=${FREEQNAP_INITRAMFS_ROOT:-/build/freeqnap-initramfs}
[ ! -e "$root" ] || { echo 'Build root already exists'; exit 1; }
cp -a /build/persistent-initramfs "$root"
mkdir -p "$root/freeqnap" "$root/etc/mdadm" "$FREEQNAP_OUTPUT/modules"
rm -f "$root/etc/mdadm/mdadm.conf"
cp "$FREEQNAP_SOURCE/target/init" "$root/init"
cp "$FREEQNAP_SOURCE/target/boot-record.sh" "$FREEQNAP_SOURCE/target/boot-policy.sh" "$FREEQNAP_SOURCE/target/select-root.sh" "$root/freeqnap/"
chmod 755 "$root/init" "$root/freeqnap/"*.sh
arm-linux-gnueabihf-gcc -Os -s -static -I"$FREEQNAP_BOARD_SOURCE" "$FREEQNAP_BOARD_SOURCE/restore-factory-macs.c" -o "$root/bin/eyeq-restore-factory-macs"
arm-linux-gnueabihf-gcc -Os -s -static "$FREEQNAP_SOURCE/target/read-mcu-identity.c" -o "$root/bin/freeqnap-read-mcu-identity"
# Add blkid with its ARM interpreter/library closure, without running ARM programs.
queue=/build/freeqnap-elf-queue; seen=/build/freeqnap-elf-seen
printf '%s\n' /usr/sbin/blkid /usr/bin/lsblk > "$queue"; : > "$seen"
while [ -s "$queue" ]; do
 item=$(head -n 1 "$queue"); sed '1d' "$queue" > "$queue.next"; mv "$queue.next" "$queue"
 grep -Fxq "$item" "$seen" && continue
 [ -f "/build/debian-rootfs$item" ]; mkdir -p "$root$(dirname "$item")"
 cp -L "/build/debian-rootfs$item" "$root$item"; printf '%s\n' "$item" >> "$seen"
 arm-linux-gnueabihf-readelf -l "/build/debian-rootfs$item" | sed -n 's/.*Requesting program interpreter: \([^]]*\)].*/\1/p' >> "$queue"
 for library in $(arm-linux-gnueabihf-readelf -d "/build/debian-rootfs$item" | sed -n 's/.*Shared library: \[\([^]]*\)\].*/\1/p'); do
  found=no
  for directory in /lib/arm-linux-gnueabihf /usr/lib/arm-linux-gnueabihf /lib /usr/lib; do
   if [ -f "/build/debian-rootfs$directory/$library" ]; then printf '%s\n' "$directory/$library" >> "$queue"; found=yes; break; fi
  done
  [ "$found" = yes ] || exit 1
 done
done
python3 "$FREEQNAP_SOURCE/audit-initramfs.py" "$root"
cd /build/linux-6.12.114
scripts/config --set-str LOCALVERSION '-eyeq-ts431xeu-freeqnap1' --set-str INITRAMFS_SOURCE "$root"
scripts/config --disable MD_AUTODETECT
scripts/config --enable USB_ACM --enable INITRAMFS_COMPRESSION_NONE --disable INITRAMFS_COMPRESSION_GZIP
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig
for key in KUSER_HELPERS COMPAT_32BIT_TIME ARM_APPENDED_DTB MD_RAID1 EXT4_FS USB_ACM; do grep -qx "CONFIG_$key=y" .config; done
grep -qx 'CONFIG_SATA_MOBILE_LPM_POLICY=1' .config
# Build dependency artifacts before embedding the matching external modules.
make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- zImage modules
for directory in /build/al_eth-standalone/src /build/al_thermal-standalone/src; do
 make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- M="$directory" modules
done
cp /build/al_eth-standalone/src/al_eth.ko /build/al_thermal-standalone/src/al_thermal.ko "$root/lib/modules/"
make -j4 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- zImage
cp "$root/lib/modules/"*.ko "$FREEQNAP_OUTPUT/modules/"
python3 "$FREEQNAP_SOURCE/audit-initramfs.py" --cpio usr/initramfs_data.cpio
cp arch/arm/boot/zImage "$FREEQNAP_OUTPUT/zImage"
cp arch/arm/boot/dts/amazon/alpine-qnap-ts431xeu.dtb "$FREEQNAP_OUTPUT/board.dtb"
cat "$FREEQNAP_OUTPUT/zImage" "$FREEQNAP_OUTPUT/board.dtb" > "$FREEQNAP_OUTPUT/zImage-dtb"
mkimage -A arm -O linux -T kernel -C none -a 0x8000 -e 0x8000 -n 'FreeQNAP generic bootstrap 0.1' -d "$FREEQNAP_OUTPUT/zImage-dtb" "$FREEQNAP_OUTPUT/uImage"
cp .config "$FREEQNAP_OUTPUT/kernel.config"
cp "$seen" "$FREEQNAP_OUTPUT/extra-elf-closure.txt"
