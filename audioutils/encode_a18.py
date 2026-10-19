#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Convert any audio file to Furby Connect .a18, on any OS, with no DLL.

Uses ffmpeg to decode and resample to 16 kHz mono, then the open-source
A1800 encoder (https://github.com/John-K/a1800_codec, `pip install
a1800-codec`), which was reverse engineered from GeneralPlus's A1800.DLL.

USAGE:
    python audioutils/encode_a18.py song.mp3 song.a18
    python audioutils/encode_a18.py song.mp3 song.a18 --start 0:42 --duration 20
"""

import argparse
import os
import struct
import subprocess

import a1800_codec

BITRATE = 16000  # what the Furby's own tracks use


def encode(src, dst, start=None, duration=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start:
        cmd += ["-ss", start]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-i", src, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
    pcm = subprocess.run(cmd, check=True, capture_output=True).stdout

    a18 = bytes(a1800_codec.encode(pcm, BITRATE))
    frames = a18[6:]
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)  # e.g. build/ in a fresh clone
    # The codec's length field counts only frame bytes. GeneralPlus's tools,
    # and furby.py's track reader, also count the 2-byte bitrate after it;
    # without this, the last frame of every clip gets cut short.
    with open(dst, "wb") as f:
        f.write(struct.pack("<IH", len(frames) + 2, BITRATE) + frames)
    print("Wrote %s: %.1f s, %d KB" % (dst, len(pcm) / 32000, (len(frames) + 6) // 1000))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("src", help="any audio file ffmpeg can read")
    parser.add_argument("dst", help="output .a18")
    parser.add_argument("--start", help="where to start, e.g. 0:42")
    parser.add_argument("--duration", type=float, help="seconds to keep")
    args = parser.parse_args()
    encode(args.src, args.dst, args.start, args.duration)
