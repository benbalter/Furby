#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Build the two-Furby Halloween show from halloween/show.toml.

Each Furby gets its own DLC: its eye theme, plus one clip on each of a set of
75 actions (see spooky_eyes.scene_slots). A DLC only plays when something
triggers those actions over Bluetooth, so something has to do that on the
night. This also writes build/halloween/show.json, which the show engine
(furbyshow.py) plays, from a computer with porch.py or from an ESP32 with
firmware/main.py. It records each DLC's checksum, so the show can warn when a
Furby needs reflashing.

USAGE:
    python halloween.py                 # build/halloween/pink.dlc, blue.dlc, show.json
    python halloween.py --skip-missing  # leave out clips you haven't made yet

Flash each DLC to its Furby with FurBLE's "Upload Custom": pink.dlc to the
pink Furby and blue.dlc to the blue one. The show tells them apart by the name
of the DLC each has active, so keep the file names.
"""

import argparse
import json
import os
import tomllib
import zlib

from furby import dlc
from spooky_eyes import _a18, build, scene_slots

A18_BYTES_PER_SECOND = 2000  # 16 kbit/s


def load_show(path="./halloween/show.toml"):
    with open(path, "rb") as f:
        show = tomllib.load(f)
    for scene in show["scenes"]:
        for step in scene["steps"]:
            furby, _, clip = step.partition(".")
            if clip not in show["furbies"].get(furby, {}).get("clips", {}):
                raise SystemExit("%s: scene step %r names a clip that isn't defined" % (path, step))
    return show


def build_show(show, out_dir="./build/halloween", skip_missing=False, dlc_in="./dlc/dlc2/tu003410.dlc"):
    """Build each Furby's DLC and show.json; returns show.json's path."""
    os.makedirs(out_dir, exist_ok=True)
    slots = scene_slots(dlc(dlc_in))
    plan = {"gap": show["show"]["gap"], "every": show["show"]["every"], "furbies": {}, "scenes": []}
    for name, furby in show["furbies"].items():
        clips = {k: v for k, v in furby["clips"].items() if os.path.exists(v)}
        missing = sorted(set(furby["clips"]) - set(clips))
        if missing and not skip_missing:
            raise SystemExit(
                "%s is missing clips: %s. Make them, or pass --skip-missing to build without them."
                % (name, ", ".join("%s (%s)" % (m, furby["clips"][m]) for m in missing))
            )
        if len(clips) > len(slots):
            raise SystemExit("%s has %d clips; a DLC has room for %d." % (name, len(clips), len(slots)))
        work_dir = os.path.join(out_dir, name)
        os.makedirs(work_dir, exist_ok=True)
        a18 = {k: _a18(v, work_dir) for k, v in clips.items()}
        codes = dict(zip(sorted(a18), slots, strict=False))  # checked above: there are enough slots
        dlc_out = build(
            furby["theme"], clips={codes[k]: a18[k] for k in a18}, dlc_in=dlc_in, out_dir=out_dir, name=name
        )
        with open(dlc_out, "rb") as f:
            checksum = zlib.adler32(f.read())  # the Furby reports this for its active DLC
        plan["furbies"][name] = {
            "checksum": checksum,
            "clips": {
                k: {"action": list(codes[k]), "seconds": round((os.path.getsize(a18[k]) - 6) / A18_BYTES_PER_SECOND, 2)}
                for k in sorted(a18)
            },
        }
    for scene in show["scenes"]:
        playable = all(s.split(".")[1] in plan["furbies"][s.split(".")[0]]["clips"] for s in scene["steps"])
        if playable:
            plan["scenes"].append(scene["steps"])
    path = os.path.join(out_dir, "show.json")
    with open(path, "w") as f:
        json.dump(plan, f, indent=2)
    print("Wrote %s: %d scenes." % (path, len(plan["scenes"])))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("show", nargs="?", default="./halloween/show.toml")
    parser.add_argument("--skip-missing", action="store_true", help="build without clips that don't exist yet")
    parser.add_argument("-o", "--out-dir", default="./build/halloween")
    args = parser.parse_args()
    build_show(load_show(args.show), args.out_dir, args.skip_missing)
