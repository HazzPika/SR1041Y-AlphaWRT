#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Select the bank the SR1041Y free bootbase boots next, by rewriting the boot
# flag record in bank A's UBI volumes 3 (ubi_flagA) and 4 (ubi_flagB).
#   sh set_bank.sh <flag-record>      (from mkflag.py: bank A = stock, B = AlphaWRT)
# The bootbase falls back to the other bank by itself if the chosen kernel's
# CRC is wrong, but not if that kernel boots and then hangs.
# functions.sh reads unset variables, so source it before set -u
. /lib/functions.sh
set -eu
FLAG=$1
[ "$(board_name)" = "fiberhome,sr1041y" ] || { echo "not an SR1041Y" >&2; exit 1; }
[ "$(wc -c < "$FLAG")" = 16 ] || { echo "$FLAG is not a 16-byte flag record" >&2; exit 1; }
A=$(find_mtd_index KernelA)

for d in /sys/class/ubi/ubi[0-9]*; do
	[ -f "$d/mtd_num" ] && [ "$(cat "$d/mtd_num")" = "$A" ] && ubidetach -m "$A"
done
ubiattach -m "$A" -d 6 >/dev/null
trap 'ubidetach -d 6 >/dev/null 2>&1' EXIT
[ "$(cat /sys/class/ubi/ubi6_3/name)" = "ubi_flagA" ] || { echo "vol 3 is not ubi_flagA" >&2; exit 1; }
[ "$(cat /sys/class/ubi/ubi6_4/name)" = "ubi_flagB" ] || { echo "vol 4 is not ubi_flagB" >&2; exit 1; }
ubiupdatevol /dev/ubi6_3 "$FLAG"
ubiupdatevol /dev/ubi6_4 "$FLAG"
[ "$(head -c 16 /dev/ubi6_3 | sha256sum)" = "$(sha256sum < "$FLAG")" ] || { echo "read-back mismatch" >&2; exit 1; }
echo "next boot: bank $(head -c 1 "$FLAG" | hexdump -e '1/1 "%d"' | sed 's/0/A/;s/1/B/')"
