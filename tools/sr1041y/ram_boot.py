#!/usr/bin/env python3
"""RAM-boot an OpenWrt initramfs on the SR1041Y via the EcoNet 'free bootbase'.
ZERO flash writes: loads the image to RAM and jumps to it. A power-cycle undoes it.

Sequence: catch "boot command mode" -> enter bldr> -> `xmdm <addr> <len>` ->
XMODEM-send the image -> `jump <addr>` -> print the boot output.

Usage: python3 -I ram_boot.py <image.bin> [port] [loadaddr_hex]
Defaults: port = first /dev/cu.usbserial*, loadaddr = 0x80020000 (CONFIG_ZBOOT_LOAD_ADDRESS).
Power-cycle the board right after starting.
"""
import glob, os, select, sys, termios, time

IMG = sys.argv[1]
PORT = sys.argv[2] if len(sys.argv) > 2 else (sorted(glob.glob("/dev/cu.usbserial*")) or ["/dev/cu.usbserial-0001"])[0]
LOAD = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x80020000

SOH, STX, EOT, ACK, NAK, CAN, CRCCHR = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, 0x43
data = open(IMG, "rb").read()
LEN = len(data)

fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
os.set_blocking(fd, True)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)


def rd(t):
    r, _, _ = select.select([fd], [], [], t)
    return os.read(fd, 4096) if r else b""


def rd1(t):
    r, _, _ = select.select([fd], [], [], t)
    return os.read(fd, 1) if r else b""


def log(m):
    print(m, flush=True)


def crc16(b):
    c = 0
    for ch in b:
        c ^= ch << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if (c & 0x8000) else (c << 1) & 0xFFFF
    return c


# --- 1. enter boot command mode -------------------------------------------
log(f"### {PORT} @115200 — POWER-CYCLE THE BOARD NOW (image {LEN} bytes -> {LOAD:#x})")
buf = b""
end = time.time() + 120
armed = False
spam_until = 0
at_prompt = False
while time.time() < end:
    d = rd(0.05)
    if d:
        sys.stdout.buffer.write(d); sys.stdout.flush()
        buf = (buf + d)[-512:]
        if (b"boot command mode" in buf) and not armed:
            armed = True; spam_until = time.time() + 4
            log("\n### boot-command prompt seen: tapping Enter")
        if armed and buf.rstrip().endswith(b"bldr>"):
            at_prompt = True; break
    if armed and time.time() < spam_until:
        os.write(fd, b"\r"); time.sleep(0.05)
if not at_prompt:
    sys.exit("### never reached bldr>. Check RX wiring / power-cycle timing.")
log("\n### at bldr> — starting xmdm")

# --- 2. issue xmdm and wait for the receiver handshake --------------------
rd(0.3)
os.write(fd, f"xmdm {LOAD:x} {LEN:x}\r".encode())   # bare hex (no 0x), else addr parses as 0 -> crash
crc = None
end = time.time() + 30
while time.time() < end:
    c = rd1(0.5)
    if not c:
        continue
    b = c[0]
    if b == CRCCHR:   # 'C'
        crc = True; break
    if b == NAK:
        crc = False; break
if crc is None:
    sys.exit("\n### receiver never sent C/NAK after xmdm. Check the command/args.")
log(f"\n### receiver ready ({'CRC' if crc else 'checksum'} mode) — sending {LEN} bytes...")


def wait_ack(timeout):
    """Return ACK/NAK/CAN control byte, skipping stray 'C'/noise, or None on timeout."""
    end = time.time() + timeout
    while time.time() < end:
        c = rd1(end - time.time())
        if not c:
            return None
        b = c[0]
        if b == CAN:
            # XMODEM cancels with CAN CAN; a lone 0x18 is line noise -> resend
            c2 = rd1(1.0)
            if c2 and c2[0] in (CAN, ACK):
                return c2[0]
            return NAK
        if b in (ACK, NAK):
            return b
        # ignore CRCCHR ('C') and any other noise
    return None


# --- 3. XMODEM send (128-byte blocks) -------------------------------------
BLK = 128
nblocks = (LEN + BLK - 1) // BLK
termios.tcflush(fd, termios.TCIFLUSH)      # drop the queued 'C's before block 1
t0 = time.time()
for i in range(nblocks):
    chunk = data[i * BLK:(i + 1) * BLK]
    if len(chunk) < BLK:
        chunk += b"\x1a" * (BLK - len(chunk))
    n = (i + 1) & 0xFF
    hdr = bytes([SOH, n, 0xFF - n])
    trailer = (crc16(chunk).to_bytes(2, "big") if crc else bytes([sum(chunk) & 0xFF]))
    pkt = hdr + chunk + trailer
    termios.tcflush(fd, termios.TCIFLUSH)   # drop stale/duplicate ACKs from prev block
    for attempt in range(10):
        os.write(fd, pkt)
        b = wait_ack(2.0)
        if b == ACK:
            break
        if b == CAN:
            sys.exit("\n### receiver CANcelled transfer")
        # NAK or timeout -> resend
    else:
        sys.exit(f"\n### block {i+1}/{nblocks} failed after retries")
    if (i + 1) % 500 == 0 or i + 1 == nblocks:
        pct = (i + 1) * 100 // nblocks
        rate = (i + 1) * BLK / max(time.time() - t0, 0.1) / 1024
        log(f"### {i+1}/{nblocks} blocks ({pct}%)  {rate:.1f} KiB/s")
# EOT
for _ in range(5):
    os.write(fd, bytes([EOT]))
    r = rd1(2.0)
    if r and r[0] == ACK:
        break
log(f"### transfer done in {time.time()-t0:.0f}s")

# --- 4. jump -------------------------------------------------------------
rd(1.0)
# Bootbase drops chars right after XMODEM: wait for a clean prompt, type slowly,
# verify the echo, and only then press Enter (a truncated jump crashed v3 once).
cmd = f"jump {LOAD:x}"
for attempt in range(5):
    os.write(fd, b"\r")
    p = b""
    end = time.time() + 3
    while time.time() < end and not p.rstrip().endswith(b"bldr>"):
        p += rd(0.2)
    echo = b""
    for ch in cmd.encode():
        os.write(fd, bytes([ch]))
        time.sleep(0.05)
        echo += rd(0.05)
    echo += rd(0.3)
    if cmd.encode() in echo:
        break
    log(f"\n### echo mismatch ({echo!r}); clearing line, retry")
    os.write(fd, b"\x08" * (len(cmd) + 4))   # backspace out the partial line
    rd(0.3)
else:
    sys.exit("\n### could not type the jump command cleanly; image is still in RAM — type it by hand")
log(f"\n### {cmd}")
os.write(fd, b"\r")
# --- 5. watch the boot ---------------------------------------------------
end = time.time() + 60
while time.time() < end:
    d = rd(0.5)
    if d:
        sys.stdout.buffer.write(d); sys.stdout.flush()
log("\n### (listen window ended)")
