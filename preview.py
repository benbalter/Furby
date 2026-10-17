#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Preview the Halloween show in a browser: a virtual porch with both Furbies.

It writes build/preview/index.html, which plays each scene the way the show
runs it on the night, from the built show alone (no Furbies, no server):

- Timing, antenna colours and busy waits come from running the real show
  engine (furbyshow.py) against emulate.py's virtual Furbies, so the page
  replays what the engine would send, at the times it would send it.
- Sound is each clip's audio as the Furby stores it: the DLC's AMF tracks
  for the clip's action, decoded with a1800-codec.
- Eyes are the DLC's eye animations as eyecheck.compose() models the
  firmware drawing them. That's a model, not a measurement.

The page contains audio decoded from DLCs built on Hasbro's, so it's for
looking at on this computer only: never commit or publish build/preview/.

USAGE:
    uv run preview.py                    # build/halloween/show.json → build/preview/index.html
    uv run preview.py --open             # ...and open it in the default browser
    uv run preview.py --show other/show.json --out build/other-preview
"""

import argparse
import inspect
import json
import os
import shutil
import subprocess
import sys
import wave

import a1800_codec
from PIL import Image

import emulate
import eyecheck
import furbyshow
from furby import dlc
from halloween import A18_RATE

# eyecheck.save_gif's frame time, itself a guess: no one has timed an eye animation's frame rate yet
FRAME_MS = inspect.signature(eyecheck.save_gif).parameters["ms"].default
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.html")
EYES = ("right", "left")  # a sprite sheet's rows: the Furby's right eye (on the viewer's left), then its left


def clip_audio(D, action):
    """16-bit mono PCM of what the Furby plays for an action: its APL's tracks, with pauses as silence."""
    S = D.dlc_sections
    seq = S["SEQ"].sequences[S["XLS"].action_tree[action[0]][action[1]][action[2]][action[3]]["seq"]]
    pcm = b""
    for n, kind in S["APL"].playlists[seq[1] - S["SEQ"].playlist_offset]:
        if kind == "AUDIO":
            pcm += bytes(a1800_codec.decode(S["AMF"].tracks[n]))
        elif kind == "PAUSE":
            pcm += bytes(2 * int((n & 0xFFF) * emulate.DELAY_UNIT_S * A18_RATE))
    return pcm


def write_wav(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(A18_RATE)
        w.writeframes(pcm)


def sequence_info(D, action):
    """An action's sequence for the page: its eye steps, in order, and its motor word."""
    S = D.dlc_sections
    seq = S["SEQ"].sequences[S["XLS"].action_tree[action[0]][action[1]][action[2]][action[3]]["seq"]]
    steps = []
    for w in seq[3:-1]:
        if eyecheck.FIRST_DLC_WORD <= w <= eyecheck.LAST_DLC_WORD:
            steps.append({"eyes": "%04x" % w})
        elif w >> 12 == 0x1:  # a delay word: the eyes hold their last frame (emulate's reading of its units)
            steps.append({"hold": round((w & 0xFFF) * emulate.DELAY_UNIT_S, 2)})
    motor = seq[2]
    low, high = emulate.MOTOR_RANGE_S.get(motor >> 12, (0, 0))
    kind = {0xE: "built-in movement", 0xC: "the DLC's own movement"}.get(motor >> 12, "movement")
    label = "motor 0x%04x, %s" % (motor, kind) + (" (%g-%g s measured)" % (low, high) if high else "")
    return steps, label


def eye_sprite(model, word, path):
    """A sprite sheet of eye word `word`, as the virtual Furby draws it: a row per eye, a column per frame."""
    rows = [model.eyes(word, eye) for eye in EYES]
    n = max(len(r) for r in rows)
    if not n:
        return 0
    sheet = Image.new("RGB", (n * eyecheck.SIZE, len(rows) * eyecheck.SIZE))
    for y, frames in enumerate(rows):
        for x in range(n):
            if frames:
                sheet.paste(frames[min(x, len(frames) - 1)], (x * eyecheck.SIZE, y * eyecheck.SIZE))
    sheet.save(path)
    return n


def timeline(plan, dlcs, worst):
    """Every scene, played by the real engine on virtual Furbies: emulate.simulate()'s report, for the page."""
    report = emulate.simulate(plan, dlcs, durations=emulate.load_durations(worst=worst))
    clips = {name: {tuple(i["action"]): c for c, i in f["clips"].items()} for name, f in plan["furbies"].items()}
    scenes = []
    for r in report:
        events, end = [], r["seconds"]
        for t, furby, kind, detail in r["events"]:
            if kind == "played":
                action, audio, busy = detail
                events.append({"t": t, "furby": furby, "kind": "play", "clip": clips[furby].get(tuple(action))})
                events[-1].update(audio=audio, busy=busy)
                end = max(end, t + busy)  # the last sequence can outlast the scene
            elif kind == "silent":
                waiting = [e for e in events if e.get("furby") == furby and e["kind"] in ("play", "busy")]
                if waiting and waiting[-1]["kind"] == "busy":
                    continue  # still waiting for the same sequence: one log line is enough
                events.append({"t": t, "furby": furby, "kind": "busy", "clip": clips[furby].get(tuple(detail))})
            elif kind == "antenna":
                events.append({"t": t, "furby": furby, "kind": "antenna", "rgb": list(detail)})
            elif kind == "log" and not detail.startswith("Connected"):  # the page starts connected
                events.append({"t": t, "kind": "log", "text": detail})
        scenes.append({"steps": r["steps"], "seconds": r["seconds"], "end": round(end, 3), "events": events})
    return scenes


def build_preview(plan_path, out_dir):
    """Write the preview page and its audio, eyes and data into out_dir; returns index.html's path."""
    with open(plan_path) as f:
        plan = json.load(f)
    here = os.path.dirname(plan_path)
    dlcs = {name: os.path.join(here, "%s.dlc" % name) for name in plan["furbies"]}
    missing = [p for p in dlcs.values() if not os.path.exists(p)]
    if missing:
        raise SystemExit("No %s; build the show first (uv run halloween.py)." % ", ".join(missing))
    for sub in ("audio", "eyes"):
        shutil.rmtree(os.path.join(out_dir, sub), ignore_errors=True)
        os.makedirs(os.path.join(out_dir, sub))

    furbies = {}
    for name, fplan in plan["furbies"].items():
        D = dlc(dlcs[name])
        # The virtual Furby, so its eyes use whichever cels it would (see emulate.FurbyModel.activate)
        model = emulate.furby_class()("preview-" + name, dlcs[name], "%s.DLC" % name.upper().rjust(8, "_")).model
        errors, _ = eyecheck.envelope(D)
        sprites, clips = {}, {}
        for clip, info in sorted(fplan["clips"].items()):
            action = tuple(info["action"])
            audio = "audio/%s_%s.wav" % (name, clip)
            write_wav(os.path.join(out_dir, audio), clip_audio(D, action))
            steps, motor = sequence_info(D, action)
            for step in steps:
                word = step.get("eyes")
                if word and word not in sprites:
                    src = "eyes/%s_%s.png" % (name, word)
                    sprites[word] = {"src": src, "frames": eye_sprite(model, int(word, 16), os.path.join(out_dir, src))}
            clips[clip] = {
                "action": list(action),
                "audio": audio,
                "seconds": info["seconds"],
                "theme": info.get("eyes"),
                "eyes": steps,
                "motor": motor,
            }
        furbies[name] = {
            "antenna": fplan.get("antenna"),
            "clips": clips,
            "sprites": sprites,
            "warnings": errors,
        }

    show = furbyshow.Show(plan, None)
    data = {
        "furbies": furbies,
        "frame_ms": FRAME_MS,
        "size": eyecheck.SIZE,
        "every": plan["every"],
        "scenes": plan["scenes"],
        "timer": [i for i, s in enumerate(plan["scenes"]) if s in show.scenes()],
        "greetings": [i for i, s in enumerate(plan["scenes"]) if s in show.scenes(greeting=True)],
        "timelines": {"typical": timeline(plan, dlcs, False), "worst": timeline(plan, dlcs, True)},
    }
    with open(os.path.join(out_dir, "data.js"), "w") as f:
        f.write("// Written by preview.py; contains nothing to edit.\nwindow.PREVIEW = ")
        json.dump(data, f, separators=(",", ":"))
        f.write(";\n")
    index = os.path.join(out_dir, "index.html")
    shutil.copyfile(TEMPLATE, index)
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--show", default="./build/halloween/show.json", help="the show.json to preview")
    parser.add_argument("--out", default="./build/preview", help="where to write the page")
    parser.add_argument("--open", action="store_true", help="open the page in the default browser")
    args = parser.parse_args(argv)
    if not os.path.exists(args.show):
        raise SystemExit("No %s; build the show first (uv run halloween.py)." % args.show)
    index = os.path.abspath(build_preview(args.show, args.out))
    print("Wrote %s (keep it on this computer: it holds Hasbro-derived audio)." % index)
    print(
        "If the browser won't play it from disk: python3 -m http.server -d %s, then open http://localhost:8000"
        % os.path.dirname(index)
    )
    if args.open:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, index], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
