#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Build the two-Furby Halloween show from halloween/show.toml.

Each Furby gets its own DLC: its eye theme, plus one clip on each of a set of
75 actions (see quick_slots). A DLC only plays when something
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
import subprocess
import sys
import tomllib
import zlib

from furby import dlc
from furbyshow import step_parts
from spooky_eyes import build, scene_slots

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "audioutils"))
from encode_a18 import encode  # noqa: E402

A18_BYTES_PER_SECOND = 2000  # 16 kbit/s
DLC_MOTOR = 0xC  # top nibble of a sequence's motor word when it runs one of the DLC's own routines


def quick_slots(D):
    """Scene slots whose sequence ends soon after its clip, in the order to fill them.

    A Furby stays busy until a sequence's body movement and eye delays finish,
    and plays anything triggered before then without its audio. Timed on a
    real Furby, the slots that run the DLC's own motor routines take 10-21 s
    whatever the clip, while those using built-in movements take about 1-9 s.
    """
    seqs = D.dlc_sections["SEQ"].sequences
    tree = D.dlc_sections["XLS"].action_tree
    return [c for c in scene_slots(D) if seqs[tree[c[0]][c[1]][c[2]][c[3]]["seq"]][2] >> 12 != DLC_MOTOR]


def load_show(path="./halloween/show.toml"):
    with open(path, "rb") as f:
        show = tomllib.load(f)
    for scene in show["scenes"]:
        for step in scene["steps"]:
            for part in step_parts(step):
                furby, _, clip = part.partition(".")
                if clip not in show["furbies"].get(furby, {}).get("clips", {}):
                    raise SystemExit("%s: scene step %r names a clip that isn't defined" % (path, part))
    used = {p for scene in show["scenes"] for step in scene["steps"] for p in step_parts(step)}
    for furby, spec in show["furbies"].items():
        for clip in sorted(spec.get("clips", {})):
            if "%s.%s" % (furby, clip) not in used:
                print("%s: %s.%s isn't in any scene, but still takes up room in the DLC." % (path, furby, clip))
    return show


def clip_spec(value):
    """A clip from show.toml: a path, or a table with path and optional start, seconds, before and optional."""
    spec = {"path": value} if isinstance(value, str) else dict(value)
    spec.setdefault("optional", False)
    return spec


def encode_clip(name, spec, work_dir):
    """The clip as .a18, cut to its start and seconds if given; returns its path."""
    if spec["path"].endswith(".a18") and not (spec.get("start") or spec.get("seconds")):
        return spec["path"]
    out = os.path.join(work_dir, name + ".a18")
    encode(spec["path"], out, spec.get("start"), spec.get("seconds"))
    return out


def preview_clip(name, spec, work_dir):
    """A WAV of just the snippet, for porch.py --rehearse; returns its path."""
    out = os.path.join(work_dir, name + ".wav")
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if spec.get("start"):
        cmd += ["-ss", spec["start"]]
    if spec.get("seconds"):
        cmd += ["-t", str(spec["seconds"])]
    subprocess.run(cmd + ["-i", spec["path"], out], check=True)
    return out


def build_show(show, out_dir="./build/halloween", skip_missing=False, dlc_in="./dlc/dlc2/tu003410.dlc"):
    """Build each Furby's DLC and show.json; returns show.json's path."""
    os.makedirs(out_dir, exist_ok=True)
    slots = quick_slots(dlc(dlc_in))
    plan = {
        "gap": show["show"]["gap"],
        "every": show["show"]["every"],
        "cooldown": show["show"].get("cooldown", 0),
        "furbies": {},
        "scenes": [],
        "greetings": [],
    }
    for name, furby in show["furbies"].items():
        specs = {k: clip_spec(v) for k, v in furby["clips"].items()}
        clips = {k: v for k, v in specs.items() if os.path.exists(v["path"])}
        for k in sorted(set(specs) - set(clips)):
            if specs[k]["optional"]:
                print("%s.%s: no %s yet, so scenes using it are left out." % (name, k, specs[k]["path"]))
        missing = sorted(k for k in set(specs) - set(clips) if not specs[k]["optional"])
        if missing and not skip_missing:
            raise SystemExit(
                "%s is missing clips: %s. Make them, or pass --skip-missing to build without them."
                % (name, ", ".join("%s (%s)" % (m, specs[m]["path"]) for m in missing))
            )
        if len(clips) > len(slots):
            raise SystemExit("%s has %d clips; a DLC has room for %d." % (name, len(clips), len(slots)))
        work_dir = os.path.join(out_dir, name)
        os.makedirs(work_dir, exist_ok=True)
        a18 = {k: encode_clip(k, v, work_dir) for k, v in clips.items()}
        codes = dict(zip(sorted(a18), slots, strict=False))  # checked above: there are enough slots
        dlc_out = build(
            furby["theme"], clips={codes[k]: a18[k] for k in a18}, dlc_in=dlc_in, out_dir=out_dir, name=name
        )
        with open(dlc_out, "rb") as f:
            checksum = zlib.adler32(f.read())  # the Furby reports this for its active DLC
        plan["furbies"][name] = {
            "checksum": checksum,
            "antenna": furby.get("antenna"),
            "clips": {
                k: {
                    "action": list(codes[k]),
                    "seconds": round((os.path.getsize(a18[k]) - 6) / A18_BYTES_PER_SECOND, 2),
                    # porch.py --rehearse plays this: just the snippet when the clip is cut
                    "source": preview_clip(k, clips[k], work_dir)
                    if clips[k].get("start") or clips[k].get("seconds")
                    else clips[k]["path"],
                    **({"before": clips[k]["before"]} if clips[k].get("before") else {}),
                }
                for k in sorted(a18)
            },
        }
    for scene in show["scenes"]:
        parts = [p.split(".") for step in scene["steps"] for p in step_parts(step)]
        playable = all(clip in plan["furbies"][furby]["clips"] for furby, clip in parts)
        if playable:
            plan["scenes"].append(scene["steps"])
            if scene.get("greeting"):
                plan["greetings"].append(scene["steps"])
    path = os.path.join(out_dir, "show.json")
    with open(path, "w") as f:
        json.dump(plan, f, indent=2)
    print("Wrote %s: %d scenes, %d of them greetings." % (path, len(plan["scenes"]), len(plan["greetings"])))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("show", nargs="?", default="./halloween/show.toml")
    parser.add_argument("--skip-missing", action="store_true", help="build without clips that don't exist yet")
    parser.add_argument("-o", "--out-dir", default="./build/halloween")
    args = parser.parse_args()
    build_show(load_show(args.show), args.out_dir, args.skip_missing)
