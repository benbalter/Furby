# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""The first pipeline's generator: raw Chatterbox takes of each line, mimicking ref.wav.

Writes build/voice_mimic/takes/<line>_t<k>.wav, one per (exaggeration, cfg_weight) in TAKES.
gen2.py replaced it (more refs, best-of-N); it's kept as the simple version of the idea.
Args: optional line names, to make just those.

Run: uv run --no-project --python 3.11 --with chatterbox-tts --with 'setuptools<80' python gen.py
"""

import json
import os
import sys

from furbylib import DATA, lines

TAKES = [(0.5, 0.5), (0.6, 0.4)]  # (exaggeration, cfg_weight): how much drama, how closely it follows the text


def load():
    import torch
    from chatterbox.tts import ChatterboxTTS

    if torch.backends.mps.is_available():  # checkpoints were saved on CUDA; map them to the CPU first
        orig = torch.load
        torch.load = lambda *a, **k: orig(*a, **{**k, "map_location": k.get("map_location", torch.device("cpu"))})
        try:
            return ChatterboxTTS.from_pretrained(device="mps"), "mps"
        except Exception as e:
            print("mps failed, falling back to cpu:", e, file=sys.stderr)
    return ChatterboxTTS.from_pretrained(device="cpu"), "cpu"


if __name__ == "__main__":
    import torch
    import torchaudio as ta

    model, dev = load()
    print("device", dev, flush=True)
    out = os.path.join(DATA, "takes")
    os.makedirs(out, exist_ok=True)
    ref = os.path.join(DATA, "ref.wav")
    for line in lines(set(sys.argv[1:])):
        for i, (ex, cfg) in enumerate(TAKES):
            torch.manual_seed(1000 + i)
            wav = model.generate(line["text"], audio_prompt_path=ref, exaggeration=ex, cfg_weight=cfg)
            ta.save(os.path.join(out, f"{line['name']}_t{i}.wav"), wav.cpu(), model.sr)
            print(line["name"], i, ex, cfg, round(wav.shape[-1] / model.sr, 2), flush=True)
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump({"device": dev}, f)
