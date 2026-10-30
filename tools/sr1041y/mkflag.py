#!/usr/bin/env python3
"""Build SR1041Y boot flag records and check a kernel trx before flashing.

  python3 mkflag.py flags <outdir>      writes flag-bankA.bin and flag-bankB.bin
  python3 mkflag.py check <kernel.trx>  verifies the trx header CRC

Flag record (16 bytes, read by the free bootbase from bank A UBI vols 3/4):
  byte 0 kernel bank (0 = A, 1 = B), byte 1 rootfs, byte 2 app, bytes 3-11 zero,
  bytes 12-15 JAMCRC (inverted CRC-32) of bytes 0-11, big-endian.
The all-zero record gives 0x842a3990, the value found on stock units.
"""
import os, struct, sys, zlib


def jamcrc(b):
    return zlib.crc32(b) ^ 0xFFFFFFFF


def record(bank):
    body = bytes([bank, 0, 0]) + bytes(9)
    return body + struct.pack(">I", jamcrc(body))


if sys.argv[1] == "flags":
    assert record(0)[12:] == bytes.fromhex("842a3990"), "formula no longer matches stock"
    for bank, name in ((0, "A"), (1, "B")):
        p = os.path.join(sys.argv[2], f"flag-bank{name}.bin")
        open(p, "wb").write(record(bank))
        print(p, record(bank).hex(" "))
elif sys.argv[1] == "check":
    d = open(sys.argv[2], "rb").read()
    total, crc = struct.unpack_from("<II", d, 8)
    calc = jamcrc(d[0x100:total])
    print(f"magic {d[:4]!r}  total {total}  file {len(d)}  crc {crc:#010x}  calc {calc:#010x}")
    sys.exit(0 if (d[:4] in (b"HDR0", b"HDR2") and total == len(d) and crc == calc) else 1)
