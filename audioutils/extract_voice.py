#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Decode every audio clip in a DLC to WAV.

Gives you a library of real Furby audio to listen to, remix, or use as a
voice-cloning reference. Clips are decoded with the open-source A1800 codec
(https://github.com/John-K/a1800_codec), so this runs on any OS.

USAGE:
    python audioutils/extract_voice.py                 # stock DLC → build/voice/
    python audioutils/extract_voice.py my.dlc -o out/

Writes track_NNN.wav per clip, plus index.csv listing the input-75 ("App
Videos") actions that play each one. A DLC's clips are app-video content:
the Furby's everyday reactions (loud noises, petting) come from its built-in
personality, so lookups for other inputs land on unrelated clips.
"""

import argparse
import csv
import os
import sys
import wave

import a1800_codec

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from furby import dlc  # noqa: E402
from spooky_eyes import _actions, _tracks  # noqa: E402

RATE = 16000


def extract(dlc_in="./dlc/dlc2/tu003410.dlc", out_dir="./build/voice"):
    D = dlc(dlc_in)
    tracks = D.dlc_sections["AMF"].tracks
    plays = {}
    for code in _actions(D, [75]):
        for t in _tracks(D, code):
            plays.setdefault(t, []).append(".".join(map(str, code)))
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for t, track in enumerate(tracks):
        pcm = bytes(a1800_codec.decode(bytes(track)))
        name = "track_%03d.wav" % t
        with wave.open(os.path.join(out_dir, name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm)
        rows.append([name, t, "%.2f" % (len(pcm) / (2 * RATE)), " ".join(plays.get(t, []))])
    with open(os.path.join(out_dir, "index.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "track", "seconds", "actions"])
        writer.writerows(rows)
    print("Wrote %d clips to %s (see index.csv)" % (len(rows), out_dir))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dlc", nargs="?", default="./dlc/dlc2/tu003410.dlc")
    parser.add_argument("-o", "--out-dir", default="./build/voice")
    args = parser.parse_args()
    extract(args.dlc, args.out_dir)
