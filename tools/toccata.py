#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Render the opening of Bach's Toccata in D minor (BWV 565) from its notes, for the show's toccata clip.

Bach's score has been in the public domain for centuries, but a recording of
it belongs to whoever performed it. So rather than ship a recording, this
plays the opening bars from the notes below with a simple additive organ (a
few sine harmonics with a soft attack and release) and writes a 16 kHz mono
WAV, the rate the Furby's audio uses. No soundfont or sample library goes in,
so there's nothing else to license. It won't fool an organist, but through a
Furby's speaker the opening is unmistakable.

The notes follow the opening as it's usually played: the mordent on A and the
falling run to a held D, three times, an octave lower each time; then a low D
under a diminished chord that climbs and settles on D minor. Durations are
approximate and in seconds.

USAGE (from the repo root):
    uv run tools/toccata.py      # audio/new_audio/toccata_bwv565_opening.wav, the file the show uses
"""

import argparse
import math
import os
import struct
import wave

RATE = 16000
OUT = "./audio/new_audio/toccata_bwv565_opening.wav"
HARMONICS = [(1, 1.0), (2, 0.5), (3, 0.3), (4, 0.15), (6, 0.08)]  # (multiple of the note, loudness)
NAMES = {"C": 0, "C#": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "Bb": 10, "B": 11}


def hz(note):
    """A note name such as "A5" or "C#3" as its frequency."""
    name, octave = note[:-1], int(note[-1])
    return 440 * 2 ** ((NAMES[name] + 12 * (octave + 1) - 69) / 12)


def phrase(octave, start):
    """The opening phrase an octave down from the top: (start, seconds, notes) events, and when it ends."""
    o, low = str(octave), str(octave - 1)
    events, t = [], start
    for note, seconds in [("A", 0.13), ("G", 0.13), ("A", 1.1)]:  # the mordent, then the held A
        events.append((t, seconds, [note + o, note + low]))
        t += seconds
    t += 0.15
    for note, seconds in [("G", 0.12), ("F", 0.12), ("E", 0.12), ("D", 0.12), ("C#", 0.5)]:
        events.append((t, seconds, [note + o, note + low]))
        t += seconds
    events.append((t, 1.3, ["D" + o, "D" + low]))
    return events, t + 1.3 + 0.35


def score():
    """Every (start, seconds, notes) event of the opening."""
    events, t = [], 0.0
    for octave in (5, 4, 3):
        more, t = phrase(octave, t)
        events += more
    pedal = 3.2
    events.append((t, pedal, ["D2"]))  # the low D, held under the chord
    for k, note in enumerate(["C#3", "E3", "G3", "Bb3", "C#4", "E4"]):  # the diminished chord, climbing
        events.append((t + 0.14 * k, 2.0 - 0.14 * k, [note]))
    events.append((t + 2.0, pedal - 2.0 + 1.0, ["D3", "F3", "A3", "D4"]))  # settling on D minor
    return events


def render(events):
    """Mix the events into 16-bit samples."""
    end = max(start + seconds for start, seconds, _ in events) + 0.5
    mix = [0.0] * int(RATE * end)
    for start, seconds, notes in events:
        n = int(RATE * seconds)
        first = int(RATE * start)
        for note in notes:
            f = hz(note)
            for i in range(n):
                attack = min(1.0, i / (0.02 * RATE))
                release = min(1.0, (n - i) / (0.06 * RATE))
                x = 2 * math.pi * f * i / RATE
                mix[first + i] += attack * release * sum(a * math.sin(m * x) for m, a in HARMONICS if m * f < RATE / 2)
    peak = max(abs(v) for v in mix) or 1
    return [int(26000 * v / peak) for v in mix]


def write(path=OUT):
    """Render the opening to a WAV at path; returns path."""
    samples = render(score())
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-o", "--out", default=OUT)
    args = parser.parse_args(argv)
    path = write(args.out)
    print("Wrote %s (%d KB)" % (path, os.path.getsize(path) // 1000))


if __name__ == "__main__":
    main()
