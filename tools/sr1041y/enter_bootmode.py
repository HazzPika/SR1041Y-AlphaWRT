#!/usr/bin/env python3
"""Catch the EcoNet bootbase 'enter boot command mode' window and press keys,
to (a) find which XP1 pin is the board RX and (b) drop into the bootloader shell.

Reads board TX continuously; when it sees the boot-command prompt it spams Enter
for the countdown. Does NOT touch the earlier 'bootloader upgrade' prompt.

Wiring: adapter RX -> board TX (pin 2), adapter GND -> header GND,
        adapter TX -> a CANDIDATE board-RX pin (try the non-GND, non-TX pins).
ADAPTER MUST BE SET TO 3.3V before connecting TX.

Usage: python3 -I enter_bootmode.py [port] [seconds]
Power-cycle the board right after starting.
"""
import glob, os, select, sys, termios, time

PORT = sys.argv[1] if len(sys.argv) > 1 else (sorted(glob.glob("/dev/cu.usbserial*")) or ["/dev/cu.usbserial-0001"])[0]
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 30

fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
os.set_blocking(fd, True)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)

print(f"### {PORT} @115200 for {SECS:.0f}s — POWER-CYCLE THE BOARD NOW", flush=True)
buf = b""
end = time.time() + SECS
armed = False          # True once we've seen the boot-command prompt
spam_until = 0
got_prompt = False
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.05)
    if r:
        d = os.read(fd, 4096)
        sys.stdout.buffer.write(d); sys.stdout.flush()
        buf = (buf + d)[-512:]
        if (b"boot command mode" in buf or b"enter boot command" in buf) and not armed:
            armed = True
            spam_until = time.time() + 4.0        # cover the 3 s countdown
            print("\n### >>> boot-command prompt seen: sending keys <<<", flush=True)
        # a bootbase shell prompt usually ends in '>' or '#'
        tail = buf.rstrip()
        if armed and tail.endswith((b">", b"#", b"$")) and b"secs" not in buf[-40:]:
            got_prompt = True
            break
    if armed and time.time() < spam_until:
        os.write(fd, b"\r")                       # Enter; avoids typing stray chars into a shell
        time.sleep(0.05)

if got_prompt:
    print(f"\n### SHELL PROMPT DETECTED — this candidate pin IS the board RX. Prompt tail: {buf.rstrip()[-20:]!r}", flush=True)
    # gentle nudge to show the prompt clearly
    os.write(fd, b"\r")
    time.sleep(0.5)
    r, _, _ = select.select([fd], [], [], 1.0)
    if r:
        sys.stdout.buffer.write(os.read(fd, 4096)); sys.stdout.flush()
else:
    print("\n### no shell prompt. Either wrong RX pin (move adapter TX to the next candidate) "
          "or the keypresses didn't register. Keep RX on pin 2, GND on header GND.", flush=True)
