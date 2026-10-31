#!/bin/sh
# Matching upstream optional module; no flash or target installation.
set -eu
umask 077
: "${FREEQNAP_KERNEL_SOURCE:?Prepared accepted kernel tree required}"
: "${FREEQNAP_MODULE_OUTPUT:?New output directory required}"
[ ! -e "$FREEQNAP_MODULE_OUTPUT" ] || { echo 'Refusing existing output';exit 1; }
[ "$(make -s -C "$FREEQNAP_KERNEL_SOURCE" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- kernelversion)" = 6.12.114 ]
case ${1:-} in
 freeqnap_poweroff) source=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/hardware/ts431xeu/freeqnap-poweroff.c;module=freeqnap_poweroff;;
 nft_limit) source=net/netfilter/nft_limit.c;module=nft_limit;;
 tun) source=drivers/net/tun.c;module=tun;;
 algif_skcipher) source=crypto/algif_skcipher.c;module=algif_skcipher;;
 dm-zero) source=drivers/md/dm-zero.c;module=dm-zero;;
 loop) source=drivers/block/loop.c;module=loop;;
 fuse) source=fs/fuse;module=fuse;;
 *) echo 'Choose nft_limit, tun, fuse, algif_skcipher, dm-zero, loop or freeqnap_poweroff';exit 1;;
esac
mkdir -p "$FREEQNAP_MODULE_OUTPUT"
if [ "$module" = fuse ];then
 cp -R "$FREEQNAP_KERNEL_SOURCE/$source/." "$FREEQNAP_MODULE_OUTPUT/"
 sed 's/obj-$(CONFIG_FUSE_FS)/obj-m/' "$FREEQNAP_MODULE_OUTPUT/Makefile" > "$FREEQNAP_MODULE_OUTPUT/Makefile.next"
 mv "$FREEQNAP_MODULE_OUTPUT/Makefile.next" "$FREEQNAP_MODULE_OUTPUT/Makefile"
else
 if [ "$module" = freeqnap_poweroff ];then cp "$source" "$FREEQNAP_MODULE_OUTPUT/";mv "$FREEQNAP_MODULE_OUTPUT/freeqnap-poweroff.c" "$FREEQNAP_MODULE_OUTPUT/freeqnap_poweroff.c";else cp "$FREEQNAP_KERNEL_SOURCE/$source" "$FREEQNAP_MODULE_OUTPUT/";fi
printf 'obj-m := %s.o\n' "$module" > "$FREEQNAP_MODULE_OUTPUT/Makefile"
 if [ "$module" = loop ];then printf 'ccflags-y := -DCONFIG_BLK_DEV_LOOP_MIN_COUNT=8\n' >> "$FREEQNAP_MODULE_OUTPUT/Makefile";fi
fi
make -C "$FREEQNAP_KERNEL_SOURCE" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- M="$FREEQNAP_MODULE_OUTPUT" modules
sha256sum "$FREEQNAP_MODULE_OUTPUT/$module.ko"
printf 'Check exact target vermagic before installing; do not force unresolved modules.\n'
