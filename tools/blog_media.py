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
from xml.sax.saxutils import escape

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
PINK, BLUE = (194, 51, 122), (47, 111, 208)  # the eye videos' labels; THEME has the diagrams' colours
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


# Each colour the diagrams use, light then dark. Pink and blue pass the dataviz palette checks on both cards.
THEME = {
    "card": ("#f8f7f4", "#1c1d21"),
    "panel": ("#ffffff", "#25262b"),
    "chip": ("#f0ede6", "#2c2d33"),
    "ink": ("#1d1d1f", "#ececf0"),
    "muted": ("#5c5c66", "#a5a5af"),
    "rule": ("#d6d3cc", "#3d3e45"),
    "grid": ("#e8e5de", "#2c2d33"),
    "pink": ("#c2337a", "#e0609e"),
    "blue": ("#2f6fd0", "#5b93e6"),
    "pink-tint": ("#efc2d8", "#5a2b44"),
    "blue-tint": ("#c4d6f3", "#26395a"),
    "grey": ("#78787f", "#9a9aa3"),
    "grey-tint": ("#d6d6da", "#45464d"),
    "amber": ("#b08014", "#d9a640"),
    "eyes": ("#e1d6ec", "#3d3350"),
    "audio": ("#d6e6de", "#2b4237"),
    "links": ("#ece9e2", "#34353b"),
}
FONT_STACK = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"


def text_width(text, size, bold=False):
    """About how wide text is at this size, measured in SF, which most viewers' system-ui matches."""
    return font(size, bold=bold).getlength(text)


class Svg:
    """A vector diagram on a rounded card that follows the viewer's light or dark mode, built up shape by shape.

    Colours are THEME names, drawn through CSS variables that a prefers-color-scheme query swaps, so the SVG
    works as a plain <img> with no external fonts or CSS.
    """

    def __init__(self, size, title, desc):
        self.size, self.title, self.desc, self.parts = size, title, desc, []
        self.rect(0, 0, size[0], size[1], fill="card", r=28)

    @staticmethod
    def _style(fill=None, stroke=None, width=None, dash=None):
        style = ["fill:%s" % ("var(--%s)" % fill if fill else "none")]
        if stroke:
            style.append("stroke:var(--%s);stroke-width:%g" % (stroke, width or 1))
            if dash:
                style.append("stroke-dasharray:%g %g" % (dash, dash))
        return ";".join(style)

    def rect(self, x0, y0, x1, y1, fill=None, stroke=None, width=None, r=0, dash=None):
        self.parts.append('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" style="%s"/>'
                          % (x0, y0, x1 - x0, y1 - y0, r, self._style(fill, stroke, width, dash)))  # fmt: skip

    def line(self, a, b, stroke="ink", width=3, dash=None):
        self.parts.append('<line x1="%g" y1="%g" x2="%g" y2="%g" style="%s"/>'
                          % (*a, *b, self._style(None, stroke, width, dash)))  # fmt: skip

    def polygon(self, points, fill="ink"):
        coords = " ".join("%g,%g" % p for p in points)
        self.parts.append('<polygon points="%s" style="%s"/>' % (coords, self._style(fill)))

    def text(self, x, y, s, size, fill="muted", bold=False, anchor="start"):
        """s with the top of its letters at y, as Pillow places text, so layouts carry over."""
        baseline = y + font(size, bold=bold).getmetrics()[0] * 0.8
        self.parts.append('<text x="%g" y="%g" font-size="%g"%s%s style="fill:var(--%s)">%s</text>' % (
            x, baseline, size, ' font-weight="700"' if bold else "",
            ' text-anchor="%s"' % anchor if anchor != "start" else "", fill, escape(s)))  # fmt: skip

    def render(self):
        light = ";".join("--%s:%s" % (k, v[0]) for k, v in THEME.items())
        dark = ";".join("--%s:%s" % (k, v[1]) for k, v in THEME.items())
        w, h = self.size
        return "\n".join([
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" '
            'aria-labelledby="title desc">' % (w, h, w, h),
            "<title id=\"title\">%s</title>" % escape(self.title),
            "<desc id=\"desc\">%s</desc>" % escape(self.desc),
            "<style>svg{%s}@media (prefers-color-scheme: dark){svg{%s}}text{font-family:%s}</style>"
            % (light, dark, FONT_STACK),
            *self.parts,
            "</svg>",
            "",
        ])  # fmt: skip

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render())
        return path


def box(svg, xy, title, lines=(), outline="ink", dashed=False, title_color="ink", tag=None):
    """A labelled box; tag is a small, muted line under the title, such as a DLC section's name."""
    x0, y0, x1, y1 = xy
    if dashed:
        svg.rect(x0, y0, x1, y1, fill="card", stroke=outline, width=2, r=14, dash=10)
    else:
        svg.rect(x0, y0, x1, y1, fill="panel", stroke=outline, width=3, r=14)
    svg.text(x0 + 18, y0 + 14, title, 26, fill=title_color, bold=True)
    if tag:
        svg.text(x0 + 18, y0 + 48, tag, 16)
    for i, line in enumerate(lines):
        svg.text(x0 + 18, y0 + (76 if tag else 52) + 28 * i, line, 20)


def arrow(svg, a, b, label=None, color="ink", both=False, label_at=0.5, label_dy=-30):
    """An arrow from a to b, with an optional label on a card-coloured patch beside its middle."""
    import math

    svg.line(a, b, stroke=color, width=3)
    for tip, tail in ((b, a), (a, b)) if both else ((b, a),):
        ang = math.atan2(tip[1] - tail[1], tip[0] - tail[0])
        svg.polygon([tip] + [(tip[0] - 16 * math.cos(ang + k), tip[1] - 16 * math.sin(ang + k)) for k in (0.45, -0.45)],
                    fill=color)  # fmt: skip
    if label:
        mx, my = a[0] + (b[0] - a[0]) * label_at, a[1] + (b[1] - a[1]) * label_at
        w = text_width(label, 19)
        svg.rect(mx - w / 2 - 6, my + label_dy - 2, mx + w / 2 + 6, my + label_dy + 24, fill="card")
        svg.text(mx - w / 2, my + label_dy, label, 19)


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
    """The show's parts and how they talk, in plain words, as an SVG that follows light and dark mode."""
    size = (1600, 1000)
    alt = (
        "Diagram. A show script is built into one DLC file per Furby, and each is uploaded to its Furby over "
        "Bluetooth, which takes about two to three and a half minutes and must stay under 350 KB. A small show "
        "board hidden on the porch (or a laptop running the same show) cues each Furby's lines over Bluetooth and "
        "hears when each starts and ends. A motion sensor greets new arrivals and a button plays a greeting right "
        "away. An iPhone remote talks to the board over Bluetooth to greet, pick a scene or see status. LED glasses "
        "worn by the candy-giver show sound-reactive demon eyes and have no link to the show."
    )
    svg = Svg(size, "How the porch show fits together", alt)
    svg.text(60, 44, "How the porch show fits together", 40, fill="ink", bold=True)
    svg.text(60, 98, "What talks to what over Bluetooth, how the show gets onto each Furby, and the one prop that "
             "runs on its own.", 22)  # fmt: skip

    # How the show gets onto the Furbies
    chips = ["show script", "one DLC per Furby", "uploaded over Bluetooth"]
    x, y = 60, 160
    for i, chip in enumerate(chips):
        w = text_width(chip, 21) + 44  # room for a system font a little wider than SF
        svg.rect(x, y, x + w, y + 44, fill="chip", stroke="rule", width=2, r=22)
        svg.text(x + w / 2, y + 10, chip, 21, fill="ink", anchor="middle")
        x += w
        if i < len(chips) - 1:
            arrow(svg, (x + 6, y + 22), (x + 40, y + 22), color="muted")
            x += 46
    svg.text(x + 16, y + 10, "about 2–3½ min each, 350 KB max", 20)

    # Controllers
    box(svg, (60, 280, 600, 380), "or a laptop", ["running the same show"], outline="muted", dashed=True)
    box(svg, (60, 420, 600, 600), "Show board", ["A small Bluetooth board, hidden on the porch.",
        "Its light says which Furby to wake next."], tag="an ESP32: DFRobot FireBeetle 2")  # fmt: skip
    box(svg, (60, 720, 310, 880), "Motion sensor", ["Greets new", "arrivals"])
    box(svg, (350, 720, 600, 880), "Button", ["Plays a greeting", "right away"])
    arrow(svg, (185, 720), (185, 600), "motion", label_dy=-12)
    arrow(svg, (475, 720), (475, 600), "press", label_dy=-12)

    # Furbies
    box(svg, (1080, 260, 1540, 420), "Pink Furby", ["Evil, with demon eyes"], outline="pink", title_color="pink")
    box(svg, (1080, 470, 1540, 630), "Blue Furby", ["Friendly, with pumpkin eyes"], outline="blue",
        title_color="blue")  # fmt: skip
    arrow(svg, (600, 480), (1080, 340), both=True)
    arrow(svg, (600, 540), (1080, 550), both=True)
    for i, label in enumerate(("Bluetooth: cues each line,", "hears when it starts and ends")):
        svg.text(840, 566 + 26 * i, label, 19, anchor="middle")

    # Remote and glasses
    box(svg, (660, 740, 1020, 900), "iPhone remote", ["Greet, pick a scene,", "see status"])
    arrow(svg, (760, 740), (560, 600), "Bluetooth", both=True, label_at=0.45, label_dy=-14)
    box(svg, (1080, 720, 1540, 900), "LED glasses", ["Worn by the candy-giver:", "sound-reactive demon eyes,",
        "no link to the show"], outline="amber", dashed=True)  # fmt: skip
    return {
        "files": [svg.save(os.path.join(WORK, "architecture-%dx%d.svg" % size))],
        "size": size,
        "kind": "image",
        "alt": alt,
        "caption": "One board runs the show: it cues each Furby's lines over Bluetooth, and the Furbies say "
        "when they're done. The glasses are a separate costume piece.",
    }


def dlc_anatomy(ctx):
    """One of the show's actions followed through the stock DLC, in plain words, with the real numbers, as an SVG."""
    import emulate
    import halloween
    import stock_dlc
    from furby import dlc

    D = dlc(stock_dlc.require())  # your stock DLC: the diagram reads its real numbers, and ships none of it
    sec = D.dlc_sections
    code = halloween.quick_slots(D)[0]  # the first slot the show fills: a built-in movement, so a short sequence
    seq_no = sec["XLS"].action_tree[code[0]][code[1]][code[2]][code[3]]["seq"]
    seq = sec["SEQ"].sequences[seq_no]
    apl_no = seq[1] - sec["SEQ"].playlist_offset
    tracks = [n for n, kind in sec["APL"].playlists[apl_no] if kind == "AUDIO"]
    track_bytes = sum(len(sec["AMF"].tracks[n]) for n in tracks)
    seconds = track_bytes / emulate.A18_BYTES_PER_SECOND
    delays = [w for w in seq[3:-1] if w >> 12 == 0x1]
    motor = seq[2]
    action = "·".join(map(str, code))
    # Plain names for the sections, from what the repo knows they hold (README's DLC API), not what the letters mean
    names = {
        "PAL": "Color palettes",
        "SPR": "Frame lists",
        "CEL": "Image tiles",
        "XLS": "Action table",
        "AMF": "Audio clips",
        "APL": "Audio playlists",
        "LPS": "Lip movements",
        "SEQ": "Sequences",
        "MTR": "Motor movements",
    }
    kinds = {
        "eyes: palettes, frame lists, image tiles": ("eyes", ["PAL", "SPR", "CEL"]),
        "audio clips": ("audio", ["AMF"]),
        "the wiring between them: action table, sequences, playlists, lip and motor data": (
            "links", ["XLS", "APL", "LPS", "SEQ", "MTR"]),
    }  # fmt: skip
    kind_of = {n: colour for colour, ns in kinds.values() for n in ns}
    alt = (
        "Diagram of a Furby DLC file, the package of eyes, sounds and moves the Furby plays. A bar shows its parts "
        "by size: the eyes (color palettes, frame lists and image tiles) and the audio clips take nearly all of it, "
        "and a small remainder wires them together. Below, one action, number %s, the four-part number the show "
        "sends over Bluetooth, is followed through the action table to a sequence. The sequence picks an audio "
        "playlist (one clip of compressed audio, about %.0f seconds), a body movement and an eye animation, and "
        "the Furby stays busy until all of them finish." % (action, seconds)
    )

    size = (1600, 900)
    svg = Svg(size, "Inside a Furby DLC", alt)
    svg.text(60, 44, "Inside a Furby DLC", 40, fill="ink", bold=True)
    svg.text(60, 98, "What one action plays, followed through Hasbro's stock DLC. An action is the four-part number "
             "the show sends.", 22)  # fmt: skip

    # The file's sections, as a bar in proportion to their size, coloured by what they hold
    order = ["PAL", "SPR", "CEL", "XLS", "AMF", "APL", "LPS", "SEQ", "MTR"]
    total = sum(sec[n].length for n in order)
    x0, x1, y = 60, 1540, 160
    x = x0
    for n in order:
        w = max(4, (x1 - x0) * sec[n].length / total)
        svg.rect(x, y, x + w - 2, y + 56, fill=kind_of[n])
        if w > 160:
            svg.text(x + 10, y + 8, names[n], 20, fill="ink", bold=True)
            svg.text(x + 10, y + 32, "%s · %d KB" % (n, round(sec[n].length / 1000)), 16)
        x += w
    ly = y + 70
    for i, (label, (colour, ns)) in enumerate(kinds.items()):
        yy = ly + 28 * i
        svg.rect(x0, yy, x0 + 22, yy + 22, fill=colour, stroke="rule", width=1)
        svg.text(x0 + 30, yy, "%s (%d KB)" % (label, round(sum(sec[n].length for n in ns) / 1000)), 18)
    svg.text(x0, ly + 90, "%.1f MB in all. Stock DLCs come from the app; ours must stay under about 350 KB to "
             "upload." % (total / 1e6), 18)  # fmt: skip

    # The chain for one action
    y = 400
    steps = [
        ("Action %s" % action, None, ["the four-part number", "the show sends over", "Bluetooth"]),
        ("Action table", "XLS", ["finds this action's", "sequence"]),
        ("Sequence #%d" % seq_no, "SEQ", ["picks an audio playlist,", "a body movement and", "an eye animation"]),
        ("Audio playlist", "APL", ["lists the clips to play:", "here, just one"]),
        ("Audio clips", "AMF", ["%d KB of compressed" % round(track_bytes / 1000),
                                "audio, about %.1f s" % seconds]),
    ]  # fmt: skip
    w, gap = 252, 55
    for i, (title, tag, lines) in enumerate(steps):
        x = 60 + i * (w + gap)
        box(svg, (x, y, x + w, y + 170), title, lines, outline="pink" if i == 0 else "ink", tag=tag)
        if i < len(steps) - 1:
            arrow(svg, (x + w + 4, y + 85), (x + w + gap - 4, y + 85))

    # What else the sequence drives
    seq_x = 60 + 2 * (w + gap) + w // 2
    y2 = 660
    pause_s = sum((v & 0xFFF) * emulate.DELAY_UNIT_S for v in delays)
    move = (
        "This one is the DLC's own routine: 10–21 s on a Furby"
        if motor >> 12 == 0xC
        else "This one is built into the Furby: about 1–10 s"
    )
    box(svg, (60, y2, 720, y2 + 180), "Eyes", ["An eye animation is a list of frames. Each frame",
        "is four 64×64 image tiles in 64 colors."], tag="SPR · CEL · PAL")  # fmt: skip
    box(svg, (780, y2, 1540, y2 + 180), "Body: a movement, plus pauses", [move,
        "%d pauses add about %.1f s more (timing assumed)" % (len(delays), pause_s) if delays
        else "No pauses in this one, so the movement sets its length",
        "The Furby stays busy until all of it ends"])  # fmt: skip
    arrow(svg, (seq_x - 40, y + 170), (390, y2), color="muted")
    arrow(svg, (seq_x + 40, y + 170), (1160, y2), color="muted")
    return {
        "files": [svg.save(os.path.join(WORK, "dlc-anatomy-%dx%d.svg" % size))],
        "size": size,
        "kind": "image",
        "alt": alt,
        "caption": "Following one action through a DLC. A clip's sequence also runs eyes and a body movement, "
        "and the Furby ignores the next clip's audio until the slowest of them finishes.",
    }


def pacing_chart(ctx):
    """One scene on two lanes, as emulate.py --worst plays it: each line's audio, then the time its Furby stays busy."""
    plan, report = emulated(ctx["plan"], worst=True)
    scene = sample_scene(plan, report)
    lines = played_lines(plan, scene)
    # A trigger that came while its Furby was still busy: answered 20:07, then retried when the Furby said 20:0e
    retries = [(t, f.replace("virtual-", ""), d) for t, f, e, d in scene["events"] if e == "silent"]
    end = max(t + busy for t, _, _, _, busy in lines)
    desc = "; ".join("%s.%s starts at %.1f s, speaks %.1f s, busy %.1f s" % (w, c, t, a, b) for t, w, c, a, b in lines)
    waits = " ".join("%s was still busy at %.1f s and waited to retry." % (w, t) for t, w, _ in retries)
    alt = ("Timeline with a pink lane and a blue lane. %s. %s" % (desc, waits)).strip()

    size = (1600, 680)
    svg = Svg(size, "One scene, two Furbies", alt)
    svg.text(60, 40, "One scene, two Furbies", 38, fill="ink", bold=True)
    svg.text(60, 92, " → ".join(scene["steps"]) + ". A Furby stays busy until its movement ends, so a line sent "
             "before then has to wait.", 21)  # fmt: skip
    left, right, top, lane_h = 200, 1540, 170, 150
    span = max(1, int(end + 1.999))
    px = (right - left) / span

    def X(t):
        return left + t * px

    for k in range(span + 1):  # recessive grid, a line a second
        svg.line((X(k), top), (X(k), top + 2 * lane_h), stroke="grid", width=1)
        svg.text(X(k), top + 2 * lane_h + 10, "%d" % k, 18, anchor="middle")
    svg.text(right, top + 2 * lane_h + 36, "seconds", 18, anchor="end")
    for row, name in enumerate(("pink", "blue")):
        y = top + row * lane_h
        svg.text(60, y + 52, name, 28, fill="ink", bold=True)
        svg.line((left, y + lane_h), (right, y + lane_h), stroke="rule", width=1)
        y0, y1 = y + 46, y + 96
        for t, who, clip, audio, busy in lines:
            if who != name:
                continue
            svg.rect(X(t), y0, X(t + busy), y1, fill=name + "-tint", r=4)
            svg.rect(X(t), y0, max(X(t) + 8, X(t + audio) - 2), y1, fill=name, r=4)
            svg.text(X(t), y + 14, clip, 21, fill="ink")
        for t, who, _ in retries:
            retry = min((t2 for t2, w2, _, _, _ in lines if w2 == who and t2 >= t), default=None)
            if who != name or retry is None:  # a retry that never played has nothing to measure to
                continue
            svg.rect(X(t), y0, X(retry) - 4, y1, stroke=name, width=2, dash=6)
            svg.text(X(t), y + 102, "20:07 busy: waits %.1f s" % (retry - t), 17)
    ly = top + 2 * lane_h + 64
    x = 60
    for label, fill in (("speaking", "grey"), ("moving, still busy", "grey-tint"), ("waiting to retry", None)):
        if fill:
            svg.rect(x, ly, x + 34, ly + 22, fill=fill, r=4)
        else:
            svg.rect(x, ly, x + 34, ly + 22, stroke="grey", width=2, dash=6)
        svg.text(x + 44, ly, label, 19)
        x += 64 + text_width(label, 19)
    svg.text(x + 10, ly, "20:07 = the Furby's reply that it's busy", 19, fill="ink")
    svg.text(60, ly + 40, "Emulated by emulate.py --worst: stand-in clip lengths, and each movement at the top of "
             "the range timed across the show's slots (9 s). Not a recording.", 17)  # fmt: skip
    with open(os.path.join(WORK, "pacing-chart.json"), "w") as f:
        json.dump({"steps": scene["steps"], "lines": lines}, f, indent=1)
    return {
        "files": [svg.save(os.path.join(WORK, "pacing-chart-%dx%d.svg" % size))],
        "size": size,
        "kind": "image",
        "alt": alt,
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
