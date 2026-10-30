# FiberHome SR1041Y: flash bank format (stock "free bootbase")

Derived from a full stock flash dump and the bootbase binary (2026-10-30).
Every value below was checked against the dump, not assumed.

## Bootbase
- Stored LZMA-compressed in `boot` (mtd0) at offset 0x20000; decompresses to
  228448 bytes, load address **0x83fb0000** (consistent with a crash EPC of
  0x83fbb468 seen during an XMODEM test).
- Banner: `EN7528 at 2021-09-28 ... version 1.1 free bootbase`.
- Shell `bldr>` after "Press any key in 3 secs to enter boot command mode".
  Addresses/lengths are **bare hex** (`xmdm 80020000 7a0000`); a `0x` prefix
  parses as 0 and crashes the bootbase.

## Banks
`KernelA` (0x0200000, 40 MiB) and `KernelB` (0x2a00000, 40 MiB) each hold one
UBI device (stock passes `ubi.mtd=1 ubi.mtd=2`). Volumes per bank:

| volume       | type    | content |
|--------------|---------|---------|
| `ubi_kernel` | static  | tclinux trx: 256-byte header + LZMA kernel |
| `ubi_rootfs` | static  | squashfs |
| `ubi_fhapp`  | static  | squashfs (FiberHome apps) |
| `ubi_flagA`  | dynamic | boot flag record (below) |
| `ubi_flagB`  | dynamic | boot flag record, redundant copy |

Both stock banks are byte-identical.

## Kernel volume header (stock)
| off  | value | meaning |
|------|-------|---------|
| 0x00 | `HDR0` | magic (stock). The bootbase code also builds `HDR2` (0x32524448 LE), the magic OpenWrt's `tclinux-trx.sh` writes |
| 0x04 | 0x100 (LE) | header length |
| 0x08 | total length (LE) | = volume data size |
| 0x0c | CRC (LE) | **JAMCRC (inverted CRC-32) of bytes [0x100, total)** — verified |
| 0x10 | `7.3.251.550_v027\n` | version |
| 0x30 | `\n` | customer version |
| 0x50 | kernel length (LE) | total - 0x100 |
| 0x54 | 0 | rootfs length (rootfs is its own volume) |
| 0x5c | `3 6035 122 0\n` | model string |
| 0x7c | 0x80002000 (LE) | load address (free bootbase) |

## Boot flag record (`ubi_flagA` / `ubi_flagB`)
16 bytes: byte 0 = kernel bank (0 = A, 1 = B), byte 1 = rootfs, byte 2 = app,
bytes 3-11 = 0, bytes 12-15 = **JAMCRC of bytes 0-11, big-endian**. Verified:
the all-zero record gives 0x842a3990, the value stored on stock units; the
bank-B record is `01 00 … 00 1f 8f 75 ff`. Bootbase messages:
`get boot flag from flag A/B Error`, `ERR: boot flag crc Error!`.

## How the bootbase picks a bank (from its disassembly)
- It scans bank A's UBI with its own minimal scanner (PEB 0x10-0x14f; bank B
  is PEB 0x150-0x28f) and reads the flag record from **bank A only**:
  volume ID 3, then volume ID 4 if that fails. A bad record CRC means all
  flags 0 (bank A).
- Volumes are found **by ID, not name**: kernel = ID 0 (at most 42 LEBs),
  flags = IDs 3/4, plus the layout volume. Bank B needs only ID 0.
- Kernel byte 1: load bank B's ID 0 to 0x819fff00 and check its CRC; on a CRC
  error, fall back to bank A. Kernel byte 0: the same with A first, B as
  fallback. Both bad: hang.
- The kernel CRC check (`fh_check_kernel_crc`) reads `total length` (0x08) and
  `crc` (0x0c) from the 256-byte header and compares the CRC-32 without final
  XOR (JAMCRC) of `length - 0x100` payload bytes. **The magic is not checked**:
  `HDR0` (stock) and `HDR2` (OpenWrt's `tclinux-trx.sh`) both boot.
- The LZMA payload is decompressed to 0x80002000; the flag record is copied to
  0x80001000 for the kernel.
- `bootflag_set` at `bldr>` erases and writes 0x1a0 bytes at flash 0x80000 (a
  separate "platform flag" area); the UBI record overrides it, so it does not
  pick the bank. `flag_reset` and `flag_get` are empty stubs.

A kernel that boots but then hangs is not caught by the CRC fallback: recover
with the UART (RAM boot, then select bank A).

## Bootbase web upload (`httpd` at `bldr>`)
Accepts a FiberHome "multi image" package and writes it to flash. The package
header is verified for `hwcfg` (SR1041Y = 0x10001003), `cpu_type`,
`product_type`, `crc_head` and `crc_data`. Format not yet reconstructed; this
is the most user-friendly install path once it is.

## AlphaWRT in bank B (tested)
| Vol ID | Name | Type | Content |
|---|---|---|---|
| 0 | `ubi_kernel` | static | kernel trx (HDR2, LZMA, load 0x80002000) |
| 1 | `rootfs` | dynamic | squashfs; the kernel mounts it via ubiblock |
| 2 | `rootfs_data` | dynamic | UBIFS overlay |
| 127 | `provisioning` | dynamic | created by OpenWrt's `nand.sh` |

`KernelB` has `compatible = "linux,ubi"`, so the kernel attaches it at boot;
OpenWrt's ubiblock patches mount `rootfs`. The kernel takes its command line
from the DTB only (`CONFIG_MIPS_CMDLINE_FROM_DTB`), so the bootbase's
`ubi.mtd=1 ubi.mtd=2` never attaches bank A.
