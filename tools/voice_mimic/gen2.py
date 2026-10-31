# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""Best-of-N generation: every line × every candidate ref × a small settings grid.

Writes build/voice_mimic/takes2/<line>__<ref>__<k>.wav plus takes2/manifest.json.
Resumable: existing takes are skipped. Args: optional line names; --turbo also tries
ChatterboxTurboTTS on refs/turbo15.wav. Run via run2.sh.
"""

import json
import os
import sys

from furbylib import DATA, lines

TAKES = os.path.join(DATA, "takes2")
REFS = ["v1", "hi", "kitten", "excited"]
# (exaggeration, cfg_weight, temperature, seed) per personality: pink gets more drama
GRID = {"blue": [(0.5, 0.5, 0.8, 1), (0.65, 0.4, 0.9, 2)], "pink": [(0.7, 0.3, 0.8, 1), (0.9, 0.3, 0.9, 2)]}
TURBO_GRID = [(0.8, 1), (0.95, 2)]  # (temperature, seed); Turbo ignores exaggeration and cfg


def device():
    import torch

    if torch.backends.mps.is_available():  # checkpoints were saved on CUDA; map them to the CPU first
        orig = torch.load
        torch.load = lambda *a, **k: orig(*a, **{**k, "map_location": k.get("map_location", torch.device("cpu"))})
        return "mps"
    return "cpu"


def main():
    import torch
    import torchaudio as ta

    turbo = "--turbo" in sys.argv
    todo = lines({a for a in sys.argv[1:] if not a.startswith("--")})
    with open(os.path.join(DATA, "refs", "refs.json")) as f:
        refs = json.load(f)
    os.makedirs(TAKES, exist_ok=True)
    mpath = os.path.join(TAKES, "manifest.json")
    manifest = {}
    if os.path.exists(mpath):
        with open(mpath) as f:
            manifest = json.load(f)

    def done(key):
        return os.path.exists(os.path.join(TAKES, key + ".wav"))

    def save(key, wav, sr, info):
        ta.save(os.path.join(TAKES, key + ".wav"), wav.cpu(), sr)
        manifest[key] = info
        with open(mpath, "w") as f:
            json.dump(manifest, f, indent=1)
        print(key, info, round(wav.shape[-1] / sr, 2), flush=True)

    keys = [
        f"{line['name']}__{r}__{k}" for r in REFS for line in todo for k in range(len(GRID[line["name"].split("_")[0]]))
    ]
    turbo_keys = [f"{line['name']}__turbo15__{k}" for line in todo for k in range(len(TURBO_GRID))] if turbo else []
    if all(done(k) for k in keys + turbo_keys):
        print("all takes present; nothing to generate")
        return
    d = device()
    from chatterbox.tts import ChatterboxTTS

    model = ChatterboxTTS.from_pretrained(device=d)
    for ref in REFS:
        model.prepare_conditionals(refs[ref]["path"], exaggeration=0.5)  # embed the ref once per ref
        for line in todo:
            for k, (ex, cfg, temp, seed) in enumerate(GRID[line["name"].split("_")[0]]):
                key = f"{line['name']}__{ref}__{k}"
                if done(key):
                    continue
                torch.manual_seed(seed)
                wav = model.generate(line["text"], exaggeration=ex, cfg_weight=cfg, temperature=temp)
                save(
                    key,
                    wav,
                    model.sr,
                    {
                        "line": line["name"],
                        "ref": ref,
                        "engine": f"ChatterboxTTS/{d}",
                        "exaggeration": ex,
                        "cfg_weight": cfg,
                        "temperature": temp,
                        "seed": seed,
                    },
                )
    if turbo:
        del model
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            tm = ChatterboxTurboTTS.from_pretrained(device=d)
            tm.prepare_conditionals(refs["turbo15"]["path"])
            for line in todo:
                for k, (temp, seed) in enumerate(TURBO_GRID):
                    key = f"{line['name']}__turbo15__{k}"
                    if done(key):
                        continue
                    torch.manual_seed(seed)
                    wav = tm.generate(line["text"], temperature=temp)
                    save(
                        key,
                        wav,
                        tm.sr,
                        {
                            "line": line["name"],
                            "ref": "turbo15",
                            "engine": f"ChatterboxTurboTTS/{d}",
                            "temperature": temp,
                            "seed": seed,
                        },
                    )
        except Exception as e:
            print("Turbo skipped:", repr(e), file=sys.stderr)


if __name__ == "__main__":
    main()
