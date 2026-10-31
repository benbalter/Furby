# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""Transcribe every stock clip in build/voice/ with Whisper, for analyze.py.

Writes build/voice_mimic/voice_transcripts.csv: file, seconds, the transcript, and
Whisper's confidence (no_speech_prob, avg_logprob of the first segment), which analyze.py
uses to keep clean speech and drop singing, effects and mumbles. The transcripts are of
Hasbro's recordings, so the file stays in build/.

Run: uv run --no-project --python 3.11 --with mlx-whisper python transcribe.py
"""

import csv
import os

from furbylib import DATA, VOICE, WHISPER, dur

if __name__ == "__main__":
    import mlx_whisper

    os.makedirs(DATA, exist_ok=True)
    rows = []
    for name in sorted(f for f in os.listdir(VOICE) if f.startswith("track_") and f.endswith(".wav")):
        path = os.path.join(VOICE, name)
        result = mlx_whisper.transcribe(path, path_or_hf_repo=WHISPER, language="en")
        first = (result.get("segments") or [{}])[0]
        rows.append(
            [
                name,
                "%.2f" % dur(path),
                result["text"].strip(),
                "%.3f" % first.get("no_speech_prob", 1.0),
                "%.3f" % first.get("avg_logprob", -9.0),
            ]
        )
    with open(os.path.join(DATA, "voice_transcripts.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "seconds", "whisper_transcript", "no_speech_prob", "avg_logprob"])
        w.writerows(rows)
    print("transcribed %d clips" % len(rows))
