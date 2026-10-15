#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Build a Halloween DLC: spooky eyes, plus optional custom audio.

Draws two-frame, 128x128, 64-colour eye GIFs with Pillow (the same format as
images/demo_eyes), then builds the DLC the same way as Context's hacked.dlc:
every stock track trimmed to 128 bytes, and the eyes wired to actions
75-0-4-4, 75-0-3-4 and 75-0-0-3 by demo.install_eyes(). Apart from audio, the
result matches FurBLE's hacked.dlc section for section, so it's a known-good
shape to flash.

USAGE:
    python spooky_eyes.py                       # red demon eyes, Imperial March
    python spooky_eyes.py --theme pumpkin
    python spooky_eyes.py --song my_song.mp3 --sting my_scream.wav

The song plays on 75-0-4-4 and the sting on 75-0-3-4, each with the eyes.
Audio can be .a18 or anything ffmpeg reads (converted with
audioutils/encode_a18.py). Flash the output with FurBLE.

A DLC only changes what plays when a phone or computer triggers an action over
Bluetooth: the Furby's own reactions to noise, petting and so on come from its
built-in memory, even with a DLC active. halloween.py builds on this to put a
clip on each of many 75 actions for porch.py to play.
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

from demo import install_eyes
from furby import dlc

SIZE = 128
SCALE = 4  # draw big, then shrink, for smooth edges
TRANSPARENT = 63  # same transparency index as images/demo_eyes
MAX_UPLOAD = 350_000  # bigger DLCs time out mid-upload

# Black → deep red → red → orange → yellow → white: 63 shades, so glows
# survive the 64-colour palette without banding into blocks.
STOPS = [(0, 0, 0), (90, 0, 0), (255, 0, 0), (255, 110, 0), (255, 220, 40), (255, 255, 255)]


def _palette():
    colours = []
    for i in range(TRANSPARENT):
        t = i / (TRANSPARENT - 1) * (len(STOPS) - 1)
        a, b = STOPS[int(t)], STOPS[min(int(t) + 1, len(STOPS) - 1)]
        f = t - int(t)
        colours.append(tuple(round(a[c] + (b[c] - a[c]) * f) for c in range(3)))
    colours.append((0, 0, 0))
    pal = Image.new("P", (1, 1))
    pal.putpalette([v for c in colours for v in c])
    return pal


def _demon(heat, mirror):
    """A glowing red eye with a cat's slit pupil. heat is 0 (dim) to 1 (blazing)."""
    s = SIZE * SCALE
    im = Image.new("RGB", (s, s), "black")
    glow = Image.new("RGB", (s, s), "black")
    ImageDraw.Draw(glow).ellipse([s * 0.08, s * 0.08, s * 0.92, s * 0.92], fill=(255, int(60 * heat), 0))
    im.paste(glow.filter(ImageFilter.GaussianBlur(s * 0.08)))
    d = ImageDraw.Draw(im)
    d.ellipse([s * 0.2, s * 0.2, s * 0.8, s * 0.8], fill=(255, int(30 + 140 * heat), 0))
    slit = 0.07 - 0.04 * heat  # the pupil narrows as the eye flares
    offset = 0.03 if mirror else -0.03  # pupils glance outward, mirrored
    d.ellipse([s * (0.5 - slit + offset), s * 0.22, s * (0.5 + slit + offset), s * 0.78], fill="black")
    return im


def _pumpkin(heat, mirror):
    """A jack-o'-lantern's triangle eye, lit from inside by a flickering candle."""
    s = SIZE * SCALE
    im = Image.new("RGB", (s, s), "black")
    tri = [(s * 0.5, s * 0.15), (s * 0.12, s * 0.82), (s * 0.88, s * 0.82)]
    if mirror:
        tri = [(s - x, y) for x, y in tri]
    flame = Image.new("RGB", (s, s), "black")
    ImageDraw.Draw(flame).polygon(tri, fill=(255, int(120 + 100 * heat), int(40 * heat)))
    im.paste(flame.filter(ImageFilter.GaussianBlur(s * 0.05)))
    ImageDraw.Draw(im).polygon(
        [(x * 0.8 + s * 0.1, y * 0.8 + s * 0.12) for x, y in tri], fill=(255, int(180 + 60 * heat), int(60 * heat))
    )
    return im


THEMES = {"demon": _demon, "pumpkin": _pumpkin}


def draw_eyes(theme, out_dir):
    """Write one GIF per frame for each eye; returns ([left frames], [right frames]).

    Frames are separate files because Pillow's animated-GIF writer crops later
    frames and gives them their own palette, and the Furby needs every frame
    full-size on one shared palette. preview.gif is just for looking at.
    """
    os.makedirs(out_dir, exist_ok=True)
    pal = _palette()
    eyes, previews = [], []
    for side, mirror in (("left", False), ("right", True)):
        paths = []
        for n, heat in enumerate((0.3, 1.0)):
            frame = THEMES[theme](heat, mirror).resize((SIZE, SIZE), Image.LANCZOS)
            path = os.path.join(out_dir, "%s_%d.gif" % (side, n))
            frame.quantize(palette=pal, dither=Image.Dither.NONE).save(path, optimize=False, transparency=TRANSPARENT)
            paths.append(path)
            if side == "left":
                previews.append(Image.new("RGB", (SIZE * 2 + 16, SIZE)))
            previews[n].paste(frame, (0 if side == "left" else SIZE + 16, 0))
        eyes.append(paths)
    previews[0].save(
        os.path.join(out_dir, "preview.gif"), save_all=True, append_images=previews[1:], duration=250, loop=0
    )
    return eyes


def _actions(D, inputs):
    """Every fully specified action code under the given inputs, e.g. 20 → (20, 0, 1, 0)."""
    tree = D.dlc_sections["XLS"].action_tree
    sequences = len(D.dlc_sections["SEQ"].sequences)

    def kids(node):
        return [k for k in node if isinstance(k, int)]

    # Some actions point past this DLC's sequences (they live elsewhere); skip them.
    return [
        (i, a, b, c)
        for i in inputs
        for a in kids(tree[i])
        for b in kids(tree[i][a])
        for c in kids(tree[i][a][b])
        if tree[i][a][b][c].get("seq", sequences) < sequences
    ]


def _tracks(D, code):
    """AMF track numbers an action plays (the same lookup replace_audio() does)."""
    seq = D.dlc_sections["XLS"].action_tree[code[0]][code[1]][code[2]][code[3]]["seq"]
    apl = D.dlc_sections["SEQ"].sequences[seq][1] - D.dlc_sections["SEQ"].playlist_offset
    return [t[0] for t in D.dlc_sections["APL"].playlists[apl] if t[1] == "AUDIO"]


def _a18(path, work_dir):
    """Return path as .a18, converting any other audio format on the fly."""
    if path.endswith(".a18"):
        return path
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "audioutils"))
    from encode_a18 import encode

    out = os.path.join(work_dir, os.path.splitext(os.path.basename(path))[0] + ".a18")
    encode(path, out)
    return out


def scene_slots(D):
    """75 actions that each play one track that no other 75 action plays.

    Each can hold its own clip without it turning up under another action.
    75-0-4-4 and 75-0-3-4 (the song and sting) are among them.
    """

    def seq(c):
        return D.dlc_sections["XLS"].action_tree[c[0]][c[1]][c[2]][c[3]]["seq"]

    actions = _actions(D, [75])
    tracks = [t for c in actions for t in _tracks(D, c)]
    seqs = [seq(c) for c in actions]
    return [
        c
        for c in actions
        if len(_tracks(D, c)) == 1 and tracks.count(_tracks(D, c)[0]) == 1 and seqs.count(seq(c)) == 1
    ]


def build(
    theme="demon", song=None, sting=None, clips=None, dlc_in="./dlc/dlc2/tu003410.dlc", out_dir="./build", name=None
):
    """Build the DLC; returns its path.

    clips: {action code: audio file}, each played with the eyes. Use actions
    from scene_slots() so no clip plays under another action.
    """
    work_dir = os.path.join(out_dir, name or theme)
    left, right = draw_eyes(theme, work_dir)

    D = dlc(dlc_in)
    D.dlc_sections["AMF"].minify_audio(128)

    if song:
        D.replace_audio((75, 0, 4, 4), [_a18(song, work_dir)])
    if sting:
        D.replace_audio((75, 0, 3, 4), [_a18(sting, work_dir)])
    install_eyes(D, left, right)
    for code, clip in (clips or {}).items():
        D.replace_audio(code, [_a18(clip, work_dir)])
        D.trigger_custom_graphics(code)

    dlc_out = os.path.join(out_dir, "%s.dlc" % (name or "spooky_%s" % theme))
    D.build(dlc_out)
    size = os.path.getsize(dlc_out)
    if size > MAX_UPLOAD:
        raise SystemExit(
            "%s is %d KB; uploads time out above about %d KB. Use shorter or fewer clips."
            % (dlc_out, size // 1000, MAX_UPLOAD // 1000)
        )
    print("Built %s (%d KB)." % (dlc_out, size // 1000))
    return dlc_out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--theme", choices=sorted(THEMES), default="demon")
    parser.add_argument("--song", default="./audio/new_audio/imperial_march-16000_wav.a18", help="audio for 75-0-4-4")
    parser.add_argument("--sting", default="./audio/new_audio/darkside_wav.a18", help="audio for 75-0-3-4")
    parser.add_argument("--no-song", action="store_true", help="leave 75-0-4-4 and 75-0-3-4 alone, to save space")
    parser.add_argument("--out-dir", default="./build")
    args = parser.parse_args()
    if args.no_song:
        args.song = args.sting = None
    build(args.theme, args.song, args.sting, out_dir=args.out_dir)
