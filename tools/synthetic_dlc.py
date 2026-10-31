#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Build a Furby Connect DLC from scratch, with no Hasbro content, for tests and CI.

The repo can't ship Hasbro's stock DLC, but nearly everything here builds on
one: halloween.py swaps clips into its scene slots, spooky_eyes.py replaces its
eyes, emulate.py times its sequences. This writes a stand-in with the same
shape, so all of that can be tested anywhere:

- input 75's actions in the stock layout (index 0, sub-indexes 0-8), with the
  same 24 scene slots, 18 of them quick slots that use a built-in movement and
  6 that use one of the DLC's own motor routines (0xc4xx);
- every other input from 1 to 74, each with one action, as the firmware's
  action table numbers them;
- one sequence and one audio playlist per scene slot, each playing its own
  tone, plus a shared one for the other actions;
- 16 eye playlists laid out as the stock DLC's (8 single-frame ones, then the
  38-frame animation's three layers for each eye, then 2 more), drawn from
  plain generated cels: a ring-shaped eye in four keyframes;
- placeholder lip and motor data, which only furby.py's parser reads.

Its numbers are format facts (counts, offsets, the action codes the show
sends); nothing is copied from a stock DLC. It's never meant to go on a Furby.

USAGE (from the repo root):
    uv run tools/synthetic_dlc.py                  # build/synthetic.dlc
    uv run tools/synthetic_dlc.py -o /tmp/test.dlc
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
from furby import dlc  # noqa: E402

RATE = BITRATE = 16000
INPUTS = 75
# Input 75's sub-indexes and how many actions each holds, as the show's action codes number them
SUBS = [8, 8, 8, 8, 8, 7, 7, 7, 1]
# 75 actions that play their own track: the show's quick slots, then those that run a DLC motor routine
QUICK = [(0, 2), (3, 2), (3, 5), (4, 0), (4, 1), (4, 2), (4, 5), (4, 6), (4, 7),
         (5, 3), (5, 5), (5, 6), (6, 5), (6, 6), (7, 0), (7, 2), (7, 3), (7, 6)]  # fmt: skip
SLOW = [(0, 3), (0, 4), (3, 3), (3, 4), (4, 3), (4, 4)]
SEQ_START = 0x3000  # a sequence's first word
DELAY = 0x1000 | 30  # a pause word: 30 units (0.3 s at emulate.py's assumed 10 ms)
TRACK_SECONDS = 0.8
# The stock layout's 16 eye playlists: (frame count, layer field)
EYE_PLAYLISTS = [(1, 0), (1, 64)] + [(1, 128)] * 6 + [(38, 192)] * 2 + [(38, 262400)] * 2 + [(38, 524608)] * 2 \
    + [(1, 128)] * 2  # fmt: skip
# Palette words: 64×64 at 6 bits a pixel, bits 8-11 the palette slot (one per layer), bit 2 a horizontal flip
EYE, CHILLI, FLAME = 0x10F2, 0x14F2, 0x18F2
FLIP = 0x4
FRAMES = 38
KEYFRAMES = 4
PLAIN_CEL = 17  # spooky_eyes.BLANK_CEL: a cel of one colour
SEQUENCES = 60  # as many as the stock layout, so demo.py's sequence numbers exist
# The sequences demo.py points at our eyes, by number: 75-0-4-4, 75-0-3-4 and 75-0-0-3 (spooky_eyes.DEMO_ACTIONS)
DEMO_SEQUENCES = {(4, 4): 15, (3, 4): 50, (0, 3): 22}
DEMO_EYES = {15: 4, 50: 4, 22: 6}  # the eye words demo.py rewrites in each


def tone(seconds, hz, lead=0.0):
    """A sine tone that swells and fades, after lead seconds of silence, as .a18 bytes.

    The same bytes are an AMF track and an .a18 file: length (counting the 2-byte bitrate), bitrate, frames.
    """
    n, quiet = int(RATE * seconds), int(RATE * lead)
    samples = array(
        "h",
        [0] * quiet
        + [int(12000 * math.sin(math.pi * i / n) * math.sin(2 * math.pi * hz * i / RATE)) for i in range(n)],
    )
    if sys.byteorder == "big":
        samples.byteswap()  # the codec takes little-endian samples
    frames = bytes(a1800_codec.encode(samples.tobytes(), BITRATE))[6:]
    return struct.pack("<IH", len(frames) + 2, BITRATE) + frames


def sequence(playlist, motor, eye_word, eyes):
    """A SEQ entry: its first word, playlist, movement, then eyes eye words with a pause between each, then 0."""
    return [SEQ_START, playlist, motor] + [eye_word, DELAY] * (eyes - 1) + [eye_word, 0]


def write_tone(path, seconds, hz, lead=0.0):
    """tone() as an .a18 file at path; returns path."""
    with open(path, "wb") as f:
        f.write(tone(seconds, hz, lead))
    return path


def palette():
    """64 ARGB colours: 0 see-through, then white, a blue ramp for the iris, and black for the pupil."""
    colours = [(248, 0, 248, 0), (248, 248, 248, 0xFF)]
    colours += [(16, 40 + 3 * i, 120 + 2 * i, 0xFF) for i in range(61)]
    return colours + [(0, 0, 0, 0xFF)]


def eye(key):
    """One 128×128 keyframe as palette indexes: a white eye with a ring-shaped iris that looks side to side."""
    cx = 64 + (-12, 0, 12, 0)[key % 4]
    pixels = []
    for y in range(128):
        row = []
        for x in range(128):
            r = math.hypot(x - 64, y - 64)
            iris = math.hypot(x - cx, y - 64)
            if r > 60:
                row.append(0)
            elif iris < 12:
                row.append(63)
            elif iris < 30:
                row.append(2 + int(60 * (iris - 12) / 18))
            else:
                row.append(1)
        pixels.append(row)
    return pixels


def quarters(pixels):
    """A 128×128 keyframe as its four 64×64 cels: top left, top right, bottom left, bottom right."""
    return [[row[x0 : x0 + 64] for row in pixels[y0 : y0 + 64]] for y0, x0 in ((0, 0), (0, 64), (64, 0), (64, 64))]


def frame(cels, word=EYE, flipped=False):
    """An SPR frame: four cels, each with its palette word, then the terminator.

    flipped sets the flip bit on all but the first quarter, as the stock layout's blank frames do; it only
    matters for a cel that isn't see-through.
    """
    words = []
    for q, c in enumerate(cels):
        words += [c, word | (FLIP if flipped and q else 0)]
    return words + [0xFFFF]


def action_tree(seq_of):
    """XLS's tree for every input, laid out the way furby.py's writer expects, and its length in bytes.

    seq_of maps (input, index, sub-index, specific) to a sequence; the rest play sequence 0.
    """
    shape = {i: [[1]] for i in range(1, INPUTS)}  # input → indexes → specifics per sub-index
    shape[INPUTS] = [SUBS]
    tree = {}
    cursor = 6 * (1 + INPUTS)  # past the count, the entry length and one type-1 entry per input
    for i in range(1, INPUTS + 1):  # type-2: an entry per index
        tree[i] = {"entries": len(shape[i]), "points_at": cursor}
        cursor += 6 * len(shape[i])
    for i in tree:  # type-3: an entry per sub-index
        for j, subs in enumerate(shape[i]):
            tree[i][j] = {"entries": len(subs), "points_at": cursor}
            cursor += 20 * len(subs)
    for i in tree:  # type-4: an entry per specific action
        for j, subs in enumerate(shape[i]):
            for k, count in enumerate(subs):
                tree[i][j][k] = {
                    "entries": count,
                    "points_at": cursor,
                    # 0, 100, the type-4 count and offset, then 5: a callable DLC action, as furby.py reads it
                    "raw": [0, 100, count, cursor >> 1, 5, 0, 0, 0, 0],
                }
                for l in range(count):  # noqa: E741
                    tree[i][j][k][l] = {"vals": (seq_of.get((i, j, k, l), 0), 0, 0, 1, 0)}
                cursor += 10 * count
    return tree, cursor


def build(path, seconds=TRACK_SECONDS):
    """Write the synthetic DLC to path; returns path."""
    D = dlc()
    D.dlc_header = D.HEADER_section()
    sec = {name: getattr(D, name + "_section")() for name in ("PAL", "SPR", "CEL", "XLS", "AMF", "APL", "LPS", "SEQ",
                                                               "MTR")}  # fmt: skip
    D.dlc_sections = sec

    # Audio: a shared track for the actions without a slot, then one per slot, each its own pitch
    slots = QUICK + SLOW
    sec["AMF"].tracks = [tone(seconds, 220)] + [tone(seconds, 300 + 25 * n) for n in range(len(slots))]
    sec["APL"].playlists = [[(t, "AUDIO"), (0xF000, "EOF")] for t in range(len(sec["AMF"].tracks))]

    # Sequences: SEQ_START, its playlist, a movement, then eye animations with a pause between each. demo.py
    # rewrites the eye words of sequences 15, 50 and 22 by number and position, so the actions it names get
    # those, with as many eye words as it rewrites.
    offset = sec["SEQ"].playlist_offset
    count = max(SEQUENCES, len(slots) + 1)
    free = iter(n for n in range(1, count) if n not in DEMO_SEQUENCES.values())
    sequences = [sequence(offset, 0xE000, 0x8003, 2) for _ in range(count)]
    seq_of = {}
    for n, (sub, spec) in enumerate(slots):
        motor = (0xE000 | (n % 41)) if (sub, spec) in QUICK else (0xC400 | (n % 6))
        seq = DEMO_SEQUENCES.get((sub, spec)) or next(free)
        sequences[seq] = sequence(offset + 1 + n, motor, 0x8003 + n, DEMO_EYES.get(seq, 2))
        seq_of[(INPUTS, 0, sub, spec)] = seq
    sec["SEQ"].sequences = sequences
    sec["LPS"].phrases = [[0x1000, 0xFFFF] for _ in sequences]
    sec["MTR"].animations = [[0x1000, 0xF000] for _ in range(6)]
    # furby.py's writer seeks around a zeroed buffer, checking the length that parsing would have set
    sec["XLS"].action_tree, sec["XLS"].length = action_tree(seq_of)

    # Eyes: cel 0 see-through, 1-16 the four keyframes' quarters, 17 plain
    sec["PAL"].palettes = [palette() for _ in range(6)]
    cels = [[[0] * 64 for _ in range(64)]]
    for key in range(KEYFRAMES):
        cels += quarters(eye(key))
    cels.append([[1] * 64 for _ in range(64)])
    assert len(cels) - 1 == PLAIN_CEL
    sec["CEL"].cels = cels
    # Every frame slot gets a frame of its own, as in the stock layout: the eye builders rewrite frames in
    # place, so a shared one would change wherever else it's used.
    frames, playlists = [], []
    for n, (length, layer) in enumerate(EYE_PLAYLISTS):
        for f in range(length):
            if n == 0:
                frames.append(frame([0] * 4, EYE, flipped=True))
            elif n == 1:  # the background: cels 1-4, which the eye builders keep (they rebuild the rest)
                frames.append(frame(range(1, 5)))
            elif length == 1:
                frames.append(frame([0] * 4, EYE | FLIP))
            elif n in (8, 9):  # the eye layer: the keyframes in turn
                key = (f // 4) % KEYFRAMES
                frames.append(frame(range(1 + 4 * key, 5 + 4 * key)))
            else:  # the layers above: see-through
                frames.append(frame([0] * 4, CHILLI if n in (10, 11) else FLAME, flipped=True))
        indices = list(range(len(frames) - length, len(frames)))
        playlists.append({"framecount": length, "layer": layer, "framelist_index": n, "frame_indices": indices})
    sec["SPR"].frames = frames
    sec["SPR"].frame_playlists = playlists

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    D.build(path)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-o", "--out", default="./build/synthetic.dlc")
    args = parser.parse_args(argv)
    path = build(args.out)
    print("Built %s (%d KB)" % (path, os.path.getsize(path) // 1000))
    return path


if __name__ == "__main__":
    main()
