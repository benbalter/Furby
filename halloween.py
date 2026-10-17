#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Build the two-Furby Halloween show from halloween/show.toml.

Each Furby gets its own DLC: one clip on each of a set of 75 actions (see
quick_slots), each with an eye animation from the Furby's eyes list (see
clip_eyes). A DLC only plays when something
triggers those actions over Bluetooth, so something has to do that on the
night. This also writes build/halloween/show.json, which the show engine
(furbyshow.py) plays, from a computer with porch.py or from an ESP32 with
firmware/main.py. It records each DLC's checksum, so the show can warn when a
Furby needs reflashing.

USAGE:
    uv run halloween.py                 # build/halloween/pink.dlc, blue.dlc, show.json
    uv run halloween.py --skip-missing  # leave out clips you haven't made yet

Flash each DLC to its Furby with flash.py, one Furby awake at a time:
pink.dlc to the pink Furby and blue.dlc to the blue one. The show tells them
apart by the name of the DLC each has active, so keep the file names.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tomllib
import zlib
from array import array

import a1800_codec

from furby import dlc
from furbyshow import EFFECTS, ENVELOPE_HZ, LIGHT_HZ, LIGHT_MAX_HZ, scale, step_parts
from spooky_eyes import FRAMES, MIXES, build, scene_slots

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "audioutils"))
from encode_a18 import encode  # noqa: E402

A18_BYTES_PER_SECOND = 2000  # 16 kbit/s
A18_RATE = 16000  # samples a second when decoded
DLC_MOTOR = 0xC  # top nibble of a sequence's motor word when it runs one of the DLC's own routines
# The antenna's light for each eye theme, so it plays along with the eyes
# (furbyshow.light_rgb draws the effects). show.toml can change any of it.
THEME_LIGHTS = {
    "demon": {"effect": "pulse", "color": [255, 0, 0]},
    "bloodshot": {"effect": "voice", "color": [170, 0, 0]},
    "storm": {"effect": "lightning", "color": [60, 80, 255]},
    "pumpkin": {"effect": "candle", "color": [255, 80, 0]},
    "ghost": {"effect": "wisp", "color": [150, 200, 255]},
    "hypno": {"effect": "cycle", "color": [255, 0, 255]},
}
# An envelope's 0: this far below the clip's loudest moment, or quieter. At
# -36 speech sat at 7-9 throughout; -24 lets syllables show.
QUIETEST_DB = -24
GP_HEADER, GP_HEADER_SIZE = b"\x00\xff\x00\xffGENERALPLUS", 0x30


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
    """A clip from show.toml: a path, or a table with path and optional start, seconds, before and optional.

    A table can also have text, the words of a voice line, which voices.py reads;
    it doesn't change the build.
    """
    spec = {"path": value} if isinstance(value, str) else dict(value)
    spec.setdefault("optional", False)
    return spec


def clip_eyes(furby, clips, one=False):
    """The Furby's main eye theme, and {clip: theme}.

    Clips take turns through the Furby's eyes list in clip-name order, so
    consecutive lines tend to look different; a clip table's eyes picks its
    own. Without an eyes list, the Furby's theme picks a mix (spooky_eyes.MIXES).
    The first theme is the main one: it goes in the DLC's animation 1, the
    layout that has run on a Furby. one = True shows only that one.
    """
    mix = furby.get("eyes") or MIXES.get(furby.get("theme"), [furby.get("theme", "demon")])
    mix = [mix] if isinstance(mix, str) else list(mix)
    if one:
        return mix[0], dict.fromkeys(clips, mix[0])
    turns = [c for c in sorted(clips) if not clips[c].get("eyes")]
    eyes = {c: mix[i % len(mix)] for i, c in enumerate(turns)}
    eyes.update({c: clips[c]["eyes"] for c in clips if clips[c].get("eyes")})
    return mix[0], eyes


def light_spec(value, where):
    """A light from show.toml as a dict: an effect name, an eye theme's light, or a table."""
    if value is None:
        return {}
    if isinstance(value, str):
        value = dict(THEME_LIGHTS[value]) if value in THEME_LIGHTS else {"effect": value}
    spec = dict(value)
    if spec.get("effect", "steady") not in EFFECTS:
        raise SystemExit(
            "%s: unknown light %r. Use an effect (%s) or an eye theme (%s)."
            % (where, spec["effect"], ", ".join(EFFECTS), ", ".join(THEME_LIGHTS))
        )
    return spec


def clip_light(name, furby, clip, theme, spec):
    """A clip's antenna light for show.json, {"effect", "color"}, or None for none.

    Its eye theme's light (THEME_LIGHTS), changed by the Furby's light and then
    the clip's own. The Furby's antenna color is the fallback for a light with
    no color of its own.
    """
    light = {"effect": "voice", "color": furby.get("antenna")}
    light.update(THEME_LIGHTS.get(theme, {}))
    light.update(light_spec(furby.get("light"), "furbies.%s.light" % name))
    light.update(light_spec(spec.get("light"), "furbies.%s.clips.%s.light" % (name, clip)))
    if light["effect"] == "off" or not light.get("color"):
        return None
    return {"effect": light["effect"], "color": list(light["color"])}


def envelope(a18_path, hz=ENVELOPE_HZ):
    """How loud a clip is over time, as one digit (0-9) per 1/hz s, e.g. "0379975310".

    Taken from the encoded clip, so it lines up with what the Furby plays. Each
    level is the loudness (RMS) of its slice in decibels below the clip's
    loudest slice: 9 is the loudest, 0 is QUIETEST_DB or quieter. A digit
    string costs a byte a frame in show.json and on the board.
    """
    with open(a18_path, "rb") as f:
        data = f.read()
    if data.startswith(GP_HEADER):  # A1800.DLL's files (like audio/new_audio's) have an extra header
        data = data[GP_HEADER_SIZE:]
    try:
        samples = array("h", bytes(a1800_codec.decode(data)))
    except ValueError as e:  # the show still runs: its light just doesn't follow the sound
        print("%s: can't decode it for the antenna light (%s)" % (a18_path, e))
        return None
    if sys.byteorder == "big":
        samples.byteswap()  # the codec gives little-endian samples
    n = A18_RATE // hz
    slices = [samples[i : i + n] for i in range(0, len(samples), n)]
    rms = [math.sqrt(sum(s * s for s in part) / len(part)) for part in slices]
    loudest = max(rms, default=0) or 1
    levels = []
    for r in rms:
        db = 20 * math.log10(r / loudest) if r else QUIETEST_DB
        levels.append(str(max(0, min(9, round(9 * (1 - db / QUIETEST_DB))))))
    return "".join(levels)


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
    idle_glow = show["show"].get("idle_glow", 0)
    plan = {
        "gap": show["show"]["gap"],
        "every": show["show"]["every"],
        "cooldown": show["show"].get("cooldown", 0),
        "light_hz": max(1, min(LIGHT_MAX_HZ, int(show["show"].get("light_hz", LIGHT_HZ)))),
        "envelope_hz": ENVELOPE_HZ,
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
        theme, eyes = clip_eyes(furby, clips, show["show"].get("one_eye_animation", False))
        dlc_out = build(
            theme,
            clips={codes[k]: a18[k] for k in a18},
            dlc_in=dlc_in,
            out_dir=out_dir,
            name=name,
            eyes={codes[k]: eyes[k] for k in a18},
            frames=show["show"].get("eye_frames", FRAMES),
        )
        with open(dlc_out, "rb") as f:
            checksum = zlib.adler32(f.read())  # the Furby reports this for its active DLC
        lights = {k: clip_light(name, furby, k, eyes[k], clips[k]) for k in a18}
        # Only effects that change with the sound need its envelope
        envelopes = {k: envelope(a18[k]) for k in a18 if lights[k] and lights[k]["effect"] != "steady"}
        main = clip_light(name, furby, None, theme, {})  # the main eyes' light, for the idle glow
        plan["furbies"][name] = {
            "checksum": checksum,
            "antenna": furby.get("antenna"),
            **({"idle": list(scale(main["color"], idle_glow))} if idle_glow and main else {}),
            "clips": {
                k: {
                    "action": list(codes[k]),
                    "eyes": eyes[k],
                    "light": lights[k] or {"effect": "off"},
                    # Only effects that change with the sound need it
                    **({"envelope": envelopes[k]} if envelopes.get(k) else {}),
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
