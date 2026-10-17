#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Build a Halloween DLC: animated spooky eyes, plus optional custom audio.

Draws each eye theme with Pillow as a few 128x128 keyframes, then plays them
across a whole animation timeline (38 frames, the stock animation's length)
in a pattern of its own: a pulse, a candle flicker, a lightning strike. The
DLC is built the same way as Context's hacked.dlc: every stock track trimmed
to 128 bytes, the stock eye layers blanked, and the custom frames on the top
layer of the DLC's animation 1 (eye word 0x8401), which plays on actions
75-0-4-4, 75-0-3-4 and 75-0-0-3.

Several themes can go in one DLC: each extra theme becomes its own animation
(0x8402, 0x8403, ...), a copy of animation 1's layout. That part is inferred
from how the firmware's own eye files are laid out, not yet seen on a Furby:
see --probe. Prior art: lib-fluff-so/furby-connect-eyes-extract worked out
the 8-playlists-per-animation grouping by rendering the firmware's files, and
taituo/fluffkit (MIT) spreads a few keyframes over the 38 frames and shares
identical cels; this reimplements both ideas on furby.py's model.

USAGE:
    python spooky_eyes.py                       # red demon eyes, Imperial March
    python spooky_eyes.py --theme pumpkin
    python spooky_eyes.py --song my_song.mp3 --sting my_scream.wav
    python spooky_eyes.py --preview             # build/eyes/<theme>.gif for every theme
    python spooky_eyes.py --probe               # a test DLC that answers what's unverified

The song plays on 75-0-4-4 and the sting on 75-0-3-4, each with the eyes.
Audio can be .a18 or anything ffmpeg reads (converted with
audioutils/encode_a18.py). Flash the output with FurBLE.

A DLC only changes what plays when a phone or computer triggers an action over
Bluetooth: the Furby's own reactions to noise, petting and so on come from its
built-in memory, even with a DLC active. halloween.py builds on this to put a
clip on each of many 75 actions for porch.py to play.
"""

import argparse
import math
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from furby import dlc

SIZE = 128
SCALE = 4  # draw big, then shrink, for smooth edges
COLOURS = 63  # palette index 0 is kept transparent, as in the stock palettes
MAX_UPLOAD = 350_000  # bigger DLCs time out mid-upload
FRAMES = 38  # frames per animation: the stock animation's length, the only one tested on a Furby
MAX_FRAMES = 95  # the longest animation in the firmware's own eye files
FRAME_MS = 66  # preview speed only: a guess (furby-connect-eyes-extract's), not measured on a Furby
FIRST_ANIMATION = 0x8401  # eye word for the DLC's animation 1; 0x8402 is animation 2, and so on
BLANK_CEL = 17  # a plain cel in the stock DLC, copied to cel 1 for the blanked layers (as demo.py does)


def _canvas():
    s = SIZE * SCALE
    return Image.new("RGB", (s, s), "black"), s


def _glow(im, shape, fill, blur, **kw):
    """Paint a blurred shape onto im, brightening it (a glow)."""
    layer = Image.new("RGB", im.size, "black")
    getattr(ImageDraw.Draw(layer), shape)(fill=fill, **kw)
    return ImageChops.add(im, layer.filter(ImageFilter.GaussianBlur(blur)))


def _demon(heat):
    """A glowing red eye with a cat's slit pupil. heat is 0 (dim) to 1 (blazing)."""
    im, s = _canvas()
    im = _glow(im, "ellipse", (255, int(60 * heat), 0), s * 0.08, xy=[s * 0.08, s * 0.08, s * 0.92, s * 0.92])
    d = ImageDraw.Draw(im)
    d.ellipse([s * 0.2, s * 0.2, s * 0.8, s * 0.8], fill=(255, int(30 + 140 * heat), 0))
    slit = 0.07 - 0.04 * heat  # the pupil narrows as the eye flares
    d.ellipse([s * (0.5 - slit), s * 0.22, s * (0.5 + slit), s * 0.78], fill="black")
    return im


def _pumpkin(heat):
    """A jack-o'-lantern's triangle eye, lit from inside by a flickering candle."""
    im, s = _canvas()
    tri = [(s * 0.5, s * 0.15), (s * 0.12, s * 0.82), (s * 0.88, s * 0.82)]
    im = _glow(im, "polygon", (255, int(90 + 130 * heat), int(40 * heat)), s * (0.03 + 0.04 * heat), xy=tri)
    ImageDraw.Draw(im).polygon(
        [(x * 0.8 + s * 0.1, y * 0.8 + s * 0.12) for x, y in tri],
        fill=(int(220 + 35 * heat), int(100 + 140 * heat), int(10 + 50 * heat)),
    )
    return im


def _bolt(s, seed):
    """A jagged lightning bolt from the top edge to the bottom, as polyline points."""
    rnd = random.Random(seed)
    x, pts = s * 0.55, []
    for i in range(9):
        pts.append((x, s * i / 8))
        x = min(max(x + rnd.uniform(-0.14, 0.14) * s, s * 0.2), s * 0.8)
    return pts


def _storm(phase):
    """A cold blue storm eye. phase 0: brooding; 1: lightning strikes; 2: the flash whites everything out."""
    im, s = _canvas()
    if phase == 2:
        im = _glow(im, "ellipse", (170, 200, 255), s * 0.15, xy=[-s * 0.2, -s * 0.2, s * 1.2, s * 1.2])
    im = _glow(im, "ellipse", (20, 60, 200), s * 0.08, xy=[s * 0.1, s * 0.1, s * 0.9, s * 0.9])
    d = ImageDraw.Draw(im)
    iris = (60, 140, 255) if phase else (30, 90, 220)
    d.ellipse([s * 0.22, s * 0.22, s * 0.78, s * 0.78], fill=iris)
    d.ellipse([s * 0.3, s * 0.3, s * 0.7, s * 0.7], fill=(150, 210, 255) if phase else (70, 140, 240))
    d.ellipse([s * 0.42, s * 0.42, s * 0.58, s * 0.58], fill="black")
    if phase == 1:
        bolt = _bolt(s, 7)
        im = _glow(im, "line", (120, 160, 255), s * 0.04, xy=bolt, width=int(s * 0.08))
        ImageDraw.Draw(im).line(bolt, fill="white", width=int(s * 0.03), joint="curve")
    return im


def _bloodshot(gaze):
    """A bloodshot eyeball with a red slit pupil that darts about. gaze is -1 (left) to 1 (right)."""
    im, s = _canvas()
    d = ImageDraw.Draw(im)
    d.ellipse([s * 0.04, s * 0.04, s * 0.96, s * 0.96], fill=(235, 215, 200))
    rnd = random.Random(3)  # the same veins in every frame
    for _ in range(14):
        a = rnd.uniform(0, 2 * math.pi)
        r, x, y = s * 0.46, 0.0, 0.0
        x, y = s / 2 + r * math.cos(a), s / 2 + r * math.sin(a)
        for _ in range(5):
            a += rnd.uniform(-0.6, 0.6)
            step = s * rnd.uniform(0.04, 0.08)
            nx, ny = x - step * math.cos(a), y - step * math.sin(a)
            d.line([(x, y), (nx, ny)], fill=(190, 20, 30), width=int(s * 0.012))
            x, y = nx, ny
    im = im.filter(ImageFilter.GaussianBlur(s * 0.004))
    cx = s * (0.5 + 0.17 * gaze)
    im = _glow(im, "ellipse", (255, 0, 0), s * 0.03, xy=[cx - s * 0.24, s * 0.26, cx + s * 0.24, s * 0.74])
    d = ImageDraw.Draw(im)
    d.ellipse([cx - s * 0.2, s * 0.3, cx + s * 0.2, s * 0.7], fill=(200, 0, 10))
    d.ellipse([cx - s * 0.14, s * 0.36, cx + s * 0.14, s * 0.64], fill=(255, 60, 20))
    d.ellipse([cx - s * 0.035, s * 0.31, cx + s * 0.035, s * 0.69], fill="black")
    # Clip to the eyeball, on black.
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).ellipse([s * 0.04, s * 0.04, s * 0.96, s * 0.96], fill=255)
    return Image.composite(im, Image.new("RGB", im.size, "black"), mask)


def _ghost(bob):
    """A friendly little ghost that bobs up and down. bob is 0 (low) to 1 (high)."""
    im, s = _canvas()
    y = s * (0.0 - 0.07 * bob)
    body = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(body)
    d.ellipse([s * 0.2, s * 0.1 + y, s * 0.8, s * 0.7 + y], fill=255)
    d.rectangle([s * 0.2, s * 0.4 + y, s * 0.8, s * 0.8 + y], fill=255)
    for i in range(4):  # a wavy hem, which shifts as it bobs
        cx = s * (0.275 + 0.15 * i + 0.03 * bob)
        d.ellipse([cx - s * 0.075, s * 0.73 + y, cx + s * 0.075, s * 0.88 + y], fill=0 if i % 2 else 255)
    im = _glow(im, "ellipse", (60, 120, 90), s * 0.08, xy=[s * 0.12, s * 0.06 + y, s * 0.88, s * 0.9 + y])
    im.paste((235, 255, 245), mask=body)
    d = ImageDraw.Draw(im)
    for ex in (0.38, 0.62):
        d.ellipse([s * (ex - 0.06), s * 0.32 + y, s * (ex + 0.06), s * 0.48 + y], fill=(20, 20, 30))
    d.ellipse([s * 0.44, s * 0.52 + y, s * 0.56, s * 0.64 + y], fill=(20, 20, 30))  # "oooo"
    return im


def _hypno(turn):
    """A three-armed hypnotic spiral, turned by turn thirds of an arm (so frames loop seamlessly)."""
    im, s = _canvas()
    d = ImageDraw.Draw(im)
    for arm in range(3):
        pts = []
        for i in range(120):
            t = i / 119
            a = 2 * math.pi * (arm / 3 + turn / 9) + t * 3.2 * math.pi
            r = s * 0.48 * t
            pts.append((s / 2 + r * math.cos(a), s / 2 + r * math.sin(a)))
        d.line(pts, fill=(150, 60, 255), width=int(s * 0.07), joint="curve")
    im = im.filter(ImageFilter.GaussianBlur(s * 0.006))
    return _glow(im, "ellipse", (120, 255, 80), s * 0.03, xy=[s * 0.43, s * 0.43, s * 0.57, s * 0.57])


def _digit(n, colour):
    """A big seven-segment digit, for --probe."""
    im, s = _canvas()
    segs = {"a": (0, 0, 1, 0), "b": (1, 0, 1, 1), "c": (1, 1, 1, 2), "d": (0, 2, 1, 2), "e": (0, 1, 0, 2)}
    segs.update({"f": (0, 0, 0, 1), "g": (0, 1, 1, 1)})
    lit = ["abcdef", "bc", "abdeg", "abcdg", "bcfg", "acdfg", "acdefg", "abc", "abcdefg", "abcdfg"][n]
    d = ImageDraw.Draw(im)
    for seg in lit:
        x0, y0, x1, y1 = segs[seg]
        d.line(
            [(s * (0.3 + 0.4 * x0), s * (0.12 + 0.38 * y0)), (s * (0.3 + 0.4 * x1), s * (0.12 + 0.38 * y1))],
            fill=colour,
            width=int(s * 0.1),
        )
    return im


def _repeat(pattern, frames):
    return [pattern[i % len(pattern)] for i in range(frames)]


# Each theme: a function that draws one keyframe from a parameter, the
# parameters for its keyframes, and which keyframe each frame of the timeline
# shows (repeated to fill the timeline). Every keyframe costs about 25 KB of
# the DLC, so themes get their motion from the order of a few keyframes.
THEMES = {
    "demon": {  # a slow, smouldering pulse
        "draw": _demon,
        "keys": (0.25, 0.6, 1.0),
        "pattern": [0] * 5 + [1] * 3 + [2] * 8 + [1] * 3,
    },
    "pumpkin": {  # a candle guttering in the wind
        "draw": _pumpkin,
        "keys": (0.1, 0.55, 1.0),
        "pattern": [2, 2, 1, 2, 2, 2, 0, 1, 2, 2, 1, 1, 2, 2, 2, 1, 0, 1, 2, 2, 2, 2, 1, 2, 1, 2, 2, 0, 1, 2, 2, 2, 1],
    },
    "storm": {  # brooding, then a double lightning strike
        "draw": _storm,
        "keys": (0, 1, 2),
        "pattern": [0] * 14 + [2, 1, 1, 0, 0, 2, 1, 0] + [0] * 16,
    },
    "bloodshot": {  # stares, then darts to one side and the other
        "draw": _bloodshot,
        "keys": (0, -1, 1),
        "pattern": [0] * 10 + [1] * 7 + [0] * 4 + [2] * 7 + [0] * 3 + [1, 1, 2, 2, 0, 0, 0],
    },
    "ghost": {  # bobs gently
        "draw": _ghost,
        "keys": (0, 0.5, 1),
        "pattern": [0, 0, 0, 1, 1, 2, 2, 2, 2, 1, 1, 0],
    },
    "hypno": {  # spins
        "draw": _hypno,
        "keys": (0, 1, 2),
        "pattern": [0, 0, 1, 1, 2, 2],
    },
}

# What a Furby shows when show.toml gives it a theme but no eyes list.
MIXES = {"demon": ["demon", "bloodshot", "storm"], "pumpkin": ["pumpkin", "ghost", "hypno"]}


def keyframes(theme):
    """The theme's keyframes, as 128x128 RGB images."""
    t = THEMES[theme]
    return [t["draw"](k).resize((SIZE, SIZE), Image.LANCZOS) for k in t["keys"]]


def timeline(theme, frames=FRAMES):
    """Which keyframe each of the animation's frames shows."""
    return _repeat(THEMES[theme]["pattern"], frames)


def _palette(images, zero=(248, 0, 248, 0)):
    """One palette for every frame: index 0 (unused; `zero`, by default transparent), then COLOURS colours.

    Returns (palette as 64 (R, G, B, A) tuples, each image as a list of palette indices).
    """
    strip = Image.new("RGB", (SIZE, SIZE * len(images)))
    for i, im in enumerate(images):
        strip.paste(im, (0, SIZE * i))
    # k-means keeps glows smooth where plain median cut bands them.
    rgb = strip.quantize(colors=COLOURS, method=Image.Quantize.MEDIANCUT, kmeans=5).getpalette()[: COLOURS * 3]
    rgb = [v & 0xF8 for v in rgb]  # the Furby keeps 5 bits a channel, so dither against what it shows
    rgb += rgb[:3] * (COLOURS - len(rgb) // 3)
    pal = Image.new("P", (1, 1))
    pal.putpalette(rgb + rgb[:3] * (256 - COLOURS))  # padding repeats colour 0, which wins ties
    palette = [zero] + [(rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2], 0xFF) for i in range(COLOURS)]
    # Each image dithers on its own, so identical areas stay identical and share cels.
    return palette, [[(p if p < COLOURS else 0) + 1 for p in im.quantize(palette=pal).tobytes()] for im in images]


def _quarters(pixels):
    """A 128x128 image's palette indices as its TL, TR, BL, BR 64x64 cels (lists of rows)."""
    half = SIZE // 2
    return [
        [pixels[(y0 + y) * SIZE + x0 : (y0 + y) * SIZE + x0 + half] for y in range(half)]
        for y0, x0 in ((0, 0), (0, half), (half, 0), (half, half))
    ]


def _set_frames(S, playlist, frames):
    """Point a playlist at these frames (each 4 x (cel, ref)), reusing its own frame slots first."""
    p = S.frame_playlists[playlist]
    slots = p["frame_indices"][: len(frames)]
    while len(slots) < len(frames):
        S.frames.append(None)
        slots.append(len(S.frames) - 1)
    for i, frame in zip(slots, frames, strict=True):
        S.frames[i] = [w for quarter in frame for w in quarter] + [S.t3_terminator]
    p["frame_indices"], p["framecount"] = slots, len(slots)


def _add_cels(cels, frames, dedup="frame"):
    """Append each frame's 4 quarter cels to cels; returns each frame's 4 cel numbers.

    dedup "frame" stores an identical frame once, as 4 consecutive cels, the
    way every frame demo.install_eyes() writes looks (and that shows on a
    Furby). "quarter" also shares identical quarters, even within a frame,
    e.g. TL and BL both black: frames like (2, 3, 2, 4), which the Furby
    showed offset and duplicated. "none" stores every frame.
    """
    index, out = {}, []
    for quarters in frames:
        if dedup == "quarter":
            numbers = []
            for q in quarters:
                key = bytes(v for row in q for v in row)
                if key not in index:
                    index[key] = len(cels)
                    cels.append(q)
                numbers.append(index[key])
        else:
            key = bytes(v for q in quarters for row in q for v in row)
            if dedup == "none" or key not in index:
                index[key] = len(cels)
                cels.extend(quarters)
            numbers = list(range(index[key], index[key] + 4))
        out.append(numbers)
    return out


def install_animations(D, animations, zero=(248, 0, 248, 0), dedup="frame", share=False):
    """Put animations on the DLC's eyes; returns the eye word for each (0x8401, 0x8402, ...).

    animations: a list of (keyframes, timeline) pairs, keyframes being 128x128
    RGB images and timeline the keyframe each frame shows (so its length is
    the animation's). Both eyes show the same image, but each eye has its own
    copy of the cels (left eye's first, as demo.install_eyes() does): every
    probe whose eyes shared cels (eyesb, eyese, eyesh) showed garbled digits
    on a Furby. Those also all had under 16 cels, so which of the two broke
    them is open (eyesk and eyesl split it). share=True shares them anyway,
    to rebuild those probes.

    The first animation takes the place of the stock one (SPR playlists 8-15),
    laid out exactly as demo.install_eyes() does, which has run on a Furby:
    the stock eye and chilli layers blanked to a plain cel, and the frames on
    the flame layer (playlist 12 right, 13 left). Each later animation is a
    copy of that one's 8 playlists, appended after it. Every frame shares one
    palette, written to both palette slots the layout uses, so it works
    whichever of the playlist's layer field or the frame's palette word
    picks the palette (that's not settled).
    """
    for _, order in animations:
        if not FRAMES <= len(order) <= MAX_FRAMES:
            raise SystemExit("Animations can be %d to %d frames, not %d." % (FRAMES, MAX_FRAMES, len(order)))
    CEL, S, PAL = D.dlc_sections["CEL"], D.dlc_sections["SPR"], D.dlc_sections["PAL"]
    palette, pixels = _palette([k for keys, _ in animations for k in keys], zero)
    PAL.palettes[4][:] = palette
    PAL.palettes[5][:] = palette

    CEL.cels = CEL.cels[:1] + [[row[:] for row in CEL.cels[BLANK_CEL]]]
    quarters = [_quarters(p) for p in pixels]
    left_cels = _add_cels(CEL.cels, quarters, dedup)
    right_cels = left_cels if share else _add_cels(CEL.cels, quarters, dedup)

    # The palette words demo.install_eyes() uses, from the stock frames.
    refs = sorted({w for f in S.frames for w in f[1:8:2]})
    eye_ref, left_ref, right_ref = refs[0], refs[2], refs[4]
    blank = [(1, eye_ref)] * 4
    first = 8  # animation 1's first playlist
    template = [dict(S.frame_playlists[first + k]) for k in range(S.channels_per_anim)]
    del S.frame_playlists[first + S.channels_per_anim :]

    words, offset = [], 0
    for n, (keys, order) in enumerate(animations):
        base = first + n * S.channels_per_anim
        for k, t in enumerate(template):
            if base + k >= len(S.frame_playlists):
                S.frame_playlists.append(dict(t, frame_indices=[], framelist_index=base + k))
        right = [right_cels[offset + i] for i in order]
        left = [left_cels[offset + i] for i in order]
        offset += len(keys)
        for k in range(6):  # eye, chilli and flame layers, right and left
            if k == 4:
                _set_frames(S, base + k, [[(c, right_ref) for c in f] for f in right])
            elif k == 5:
                _set_frames(S, base + k, [[(c, left_ref) for c in f] for f in left])
            else:
                _set_frames(S, base + k, [blank] * len(order))
        if n:  # the top layer: a copy of animation 1's one transparent frame
            for k in (6, 7):
                _set_frames(S, base + k, [[(0, refs[1])] * 4])
        words.append(FIRST_ANIMATION + n)
    return words


def render(D, word=FIRST_ANIMATION):
    """One eye of an animation as the Furby should show it, from the DLC's own data: a list of RGB frames.

    Draws the flame layer (where the frames go) with palette 5, the slot both
    of the layout's palette words point at.
    """
    S, CEL, PAL = D.dlc_sections["SPR"], D.dlc_sections["CEL"], D.dlc_sections["PAL"]
    palette = [c[:3] for c in PAL.palettes[5]]
    playlist = 8 + (word - FIRST_ANIMATION) * S.channels_per_anim + 4
    frames = []
    for f in S.frame_playlists[playlist]["frame_indices"]:
        im = Image.new("RGB", (SIZE, SIZE))
        for q, (y0, x0) in enumerate(((0, 0), (0, 64), (64, 0), (64, 64))):
            tile = Image.new("RGB", (64, 64))
            tile.putdata([palette[p] for row in CEL.cels[S.frames[f][2 * q]] for p in row])
            im.paste(tile, (x0, y0))
        frames.append(im)
    return frames


def save_preview(frames, path, zoom=2):
    """Both eyes side by side, at zoom x their size, as an animated GIF (at a guessed frame rate)."""
    w = SIZE * zoom
    sheet = []
    for f in frames:
        big = f.resize((w, w), Image.NEAREST)
        im = Image.new("RGB", (w * 2 + 8 * zoom, w), (40, 40, 40))
        im.paste(big, (0, 0))
        im.paste(big, (w + 8 * zoom, 0))
        sheet.append(im)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sheet[0].save(path, save_all=True, append_images=sheet[1:], duration=FRAME_MS, loop=0)
    return path


def preview(theme, out_dir="./build/eyes", frames=FRAMES):
    """Write <theme>.gif (the timeline, through a 63-colour palette) and <theme>.png (its keyframes)."""
    keys = keyframes(theme)
    palette, pixels = _palette(keys)
    shown = []
    for p in pixels:
        im = Image.new("RGB", (SIZE, SIZE))
        im.putdata([palette[i][:3] for i in p])
        shown.append(im)
    sheet = Image.new("RGB", (SIZE * 2 * len(keys) + 8 * (len(keys) - 1), SIZE * 2), (40, 40, 40))
    for i, im in enumerate(shown):
        sheet.paste(im.resize((SIZE * 2, SIZE * 2), Image.NEAREST), (i * (SIZE * 2 + 8), 0))
    os.makedirs(out_dir, exist_ok=True)
    sheet.save(os.path.join(out_dir, "%s.png" % theme))
    return save_preview([shown[i] for i in timeline(theme, frames)], os.path.join(out_dir, "%s.gif" % theme))


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


def _seq(D, code):
    return D.dlc_sections["XLS"].action_tree[code[0]][code[1]][code[2]][code[3]]["seq"]


def _tracks(D, code):
    """AMF track numbers an action plays (the same lookup replace_audio() does)."""
    apl = D.dlc_sections["SEQ"].sequences[_seq(D, code)][1] - D.dlc_sections["SEQ"].playlist_offset
    return [t[0] for t in D.dlc_sections["APL"].playlists[apl] if t[1] == "AUDIO"]


def eye_words(D, code):
    """The eye animations an action's sequence plays, in order."""
    return [w for w in D.dlc_sections["SEQ"].sequences[_seq(D, code)][3:-1] if w >> 12 in (0x8, 0xA)]


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
    actions = _actions(D, [75])
    tracks = [t for c in actions for t in _tracks(D, c)]
    seqs = [_seq(D, c) for c in actions]
    return [
        c
        for c in actions
        if len(_tracks(D, c)) == 1 and tracks.count(_tracks(D, c)[0]) == 1 and seqs.count(_seq(D, c)) == 1
    ]


DEMO_ACTIONS = [(75, 0, 4, 4), (75, 0, 3, 4), (75, 0, 0, 3)]  # where demo.py's eyes play


def _check_size(path, hint):
    size = os.path.getsize(path)
    if size > MAX_UPLOAD:
        raise SystemExit(
            "%s is %d KB; uploads time out above about %d KB. %s" % (path, size // 1000, MAX_UPLOAD // 1000, hint)
        )
    return size


def build(
    theme="demon",
    song=None,
    sting=None,
    clips=None,
    dlc_in="./dlc/dlc2/tu003410.dlc",
    out_dir="./build",
    name=None,
    eyes=None,
    frames=FRAMES,
):
    """Build the DLC; returns its path.

    clips: {action code: audio file}, each played with the eyes. Use actions
    from scene_slots() so no clip plays under another action.
    eyes: {action code: theme} for clips that show another theme than `theme`.
    Each theme becomes its own animation; `theme` is animation 1 (0x8401), the
    one that has run on a Furby. frames: each animation's length.
    """
    eyes = eyes or {}
    themes = [theme] + sorted(set(eyes.values()) - {theme})
    for t in themes:
        if t not in THEMES:
            raise SystemExit("No eye theme %r; there's %s." % (t, ", ".join(sorted(THEMES))))
    work_dir = os.path.join(out_dir, name or theme)
    os.makedirs(work_dir, exist_ok=True)

    D = dlc(dlc_in)
    D.dlc_sections["AMF"].minify_audio(128)

    if song:
        D.replace_audio((75, 0, 4, 4), [_a18(song, work_dir)])
    if sting:
        D.replace_audio((75, 0, 3, 4), [_a18(sting, work_dir)])
    words = dict(zip(themes, install_animations(D, [(keyframes(t), timeline(t, frames)) for t in themes]), strict=True))
    for code in DEMO_ACTIONS:
        D.trigger_custom_graphics(code, words[theme])
    for code, clip in (clips or {}).items():
        D.replace_audio(code, [_a18(clip, work_dir)])
        D.trigger_custom_graphics(code, words[eyes.get(code, theme)])

    dlc_out = os.path.join(out_dir, "%s.dlc" % (name or "spooky_%s" % theme))
    D.build(dlc_out)
    size = _check_size(dlc_out, "Use shorter or fewer clips, or fewer eye themes (each costs about 74 KB).")
    built = dlc(dlc_out)
    for t, w in words.items():
        save_preview(render(built, w), os.path.join(work_dir, "eyes_%s.gif" % t))
    print(
        "Built %s (%d KB): eyes %s. Previews in %s."
        % (dlc_out, size // 1000, ", ".join("%s = 0x%04x" % (t, w) for t, w in words.items()), work_dir)
    )
    return dlc_out


# --probe's test DLCs, one question each, every digit unique so a photo says
# which animation it came from. {file: (animations, actions, how)}. Each
# animation is (digits, frames, colour): the digits count up across its
# frames on solid black. actions maps an action to the animation it shows.
# how: "multi" is install_animations() with palette index 0 opaque black;
# "single" is the same with one animation (one_eye_animation); "demo" is the
# old path that has shown eyes on a Furby: GIFs through demo.install_eyes().
# The first probe.dlc (several animations, index 0 transparent) showed
# scrambled blue, red and green tiles instead of digits on every action.
RED, GREEN, CYAN = (255, 40, 20), (40, 255, 60), (40, 230, 255)
BLACK = (0, 0, 0, 0xFF)
EVERY = [(75, 0, 4, 4), (75, 0, 3, 4), (75, 0, 0, 3), (75, 0, 4, 2)]
DEMO_ORDER = [0] * 10 + [1] * 9 + [0] * 10 + [1] * 9  # demo.install_eyes()'s 2-frame split
PROBE = {
    # Round 2: eyesc showed red 1-2 cleanly; eyesb's digits were "there ish, but offset and duplicated".
    "eyesa.dlc": (
        [("12", FRAMES, RED), ("34", FRAMES, GREEN), ("5678", 2 * FRAMES, CYAN)],
        {(75, 0, 4, 4): 0, (75, 0, 3, 4): 1, (75, 0, 0, 3): 2, (75, 0, 4, 2): 0},
        ("multi", {"dedup": "quarter", "share": True}),
    ),
    "eyesb.dlc": ([("12", FRAMES, RED)], dict.fromkeys(EVERY, 0), ("single", {"dedup": "quarter", "share": True})),
    "eyesc.dlc": ([("12", FRAMES, RED)], dict.fromkeys(DEMO_ACTIONS, 0), ("demo", {})),
    # Round 3: eyesc plus one of eyesb's changes each.
    "eyesd.dlc": ([("12", FRAMES, RED)], dict.fromkeys(DEMO_ACTIONS, 0), ("layout", {"palette": "kmeans"})),
    "eyese.dlc": ([("12", FRAMES, RED)], dict.fromkeys(DEMO_ACTIONS, 0), ("layout", {"share": True})),
    "eyesf.dlc": ([("12", FRAMES, RED)], dict.fromkeys(DEMO_ACTIONS, 0), ("layout", {"dedup": "quarter"})),
    "eyesg.dlc": ([("12", FRAMES, RED)], dict.fromkeys(DEMO_ACTIONS, 0), ("layout", {"order": "halves"})),
    # The new pipeline with whole-frame dedup only: eyesb minus the suspected cause.
    "eyesh.dlc": ([("12", FRAMES, RED)], dict.fromkeys(EVERY, 0), ("single", {"dedup": "frame", "share": True})),
    # Round 4: eyesf passed (a cel repeated within a frame is fine); eyese and eyesh, whose eyes share
    # cels, came out garbled. But every garbled probe also had under 16 cels (eyesb 9, eyese and eyesh 10;
    # eyesf 16, eyesc 18), and Hasbro's own DLC shares cels between its eyes. eyesk and eyesl split the two.
    "eyesi.dlc": ([("12", FRAMES, RED)], dict.fromkeys(EVERY, 0), ("single", {})),
    "eyesj.dlc": (
        [("12", FRAMES, RED), ("34", FRAMES, GREEN), ("5", FRAMES, CYAN)],
        {(75, 0, 4, 4): 0, (75, 0, 3, 4): 1, (75, 0, 0, 3): 2, (75, 0, 4, 2): 0},
        ("multi", {}),
    ),
    "eyesk.dlc": ([("12", FRAMES, RED)], dict.fromkeys(DEMO_ACTIONS, 0), ("layout", {"share": True, "pad": 8})),
    "eyesl.dlc": ([("1", FRAMES, RED)], dict.fromkeys(DEMO_ACTIONS, 0), ("layout", {})),
}


def _ramp():
    """The palette the old draw_eyes() used: 63 shades black → red → yellow → white, then black."""
    stops = [(0, 0, 0), (90, 0, 0), (255, 0, 0), (255, 110, 0), (255, 220, 40), (255, 255, 255)]
    colours = []
    for i in range(63):
        t = i / 62 * (len(stops) - 1)
        a, b = stops[int(t)], stops[min(int(t) + 1, len(stops) - 1)]
        colours.append(tuple(round(a[c] + (b[c] - a[c]) * (t - int(t))) for c in range(3)))
    pal = Image.new("P", (1, 1))
    pal.putpalette([v for c in colours + [(0, 0, 0)] for v in c])
    return pal


def _demo_gifs(keys, work_dir):
    """Keyframes as single-frame GIFs on one palette, the way the old draw_eyes() wrote them."""
    os.makedirs(work_dir, exist_ok=True)
    pal, paths = _ramp(), []
    for n, key in enumerate(keys):
        path = os.path.join(work_dir, "frame_%d.gif" % n)
        key.quantize(palette=pal, dither=Image.Dither.NONE).save(path, optimize=False, transparency=63)
        paths.append(path)
    return paths


def install_layout(D, keys, work_dir, palette="ramp", share=False, dedup="none", order="demo", pad=0):
    """demo.install_eyes()'s layout for 2 keyframes, with one of install_animations()' changes switchable.

    With the defaults it builds the same DLC as demo.install_eyes() on GIFs
    from _demo_gifs(): cels 2-9 left eye, 10-17 right, each frame's 4 cels
    consecutive, palettes 4 (left) and 5 (right), the 10/9/10/9 split.
    palette "kmeans": install_animations()' palette (index 0 black).
    share: both eyes use the left eye's cels. dedup "quarter": identical
    quarters share a cel, even within a frame. order "halves": 19 frames of
    each keyframe, as install_animations() plays 2 keyframes. pad: add that
    many unused cels at the end. One keyframe shows for the whole animation.
    """
    CEL, S, PAL = D.dlc_sections["CEL"], D.dlc_sections["SPR"], D.dlc_sections["PAL"]
    if palette == "ramp":
        gifs = _demo_gifs(keys, work_dir)
        colours = PAL.extract_palette(gifs[0])
        frames = [CEL.quarterize(g) for g in gifs]
    else:
        colours, pixels = _palette(keys, BLACK)
        frames = [_quarters(p) for p in pixels]
    PAL.palettes[4][:] = colours
    PAL.palettes[5][:] = colours
    CEL.cels[1] = [row[:] for row in CEL.cels[BLANK_CEL]]
    CEL.cels = CEL.cels[:2]
    left = _add_cels(CEL.cels, frames, dedup)
    right = left if share else _add_cels(CEL.cels, frames, dedup)
    CEL.cels.extend([row[:] for row in CEL.cels[0]] for _ in range(pad))
    refs = sorted({w for f in S.frames for w in f[1:8:2]})
    shown = DEMO_ORDER if order == "demo" else [i * len(keys) // FRAMES for i in range(FRAMES)]
    shown = [min(i, len(keys) - 1) for i in shown]
    for p in range(8, 12):
        _set_frames(S, p, [[(1, refs[0])] * 4] * FRAMES)
    _set_frames(S, 12, [[(c, refs[4]) for c in right[i]] for i in shown])
    _set_frames(S, 13, [[(c, refs[2]) for c in left[i]] for i in shown])
    for code in DEMO_ACTIONS:
        D.trigger_custom_graphics(code)
    return [FIRST_ANIMATION]


def build_probe(dlc_in="./dlc/dlc2/tu003410.dlc", out_dir="./build/eyes_probe2", only=None):
    """DLCs of numbered test animations that answer what's unverified about eyes; returns their paths."""
    from demo import install_eyes

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for name, (anims, actions, (how, opts)) in PROBE.items():
        if only and name not in only:
            continue
        animations = []
        for digits, frames, colour in anims:
            keys = [_digit(int(d), colour).resize((SIZE, SIZE), Image.LANCZOS) for d in digits]
            animations.append((keys, [i * len(digits) // frames for i in range(frames)]))
        D = dlc(dlc_in)
        D.dlc_sections["AMF"].minify_audio(128)
        work_dir = os.path.join(out_dir, name[:-4])
        if how == "demo":
            gifs = _demo_gifs(animations[0][0], work_dir)
            install_eyes(D, gifs, gifs)  # shows frame 0 for frames 0-9 and 19-28, frame 1 for the rest
            words = [FIRST_ANIMATION]
        elif how == "layout":
            words = install_layout(D, animations[0][0], work_dir, **opts)
        else:
            words = install_animations(D, animations, BLACK, **opts)
            for code, n in actions.items():
                D.trigger_custom_graphics(code, words[n])
        path = os.path.join(out_dir, name)
        D.build(path)
        _check_size(path, "Use fewer probe digits.")
        built = dlc(path)
        for w in words:
            save_preview(render(built, w), os.path.join(out_dir, "%s_%04x.gif" % (name[:-4], w)))
        print("Built %s (%d KB, %s %s):" % (path, os.path.getsize(path) // 1000, how, opts))
        for code, n in actions.items():
            digits, frames, _ = anims[n]
            print("  %s  0x%04x, %d frames: digits %s" % ("-".join(map(str, code)), words[n], frames, digits))
        paths.append(path)
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--theme", choices=sorted(THEMES), default="demon")
    parser.add_argument("--song", default="./audio/new_audio/imperial_march-16000_wav.a18", help="audio for 75-0-4-4")
    parser.add_argument("--sting", default="./audio/new_audio/darkside_wav.a18", help="audio for 75-0-3-4")
    parser.add_argument("--no-song", action="store_true", help="leave 75-0-4-4 and 75-0-3-4 alone, to save space")
    parser.add_argument("--frames", type=int, default=FRAMES, help="frames per animation (default %d)" % FRAMES)
    parser.add_argument("--preview", action="store_true", help="write build/eyes/<theme>.gif for every theme")
    parser.add_argument("--probe", action="store_true", help="build DLCs that test what's unverified")
    parser.add_argument("--out-dir", default="./build")
    args = parser.parse_args()
    if args.preview:
        for t in sorted(THEMES):
            print(preview(t, os.path.join(args.out_dir, "eyes"), args.frames))
    elif args.probe:
        build_probe(out_dir=os.path.join(args.out_dir, "eyes_probe2"))
    else:
        if args.no_song:
            args.song = args.sting = None
        build(args.theme, args.song, args.sting, out_dir=args.out_dir, frames=args.frames)
