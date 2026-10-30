#!/usr/bin/env python3
"""Loopback test: verify the adapter's own TX and RX work.
Jumper adapter TX directly to adapter RX (disconnect from the board first),
then run this. It writes a marker and checks it comes back.

Usage: python3 -I loopback.py [port]
"""
import glob, os, select, sys, termios, time

PORT = sys.argv[1] if len(sys.argv) > 1 else (sorted(glob.glob("/dev/cu.usbserial*")) or ["/dev/cu.usbserial-0001"])[0]
fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
os.set_blocking(fd, True)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)
termios.tcflush(fd, termios.TCIOFLUSH)

marker = b"ALPHAWRT-LOOPBACK-7528\r\n"
print(f"### {PORT} @115200: sending {marker!r}", flush=True)
os.write(fd, marker)
got = b""
end = time.time() + 2.0
while time.time() < end and marker.strip() not in got:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        got += os.read(fd, 256)

print(f"### received: {got!r}", flush=True)
if marker.strip() in got:
    print("### PASS — adapter TX and RX both work. Ready to drive the board.", flush=True)
else:
    print("### FAIL — nothing looped back. Check: TX<->RX jumper seated, right pins, "
          "adapter not faulty. (RX alone worked for reading, so TX or the jumper is the suspect.)", flush=True)
