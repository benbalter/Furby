# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Shared paths and helpers for the voice-mimic pipeline: the show's lines, similarity
scoring, Whisper checks, "Furby-izing" and the A1800 round trip.

Everything this pipeline writes goes in build/ (gitignored): its working files in
build/voice_mimic/ and the finished lines in build/cloned/, where show.toml looks. The
samples come from build/voice/, which audioutils/extract_voice.py decodes from your
stock DLC. They're Hasbro's recordings, so nothing here may be published.

Needs (see run2.sh): resemblyzer, praat-parselmouth, mlx-whisper, a1800-codec.
"""

import contextlib
import csv
import difflib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(ROOT, "build")
VOICE = os.path.join(BUILD, "voice")  # the stock DLC's clips, from audioutils/extract_voice.py
DATA = os.path.join(BUILD, "voice_mimic")  # refs, takes, scores: everything this pipeline makes
CLONED = os.path.join(BUILD, "cloned")  # the finished lines, where show.toml looks for them
SHOW = os.path.join(ROOT, "halloween", "show.toml")
sys.path.insert(0, os.path.join(ROOT, "audioutils"))
CAP = 4.0
PASS = 0.8  # min normalized transcript match; add spellings to ALIASES rather than lowering this
WHISPER = "mlx-community/whisper-small-mlx"

# Settings chosen by best.py's grid (mean speaker similarity over the lines); committed as the default
CHOICE = os.path.join(HERE, "furbyize.json")

ALIASES = {
    "gimme": "give me",
    "caw": "kah",
    "ca": "kah",
    "ka": "kah",
    "cah": "kah",
    "call": "kah",
    "car": "kah",
    "kaa": "kah",
    "kar": "kah",
    "cuz": "kah",
    "nula": "noo lah",
    "noola": "noo lah",
    "nulah": "noo lah",
    "noolah": "noo lah",
    "nuela": "noo lah",
    "mwahaha": "mwa ha ha",
    "muahaha": "mwa ha ha",
    "bwahaha": "mwa ha ha",
    "mwah": "mwa",
    "hahaha": "ha ha ha",
}


def lines(only=()):
    """The show's voice lines from show.toml, as [{"name", "text"}]: each clip with words whose file is in
    build/cloned/, named for that file (pink_boo for build/cloned/pink_boo.wav)."""
    with open(SHOW, "rb") as f:
        show = tomllib.load(f)
    found = []
    for furby in show["furbies"].values():
        for value in furby.get("clips", {}).values():
            if isinstance(value, dict) and value.get("text") and value.get("path", "").startswith("build/cloned/"):
                name = os.path.splitext(os.path.basename(value["path"]))[0]
                if not only or name in only:
                    found.append({"name": name, "text": value["text"]})
    return found


def norm(s):
    s = s.lower().replace("-", " ")
    for a, b in ALIASES.items():
        s = re.sub(rf"\b{a}\b", b, s)
    return re.sub(r"[^a-z ]", "", s).split()


def text_score(ref, hyp):
    return difflib.SequenceMatcher(None, " ".join(norm(ref)), " ".join(norm(hyp))).ratio()


# Line-specific misreads the char ratio can't see. Whisper's punctuation reflects the take's
# pauses: "No! Feed after midnight!" flips the Gremlins rule into "no, (go ahead and) feed".
REJECT = {"No feed after midnight...": r"^\W*no\W*[,.!?]"}


def transcript_ok(ref, hyp):
    """Close enough (>= PASS), no added words (e.g. "Ah, yay!"), and no line-specific misread."""
    return (
        text_score(ref, hyp) >= PASS
        and len(norm(hyp)) <= len(norm(ref))
        and not (ref in REJECT and re.search(REJECT[ref], hyp, re.I))
    )


_whisper = None


def tx(path):
    """Whisper's transcript of path."""
    global _whisper
    if _whisper is None:
        import mlx_whisper as _whisper
    return _whisper.transcribe(path, path_or_hf_repo=WHISPER, language="en")["text"].strip()


def dur(path):
    return float(
        subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    )


def ff(*a):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


# ---- speaker similarity -------------------------------------------------------------------
_enc = None


def embed(path):
    global _enc
    from resemblyzer import VoiceEncoder, preprocess_wav

    if _enc is None:
        _enc = VoiceEncoder("cpu", verbose=False)
    return _enc.embed_utterance(preprocess_wav(path))


def target_clips():
    """Clean real Furby speech (clips.csv clean=1) minus every clip used in a candidate ref,
    so no ref wins just by containing the clips it's scored against."""
    with open(os.path.join(DATA, "refs", "refs.json")) as f:
        used = {t for r in json.load(f).values() for t in r["clips"]}
    with open(os.path.join(DATA, "clips.csv")) as f:
        return [r["file"] for r in csv.DictReader(f) if r["clean"] == "1" and int(r["file"][6:9]) not in used]


_cen = None


def centroid():
    """The mean voice embedding of the target clips: what "sounds like the real Furby" means here."""
    global _cen
    import numpy as np

    if _cen is None:  # recomputed each run (a few seconds) so it can't go stale if refs change
        e = np.mean([embed(os.path.join(VOICE, f)) for f in target_clips()], axis=0)
        _cen = e / np.linalg.norm(e)
    return _cen


def sim(path):
    return float(embed(path) @ centroid())


# ---- post-processing ----------------------------------------------------------------------
TRIM = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
    "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse"
)


def finish(src, dst):
    """Trim the silence, cap at CAP seconds, fade out over 0.1 s and normalize loudness, at 16 kHz mono."""
    tmp = dst + ".tmp.wav"
    ff("-i", src, "-af", TRIM, "-t", str(CAP), "-ac", "1", "-ar", "16000", tmp)
    d = dur(tmp)
    ff(
        "-i",
        tmp,
        "-af",
        f"afade=t=out:st={max(d - 0.1, 0):.3f}:d=0.1,loudnorm=I=-14:TP=-1.5:LRA=11",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        dst,
    )
    os.remove(tmp)


BAND = "highpass=f=300:poles=2,lowpass=f=5000:poles=2"


def furbyize(src, dst, method="praat", st=0.0, formant=1.0, band=True):
    """Pitch up `st` semitones and scale formants by `formant`, then band-limit 300 Hz-5 kHz.

    method: "praat" = Praat's Change gender (PSOLA; pitch and formants independent),
            "chip"  = asetrate+atempo (formants move with pitch, like a sped-up tape),
            "none"  = no pitch change.
    """
    import parselmouth
    from parselmouth.praat import call

    with tempfile.TemporaryDirectory() as td:
        x = os.path.join(td, "in.wav")
        ff("-i", src, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", x)
        y = os.path.join(td, "p.wav")
        if method == "praat" and (st or formant != 1.0):
            snd = parselmouth.Sound(x)
            med = call(snd.to_pitch_ac(pitch_floor=100, pitch_ceiling=900), "Get quantile", 0, 0, 0.5, "Hertz")
            new_med = (med * 2 ** (st / 12)) if st and med == med else 0.0  # NaN-safe; 0 = keep
            out = call(snd, "Change gender", 100, 900, formant, new_med, 1.0, 1.0)
            call(out, "Scale peak", 0.9)  # PSOLA overshoots full scale; without this the save clips
            out.save(y, "WAV")
        elif method == "chip" and st:
            r = 2 ** (st / 12)
            ff("-i", x, "-af", f"asetrate={16000 * r:.0f},atempo={1 / r:.5f},aresample=16000", y)
        else:
            y = x
        ff("-i", y, "-af", BAND if band else "anull", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst)


def a18_preview(src, dst):
    """Encode with audioutils/encode_a18.py exactly as the Furby upload would, then decode: what the Furby plays."""
    import a1800_codec
    from encode_a18 import encode

    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "x.a18")
        with contextlib.redirect_stdout(io.StringIO()):
            encode(src, a)
        with open(a, "rb") as f:
            pcm = bytes(a1800_codec.decode(f.read()))
    with wave.open(dst, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    assert abs(dur(dst) - dur(src)) < 0.1, f"A18 round trip changed duration: {src}"
