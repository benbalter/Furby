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
    uv run halloween.py --verbose       # list every clip's size in the size report
    uv run halloween.py --reshuffle     # forget halloween/slots.lock.json: clips go in name order

Each clip keeps its 75 action from build to build (halloween/slots.lock.json,
committed with show.toml), so adding, renaming or removing a clip moves no
other clip. Each build ends by saying which DLCs changed, so you reflash only
those, and how full each DLC is.

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
from spooky_eyes import FRAMES, MAX_UPLOAD, MIXES, _tracks, build, scene_slots

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
    """A clip from show.toml: a path, or a table with path and optional start, seconds, before and optional."""
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


def lock_path_for(show_path):
    """Where a show.toml's slot lock lives: slots.lock.json beside it."""
    return os.path.join(os.path.dirname(os.path.abspath(show_path)), "slots.lock.json")


def read_json(path):
    """A JSON file's contents, or None if there's no such file."""
    if not path or not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def seed_lock(plan):
    """A slot lock from a show.json, so the first locked build keeps what's already flashed."""
    return {
        "furbies": {
            name: {"clips": {clip: _code(info["action"]) for clip, info in furby["clips"].items()}, "retired": {}}
            for name, furby in (plan or {}).get("furbies", {}).items()
        }
    }


def _code(code):
    """An action as the lock writes it: (75, 0, 4, 2) is "75-0-4-2"."""
    return "-".join(map(str, code))


def _action(text):
    return tuple(int(n) for n in text.split("-"))


def assign_slots(entry, defined, present, slots, name="", log=print):
    """Give each clip a slot, keeping the ones it had; returns ({clip: action}, the lock's new entry).

    entry: this Furby's part of the lock, {"clips": {clip: "75-0-4-2"},
    "retired": {clip: "75-0-4-2"}}, or None to start afresh. defined: every clip show.toml
    names, built this time or not; present: the ones being built. A clip keeps
    its slot while show.toml names it, even while its file is missing, so
    making it later moves nothing. A clip removed from show.toml leaves its
    slot "retired": new clips take the first free slot in quick_slots order,
    a retired one only when nothing else is free, and a clip that comes back
    gets its old slot if it's still free. With no entry, clips go in name
    order, present ones first: what halloween.py did before the lock.
    """
    slots = [tuple(s) for s in slots]
    entry = entry or {}
    old = {k: _action(v) for k, v in entry.get("clips", {}).items()}
    retired = {k: _action(v) for k, v in entry.get("retired", {}).items() if k not in defined}
    retired.update({k: v for k, v in old.items() if k not in defined})
    codes = {}
    for clip in sorted(defined):
        code = old.get(clip) or retired.get(clip)
        if code is None:
            continue
        if code not in slots:
            if clip in old:
                log("%s.%s: %s is no longer a quick slot, so it moves." % (name, clip, _code(code)))
        elif code in codes.values():
            log("%s.%s: %s is taken twice in the lock, so it moves." % (name, clip, _code(code)))
        else:
            codes[clip] = code
    held = set(codes.values())
    spare = [s for s in slots if s not in held and s not in retired.values()]
    spare += [s for s in slots if s not in held and s in retired.values()]
    new = sorted(c for c in defined if c not in codes)
    new = [c for c in new if c in present] + [c for c in new if c not in present]
    for clip in new:
        if not spare:  # only clips that aren't being built go without; build_show checks the rest
            log("%s.%s: no quick slot left to keep for it." % (name, clip))
            continue
        codes[clip] = spare.pop(0)
        if clip in old:
            log("%s.%s: now on %s." % (name, clip, _code(codes[clip])))
    taken = set(codes.values())
    retired = {k: v for k, v in retired.items() if v in slots and v not in taken}
    return codes, {
        "clips": {k: _code(v) for k, v in sorted(codes.items())},
        "retired": {k: _code(v) for k, v in sorted(retired.items())},
    }


LOCK_ABOUT = (
    "Which 75 action each clip plays on, kept from build to build by halloween.py so a clip doesn't move "
    "when others are added or removed. retired: clips no longer in show.toml, which get their slot back if "
    "re-added. Commit it with show.toml; halloween.py --reshuffle starts it again."
)


def write_lock(path, lock):
    """Write the slot lock if it changed; returns whether it did."""
    text = json.dumps({"about": LOCK_ABOUT, **lock}, indent=2, sort_keys=True) + "\n"
    if os.path.exists(path):
        with open(path) as f:
            if f.read() == text:
                return False
    with open(path, "w") as f:
        f.write(text)
    return True


def changes_message(old, new, deploy="uv run deploy.py --no-build"):
    """What to reflash and redeploy after a build, comparing show.json before (old) and after (new)."""
    names = list(new["furbies"])
    if old is None:
        return "First build: flash %s and deploy show.json (%s --esp32)." % (" and ".join(names), deploy)
    changed = [n for n in names if old.get("furbies", {}).get(n, {}).get("checksum") != new["furbies"][n]["checksum"]]
    if not changed:
        if old == new:
            return "Nothing changed since the last build."
        return "No DLC changed: just redeploy show.json (firmware/deploy.sh)."
    dlcs = " and ".join("%s.dlc" % n for n in changed)
    if len(changed) == len(names):
        return "%s changed: reflash %s and redeploy show.json (%s --esp32)." % (
            dlcs, {1: names[0], 2: "both"}.get(len(names), "every Furby"), deploy)  # fmt: skip
    only = " ".join("--only %s" % n for n in changed)
    return "Only %s changed: reflash %s and redeploy show.json (%s %s --esp32)." % (
        dlcs, " and ".join(changed), deploy, only)  # fmt: skip


def dlc_budget(path, codes, themes=()):
    """Where a built DLC's bytes go: {"total", "clips": {clip: bytes}, "eyes", "themes", "base"}.

    clips are each clip's audio track. eyes is the eye sections (CEL, SPR,
    PAL); themes splits off the cels only that theme uses ({} if it can't),
    the rest being shared layout. base is everything else: the stock DLC's
    actions, sequences, and the 128-byte stubs left of its own audio.
    themes: the eye themes in animation order, as spooky_eyes.build() installs them.
    """
    D = dlc(path)
    total = os.path.getsize(path)
    sections = D.dlc_sections
    tracks = sections["AMF"].tracks
    clips = {k: sum(len(tracks[t]) for t in _tracks(D, c)) for k, c in codes.items()}
    eyes = sum(sections[s].length for s in ("CEL", "SPR", "PAL"))
    per_theme = {}
    try:
        S, cels = sections["SPR"], sections["CEL"]
        used = {}
        for n, theme in enumerate(themes):
            playlist = 8 + n * S.channels_per_anim + 4  # the flame layer, as spooky_eyes.render reads it
            used[theme] = {S.frames[f][2 * q] for f in S.frame_playlists[playlist]["frame_indices"] for q in range(4)}
        cel_bytes = cels.length // len(cels.cels)
        for theme, mine in used.items():
            others = set().union(*(v for t, v in used.items() if t != theme))
            per_theme[theme] = len(mine - others) * cel_bytes
    except (IndexError, KeyError, ZeroDivisionError, AttributeError):
        per_theme = {}  # spooky_eyes laid the eyes out differently: just give the total
    return {
        "total": total,
        "clips": clips,
        "eyes": eyes,
        "themes": per_theme,
        "base": total - sum(clips.values()) - eyes,
    }


def _kb(n):
    return "%.0f" % (n / 1000) if n >= 1000 else "%.1f" % (n / 1000)


def budget_report(name, budget, unused=(), verbose=False, limit=None):
    """A few lines on how full a DLC is, warning near the limit and saying what to cut over it."""
    limit = limit or MAX_UPLOAD
    total, clips = budget["total"], budget["clips"]
    lines = [
        "%s.dlc: %s of %s KB (%d%%), %s"
        % (name, _kb(total), _kb(limit), round(100 * total / limit),
           "%s KB to spare" % _kb(limit - total) if total <= limit else "%s KB OVER" % _kb(total - limit))
    ]  # fmt: skip
    biggest = sorted(clips, key=lambda k: (-clips[k], k))
    shown = biggest if verbose else biggest[:5]
    more = len(biggest) - len(shown)
    if verbose:
        lines.append("  clips, %s KB:" % _kb(sum(clips.values())))
        lines += ["    %-14s %5s KB  %4.1f s" % (k, _kb(clips[k]), clips[k] / A18_BYTES_PER_SECOND) for k in shown]
    else:
        lines.append(
            "  clips %s KB: %s%s"
            % (_kb(sum(clips.values())), ", ".join("%s %s" % (k, _kb(clips[k])) for k in shown),
               ", +%d more" % more if more else "")
        )  # fmt: skip
    themes = budget["themes"]
    split = ", ".join("%s %s" % (t, _kb(b)) for t, b in themes.items())
    if themes:
        split += ", layout %s" % _kb(budget["eyes"] - sum(themes.values()))
    lines.append("  eyes %s KB%s; base DLC %s KB" % (_kb(budget["eyes"]), " (%s)" % split if split else "",
                                                     _kb(budget["base"])))  # fmt: skip
    if total > limit:
        excess, cut = total - limit, []
        for k in [c for c in biggest if c in unused] + [c for c in biggest if c not in unused]:
            if excess <= 0:
                break
            if k in unused:
                cut.append("drop %s (in no scene, %s KB)" % (k, _kb(clips[k])))
            elif excess < clips[k] / 2:  # trimming keeps most of it
                cut.append("cut %s by %.1f s" % (k, excess / A18_BYTES_PER_SECOND))
            else:
                cut.append("drop %s (%s KB)" % (k, _kb(clips[k])))
            excess -= clips[k]
        lines.append("  Too big to upload. To fit: %s." % "; or ".join([", ".join(cut)] + (
            ["drop an eye theme (each about 37 KB)"] if len(themes) > 1 else [])))  # fmt: skip
    elif total > 0.9 * limit:
        lines.append("  Warning: over 90%% of the %s KB upload limit. Shorten a clip before adding any." % _kb(limit))
    return "\n".join(lines)


def build_show(
    show,
    out_dir="./build/halloween",
    skip_missing=False,
    dlc_in="./dlc/dlc2/tu003410.dlc",
    lock_path=None,
    reshuffle=False,
    verbose=False,
):
    """Build each Furby's DLC and show.json; returns show.json's path.

    lock_path: the slot lock (see assign_slots), read and updated, so a clip
    keeps its action from build to build. None assigns slots afresh in name order.
    reshuffle: ignore the lock and start it again.
    """
    os.makedirs(out_dir, exist_ok=True)
    slots = quick_slots(dlc(dlc_in))
    previous = read_json(os.path.join(out_dir, "show.json"))
    lock = None if reshuffle else read_json(lock_path)
    if lock_path and lock is None and not reshuffle and previous:
        print("No %s yet: starting it from %s's actions." % (lock_path, os.path.join(out_dir, "show.json")))
        lock = seed_lock(previous)
    lock = lock or {"furbies": {}}
    used = {p for scene in show["scenes"] for step in scene["steps"] for p in step_parts(step)}
    reports = []
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
        codes, lock["furbies"][name] = assign_slots(lock["furbies"].get(name), specs, clips, slots, name)
        if set(a18) - set(codes):
            raise SystemExit(
                "%s: no free slot for %s, since clips that aren't built yet hold them. Remove some clips from "
                "show.toml, or pass --reshuffle." % (name, ", ".join(sorted(set(a18) - set(codes))))
            )
        codes = {k: codes[k] for k in a18}
        theme, eyes = clip_eyes(furby, clips, show["show"].get("one_eye_animation", False))
        themes = [theme] + sorted(set(eyes.values()) - {theme})  # the order spooky_eyes.build() installs them
        unused = {k for k in a18 if "%s.%s" % (name, k) not in used}
        try:
            dlc_out = build(
                theme,
                clips={codes[k]: a18[k] for k in a18},
                dlc_in=dlc_in,
                out_dir=out_dir,
                name=name,
                eyes={codes[k]: eyes[k] for k in a18},
                frames=show["show"].get("eye_frames", FRAMES),
            )
        except SystemExit:  # too big to upload: say what to cut
            too_big = os.path.join(out_dir, "%s.dlc" % name)
            if os.path.exists(too_big) and os.path.getsize(too_big) > MAX_UPLOAD:
                print(budget_report(name, dlc_budget(too_big, codes, themes), unused, verbose))
            raise
        reports.append(budget_report(name, dlc_budget(dlc_out, codes, themes), unused, verbose))
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
    lock["furbies"] = {k: v for k, v in lock["furbies"].items() if k in show["furbies"]}
    if lock_path and write_lock(lock_path, lock):
        print("Updated %s: commit it with show.toml, so clips keep their actions." % lock_path)
    print("\n".join(reports))
    print("Wrote %s: %d scenes, %d of them greetings." % (path, len(plan["scenes"]), len(plan["greetings"])))
    print(changes_message(previous, json.loads(json.dumps(plan))))  # through JSON, as previous was
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("show", nargs="?", default="./halloween/show.toml")
    parser.add_argument("--skip-missing", action="store_true", help="build without clips that don't exist yet")
    parser.add_argument("-o", "--out-dir", default="./build/halloween")
    parser.add_argument("--reshuffle", action="store_true", help="forget slots.lock.json and assign every slot afresh")
    parser.add_argument("-v", "--verbose", action="store_true", help="list every clip's size")
    args = parser.parse_args()
    build_show(load_show(args.show), args.out_dir, args.skip_missing, lock_path=lock_path_for(args.show),
               reshuffle=args.reshuffle, verbose=args.verbose)  # fmt: skip
