#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Install AlphaWRT into bank B (KernelB) of a FiberHome SR1041Y, in the stock
# bank format, and make the free bootbase boot it. Bank A (stock) is left as
# is apart from its two boot-flag volumes. See BANK-FORMAT.md.
#
# Run on a RAM-booted AlphaWRT:
#   sh install_bank_b.sh <kernel.trx> <root.squashfs> <flag-record>
# kernel.trx    the device's KERNEL image (tclinux trx, HDR2, LZMA)
# root.squashfs the rootfs
# flag-record   16-byte boot flag record (kernel=1 for bank B, kernel=0 for A)
#
# Bank B UBI after this:
#   vol 0 "ubi_kernel"  static   the kernel trx (the bootbase loads vol ID 0)
#   vol 1 "rootfs"      dynamic  squashfs (the kernel mounts it via ubiblock)
#   vol 2 "rootfs_data" dynamic  rest; UBIFS overlay, formatted on first mount
# functions.sh reads unset variables, so source it before set -u
. /lib/functions.sh
set -eu

KERNEL=$1 ROOTFS=$2 FLAG=$3

die() { echo "ERROR: $*" >&2; exit 1; }
size() { wc -c < "$1"; }

[ "$(board_name)" = "fiberhome,sr1041y" ] || die "not an SR1041Y"
A=$(find_mtd_index KernelA); B=$(find_mtd_index KernelB)
[ -n "$A" ] && [ -n "$B" ] || die "KernelA/KernelB partitions not found"
[ "$(head -c 4 "$KERNEL")" = "HDR2" ] || die "$KERNEL is not a tclinux trx"
[ "$(head -c 4 "$ROOTFS")" = "hsqs" ] || die "$ROOTFS is not squashfs"
[ "$(size "$FLAG")" = 16 ] || die "$FLAG is not a 16-byte flag record"
[ "$(size "$KERNEL")" -le $((42 * 126976)) ] || die "kernel larger than the 42 LEBs the bootbase reads"

detach_mtd() {
	local d
	for d in /sys/class/ubi/ubi[0-9]*; do
		[ -f "$d/mtd_num" ] || continue
		[ "$(cat "$d/mtd_num")" = "$1" ] && ubidetach -m "$1"
	done
	return 0
}

echo "== bank B: format mtd$B"
detach_mtd "$B"
ubiformat "/dev/mtd$B" -y -q
ubiattach -m "$B" -d 7 >/dev/null

echo "== bank B: write kernel ($(size "$KERNEL") bytes) and rootfs ($(size "$ROOTFS") bytes)"
ubimkvol /dev/ubi7 -n 0 -N ubi_kernel -t static -s "$(size "$KERNEL")" >/dev/null
ubiupdatevol /dev/ubi7_0 "$KERNEL"
ubimkvol /dev/ubi7 -n 1 -N rootfs -t dynamic -s "$(size "$ROOTFS")" >/dev/null
ubiupdatevol /dev/ubi7_1 "$ROOTFS"
ubimkvol /dev/ubi7 -n 2 -N rootfs_data -m >/dev/null

echo "== bank B: verify"
[ "$(sha256sum < /dev/ubi7_0)" = "$(sha256sum < "$KERNEL")" ] || die "kernel read-back mismatch"
[ "$(head -c "$(size "$ROOTFS")" /dev/ubi7_1 | sha256sum)" = "$(sha256sum < "$ROOTFS")" ] || die "rootfs read-back mismatch"
ubinfo -d 7 -a | grep -E "Volume ID|Name|Size|Type"
ubidetach -d 7

echo "== bank A: boot flags (vol 3 ubi_flagA, vol 4 ubi_flagB)"
detach_mtd "$A"
ubiattach -m "$A" -d 6 >/dev/null
[ "$(cat /sys/class/ubi/ubi6_3/name)" = "ubi_flagA" ] || { ubidetach -d 6; die "bank A vol 3 is not ubi_flagA"; }
[ "$(cat /sys/class/ubi/ubi6_4/name)" = "ubi_flagB" ] || { ubidetach -d 6; die "bank A vol 4 is not ubi_flagB"; }
ubiupdatevol /dev/ubi6_3 "$FLAG"
ubiupdatevol /dev/ubi6_4 "$FLAG"
[ "$(head -c 16 /dev/ubi6_3 | sha256sum)" = "$(sha256sum < "$FLAG")" ] || { ubidetach -d 6; die "flagA read-back mismatch"; }
ubidetach -d 6

echo "== done: the bootbase will boot bank $(head -c 1 "$FLAG" | hexdump -e '1/1 "%d"' | sed 's/0/A/;s/1/B/') next"
