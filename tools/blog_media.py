#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Render the Halloween blog post's images, loops and sample audio from the repo's own generators.

Everything is rendered into build/blog/ (gitignored), then the finished files
are copied into --out at the paths the blog serves them from, with a
manifest.json beside public/ (its file paths are relative to --out):

    <out>/public/video/furby-halloween/<id>.mp4, .webm, .jpg (H.264 + VP9 loops, a poster)
    <out>/public/assets/img/furby-halloween-<id>-<W>x<H>.png (or .gif)
    <out>/public/audio/furby-halloween/scene-sample.m4a
    <out>/manifest.json: [{id, files, width, height, alt, caption, kind}]

It wraps what's already here rather than redrawing it: spooky_eyes.preview()
for the eyes, voices.py for stand-in voice lines, halloween.build_show() and
emulate.simulate() for the pacing chart and the sample audio, and the stock
DLC (read, never shipped) for the DLC anatomy.

Audio policy. Nothing derived from Hasbro audio goes in. The blog's show is
halloween/show.toml with every build/cloned/ voice line pointed at a folder of
its own, emptied and remade by voices.py on every run. Audio that ships (the
sample .m4a) may only be:
  - espeak-ng stand-ins, made this run in build/blog/voices-espeak/, or
  - Freesound effects in build/sfx/ listed in its credits.csv, which only
    audioutils/freesound_fetch.py writes, and it fetches CC0 sounds only.
macOS's say voices are licensed for personal, non-commercial use only, so
with --voices say (or without espeak-ng) the lines are made with say for the
pacing chart's timing alone, and the sample audio is skipped. Copyrighted
music is pointed at an empty folder, so its scenes drop out. The DLCs built
along the way stay in build/. Anything else stops the script.

Photosensitivity: every video is checked for more than 3 flashes a second in
any part of the frame, and the script fails rather than ship one.

USAGE (from the repo root):
    uv run tools/blog_media.py --out ~/projects/benbalter.github.com
    uv run tools/blog_media.py --out /tmp/media --only eyes-themes --only architecture
    uv run tools/blog_media.py --list
"""

import argparse
import contextlib
import copy
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)

WORK = "build/blog"
ESPEAK_VOICES = WORK + "/voices-espeak"
SAY_VOICES = WORK + "/voices-say"  # never ships: Apple licenses its voices for personal, non-commercial use
SFX = "build/sfx"
# NO_MUSIC is where the blog's show.toml points copyrighted music: always empty, so those optional clips drop out
NO_MUSIC = WORK + "/no-music"
# The blog's DLCs never leave build/, so they may also use the repo's Toccata, whose recording has no stated license
BUILD_AUDIO = (ESPEAK_VOICES + "/", SAY_VOICES + "/", SFX + "/", "audio/new_audio/", NO_MUSIC + "/")
MAX_VIDEO_BYTES = 1_500_000
MAX_FLASHES_PER_S = 3  # the photosensitivity limit the EyeLights tests hold to, too
# WCAG 2's general flash: a swing of 10% in relative luminance (linear light, not gamma-encoded luma)
FLASH_SWING = 0.10
PINK, BLUE = (194, 51, 122), (47, 111, 208)  # passes the dataviz palette checks on the light card
INK, MUTED, CARD, RULE = (29, 29, 31), (92, 92, 102), (251, 250, 247), (214, 211, 204)
GREY = (120, 120, 128)  # legend swatches that stand for both Furbies
NIGHT = (20, 20, 22)
# A scene with an effect and two stand-in lines, for the pacing chart and the sample audio
SAMPLE_SCENE = ["blue.door", "pink.scream", "blue.gotcha"]


# ---- helpers ------------------------------------------------------------------


def font(size, mono=False, bold=False):
    """A system font at this size, or Pillow's own if there's none."""
    from PIL import ImageFont

    # SF and Menlo have the arrows; Helvetica doesn't
    names = ["/System/Library/Fonts/Menlo.ttc", "DejaVuSansMono.ttf"] if mono else ["/System/Library/Fonts/SFNS.ttf"]
    names.append("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    for name in names:
        with contextlib.suppress(OSError):
            f = ImageFont.truetype(name, size, index=1 if bold and name.endswith(".ttc") else 0)
            with contextlib.suppress(OSError, ValueError):  # a variable font: pick its weight
                f.set_variation_by_name("Bold" if bold else "Regular")
            return f
    return ImageFont.load_default(size)


def _rel(path):
    """path relative to the repo, after following symlinks, with / separators."""
    return os.path.relpath(os.path.realpath(path), ROOT).replace(os.sep, "/")


def cc0_effects():
    """The effects freesound_fetch.py (CC0 only) fetched: file names listed in build/sfx/credits.csv."""
    try:
        with open(os.path.join(SFX, "credits.csv"), newline="", encoding="utf-8") as f:
            return {row[0] for row in csv.reader(f) if row}
    except FileNotFoundError:
        return set()


def check_audio(path, ship=True):
    """Stop unless this audio may be used: shipped (ship=True) or only built into the blog's DLCs."""
    rel = _rel(path)
    if not ship:
        if not rel.startswith(BUILD_AUDIO):
            raise SystemExit(
                "%s isn't audio the blog's show may use; only audio under %s." % (rel, ", ".join(BUILD_AUDIO))
            )
        return path
    if rel.startswith(SAY_VOICES + "/"):
        raise SystemExit(
            "%s was made with macOS's say, whose voices are for personal, non-commercial use only, so it can't "
            "ship. Install espeak-ng (brew install espeak-ng) and run this again with --voices espeak." % rel
        )
    if rel.startswith(ESPEAK_VOICES + "/"):
        return path
    if rel.startswith(SFX + "/") and "/" not in rel[len(SFX) + 1 :] and os.path.basename(rel) in cc0_effects():
        return path
    raise SystemExit(
        "%s can't ship: only espeak-ng stand-ins in %s/ and CC0 effects listed in %s/credits.csv can."
        % (rel, ESPEAK_VOICES, SFX)
    )


def ffmpeg(*args):
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit("ffmpeg failed: %s" % " ".join(e.cmd)) from None


def flashes_per_second(frames, fps, grid=(6, 4), swing=FLASH_SWING):
    """The most flashes in any one second, in any region of the frame, with the frames looping.

    A flash is a pair of opposing swings in a region's mean relative luminance (0-1, linear light) of at
    least swing, as WCAG 2 counts them. Each region is tracked from its last extreme, so a slow fade counts
    once, not on every frame. Regions (a 6×4 grid, about half an eye in eyes-themes) are well under WCAG's
    area threshold, which errs strict; much finer, and the pumpkin's candle edge alone counts as flashing.
    """
    from PIL import ImageStat

    cols, rows = grid
    w, h = frames[0].size
    linear = [(v / 255) ** 2.2 * 255 for v in range(256)]  # sRGB-encoded luma to linear light, roughly
    lumas = []
    for im in frames:
        grey = im.convert("L").point(lambda v: round(linear[v]))
        lumas.append(
            [
                ImageStat.Stat(
                    grey.crop((c * w // cols, r * h // rows, (c + 1) * w // cols, (r + 1) * h // rows))
                ).mean[0]
                / 255
                for r in range(rows)
                for c in range(cols)
            ]
        )
    window = max(1, round(fps))
    worst = 0.0
    for region in range(cols * rows):
        series = [f[region] for f in lumas] * 3  # three loops, so a window can wrap around the end
        swings, lo, hi, direction = [], series[0], series[0], 0  # direction: of the last swing
        for i, v in enumerate(series):
            if direction >= 0:  # watching for a drop from the highest point since the last swing
                hi = max(hi, v)
                if hi - v >= swing:
                    swings.append(i)
                    direction, lo = -1, v
                    continue
            if direction <= 0:  # watching for a rise from the lowest point
                lo = min(lo, v)
                if v - lo >= swing:
                    swings.append(i)
                    direction, hi = 1, v
        for k, start in enumerate(swings):
            in_window = [i for i in swings[k:] if i < start + window]
            worst = max(worst, len(in_window) // 2)
    return worst


def encode_video(frames, fps, base):
    """frames (PIL images) as base.mp4 (H.264), base.webm (VP9) and base.jpg (the poster); returns the paths.

    Stops if the loop flashes more than MAX_FLASHES_PER_S times a second anywhere in the frame.
    """
    flashes = flashes_per_second(frames, fps)
    if flashes > MAX_FLASHES_PER_S:
        raise SystemExit(
            "%s flashes %d times a second somewhere in the frame, over the limit of %d for photosensitive viewers."
            % (os.path.basename(base), flashes, MAX_FLASHES_PER_S)
        )
    even = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    with tempfile.TemporaryDirectory() as tmp:
        for i, im in enumerate(frames):
            im.convert("RGB").save(os.path.join(tmp, "%04d.png" % i))
        source = ["-framerate", str(fps), "-i", os.path.join(tmp, "%04d.png"), "-vf", even, "-an"]
        h264 = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "slow", "-movflags", "+faststart"]
        ffmpeg(*source, *h264, base + ".mp4")
        ffmpeg(*source, "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0", "-crf", "36", "-row-mt", "1",
               base + ".webm")  # fmt: skip
    frames[0].convert("RGB").save(base + ".jpg", quality=85)
    paths = [base + ext for ext in (".webm", ".mp4", ".jpg")]
    for p in paths[:2]:
        if os.path.getsize(p) > MAX_VIDEO_BYTES:
            kb = os.path.getsize(p) // 1000
            print("  warning: %s is %d KB, over the %d KB goal" % (p, kb, MAX_VIDEO_BYTES // 1000))
    return paths


def rounded_card(size, scale=2):
    """A light card with rounded, see-through corners, drawn at scale× for smooth edges, and its draw handle."""
    from PIL import Image, ImageDraw

    im = Image.new("RGBA", (size[0] * scale, size[1] * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=28 * scale, fill=CARD + (255,))
    return im, d


def finish(im, size):
    from PIL import Image

    return im.resize(size, Image.LANCZOS)


def box(d, s, xy, title, lines=(), outline=INK, dashed=False, title_color=None):
    """A labelled box, in 1× coordinates on a canvas drawn at scale s."""
    x0, y0, x1, y1 = (v * s for v in xy)
    if dashed:
        d.rounded_rectangle((x0, y0, x1, y1), radius=14 * s, fill=CARD)
        _dashed_rect(d, (x0, y0, x1, y1), outline, 2 * s, 10 * s)
    else:
        d.rounded_rectangle((x0, y0, x1, y1), radius=14 * s, fill=(255, 255, 255), outline=outline, width=3 * s)
    d.text((x0 + 18 * s, y0 + 14 * s), title, font=font(26 * s, bold=True), fill=title_color or INK)
    for i, line in enumerate(lines):
        d.text((x0 + 18 * s, y0 + (52 + 28 * i) * s), line, font=font(20 * s), fill=MUTED)


def _dashed_line(d, a, b, fill, width, dash):
    import math

    length = math.dist(a, b)
    steps = max(1, int(length // dash))
    for i in range(0, steps, 2):
        t0, t1 = i / steps, min(1, (i + 1) / steps)
        d.line([(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in (t0, t1)], fill=fill, width=width)


def _dashed_rect(d, xy, fill, width, dash):
    x0, y0, x1, y1 = xy
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        _dashed_line(d, a, b, fill, width, dash)


def arrow(d, s, a, b, label=None, color=INK, both=False, label_at=0.5, label_dy=-30):
    """An arrow from a to b (1× coordinates), with an optional label beside its middle."""
    import math

    a, b = (a[0] * s, a[1] * s), (b[0] * s, b[1] * s)
    d.line([a, b], fill=color, width=3 * s)
    for tip, tail in ((b, a), (a, b)) if both else ((b, a),):
        ang = math.atan2(tip[1] - tail[1], tip[0] - tail[0])
        head = [tip] + [
            (tip[0] - 16 * s * math.cos(ang + k), tip[1] - 16 * s * math.sin(ang + k)) for k in (0.45, -0.45)
        ]
        d.polygon(head, fill=color)
    if label:
        mx, my = a[0] + (b[0] - a[0]) * label_at, a[1] + (b[1] - a[1]) * label_at
        f = font(19 * s)
        w = d.textlength(label, font=f)
        d.rectangle((mx - w / 2 - 6 * s, my + label_dy * s - 2 * s, mx + w / 2 + 6 * s, my + (label_dy + 24) * s),
                    fill=CARD)  # fmt: skip
        d.text((mx - w / 2, my + label_dy * s), label, font=f, fill=MUTED)


def gif_frames(path, frame_ms):
    """A GIF's frames at one per frame_ms, as RGB images.

    Pillow's GIF writer merges identical neighbouring frames into one longer frame, so each frame is
    repeated for its duration; reading them one per frame would play the animation too fast.
    """
    from PIL import Image, ImageSequence

    frames = []
    with Image.open(path) as im:
        for f in ImageSequence.Iterator(im):
            frames += [f.convert("RGB")] * max(1, round(f.info.get("duration", frame_ms) / frame_ms))
    return frames


# ---- the blog's show: stand-in voices, built, emulated ----------------------------


def blog_show(voices_engine="espeak", log=print):
    """halloween/show.toml with stand-in voice lines made afresh, and the show built.

    voices_engine: "espeak" (shippable; falls back to say, for timing only, if espeak-ng is missing) or "say".
    Returns show.json's path, or raises SystemExit naming what's missing.
    """
    import halloween
    import voices

    engine, folder = None, SAY_VOICES
    if voices_engine == "espeak":
        engine = voices.find_engine(which=lambda command: None if command == "say" else shutil.which(command))
        folder = ESPEAK_VOICES
        if engine is None:
            log("  no espeak-ng (brew install espeak-ng): using say for timing only, so no sample audio")
    if engine is None:
        engine, folder = (
            voices.find_engine(which=lambda command: shutil.which(command) if command == "say" else None),
            SAY_VOICES,
        )
        if engine is None:
            raise SystemExit("No text-to-speech for the stand-in voices: brew install espeak-ng")
    if os.path.isdir(NO_MUSIC) and os.listdir(NO_MUSIC):
        raise SystemExit(
            "%s should be empty (copyrighted music is pointed there to leave it out): remove it." % NO_MUSIC
        )
    toml = os.path.join(WORK, "show.toml")
    with open("halloween/show.toml", encoding="utf-8") as f:
        text = f.read()
    os.makedirs(WORK, exist_ok=True)
    with open(toml, "w", encoding="utf-8") as f:
        f.write(text.replace("build/cloned/", folder + "/").replace("build/music/", NO_MUSIC + "/"))
    show = halloween.load_show(toml)
    for furby in show["furbies"].values():
        for value in furby["clips"].values():
            check_audio(halloween.clip_spec(value)["path"], ship=False)
    # Made afresh every run, so nothing dropped into the folder by hand can pass as a stand-in
    shutil.rmtree(folder, ignore_errors=True)
    made, _ = voices.make_voices(copy.deepcopy(show), engine, force=True, log=lambda line: None)
    log("  stand-in voices: %d made with %s in %s" % (len(made), engine.name, folder))
    out = os.path.join(WORK, "show")
    with contextlib.redirect_stdout(io.StringIO()) as quiet:
        plan = halloween.build_show(show, out, skip_missing=True)
    with open(os.path.join(WORK, "build.log"), "w", encoding="utf-8") as f:
        f.write(quiet.getvalue())
    return plan


_report = {}


def emulated(plan_path, worst=False):
    """emulate.simulate() over every scene of the blog's show, once per setting of emulate.py's --worst."""
    import emulate

    if (plan_path, worst) not in _report:
        with open(plan_path) as f:
            plan = json.load(f)
        here = os.path.dirname(plan_path)
        dlcs = {name: os.path.join(here, "%s.dlc" % name) for name in plan["furbies"]}
        report = emulate.simulate(plan, dlcs, durations=emulate.load_durations(worst=worst))
        _report[plan_path, worst] = (plan, report)
    return _report[plan_path, worst]


def sample_scene(plan, report):
    """The report entry for SAMPLE_SCENE, or the first scene where every line played."""
    for r in report:
        if list(r["steps"]) == SAMPLE_SCENE and not r["silent"] and not r["skipped"]:
            return r
    for r in report:
        if len(r["steps"]) > 1 and not r["silent"] and not r["skipped"]:
            return r
    raise SystemExit("No scene in the blog's show played cleanly on the emulator.")


def played_lines(plan, scene):
    """(start, furby, clip, audio seconds, busy seconds) for each line that played in this report entry."""
    by_action = {(f, tuple(c["action"])): name for f, v in plan["furbies"].items() for name, c in v["clips"].items()}
    lines = []
    for t, furby, event, detail in scene["events"]:
        if event == "played":
            action, audio, busy = detail
            name = furby.replace("virtual-", "")
            lines.append((t, name, by_action.get((name, tuple(action)), "?"), audio, busy))
    return lines


# ---- items ----------------------------------------------------------------------


def eye_loops(themes):
    """Each theme's preview from spooky_eyes.preview(), one image per frame, and the frame rate."""
    import spooky_eyes

    out = os.path.join(WORK, "eyes")
    loops = {t: gif_frames(spooky_eyes.preview(t, out_dir=out), spooky_eyes.FRAME_MS) for t in themes}
    return loops, round(1000 / spooky_eyes.FRAME_MS)


def eyes_themes(ctx):
    """Every eye theme, from spooky_eyes.preview(), as a 3×2 looping grid."""
    from PIL import Image, ImageDraw

    import spooky_eyes

    themes = list(spooky_eyes.THEMES)
    loops, fps = eye_loops(themes)
    cols, cell_w, gap, label_h = 3, 512, 20, 44
    first = loops[themes[0]][0]
    cell_h = first.height * cell_w // first.width
    rows = -(-len(themes) // cols)
    size = (cols * cell_w + (cols + 1) * gap, rows * (cell_h + label_h) + (rows + 1) * gap)
    frames = []
    for i in range(max(len(loop) for loop in loops.values())):
        im = Image.new("RGB", size, NIGHT)
        d = ImageDraw.Draw(im)
        for k, t in enumerate(themes):
            x = gap + (k % cols) * (cell_w + gap)
            y = gap + (k // cols) * (cell_h + label_h + gap)
            loop = loops[t]
            im.paste(loop[i % len(loop)].resize((cell_w, cell_h), Image.LANCZOS), (x, y))
            d.text((x, y + cell_h + 8), t, font=font(26), fill=(230, 230, 230))
        frames.append(im)
    files = encode_video(frames, fps, os.path.join(WORK, "eyes-themes"))
    return {
        "files": files,
        "size": size,
        "kind": "video",
        "alt": "Six pairs of animated Furby eyes on black: smouldering red demon eyes, flickering jack-o'-lantern "
        "eyes, storm clouds with lightning, darting bloodshot eyes, bobbing ghosts and a spinning hypno spiral.",
        "caption": "Every eye theme spooky_eyes.py draws. Each is three keyframes put in an order, since every "
        "keyframe costs room in the DLC. Preview speed is a guess; the Furby's own frame rate isn't measured.",
    }


def eyes_pink_vs_blue(ctx):
    """Pink's demon eyes beside blue's pumpkin eyes: a video, and a small GIF."""
    from PIL import Image, ImageDraw

    import spooky_eyes

    pairs = [("pink", "demon", "evil", PINK), ("blue", "pumpkin", "friendly", BLUE)]
    loops, fps = eye_loops([t for _, t, _, _ in pairs])
    n = max(len(loop) for loop in loops.values())
    cell_w, gap, label_h = 560, 24, 52
    first = loops["demon"][0]
    cell_h = first.height * cell_w // first.width
    size = (2 * cell_w + 3 * gap, cell_h + label_h + 2 * gap)
    frames = []
    for i in range(n):
        im = Image.new("RGB", size, NIGHT)
        d = ImageDraw.Draw(im)
        for k, (who, theme, mood, colour) in enumerate(pairs):
            x = gap + k * (cell_w + gap)
            loop = loops[theme]
            im.paste(loop[i % len(loop)].resize((cell_w, cell_h), Image.LANCZOS), (x, gap))
            d.rectangle((x, gap + cell_h + 14, x + 14, gap + cell_h + 28), fill=colour)
            d.text((x + 24, gap + cell_h + 8), "%s: %s (%s)" % (who, theme, mood), font=font(26), fill=(230, 230, 230))
        frames.append(im)
    files = encode_video(frames, fps, os.path.join(WORK, "eyes-pink-vs-blue"))
    small = [
        f.resize((size[0] // 2, size[1] // 2), Image.LANCZOS).quantize(96, dither=Image.Dither.NONE) for f in frames
    ]
    gif = os.path.join(WORK, "eyes-pink-vs-blue-%dx%d.gif" % small[0].size)
    small[0].save(gif, save_all=True, append_images=small[1:], duration=spooky_eyes.FRAME_MS, loop=0, optimize=True)
    return {
        "files": files + [gif],
        "size": size,
        "kind": "video",
        "alt": "Two pairs of Furby eyes side by side on black: pink's glowing red demon eyes and blue's flickering "
        "orange jack-o'-lantern eyes.",
        "caption": "The evil Furby and the friendly one. Each DLC holds one eye animation, the only layout that "
        "has shown up cleanly on a Furby.",
    }


def architecture(ctx):
    """The show's parts and how they talk, drawn with Pillow on a light card."""
    s, size = 2, (1600, 1000)
    im, d = rounded_card(size, s)
    d.text((60 * s, 44 * s), "How the porch show fits together", font=font(40 * s, bold=True), fill=INK)
    d.text((60 * s, 98 * s), "Bluetooth Low Energy (BLE) links, the build that feeds them, and the one prop that "
           "runs on its own.", font=font(22 * s), fill=MUTED)  # fmt: skip

    # Build pipeline
    chips = ["show.toml", "halloween.py", "pink.dlc · blue.dlc · show.json", "flash.py"]
    x, y = 60, 160
    for i, chip in enumerate(chips):
        w = d.textlength(chip, font=font(21 * s)) / s + 32
        d.rounded_rectangle((x * s, y * s, (x + w) * s, (y + 44) * s), radius=22 * s, fill=(240, 237, 230),
                            outline=RULE, width=2 * s)  # fmt: skip
        d.text(((x + 16) * s, (y + 10) * s), chip, font=font(21 * s), fill=INK)
        x += w
        if i < len(chips) - 1:
            arrow(d, s, (x + 6, y + 22), (x + 40, y + 22), color=MUTED)
            x += 46
    d.text(((x + 16) * s, (y + 10) * s), "BLE upload to each Furby: about 2–3½ min, about 350 KB max",
           font=font(20 * s), fill=MUTED)  # fmt: skip

    # Controllers
    box(d, s, (60, 280, 600, 380), "or a laptop: porch.py", ["Same show engine (furbyshow.py), over bleak"],
        outline=MUTED, dashed=True)  # fmt: skip
    box(d, s, (60, 420, 600, 600), "ESP32 board", ["DFRobot FireBeetle 2 ESP32-S3", "MicroPython + aioble, hidden",
        "on the porch; LED blinks who to wake next"])  # fmt: skip
    box(d, s, (60, 720, 310, 880), "Motion sensor", ["HC-SR501 PIR", "on GPIO 4: greets", "arrivals"])
    box(d, s, (350, 720, 600, 880), "Button", ["Plays a greeting", "now; no cooldown"])
    arrow(d, s, (185, 720), (185, 600), "motion", label_dy=-12, label_at=0.5)
    arrow(d, s, (475, 720), (475, 600), "press", label_dy=-12, label_at=0.5)

    # Furbies
    box(d, s, (1080, 260, 1540, 420), "Pink Furby", ["Evil · demon eyes", "PINK.DLC (stored as ____PINK.DLC)"],
        outline=PINK, title_color=PINK)  # fmt: skip
    box(d, s, (1080, 470, 1540, 630), "Blue Furby", ["Friendly · pumpkin eyes", "BLUE.DLC (stored as ____BLUE.DLC)"],
        outline=BLUE, title_color=BLUE)  # fmt: skip
    arrow(d, s, (600, 480), (1080, 340), both=True)
    arrow(d, s, (600, 540), (1080, 550), both=True)
    for i, label in enumerate(("BLE, both ways: trigger action 0x13,", "replies 20:0c start · 20:0e end")):
        w = d.textlength(label, font=font(19 * s)) / s
        d.text(((840 - w / 2) * s, (566 + 26 * i) * s), label, font=font(19 * s), fill=MUTED)

    # Remote and glasses
    box(d, s, (660, 740, 1020, 900), "iPhone remote", ["SwiftUI app, Nordic UART", "greet · scene N · status"])
    arrow(d, s, (760, 740), (560, 600), "BLE", both=True, label_at=0.45, label_dy=-14)
    box(d, s, (1080, 720, 1540, 900), "EyeLights glasses", ["CircuitPython · sound-reactive", "demon eyes for the",
        "costume; no link to the show"], outline=(176, 128, 20), dashed=True)  # fmt: skip
    path = os.path.join(WORK, "architecture-%dx%d.png" % size)
    finish(im, size).save(path, optimize=True)
    return {
        "files": [path],
        "size": size,
        "kind": "image",
        "alt": "Diagram. halloween/show.toml is built by halloween.py into pink.dlc, blue.dlc and show.json, which "
        "flash.py uploads to each Furby over Bluetooth. An ESP32 board (or a laptop running porch.py) triggers "
        "actions on the pink and blue Furbies over Bluetooth and hears back when each starts and ends. A motion "
        "sensor and a button start greetings on the board; an iPhone remote talks to the board over Bluetooth, "
        "sending commands and reading its status. EyeLights glasses run on their own with no link to the show.",
        "caption": "One board runs the show: it triggers each Furby's lines over Bluetooth, and the Furbies say "
        "when they're done. The glasses are a separate costume piece.",
    }


def dlc_anatomy(ctx):
    """One of the show's actions followed through the stock DLC's sections, with the real numbers."""
    import emulate
    import halloween
    from furby import dlc

    D = dlc("dlc/dlc2/tu003410.dlc")
    sec = D.dlc_sections
    code = halloween.quick_slots(D)[0]  # the first slot the show fills: a built-in movement, so a short sequence
    seq_no = sec["XLS"].action_tree[code[0]][code[1]][code[2]][code[3]]["seq"]
    seq = sec["SEQ"].sequences[seq_no]
    apl_no = seq[1] - sec["SEQ"].playlist_offset
    tracks = [n for n, kind in sec["APL"].playlists[apl_no] if kind == "AUDIO"]
    track_bytes = sum(len(sec["AMF"].tracks[n]) for n in tracks)
    eyes = sorted({w for w in seq[3:-1] if w >> 12 in (0x8, 0xA)})
    delays = [w for w in seq[3:-1] if w >> 12 == 0x1]
    motor = seq[2]
    action = "·".join(map(str, code))

    s, size = 2, (1600, 900)
    im, d = rounded_card(size, s)
    d.text((60 * s, 44 * s), "Inside a Furby Connect DLC", font=font(40 * s, bold=True), fill=INK)
    d.text((60 * s, 98 * s), "What one action plays, followed through the stock DLC's sections (numbers read from "
           "dlc/dlc2/tu003410.dlc).", font=font(22 * s), fill=MUTED)  # fmt: skip

    # The file's sections, as a strip in proportion to their size, coloured by what they hold
    order = ["PAL", "SPR", "CEL", "XLS", "AMF", "APL", "LPS", "SEQ", "MTR"]
    kinds = {
        "eyes": ((225, 214, 236), ["PAL", "SPR", "CEL"]),
        "audio": ((214, 230, 222), ["AMF"]),
        "links": ((236, 233, 226), ["XLS", "APL", "LPS", "SEQ", "MTR"]),
    }
    shade = {n: c for c, names in kinds.values() for n in names}
    total = sum(sec[n].length for n in order)
    x0, x1, y = 60, 1540, 160
    x = x0
    for n in order:
        w = max(4, (x1 - x0) * sec[n].length / total)
        d.rectangle((x * s, y * s, (x + w - 2) * s, (y + 56) * s), fill=shade[n])
        if w > 54:
            d.text(((x + 8) * s, (y + 8) * s), n, font=font(20 * s, bold=True), fill=INK)
            d.text(((x + 8) * s, (y + 32) * s), "%d KB" % round(sec[n].length / 1000), font=font(16 * s), fill=MUTED)
        x += w
    x, ly = x0, y + 70
    for kind, (colour, names) in kinds.items():
        d.rectangle((x * s, ly * s, (x + 22) * s, (ly + 22) * s), fill=colour, outline=RULE, width=s)
        label = "%s: %s (%d KB)" % (kind, ", ".join(names), round(sum(sec[n].length for n in names) / 1000))
        d.text(((x + 30) * s, ly * s), label, font=font(18 * s), fill=MUTED)
        x += 70 + d.textlength(label, font=font(18 * s)) / s
    d.text((x0 * s, (ly + 32) * s), "%.1f MB in all. Stock DLCs come from the app; ours must stay under about 350 KB "
           "to upload." % (total / 1e6), font=font(18 * s), fill=MUTED)  # fmt: skip

    # The chain for one action
    y = 340
    steps = [
        ("Action %s" % action, ["input · index ·", "subindex · specific", "sent over BLE (0x13)"]),
        ("XLS", ["action tree:", "→ sequence %d" % seq_no]),
        ("SEQ #%d" % seq_no, ["playlist 0x%04x" % seq[1], "motor 0x%04x" % motor,
                               "eyes " + ", ".join("0x%04x" % w for w in eyes)]),
        ("APL #%d" % apl_no, ["audio playlist:", "track " + ", ".join(map(str, tracks))]),
        ("AMF", ["%d KB of A1800 audio" % round(track_bytes / 1000),
                 "≈ %.1f s at ~2 KB/s" % (track_bytes / emulate.A18_BYTES_PER_SECOND)]),
    ]  # fmt: skip
    w, gap = 252, 55
    for i, (title, lines) in enumerate(steps):
        x = 60 + i * (w + gap)
        box(d, s, (x, y, x + w, y + 170), title, lines, outline=PINK if i == 0 else INK)
        if i < len(steps) - 1:
            arrow(d, s, (x + w + 4, y + 85), (x + w + gap - 4, y + 85))

    # What else the sequence drives
    seq_x = 60 + 2 * (w + gap) + w // 2
    y2 = 610
    delay_s = sum((v & 0xFFF) * emulate.DELAY_UNIT_S for v in delays)
    body = (
        "0x%04x is one of the DLC's own routines: 10–21 s on a Furby" % motor
        if motor >> 12 == 0xC
        else "0x%04x is a built-in movement: about 1–10 s on a Furby" % motor
    )
    box(d, s, (60, y2, 720, y2 + 200), "Eyes: SPR → CEL → PAL", ["eye word picks an animation; SPR lists its frames,",
        "each frame is four 64×64 cels (CEL) in 64 colors", "from a palette (PAL, ARGB1555)"])  # fmt: skip
    box(d, s, (780, y2, 1540, y2 + 200), "Body: motor word, plus delays", [body,
        "%d delay words ≈ %.1f s more (10 ms units, assumed)" % (len(delays), delay_s)
        if delays
        else "No delay words in this sequence, so the movement sets its length",
        "The Furby stays busy until all of it ends"])  # fmt: skip
    arrow(d, s, (seq_x - 40, y + 170), (390, y2), color=MUTED)
    arrow(d, s, (seq_x + 40, y + 170), (1160, y2), color=MUTED)
    path = os.path.join(WORK, "dlc-anatomy-%dx%d.png" % size)
    finish(im, size).save(path, optimize=True)
    return {
        "files": [path],
        "size": size,
        "kind": "image",
        "alt": "Diagram of a Furby Connect DLC file. A strip shows its sections by size: PAL, SPR and CEL hold the "
        "eyes, AMF holds the audio, and small XLS, APL, LPS, SEQ and MTR sections link them. Below, action %s goes "
        "through XLS to sequence %d, which names audio playlist %d (track %s, about %.0f seconds), eye animations "
        "and a body movement."
        % (action, seq_no, apl_no, ", ".join(map(str, tracks)), track_bytes / emulate.A18_BYTES_PER_SECOND),
        "caption": "Following one action through a DLC. A clip's sequence also runs eyes and a body movement, "
        "and the Furby ignores the next clip's audio until the slowest of them finishes.",
    }


def pacing_chart(ctx):
    """One scene on two lanes, as emulate.py --worst plays it: each line's audio, then the time its Furby stays busy."""
    from PIL import ImageDraw

    plan, report = emulated(ctx["plan"], worst=True)
    scene = sample_scene(plan, report)
    lines = played_lines(plan, scene)
    # A trigger that came while its Furby was still busy: answered 20:07, then retried when the Furby said 20:0e
    retries = [(t, f.replace("virtual-", ""), d) for t, f, e, d in scene["events"] if e == "silent"]
    end = max(t + busy for t, _, _, _, busy in lines)
    s, size = 2, (1600, 680)
    im, d = rounded_card(size, s)
    d = ImageDraw.Draw(im)
    d.text((60 * s, 40 * s), "One scene, two Furbies", font=font(38 * s, bold=True), fill=INK)
    d.text((60 * s, 92 * s), " → ".join(scene["steps"]) + ". A Furby stays busy until its movement ends, so a line "
           "sent before then has to wait.", font=font(21 * s), fill=MUTED)  # fmt: skip
    left, right, top, lane_h = 200, 1540, 170, 150
    span = max(1, int(end + 1.999))
    px = (right - left) / span

    def X(t):
        return (left + t * px) * s

    for k in range(span + 1):  # recessive grid, a line a second
        d.line((X(k), top * s, X(k), (top + 2 * lane_h) * s), fill=(232, 229, 222), width=s)
        d.text((X(k) - 6 * s, (top + 2 * lane_h + 10) * s), "%d" % k, font=font(18 * s), fill=MUTED)
    d.text((right * s - 90 * s, (top + 2 * lane_h + 36) * s), "seconds", font=font(18 * s), fill=MUTED)
    for row, (name, colour) in enumerate((("pink", PINK), ("blue", BLUE))):
        y = top + row * lane_h
        d.text((60 * s, (y + 52) * s), name, font=font(28 * s, bold=True), fill=INK)
        d.line((left * s, (y + lane_h) * s, right * s, (y + lane_h) * s), fill=RULE, width=s)
        y0, y1 = (y + 46) * s, (y + 96) * s
        tint = tuple(int(c + (255 - c) * 0.72) for c in colour)
        for t, who, clip, audio, busy in lines:
            if who != name:
                continue
            d.rounded_rectangle((X(t), y0, X(t + busy), y1), radius=4 * s, fill=tint)
            d.rounded_rectangle((X(t), y0, max(X(t) + 8 * s, X(t + audio) - 2 * s), y1), radius=4 * s, fill=colour)
            d.text((X(t), (y + 14) * s), clip, font=font(21 * s), fill=INK)
        for t, who, _ in retries:
            retry = min((t2 for t2, w2, _, _, _ in lines if w2 == who and t2 >= t), default=None)
            if who != name or retry is None:  # a retry that never played has nothing to measure to
                continue
            _dashed_rect(d, (X(t), y0, X(retry) - 4 * s, y1), colour, 2 * s, 6 * s)
            d.text((X(t), (y + 102) * s), "20:07 busy: waits %.1f s" % (retry - t), font=font(17 * s), fill=MUTED)
    ly = top + 2 * lane_h + 64
    x = 60
    for label, colour in (("speaking", GREY), ("moving, still busy", (214, 214, 218)), ("waiting to retry", None)):
        if colour:
            d.rounded_rectangle((x * s, ly * s, (x + 34) * s, (ly + 22) * s), radius=4 * s, fill=colour)
        else:
            _dashed_rect(d, (x * s, ly * s, (x + 34) * s, (ly + 22) * s), GREY, 2 * s, 6 * s)
        d.text(((x + 44) * s, ly * s), label, font=font(19 * s), fill=MUTED)
        x += 64 + d.textlength(label, font=font(19 * s)) / s
    d.text(((x + 10) * s, ly * s), "20:07 = the Furby's reply that it's busy", font=font(19 * s), fill=INK)
    d.text((60 * s, (ly + 40) * s), "Emulated by emulate.py --worst: stand-in clip lengths, and each movement at the "
           "top of the range timed across the show's slots (9 s). Not a recording.", font=font(17 * s),
           fill=MUTED)  # fmt: skip
    path = os.path.join(WORK, "pacing-chart-%dx%d.png" % size)
    finish(im, size).save(path, optimize=True)
    with open(os.path.join(WORK, "pacing-chart.json"), "w") as f:
        json.dump({"steps": scene["steps"], "lines": lines}, f, indent=1)
    desc = "; ".join("%s.%s starts at %.1f s, speaks %.1f s, busy %.1f s" % (w, c, t, a, b) for t, w, c, a, b in lines)
    waits = " ".join("%s was still busy at %.1f s and waited to retry." % (w, t) for t, w, _ in retries)
    return {
        "files": [path],
        "size": size,
        "kind": "image",
        "alt": ("Timeline with a pink lane and a blue lane. %s. %s" % (desc, waits)).strip(),
        "caption": "One scene on virtual Furbies, with movements at their slowest. The pale tail is the movement "
        "that keeps a Furby busy after its line ends. Before the fix, a line sent then played with no sound at "
        "all, which happened to about a third of the lines in testing on a real Furby. Now the show hears the "
        "Furby's \"busy\" reply and sends the line again when it's free.",
    }


def scene_sample_audio(ctx):
    """The pacing chart's scene mixed from espeak-ng stand-ins and CC0 effects at emulated times, as .m4a."""
    plan, report = emulated(ctx["plan"])  # typical movement times: the chart's --worst gaps would drag
    scene = sample_scene(plan, report)
    lines = played_lines(plan, scene)
    inputs, filters = [], []
    for i, (t, who, clip, _, _) in enumerate(lines):
        spec = plan["furbies"][who]["clips"][clip]
        inputs += ["-t", str(spec["seconds"]), "-i", check_audio(spec["source"])]
        filters.append("[%d:a]aresample=44100,aformat=channel_layouts=mono,adelay=%d[a%d]" % (i, int(t * 1000), i))
    mix = "".join("[a%d]" % i for i in range(len(lines)))
    graph = ";".join(filters + ["%samix=inputs=%d:normalize=0,apad=pad_dur=0.5[out]" % (mix, len(lines))])
    out = os.path.join(WORK, "scene-sample.m4a")
    ffmpeg(*inputs, "-filter_complex", graph, "-map", "[out]", "-c:a", "aac", "-b:a", "96k", out)
    return {
        "files": [out],
        "size": (0, 0),
        "kind": "audio",
        "alt": "Audio of one scene: " + ", then ".join("%s.%s" % (w, c) for _, w, c, _, _ in lines) + ".",
        "caption": "The scene from the pacing chart, with espeak-ng stand-in voices and CC0 sound effects "
        "in place of the Furbies' own, timed as the emulator plays it.",
    }


# id → (function, needs the blog's show built, optional)
ITEMS = {
    "eyes-themes": (eyes_themes, False, False),
    "eyes-pink-vs-blue": (eyes_pink_vs_blue, False, False),
    "architecture": (architecture, False, False),
    "dlc-anatomy": (dlc_anatomy, False, False),
    "pacing-chart": (pacing_chart, True, False),
    "scene-sample-audio": (scene_sample_audio, True, True),
}


def destination(out, item_id, path, kind):
    """Where a rendered file goes in --out: the blog's own public/ paths."""
    name = os.path.basename(path)
    if kind == "audio":
        return os.path.join(out, "public", "audio", "furby-halloween", name)
    if kind == "video" and not name.endswith(".gif"):
        return os.path.join(out, "public", "video", "furby-halloween", name)
    return os.path.join(out, "public", "assets", "img", "furby-halloween-" + name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="the blog's root: media goes under public/, manifest.json beside it")
    parser.add_argument("--only", action="append", choices=list(ITEMS), metavar="ID",
                        help="just this item (repeatable): " + ", ".join(ITEMS))  # fmt: skip
    parser.add_argument("--voices", choices=["espeak", "say"], default="espeak",
                        help="stand-in voices (default espeak; say is for timing only and never ships)")  # fmt: skip
    parser.add_argument("--list", action="store_true", help="list the items and exit")
    args = parser.parse_args(argv)
    if args.list:
        for item_id, (fn, _, optional) in ITEMS.items():
            print("%-20s %s%s" % (item_id, fn.__doc__.splitlines()[0], " (optional)" if optional else ""))
        return 0
    if not args.out:
        parser.error("--out is required (or --list)")
    if not shutil.which("ffmpeg"):
        raise SystemExit("blog_media.py needs ffmpeg for the videos and audio: brew install ffmpeg")
    args.out = os.path.abspath(args.out)  # before the chdir, so a relative --out is the caller's
    os.chdir(ROOT)
    os.makedirs(WORK, exist_ok=True)
    wanted = args.only or list(ITEMS)
    ctx, manifest, skipped = {}, [], []
    if any(ITEMS[i][1] for i in wanted):
        print("Building the blog's show (stand-in voices, no cloned audio)...")
        try:
            ctx["plan"] = blog_show(args.voices)
        except SystemExit as e:
            raise SystemExit("Can't build the blog's show (needed for %s): %s"
                             % (", ".join(i for i in wanted if ITEMS[i][1]), e)) from None  # fmt: skip
    for item_id in wanted:
        fn, _, optional = ITEMS[item_id]
        print("%s..." % item_id)
        try:
            result = fn(ctx)
        except (SystemExit, OSError, subprocess.SubprocessError) as e:
            if not optional:
                raise SystemExit("%s failed: %s" % (item_id, e)) from None
            print("  skipped: %s" % e)
            skipped.append((item_id, str(e)))
            continue
        files = []
        for path in result["files"]:
            dest = destination(args.out, item_id, path, result["kind"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(path, dest)
            files.append(os.path.relpath(dest, args.out).replace(os.sep, "/"))
            print("  %s (%d KB)" % (files[-1], os.path.getsize(dest) // 1000))
        manifest.append(
            {
                "id": item_id,
                "files": files,
                "width": result["size"][0],
                "height": result["size"][1],
                "alt": result["alt"],
                "caption": result["caption"],
                "kind": result["kind"],
            }
        )
    path = os.path.join(args.out, "manifest.json")
    os.makedirs(args.out, exist_ok=True)
    if args.only and os.path.exists(path):  # keep the items this run didn't redo, in their order
        with open(path, encoding="utf-8") as f:
            fresh = {item["id"]: item for item in manifest}
            old = json.load(f)
        manifest = [fresh.pop(item["id"], item) for item in old if item["id"] in ITEMS] + list(fresh.values())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("Wrote %d items to %s" % (len(manifest), path))
    for item_id, why in skipped:
        print("Skipped %s: %s" % (item_id, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
