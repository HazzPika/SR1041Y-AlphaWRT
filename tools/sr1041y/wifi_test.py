#!/usr/bin/env python3
"""Load mt7915e on a RAM-booted SR1041Y over the serial console and record
everything, to find why the Wi-Fi driver resets/hangs the EN7528.

Usage: python3 -I wifi_test.py [--no-hif2] [port]
  --no-hif2  remove the second PCIe link (0000:01:00.0) before loading
Writes wifi_test[_nohif2].log next to this script and prints its tail.
"""
import os, select, sys, termios, time

no_hif2 = "--no-hif2" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
port = args[0] if args else "/dev/cu.usbserial-0001"
log = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "wifi_test_nohif2.log" if no_hif2 else "wifi_test.log")

fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
os.set_blocking(fd, True)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)
termios.tcflush(fd, termios.TCIOFLUSH)
out = open(log, "wb")


def pump(secs):
    end = time.time() + secs
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            out.write(os.read(fd, 4096)); out.flush()


def cmd(line, secs=2):
    os.write(fd, line.encode() + b"\n")
    pump(secs)


cmd("", 2)
# keep a panic on screen instead of rebooting, print everything
cmd("echo 0 > /proc/sys/kernel/panic; echo 8 > /proc/sys/kernel/printk", 2)
# the Wi-Fi calibration, in case preinit did not place it
cmd("[ -f /lib/firmware/mediatek/mt7915_eeprom_sr1041y.bin ] || "
    "cp /tmp/factory/wlan/RT30xxEEPROM_5.bin /lib/firmware/mediatek/mt7915_eeprom_sr1041y.bin; "
    "ls -l /lib/firmware/mediatek/; ls /sys/bus/pci/devices/", 3)
if no_hif2:
    cmd("echo 1 > /sys/bus/pci/devices/0000:01:00.0/remove; ls /sys/bus/pci/devices/", 3)
cmd("echo ===MODPROBE===; modprobe mt7915e; echo MODPROBE_RC=$?", 1)
pump(60)
cmd("echo ===AFTER===; ls /sys/class/ieee80211/; dmesg | tail -40", 5)
out.close()

text = open(log, "rb").read().replace(b"\x00", b"").decode("latin-1")
i = text.find("===MODPROBE===")
print(f"### log: {log} ({len(text)} chars)")
print(text[i:][-6000:] if i >= 0 else text[-6000:])
