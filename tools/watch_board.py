#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial"]
# ///
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Follow the ESP32's show log live over USB, through restarts.

USAGE:
    uv run tools/watch_board.py                 # until Ctrl-C
    uv run tools/watch_board.py --seconds 120   # for two minutes
    uv run tools/watch_board.py --port /dev/cu.usbmodem1101 --no-save
    uv run tools/watch_board.py --find          # just print the board's port (deploy.sh, getlog.sh, doctor.py)

Unlike `mpremote repl`, it only listens: it never sends the board a keystroke,
so it can't stop the show by accident, and when the board restarts (deploy.sh,
the watchdog, a power dip) it waits for the port to come back and carries on.
Each run also saves what it saw to build/board-log/watch-<time>.txt. For the
log the board kept while nobody was watching, use firmware/getlog.sh.

The board is found by its USB vendor ID (Espressif's), not by taking the first
USB serial port: other boards on the same Mac, like the EyeLights glasses or a
Flipper, have ports that look just the same, and deploy.sh would copy the show
onto them.
"""

import argparse
import os
import sys
import time

ESPRESSIF = 0x303A  # the USB vendor ID of the ESP32-S3's own USB


def serial_ports():
    """(device, vid, description) for each serial port."""
    from serial.tools import list_ports

    return [(p.device, p.vid, p.description) for p in list_ports.comports()]


def find_port(ports=None):
    """The ESP32's port, or None. Only an Espressif board counts, never just any USB serial port."""
    ports = serial_ports() if ports is None else ports
    found = sorted(device for device, vid, _ in ports if vid == ESPRESSIF)
    return found[0] if found else None


def not_found(ports=None):
    """Why find_port() found nothing, naming the USB ports that aren't the board."""
    ports = serial_ports() if ports is None else ports
    others = ["%s (%s)" % (device, description) for device, vid, description in ports if vid is not None]
    if not others:
        return "No ESP32 on USB. Plug the board in, with a data cable."
    return "No ESP32 on USB, only: %s. Plug the board in, or pass its port." % ", ".join(others)


def watch(port, seconds, out, save=None):
    """Print (and save) the board's lines until seconds pass, reconnecting when the port drops."""
    import serial  # only needed here, so --help works without pyserial

    end = time.monotonic() + seconds if seconds else None
    waiting = False
    while end is None or time.monotonic() < end:
        path = port or find_port()
        if not path or not os.path.exists(path):
            if not waiting:
                out("(waiting for the board on USB...)")
                waiting = True
            time.sleep(0.3)
            continue
        waiting = False
        try:
            with serial.Serial(path, 115200, timeout=1) as s:
                while end is None or time.monotonic() < end:
                    line = s.readline()
                    if line:
                        text = line.decode(errors="replace").rstrip()
                        out(text)
                        if save:
                            save.write(text + "\n")
                            save.flush()
        except (serial.SerialException, OSError):  # the board restarted; its port comes back in a moment
            out("(board disconnected; waiting for it to come back)")
            waiting = True
            time.sleep(0.5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--port", help="serial port (default: the ESP32 on USB, found by its vendor ID)")
    parser.add_argument("--find", action="store_true", help="print the ESP32's port and exit; fail if there's none")
    parser.add_argument("--seconds", type=float, default=0, help="stop after this long (default: until Ctrl-C)")
    parser.add_argument("--no-save", action="store_true", help="don't save a copy to build/board-log/")
    args = parser.parse_args(argv)
    if args.find:
        port = find_port()
        print(port or not_found(), file=sys.stdout if port else sys.stderr)
        return 0 if port else 1
    save = None
    if not args.no_save:
        os.makedirs("build/board-log", exist_ok=True)
        path = "build/board-log/watch-%s.txt" % time.strftime("%Y%m%d-%H%M%S")
        save = open(path, "w")
        print("Saving to %s. Ctrl-C to stop." % path, file=sys.stderr)
    try:
        # flush: piped into a file or another tool, print would hold lines back until it exits
        watch(args.port, args.seconds, lambda line: print(line, flush=True), save)
    except KeyboardInterrupt:
        pass
    finally:
        if save:
            save.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
