# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""Rank the stock Furby clips for use as Chatterbox references and as the similarity target.

Reads build/voice_mimic/voice_transcripts.csv (from transcribe.py) and writes clips.csv
(median F0, voiced fraction, resemblyzer similarity to the speech centroid, transcript) and
furby_centroid.npy (mean embedding of clean speech clips) into build/voice_mimic/. Both are
derived from Hasbro's recordings, so they stay in build/.

Run: uv run --no-project --python 3.11 --with resemblyzer --with praat-parselmouth \\
       --with 'setuptools<80' python analyze.py
"""

import csv
import os

from furbylib import DATA, VOICE

# Songs, singing and jingles (by track number, from their transcripts): left out of refs and the centroid
# fmt: off
SUNG = {3, 4, 5, 6, 10, 11, 13, 17, 18, 23, 24, 29, 32, 33, 34, 35, 38, 40, 42, 43, 46, 51,
        53, 57, 68, 69, 77, 79, 113, 114, 115, 116, 117, 118, 119, 120, 121, 125, 133, 137, 138, 139, 140, 143,
        144, 145, 20, 21, 22, 45, 124, 103, 76, 30, 36, 44, 65, 123}
# fmt: on


def f0_stats(path):
    import numpy as np
    import parselmouth

    p = parselmouth.Sound(path).to_pitch_ac(pitch_floor=120, pitch_ceiling=1200)
    f = p.selected_array["frequency"]
    v = f[f > 0]
    if len(v) < 5:
        return 0.0, 0.0, 0.0
    return float(np.median(v)), float(np.percentile(v, 90)), len(v) / len(f)


def clean(row):
    t = int(row["file"][6:9])
    return (
        t not in SUNG
        and 0.8 <= float(row["seconds"]) <= 4.5
        and float(row["no_speech_prob"]) < 0.2
        and float(row["avg_logprob"]) > -0.8
    )


if __name__ == "__main__":
    import numpy as np
    from resemblyzer import VoiceEncoder, preprocess_wav

    with open(os.path.join(DATA, "voice_transcripts.csv")) as f:
        rows = list(csv.DictReader(f))
    enc = VoiceEncoder("cpu", verbose=False)
    emb = {}
    for r in rows:
        r["f0_med"], r["f0_p90"], r["voiced"] = f0_stats(os.path.join(VOICE, r["file"]))
        r["clean"] = clean(r)
        if r["clean"]:
            emb[r["file"]] = enc.embed_utterance(preprocess_wav(os.path.join(VOICE, r["file"])))
    cen = np.mean(list(emb.values()), axis=0)
    cen /= np.linalg.norm(cen)
    np.save(os.path.join(DATA, "furby_centroid.npy"), cen)
    for r in rows:
        r["sim"] = float(emb[r["file"]] @ cen) if r["file"] in emb else ""
    with open(os.path.join(DATA, "clips.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "seconds", "f0_med", "f0_p90", "voiced", "clean", "sim", "transcript"])
        for r in sorted(rows, key=lambda r: -r["f0_med"]):
            w.writerow(
                [
                    r["file"],
                    r["seconds"],
                    f"{r['f0_med']:.0f}",
                    f"{r['f0_p90']:.0f}",
                    f"{r['voiced']:.2f}",
                    int(r["clean"]),
                    f"{r['sim']:.3f}" if r["sim"] != "" else "",
                    r["whisper_transcript"],
                ]
            )
    print(f"centroid from {len(emb)} clean speech clips")
