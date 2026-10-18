#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Probe what a Furby actually does with each scene slot: build a test DLC, flash it, play every slot and time it.

The show puts one clip on each spooky_eyes.scene_slots() action, and how long
each slot keeps the Furby busy decides whether the next line plays with its
audio (see furbyshow.Furby.play). These experiments measure that on a real
Furby instead of guessing:

    uv run probe.py build slots                 # each slot says its number, stock sequences
    uv run probe.py build motions e000-e017     # slot N says "move N" and runs motor word N
    uv run probe.py build motions2 e018-e028    # a DLC holds 24 slots, so split long lists
    uv run flash.py build/probe/slots.dlc       # flash it (only that Furby awake)
    uv run probe.py run slots                   # play each slot, time 20:0c → 20:0e
    uv run probe.py run slots --reverse --times 3 --only 2,5,6

A build writes build/probe/<name>.dlc and <name>.json, which maps each slot
number to its action and sequence; run reads that map, so the numbers you hear
match the table. run also works on a show DLC (pink, blue), using show.json's
clips. Each run prints a table and saves it as build/probe/<name>-<time>.json.

What the replies mean: 20:0c is "playing, with audio"; 20:07 is "still busy
with the last sequence", which plays the action without its audio, so run
waits and triggers again (as the show does) and counts the retries; 20:0e is
"sequence ended" and 20:0d "cancelled".
"""

import argparse
import asyncio
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

import furbyshow
from flash import check_name

OUT_DIR = "./build/probe"
STOCK_DLC = "./dlc/dlc2/tu003410.dlc"
SHOW_JSON = "./build/halloween/show.json"
EYES = "demon"  # every probe slot shows this one animation, 0x8401 (the proven layout)


# --- Building ---------------------------------------------------------------


def parse_motors(text):
    """Motor words from "e000-e002,e010" (hex, 0x optional) → [0xe000, 0xe001, 0xe002, 0xe010]."""
    words = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        try:
            lo, hi = int(lo, 16), int(hi or lo, 16)
        except ValueError:
            raise SystemExit("%r isn't a motor word: use hex like e005 or a range like e000-e017" % part) from None
        if not 0 <= lo <= hi <= 0xFFFF:
            raise SystemExit("%r isn't a 16-bit motor word range" % part)
        words += range(lo, hi + 1)
    if not words:
        raise SystemExit("No motor words given; try e000-e017")
    return words


def speak(text, path):
    """Record text as speech at path (no extension); returns the audio file's path."""
    if shutil.which("say"):  # macOS
        out = path + ".aiff"
        subprocess.run(["say", "-r", "170", "-o", out, text], check=True)
        return out
    for tts in ("espeak-ng", "espeak"):
        if shutil.which(tts):
            out = path + ".wav"
            subprocess.run([tts, "-w", out, text], check=True)
            return out
    raise SystemExit(
        "probe.py build needs a text-to-speech command to record each slot's number: macOS's `say`, "
        "or espeak-ng elsewhere (e.g. `sudo apt install espeak-ng`)."
    )


def hexes(words):
    return ["0x%04x" % w for w in words]


def build(name, motors=None, out_dir=OUT_DIR, dlc_in=STOCK_DLC, say=speak):
    """Build a probe DLC and its slot map; returns the DLC's path.

    Without motors, every scene slot says its number and keeps its stock
    sequence, so run measures how long each slot really takes. With motors,
    slot N says "move N" and its sequence becomes [word0, playlist, motor N,
    one eye animation, end], with no delays, so the time is the movement's own.
    """
    from furby import dlc
    from spooky_eyes import FIRST_ANIMATION, _check_size, _seq, scene_slots
    from spooky_eyes import build as build_dlc

    check_name(name)
    slots = scene_slots(dlc(dlc_in))
    if motors is not None and len(motors) > len(slots):
        half = len(motors) // 2
        raise SystemExit(
            "A DLC has %d scene slots, so it can't test %d motor words at once. Split them into two DLCs, "
            "e.g. %04x-%04x and %04x-%04x."
            % (len(slots), len(motors), motors[0], motors[half - 1], motors[half], motors[-1])
        )
    if motors is not None:
        slots = slots[: len(motors)]
    voice_dir = os.path.join(out_dir, name, "say")
    os.makedirs(voice_dir, exist_ok=True)
    lines = ["move %d" % n if motors is not None else str(n) for n in range(1, len(slots) + 1)]
    clips = {code: say(lines[n - 1], os.path.join(voice_dir, "%02d" % n)) for n, code in enumerate(slots, 1)}
    path = build_dlc(EYES, clips=clips, dlc_in=dlc_in, out_dir=out_dir, name=name)

    D = dlc(path)
    seqs = D.dlc_sections["SEQ"].sequences
    stock = dlc(dlc_in).dlc_sections["SEQ"].sequences
    entries = []
    for n, code in enumerate(slots, 1):
        seq = _seq(D, code)
        entry = {"n": n, "action": list(code), "say": lines[n - 1], "was": hexes(stock[seq])}
        if motors is not None:
            seqs[seq] = [seqs[seq][0], seqs[seq][1], motors[n - 1], FIRST_ANIMATION, 0]
        entry["motor"] = "0x%04x" % seqs[seq][2]
        entry["sequence"] = hexes(seqs[seq])
        entries.append(entry)
    if motors is not None:
        D.build(path)
        _check_size(path, "Probe fewer motor words per DLC.")
        built = dlc(path).dlc_sections["SEQ"].sequences  # make sure the edits survive a round trip
        for code, motor in zip(slots, motors, strict=True):
            assert built[_seq(D, code)][2] == motor, "motor word for %s didn't survive the build" % (code,)
    with open(os.path.join(out_dir, name + ".json"), "w") as f:
        json.dump({"name": name, "kind": "motions" if motors is not None else "slots", "slots": entries}, f, indent=1)
    print("Wrote %s with %d slots. Next:" % (path, len(entries)))
    print("  uv run flash.py %s" % path)
    print("  uv run probe.py run %s" % name)
    return path


# --- Running ----------------------------------------------------------------


def load_slots(name, out_dir=OUT_DIR, show_json=SHOW_JSON, dlc_in=STOCK_DLC):
    """The slots to play for a DLC name: its probe map, else show.json's clips, else the stock scene slots."""
    path = os.path.join(out_dir, name + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)["slots"]
    if os.path.exists(show_json):
        with open(show_json) as f:
            furby = json.load(f)["furbies"].get(name)
        if furby:
            return [
                {"n": n, "action": c["action"], "say": clip}
                for n, (clip, c) in enumerate(sorted(furby["clips"].items()), 1)
            ]
    from furby import dlc
    from spooky_eyes import scene_slots

    print("No %s, so playing the stock scene slots in order." % path)
    return [{"n": n, "action": list(code), "say": str(n)} for n, code in enumerate(scene_slots(dlc(dlc_in)), 1)]


class Recorder:
    """Records every status notification (20:xx) from a Furby, with when it arrived."""

    def __init__(self, furby, verbose=False, clock=time.monotonic):
        self.furby, self.clock, self.verbose = furby, clock, verbose
        self.events = []  # (code, time)
        self.changed = asyncio.Event()
        self.t0 = clock()
        original = furby.on_response

        def hook(data):
            data = bytes(data)
            if data[:1] == b"\x20" and len(data) > 1 and data[1] != 0x06:  # 20:06 is the keepalive echo
                self.events.append((data[1], self.clock()))
                self.changed.set()
                if verbose:
                    print("  %7.2f  <- %s" % (self.clock() - self.t0, data.hex(":")), flush=True)
            original(data)

        furby.on_response = hook

    async def wait_for(self, codes, after, timeout):
        """Time of the first notification in codes after `after`, or None after timeout seconds."""
        end = self.clock() + timeout
        while True:
            for code, t in self.events:
                if code in codes and t > after:
                    return code, t
            left = end - self.clock()
            if left <= 0:
                return None, None
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), left)
            except TimeoutError:
                return None, None


async def time_slot(rec, action, patience_ms=furbyshow.PLAY_PATIENCE_MS, end_timeout=40):
    """Play one action and time it from 20:0c to 20:0e; returns a result dict.

    Furby.play() does the retrying on 20:07, exactly as the show does; this
    just watches the notifications around it.
    """
    sent = rec.clock()
    played = await rec.furby.play(tuple(action), patience_ms)
    seen = [(c, t) for c, t in rec.events if t >= sent]
    retries = sum(1 for c, _ in seen if c == 0x07)
    starts = [t for c, t in seen if c == 0x0C]
    if not starts:
        return {"result": "no reply" if played else "busy", "seconds": None, "retries": retries}
    start = starts[-1]
    code, end = await rec.wait_for((0x0E, 0x0D), start, end_timeout)
    if end is None:
        return {"result": "no end", "seconds": None, "retries": retries}
    return {
        "result": "ended" if code == 0x0E else "cancelled",
        "seconds": round(end - start, 2),
        "retries": retries,
        "wait": round(start - sent, 2),  # how long it was busy before this one started
    }


async def sweep(furby, slots, times=1, reverse=False, gap=1.0, settle=5.0, verbose=False, log=print, **kw):
    """Play every slot `times` times; returns [{slot n: result}] per run."""
    rec = Recorder(furby, verbose)
    if settle:
        log("Letting anything already playing finish (%g s)..." % settle)
        await asyncio.sleep(settle)
    order = list(reversed(slots)) if reverse else list(slots)
    runs = []
    for run in range(1, times + 1):
        results = {}
        for slot in order:
            r = await time_slot(rec, slot["action"], **kw)
            results[slot["n"]] = r
            log(
                "run %d  slot %2d  %-13s %-9s %s%s"
                % (
                    run,
                    slot["n"],
                    "-".join(map(str, slot["action"])),
                    slot.get("say", ""),
                    "%.2f s" % r["seconds"] if r["seconds"] is not None else r["result"],
                    "  (%d busy retries)" % r["retries"] if r["retries"] else "",
                )
            )
            await asyncio.sleep(gap)
        runs.append(results)
    return runs


def summarize(slots, runs):
    """One row per slot: its timings across runs, plus min, max and mean."""
    rows = []
    for slot in slots:
        secs = [run[slot["n"]]["seconds"] for run in runs if slot["n"] in run]
        good = [s for s in secs if s is not None]
        rows.append(
            {
                "n": slot["n"],
                "action": slot["action"],
                "say": slot.get("say"),
                "motor": slot.get("motor"),
                "seconds": secs,
                "min": min(good) if good else None,
                "max": max(good) if good else None,
                "mean": round(statistics.mean(good), 2) if good else None,
                "retries": sum(run[slot["n"]]["retries"] for run in runs if slot["n"] in run),
            }
        )
    return rows


def table(rows):
    def fmt(x):
        return "-" if x is None else "%.2f" % x

    lines = ["slot  action        motor   say        min    max   mean  retries"]
    for r in rows:
        lines.append(
            "%4d  %-12s  %-6s  %-9s %5s  %5s  %5s  %7d"
            % (
                r["n"],
                "-".join(map(str, r["action"])),
                (r["motor"] or "")[2:],
                (r["say"] or "")[:9],
                fmt(r["min"]),
                fmt(r["max"]),
                fmt(r["mean"]),
                r["retries"],
            )
        )
    return "\n".join(lines)


async def connect(name, find=None):
    """Connect to the Furby whose active DLC is name, letting go of any others."""
    if find is None:
        import porch

        find = porch.find
    while True:
        for furby in await find([]):
            if furby.name == name:
                return furby
            print("Skipping %s (%s): its active DLC isn't %s.dlc" % (furby, furby.address, name), flush=True)
            await furby.disconnect()
        print("No Furby with %s.dlc active yet. Is it awake, flashed (uv run flash.py), and free of FurBLE?" % name)


async def run(args):
    slots = load_slots(args.name)
    if args.only:
        wanted = {int(n) for n in args.only.split(",")}
        slots = [s for s in slots if s["n"] in wanted]
    try:
        import bleak  # noqa: F401
    except ImportError:
        raise SystemExit("Talking to a Furby needs bleak. Run it with uv: uv run probe.py run %s" % args.name) from None
    furby = await connect(args.name)
    print("Connected to %s (%s)" % (furby, furby.address), flush=True)
    keepalive = asyncio.create_task(furby.keep_alive())
    started = time.strftime("%Y%m%d-%H%M%S")
    try:
        runs = await sweep(furby, slots, args.times, args.reverse, args.gap, args.settle, args.verbose)
    finally:
        keepalive.cancel()
        await furby.disconnect()
    rows = summarize(slots, runs)
    print()
    print(table(rows))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "%s-%s.json" % (args.name, started))
    with open(path, "w") as f:
        json.dump({"name": args.name, "started": started, "reverse": args.reverse, "runs": runs, "rows": rows}, f)
    print("\nSaved %s" % path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build a probe DLC: `build slots` or `build <name> <motor words>`")
    b.add_argument("name", help="DLC name, 8 lowercase letters or digits (e.g. slots, motions)")
    b.add_argument("motors", nargs="?", help="motor words to test, e.g. e000-e017 or e000,e005 (hex)")
    r = sub.add_parser("run", help="play and time each slot of the Furby whose active DLC is <name>")
    r.add_argument("name")
    r.add_argument("--reverse", action="store_true", help="play the slots last to first")
    r.add_argument("--times", type=int, default=1, help="play every slot this many times (default 1)")
    r.add_argument("--only", help="just these slot numbers, e.g. 2,5,6")
    r.add_argument("--gap", type=float, default=1.0, help="seconds between one slot ending and the next")
    r.add_argument("--settle", type=float, default=5.0, help="seconds to wait after connecting")
    r.add_argument("-v", "--verbose", action="store_true", help="print every notification the Furby sends")
    args = parser.parse_args(argv)
    if args.command == "build":
        build(args.name, parse_motors(args.motors) if args.motors else None)
    else:
        check_name(args.name)
        asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
