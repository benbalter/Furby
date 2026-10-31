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
get a tone too, so their scenes are tested rather than dropped. Without your
stock DLC (see stock_dlc.py), it builds on tools/synthetic_dlc.py's stand-in.

USAGE (from the repo root):
    python tools/ci_show.py                    # build/ci-show/{pink,blue}.dlc, show.json
    python emulate.py build/ci-show/show.json
    python eyecheck.py build/ci-show/pink.dlc build/ci-show/blue.dlc
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from synthetic_dlc import build as synthetic_dlc  # noqa: E402
from synthetic_dlc import write_tone  # noqa: E402

import halloween  # noqa: E402
import stock_dlc  # noqa: E402

DEFAULT_SECONDS = 1.2


def placeholder_show(show, clip_dir):
    """The show with each clip's audio swapped for a tone in clip_dir."""
    os.makedirs(clip_dir, exist_ok=True)
    for name, furby in show["furbies"].items():
        for i, (clip, value) in enumerate(sorted(furby["clips"].items())):
            spec = halloween.clip_spec(value)
            seconds = float(spec.pop("seconds", None) or DEFAULT_SECONDS)
            spec.pop("start", None)
            spec["optional"] = False
            spec["path"] = write_tone(os.path.join(clip_dir, "%s_%s.a18" % (name, clip)), seconds, 300 + 40 * i)
            furby["clips"][clip] = spec
    return show


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("show", nargs="?", default="./halloween/show.toml")
    parser.add_argument("-o", "--out-dir", default="./build/ci-show")
    parser.add_argument("--dlc", help="the DLC to build on (default: your stock DLC, else a synthetic one)")
    args = parser.parse_args(argv)
    dlc_in = args.dlc or stock_dlc.path()
    if not os.path.exists(dlc_in):  # CI has no stock DLC: the synthetic one has its layout
        dlc_in = synthetic_dlc(os.path.join(args.out_dir, "synthetic.dlc"))
    show = placeholder_show(halloween.load_show(args.show), os.path.join(args.out_dir, "clips"))
    return halloween.build_show(show, args.out_dir, dlc_in=dlc_in)


if __name__ == "__main__":
    main()
