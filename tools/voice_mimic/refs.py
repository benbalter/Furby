# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""Build candidate Chatterbox reference clips into build/voice_mimic/refs/, with refs.json.

Chatterbox reads only the first 6 s of a ref for style and prosody (ENC_COND_LEN) and the
first 10 s for timbre (DEC_COND_LEN), so each ref puts its most Furby-like clips first
(high-pitched, excited speech, ranked in clips.csv by analyze.py) and stays under 10 s.
Turbo reads 15 s for the encoder, so it gets a longer ref. Clips used by any ref are held
out of the similarity target (see furbylib.centroid).
"""

import json
import os
import tempfile

from furbylib import DATA, VOICE, dur, ff

OUT = os.path.join(DATA, "refs")
REFS = {
    "hi": ([109, 73, 70, 104, 16, 7], 10.0),  # highest median pitch first
    "kitten": ([88, 70, 109, 112, 73, 26], 10.0),  # a favourite clip first, then short excited lines
    "excited": ([72, 107, 56, 61], 10.0),  # excited lines nearest the speech centroid, mid pitch
    "turbo15": ([109, 73, 70, 104, 88, 112, 16, 7, 26], 15.0),  # Turbo: a 15 s encoder window
}
TRIM = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,areverse"
)
OLD_REF = [9, 52, 64, 88]  # make_ref.sh's ref.wav, kept as the baseline candidate "v1"


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    v1 = os.path.join(DATA, "ref.wav")
    meta = {"v1": {"path": v1, "clips": OLD_REF, "seconds": round(dur(v1), 2)}}
    with tempfile.TemporaryDirectory() as td:
        gap = os.path.join(td, "gap.wav")
        ff("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.25", gap)
        for name, (clips, cap) in REFS.items():
            total, used, parts = 0.0, [], []
            for t in clips:
                seg = os.path.join(td, f"seg_{t:03d}.wav")
                ff("-i", os.path.join(VOICE, f"track_{t:03d}.wav"), "-af", TRIM, "-ar", "16000", "-ac", "1", seg)
                d = dur(seg) + 0.25
                if total + d > cap + 0.25:
                    continue
                total += d
                used.append(t)
                parts += [seg, gap]
            listing = os.path.join(td, f"{name}.txt")
            with open(listing, "w") as f:
                f.writelines(f"file '{p}'\n" for p in parts[:-1])
            dst = os.path.join(OUT, f"{name}.wav")
            # -2 dB keeps peaks under full scale after Chatterbox resamples to 24 kHz
            ff("-f", "concat", "-safe", "0", "-i", listing, "-af", "volume=-2dB", "-c:a", "pcm_s16le", dst)
            meta[name] = {"path": dst, "clips": used, "seconds": round(dur(dst), 2)}
            print(name, meta[name]["seconds"], "s", used)
    with open(os.path.join(OUT, "refs.json"), "w") as f:
        json.dump(meta, f, indent=1)
