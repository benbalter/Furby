#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Make stand-in audio for the show's voice lines with the computer's own voices.

Each voice line in halloween/show.toml has its words in text = "...". For every
one whose file doesn't exist yet, this speaks the text with macOS's say (or
espeak-ng / espeak elsewhere), trims the silence at each end with ffmpeg, and
saves a 16 kHz mono WAV at the clip's path, ready for halloween.py. It won't
sound like a Furby, but it gets the whole show working, and you can replace
any line with a real recording later: files that already exist are left alone
unless you pass --force.

USAGE:
    uv run voices.py                  # make every missing line
    uv run voices.py --list           # each line, its words, and whether it has audio yet
    uv run voices.py --furby pink     # just pink's lines
    uv run voices.py --voice Whisper  # another voice (say -v '?' lists them)
    uv run voices.py --force          # remake lines that already exist

Each Furby gets its own default voice, so they sound different. Choose others
in show.toml: voice = "..." under [furbies.pink] for say, espeak = "..." for
espeak-ng.
"""

import argparse
import contextlib
import io
import os
import re
import shutil
import subprocess
import tempfile

import halloween

# Default voices, so the two Furbies sound different: a croaky one for evil
# pink and a kid's for friendly blue. Every Mac has these novelty voices.
DEFAULTS = {
    "say": {"pink": "Albert", "blue": "Junior"},
    "espeak": {"pink": "en+croak", "blue": "en+f4"},
}
# Where each engine's voice lives in a Furby's show.toml table
VOICE_KEY = {"say": "voice", "espeak": "espeak"}
LIST_VOICES = {"say": "say -v '?'", "espeak": "espeak-ng --voices=variant"}
# Cut quiet (below -50 dB) from the start, then reverse and do the same for the end
TRIM = ",".join(["silenceremove=start_periods=1:start_threshold=-50dB", "areverse"] * 2)


class Engine:
    """A text-to-speech command: say, espeak-ng or espeak."""

    def __init__(self, name, command):
        self.name = name  # "say" or "espeak", the key into DEFAULTS
        self.command = command
        self._voices = None

    def speak(self, text, voice, out):
        """Write the spoken text to out (any format ffmpeg reads)."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(text)  # from a file, so text starting with "-" isn't read as an option
        try:
            if self.name == "say":
                cmd = [self.command, "-o", out, "-f", f.name] + (["-v", voice] if voice else [])
            else:
                cmd = [self.command, "-w", out, "-f", f.name] + (["-v", voice] if voice else [])
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        finally:
            os.unlink(f.name)

    @property
    def suffix(self):
        return ".aiff" if self.name == "say" else ".wav"

    def has_voice(self, voice):
        """Whether this computer has the voice; True when that can't be told."""
        if self.name != "say":
            return True  # espeak takes variants in so many spellings that it's best left to say no itself
        if self._voices is None:
            listing = subprocess.run([self.command, "-v", "?"], capture_output=True, text=True).stdout
            # "Albert              en_US    # Hello!" or "Eddy (English (US)) en_US    # Hi"
            self._voices = {m.group(1) for m in re.finditer(r"^(.+?)\s+[a-z]{2,3}_\w+\s+#", listing, re.M)}
        return voice in self._voices


def find_engine(which=shutil.which):
    """The first text-to-speech command this computer has, or None."""
    if which("say"):
        return Engine("say", which("say"))
    for command in ("espeak-ng", "espeak"):
        if which(command):
            return Engine("espeak", which(command))
    return None


def to_wav(src, out):
    """src as a 16 kHz mono 16-bit WAV at out, with the silence at each end trimmed."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-af", TRIM, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out]
    subprocess.run(cmd, check=True)


def voice_lines(show, only=None):
    """(furby, clip, spec) for each clip with text, in show.toml order."""
    for name, furby in show["furbies"].items():
        if only and name not in only:
            continue
        for clip, value in furby.get("clips", {}).items():
            spec = halloween.clip_spec(value)
            if spec.get("text"):
                yield name, clip, spec


def pick_voice(engine, name, furby, voice=None, log=print):
    """The voice for this Furby's lines: --voice, then show.toml, then the default (None: the system's)."""
    key = VOICE_KEY[engine.name]
    chosen = voice or furby.get(key)
    if chosen:
        if not engine.has_voice(chosen):
            where = "--voice" if voice else "[furbies.%s] %s in show.toml" % (name, key)
            raise SystemExit("This computer has no %r voice (from %s). See the choices: %s"
                             % (chosen, where, LIST_VOICES[engine.name]))  # fmt: skip
        return chosen
    default = DEFAULTS[engine.name].get(name)
    if default and engine.has_voice(default):
        return default
    if default:
        log("%s: no %s voice here, so using the system voice." % (name, default))
    return None


def make_voices(show, engine, only=None, voice=None, force=False, convert=to_wav, log=print):
    """Synthesize each missing voice line; returns (made, kept), lists of "furby.clip"."""
    made, kept, voices = [], [], {}
    for name, clip, spec in voice_lines(show, only):
        path = spec["path"]
        if os.path.exists(path) and not force:
            kept.append("%s.%s" % (name, clip))
            continue
        if name not in voices:
            voices[name] = pick_voice(engine, name, show["furbies"][name], voice, log)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "raw" + engine.suffix)
            try:
                engine.speak(spec["text"], voices[name], raw)
                convert(raw, path)
            except subprocess.CalledProcessError as e:
                raise SystemExit(
                    "%s.%s: couldn't make %s: %s stopped with an error (voice: %s). See the voices: %s"
                    % (name, clip, path, os.path.basename(e.cmd[0]), voices[name], LIST_VOICES[engine.name])
                ) from None
        log("%s.%s: %s (%s)" % (name, clip, path, voices[name] or "system voice"))
        made.append("%s.%s" % (name, clip))
    return made, kept


def missing_clips(show):
    """Clips that still have no audio, other than optional ones."""
    return [
        "%s.%s" % (name, clip)
        for name, furby in show["furbies"].items()
        for clip, value in furby.get("clips", {}).items()
        if not (spec := halloween.clip_spec(value))["optional"] and not os.path.exists(spec["path"])
    ]


def list_lines(show, only=None, log=print):
    for name, clip, spec in voice_lines(show, only):
        state = "ok     " if os.path.exists(spec["path"]) else "missing"
        log('%s  %-20s "%s"  (%s)' % (state, "%s.%s" % (name, clip), spec["text"], spec["path"]))


def main(argv=None, engine=None, convert=None, which=shutil.which, log=print):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--show", default="./halloween/show.toml", help="the show (default: %(default)s)")
    parser.add_argument("--furby", action="append", metavar="NAME", help="just this Furby's lines (repeatable)")
    parser.add_argument("--voice", help="use this voice for every line, instead of each Furby's own")
    parser.add_argument("--force", action="store_true", help="remake lines whose files already exist")
    parser.add_argument("--list", action="store_true", help="list each line and whether it has audio yet")
    args = parser.parse_args(argv)
    if not os.path.exists(args.show):
        raise SystemExit("No %s. Run this from the Furby folder." % args.show)
    with contextlib.redirect_stdout(io.StringIO()):  # its notes about unused clips aren't news here
        show = halloween.load_show(args.show)
    unknown = sorted(set(args.furby or []) - set(show["furbies"]))
    if unknown:
        raise SystemExit("This show has no %s Furby; it has %s." % (", ".join(unknown), ", ".join(show["furbies"])))
    if args.list:
        list_lines(show, args.furby, log)
        return
    engine = engine or find_engine(which)
    if engine is None:
        raise SystemExit(
            "No text-to-speech here: this needs macOS's say, or espeak-ng "
            "(brew install espeak-ng, or apt install espeak-ng)."
        )
    if convert is None:
        if not which("ffmpeg"):
            raise SystemExit(
                "This needs ffmpeg to convert and trim the audio: brew install ffmpeg (or apt install ffmpeg)"
            )
        convert = to_wav
    made, kept = make_voices(show, engine, args.furby, args.voice, args.force, convert, log)
    log("\nMade %d voice line%s with %s." % (len(made), "" if len(made) == 1 else "s", engine.command))
    if kept:
        log("Kept %d that already had audio (--force remakes them)." % len(kept))
    missing = missing_clips(show)
    log("Next, build the show: uv run halloween.py%s" % (" --skip-missing" if missing else ""))
    if missing:
        log("(--skip-missing leaves out what's still missing: %s)" % ", ".join(missing))
    log("Then hear it on this computer: uv run porch.py --rehearse")


if __name__ == "__main__":
    main()
