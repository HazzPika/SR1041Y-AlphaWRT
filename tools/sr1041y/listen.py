#!/usr/bin/env python3
"""Passive, read-only UART listener. Sends NOTHING to the board: safe for
probing which XP1 pad is the board's TX. Prints whatever arrives.

Usage: python3 -I listen.py [port] [baud] [seconds]
Defaults: first /dev/cu.usbserial*, 115200, 20 s.
"""
import fcntl, glob, os, select, struct, sys, termios, time

BAUDS = {9600: termios.B9600, 19200: termios.B19200, 38400: termios.B38400,
         57600: termios.B57600, 115200: termios.B115200, 230400: termios.B230400}
IOSSIOSPEED = 0x80045402   # macOS ioctl to set an arbitrary (non-standard) baud
port = sys.argv[1] if len(sys.argv) > 1 else (sorted(glob.glob("/dev/cu.usbserial*")) or ["/dev/cu.usbserial-0001"])[0]
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 20

fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
os.set_blocking(fd, True)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = BAUDS.get(baud, termios.B115200)
termios.tcsetattr(fd, termios.TCSANOW, a)
if baud not in BAUDS:                          # arbitrary speed (e.g. 921600, 500000) on macOS
    fcntl.ioctl(fd, IOSSIOSPEED, struct.pack("I", baud))

print(f"### listening (read-only) on {port} @ {baud} for {secs:.0f}s — power-cycle the board now\n", flush=True)
end = time.time() + secs
total = 0
_CAP = bytearray()
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.5)
    if r:
        d = os.read(fd, 4096)
        total += len(d)
        _CAP.extend(d)
        sys.stdout.buffer.write(d); sys.stdout.flush()
print(f"\n### done. {total} bytes received.", flush=True)
if total == 0:
    print("### nothing: this pad is not board-TX (or wrong baud/GND). Move RX to the next XP1 pin.", flush=True)
else:
    data = bytes(_CAP)
    printable = sum(1 for b in data if 9 <= b <= 13 or 32 <= b <= 126)
    print(f"### printable/ASCII ratio: {printable}/{len(data)} = {printable/len(data):.0%} "
          f"(clean text ≈ 95%+).", flush=True)
    print(f"### hex of first 64 bytes: {data[:64].hex(' ')}", flush=True)
    # byte histogram top entries: a correct baud leaks lots of 0x0d/0x0a/space/ASCII
    from collections import Counter
    top = Counter(data).most_common(8)
    print("### most common bytes: " + ", ".join(f"0x{b:02x}×{n}" for b, n in top), flush=True)
