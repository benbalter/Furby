#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Check a DLC's custom eyes offline, before flashing a Furby.

Our own previews (spooky_eyes.render()) draw what we meant: the custom frames
on one layer, through the palette we wrote. This draws what the Furby
composes, from the DLC alone:

- An eye word 0x84NN plays the DLC's animation NN: SPR playlists 8*NN to
  8*NN+7. Those are four layers, bottom to top, each a right-eye playlist
  (even) and a left-eye playlist (odd).
- Each layer's frames are four 64x64 quarter-cels (TL, TR, BL, BR). Pixel
  index 0 is transparent, so lower layers show through.
- A quarter's attribute word is a SunPlus PPU sprite attribute: bit 2 flips
  it horizontally, the low byte otherwise says 64x64 at 6 bits a pixel, and
  bits 8-11 pick one of four 64-colour hardware palette slots.
- A playlist's layer field says which DLC palette to load, (layer & 0xffff) // 64.

Two rules for a quarter's palette fit Hasbro's DLCs, and nothing yet says
which one the firmware uses: the playlist's own layer field ("layer", which
furby-connect-eyes-extract renders the firmware's eye files with), or the
hardware slot in the attribute word, loaded from that layer's playlist
("slot"). check() renders with both and needs both to come out as intended.

It also checks the DLC against the envelope custom eyes are known to work in
on a Furby (16 SPR playlists, a stock-sized SPR). probe.dlc broke that: it had
32 playlists, and what the Furby showed matches its frames and palette drawn
over an earlier DLC's cels (--stale-cel renders that prediction).

Prior art: furby-connect-eyes-extract (lib-fluff-so, no stated license; its
compositing rules reimplemented here) and furby-connect-emulator (thatuser84,
MIT), whose emu/furby_display.py and docs pin down the CEL/PAL/SPR formats
and show the firmware drawing playlist 8 through the PPU's sprite path.

USAGE:
    python eyecheck.py build/halloween/pink.dlc build/halloween/blue.dlc
    python eyecheck.py probe.dlc --gif build/eyecheck     # what the Furby should draw
    python eyecheck.py probe.dlc --stale-cel pink.dlc      # ...if the cels don't load
"""

import argparse
import os
import sys

from PIL import Image

from furby import dlc

SIZE = 128
QUARTERS = ((0, 0), (64, 0), (0, 64), (64, 64))  # (x, y) of TL, TR, BL, BR
PLAYLISTS_PER_ANIMATION = 8
FIRST_DLC_WORD, LAST_DLC_WORD = 0x8400, 0x84FF
H_FLIP = 0x0004
SPRITE_6BPP_64 = 0xF2  # an attribute word's low byte without the flip bit: 64x64, 6 bits a pixel
MAX_FRAMES = 95  # the longest playlist in the firmware's own eye files
RULES = ("layer", "slot")

# The envelope custom eyes are known to work in on a Furby. Each limit comes
# from a DLC tested on hardware; relax one here once a probe shows more works.
# - Hasbro's tu003410.dlc, demo.install_eyes() (Context's hacked.dlc) and
#   spooky_eyes' single-animation DLCs all have 16 playlists and a 5,460-byte
#   SPR, and draw their eyes.
# - probe.dlc (32 playlists, a 20,820-byte SPR, 263 KB) showed blue, green and
#   red arcs in a cross (described, not compared pixel for pixel). Composing
#   its frames and palette over an earlier DLC's cels (the demon eyes, or
#   Hasbro's stock eye and chilli) gives that; its own cels give clean digits.
#   So, inferred: its CEL section never replaced the old one. What triggers
#   that is open: the playlist count, the SPR size or the file size (the
#   biggest custom DLC known to show its eyes is 239 KB). eyesa.dlc (32
#   playlists, 180 KB) separates playlists from file size; probe_long.dlc (16
#   playlists, a 10,476-byte SPR) separates playlists from SPR size.
PROVEN_PLAYLISTS = 16
PROVEN_SPR_BYTES = 5460
PROVEN_DLC_BYTES = 239_262  # spooky_demon.dlc; Hasbro's own are bigger, but come through the app


def animation_playlists(word):
    """The SPR playlists eye word 0x84NN plays: 8*NN to 8*NN+7."""
    return list(
        range((word - FIRST_DLC_WORD) * PLAYLISTS_PER_ANIMATION, (word - FIRST_DLC_WORD + 1) * PLAYLISTS_PER_ANIMATION)
    )


def dlc_words(D):
    """Every DLC eye word (0x84NN) the DLC's sequences play, sorted."""
    return sorted({w for s in D.dlc_sections["SEQ"].sequences for w in s[3:-1] if FIRST_DLC_WORD <= w <= LAST_DLC_WORD})


def _slot(attr):
    return (attr >> 8 & 0xF) // 4


def _palette_index(S, playlists, playlist, attr, rule):
    if rule == "layer":
        return (S.frame_playlists[playlist]["layer"] & 0xFFFF) // 64
    # "slot": the attribute word's hardware slot, which the animation's layer
    # (pair of playlists) of that number loads from its layer field.
    layer = playlists[2 * _slot(attr) + playlist % 2]
    return (S.frame_playlists[layer]["layer"] & 0xFFFF) // 64


def compose(D, word, eye="right", rule="layer", cels=None):
    """Eye word `word` as the Furby composes it: a list of 128x128 RGB frames.

    eye: "right" (even playlists) or "left" (odd). rule: how a quarter picks
    its palette (see RULES). cels: another DLC's CEL list to draw with, to
    predict what shows if the DLC's own cels don't load. A cel index past the
    end draws magenta.
    """
    S, P = D.dlc_sections["SPR"], D.dlc_sections["PAL"].palettes
    cels = D.dlc_sections["CEL"].cels if cels is None else cels
    playlists = animation_playlists(word)
    layers = [p for p in playlists if p % 2 == (eye == "left") and p < len(S.frame_playlists)]
    length = max([len(S.frame_playlists[p]["frame_indices"]) for p in layers] + [0])
    tiles = {}

    def tile(cel, attr, pal):
        key = (cel, attr & H_FLIP, pal)
        if key not in tiles:
            if cel >= len(cels):
                tiles[key] = (Image.new("RGB", (64, 64), (255, 0, 255)), None)
            else:
                im = Image.new("P", (64, 64))
                im.putdata([v for row in cels[cel] for v in row])
                if attr & H_FLIP:
                    im = im.transpose(Image.FLIP_LEFT_RIGHT)
                mask = im.point(lambda v: 255 if v else 0, "L")
                im.putpalette([c for colour in P[pal % len(P)] for c in colour[:3]])
                tiles[key] = (im.convert("RGB"), mask)
        return tiles[key]

    frames = []
    for i in range(length):
        im = Image.new("RGB", (SIZE, SIZE))
        for p in layers:
            indices = S.frame_playlists[p]["frame_indices"]
            if not indices:
                continue
            frame = S.frames[indices[min(i, len(indices) - 1)]]  # a short layer holds its last frame
            for q, xy in enumerate(QUARTERS):
                cel, attr = frame[2 * q], frame[2 * q + 1]
                pixels, mask = tile(cel, attr, _palette_index(S, playlists, p, attr, rule))
                im.paste(pixels, xy, mask)
        frames.append(im)
    return frames


def first_mismatch(frames, expected):
    """Index of the first frame that differs from expected (or of a missing one), or None."""
    for i in range(max(len(frames), len(expected))):
        if i >= len(frames) or i >= len(expected) or frames[i].tobytes() != expected[i].convert("RGB").tobytes():
            return i
    return None


def envelope(D):
    """Ways the DLC's eyes leave what's been seen working on a Furby: (errors, warnings)."""
    S, cels = D.dlc_sections["SPR"], D.dlc_sections["CEL"].cels
    errors, warnings = [], []
    n = len(S.frame_playlists)
    if n != PROVEN_PLAYLISTS:
        errors.append(
            "%d SPR playlists: only %d-playlist DLCs have shown their own eyes; probe.dlc's 32 showed the "
            "previous DLC's cels. Use one eye animation (show.toml: one_eye_animation = true)." % (n, PROVEN_PLAYLISTS)
        )
    S.__compile__()  # the size it builds to, after any edits
    size = len(S.rawbytes)
    if size > PROVEN_SPR_BYTES:
        errors.append(
            "SPR is %d bytes; every DLC whose eyes have worked has a %d-byte SPR (38-frame animations). "
            "Use eye_frames = 38." % (size, PROVEN_SPR_BYTES)
        )
    for word in dlc_words(D):
        missing = [p for p in animation_playlists(word) if p >= n]
        if missing:
            errors.append(
                "Sequences play 0x%04x, but the SPR has no playlists %d-%d." % (word, missing[0], missing[-1])
            )
    for p, pl in enumerate(S.frame_playlists):
        if pl["framecount"] > MAX_FRAMES:
            errors.append(
                "Playlist %d has %d frames; the firmware's own top out at %d." % (p, pl["framecount"], MAX_FRAMES)
            )
        for f in sorted(set(pl["frame_indices"])):
            frame = S.frames[f]
            for q in range(4):
                cel, attr = frame[2 * q], frame[2 * q + 1]
                if cel >= len(cels):
                    errors.append("Playlist %d frame %d quarter %d uses cel %d of %d." % (p, f, q, cel, len(cels)))
                if attr & 0xFF & ~H_FLIP != SPRITE_6BPP_64:
                    errors.append(
                        "Playlist %d frame %d quarter %d has attribute 0x%04x, not a 64x64 6-bit sprite."
                        % (p, f, q, attr)
                    )
    return errors, warnings


def intended(D, word, eye="right"):
    """What we meant an eye to show: the custom frames' layer (the third) on its own, through palette 5.

    That's the layer spooky_eyes and demo.install_eyes() draw on, and the
    palette spooky_eyes.render() previews with.
    """
    S, CEL = D.dlc_sections["SPR"], D.dlc_sections["CEL"].cels
    palette = [c[:3] for c in D.dlc_sections["PAL"].palettes[5]]
    playlist = animation_playlists(word)[4 + (eye == "left")]
    frames = []
    for f in S.frame_playlists[playlist]["frame_indices"]:
        im = Image.new("RGB", (SIZE, SIZE))
        for q, xy in enumerate(QUARTERS):
            cel = S.frames[f][2 * q]
            tile = Image.new("RGB", (64, 64))
            tile.putdata([palette[v] for row in CEL[cel] for v in row] if cel < len(CEL) else [(255, 0, 255)] * 4096)
            im.paste(tile, xy)
        frames.append(im)
    return frames


def check(D, expected=None):
    """Errors and warnings for a DLC's custom eyes.

    expected: {(eye word, "right" or "left"): frames} each eye should show;
    by default intended() for every animation the sequences play. An eye that
    doesn't match under any palette rule is an error; one that matches under
    only some is a warning, since which rule the firmware uses isn't known.
    """
    errors, warnings = envelope(D)
    n = len(D.dlc_sections["SPR"].frame_playlists)
    if expected is None:
        words = [w for w in dlc_words(D) if max(animation_playlists(w)) < n]
        expected = {(w, eye): intended(D, w, eye) for w in words for eye in ("right", "left")}
    for (word, eye), want in sorted(expected.items()):
        bad = {rule: first_mismatch(compose(D, word, eye, rule), want) for rule in RULES}
        bad = {rule: i for rule, i in bad.items() if i is not None}
        if len(bad) == len(RULES):
            errors.append(
                "0x%04x's %s eye doesn't render as intended (from frame %d)." % (word, eye, min(bad.values()))
            )
        elif bad:
            warnings.append(
                "0x%04x's %s eye renders as intended only if the firmware's palette rule isn't %s "
                "(differs from frame %d)." % (word, eye, " or ".join(repr(r) for r in bad), min(bad.values()))
            )
    return errors, warnings


def save_gif(eyes, path, ms=66):
    """Eyes (lists of frames) side by side at twice their size, as an animated GIF (at a guessed frame rate)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    w = SIZE * 2
    sheets = []
    for i in range(max(len(e) for e in eyes)):
        sheet = Image.new("RGB", (len(eyes) * (w + 16) - 16, w), (40, 40, 40))
        for k, e in enumerate(eyes):
            if e:
                sheet.paste(e[min(i, len(e) - 1)].resize((w, w), Image.NEAREST), (k * (w + 16), 0))
        sheets.append(sheet)
    sheets[0].save(path, save_all=True, append_images=sheets[1:], duration=ms, loop=0)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dlcs", nargs="+", help="DLC files to check")
    parser.add_argument("--gif", metavar="DIR", help="write each animation's right eye as the Furby composes it")
    parser.add_argument(
        "--stale-cel", metavar="DLC", help="with --gif: draw with this DLC's cels (the one flashed before)"
    )
    args = parser.parse_args(argv)
    stale = dlc(args.stale_cel).dlc_sections["CEL"].cels if args.stale_cel else None
    failed = False
    for path in args.dlcs:
        D = dlc(path)
        errors, warnings = check(D)
        if os.path.getsize(path) > PROVEN_DLC_BYTES:
            warnings.append(
                "%d KB is bigger than any custom DLC whose eyes have shown (%d KB); probe.dlc, at 263 KB, "
                "showed old cels." % (os.path.getsize(path) // 1000, PROVEN_DLC_BYTES // 1000)
            )
        name = os.path.splitext(os.path.basename(path))[0]
        print("%s: %s" % (path, "FAIL" if errors else "ok"))
        for e in errors:
            print("  error: " + e)
        for w in warnings:
            print("  warning: " + w)
        failed = failed or bool(errors)
        if args.gif:
            for word in dlc_words(D):
                if max(animation_playlists(word)) < len(D.dlc_sections["SPR"].frame_playlists):
                    for rule in RULES:
                        eyes = [compose(D, word, eye, rule, stale) for eye in ("left", "right")]
                        out = "%s_%04x_%s%s.gif" % (name, word, rule, "_stale" if stale else "")
                        print("  " + save_gif(eyes, os.path.join(args.gif, out)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
