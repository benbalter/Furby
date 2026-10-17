#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Build the real Halloween show with placeholder clips, so CI can run it.

The show's voice lines and effects are gitignored (and the cloned voices are
Hasbro-derived), so CI has none of them. This reads halloween/show.toml, gives
every clip a short tone as its audio, and builds the DLCs and show.json with
halloween.build_show(), the same way the real show is built. Then emulate.py
can play every scene against virtual Furbies and flag any line that would go
silent or be skipped, and eyecheck.py can check the eyes.

Each tone lasts as long as the clip's snippet (its seconds) or a second and a
bit, and is written as .a18 directly, so no ffmpeg is needed. Optional clips
get a tone too, so their scenes are tested rather than dropped.

USAGE (from the repo root):
    python tools/ci_show.py                    # build/ci-show/{pink,blue}.dlc, show.json
    python emulate.py build/ci-show/show.json
    python eyecheck.py build/ci-show/pink.dlc build/ci-show/blue.dlc
"""

import argparse
import math
import os
import struct
import sys
from array import array

import a1800_codec

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import halloween  # noqa: E402

RATE = 16000
BITRATE = 16000
DEFAULT_SECONDS = 1.2


def tone(path, seconds, hz):
    """A sine tone that swells and fades (so the antenna envelope isn't flat), as .a18."""
    n = int(RATE * seconds)
    samples = array(
        "h", (int(12000 * math.sin(math.pi * i / n) * math.sin(2 * math.pi * hz * i / RATE)) for i in range(n))
    )
    if sys.byteorder == "big":
        samples.byteswap()  # the codec takes little-endian samples
    frames = bytes(a1800_codec.encode(samples.tobytes(), BITRATE))[6:]
    with open(path, "wb") as f:  # the header encode_a18.py writes: length counts the 2-byte bitrate
        f.write(struct.pack("<IH", len(frames) + 2, BITRATE) + frames)
    return path


def placeholder_show(show, clip_dir):
    """The show with each clip's audio swapped for a tone in clip_dir."""
    os.makedirs(clip_dir, exist_ok=True)
    for name, furby in show["furbies"].items():
        for i, (clip, value) in enumerate(sorted(furby["clips"].items())):
            spec = halloween.clip_spec(value)
            seconds = float(spec.pop("seconds", None) or DEFAULT_SECONDS)
            spec.pop("start", None)
            spec["optional"] = False
            spec["path"] = tone(os.path.join(clip_dir, "%s_%s.a18" % (name, clip)), seconds, 300 + 40 * i)
            furby["clips"][clip] = spec
    return show


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("show", nargs="?", default="./halloween/show.toml")
    parser.add_argument("-o", "--out-dir", default="./build/ci-show")
    args = parser.parse_args(argv)
    show = placeholder_show(halloween.load_show(args.show), os.path.join(args.out_dir, "clips"))
    return halloween.build_show(show, args.out_dir)


if __name__ == "__main__":
    main()
