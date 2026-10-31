# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""Pick the best take per line by speaker similarity, Furby-ize it, and write build/cloned/ plus A18 previews.

1. Every take in build/voice_mimic/takes2/: trim, cap and normalize it, Whisper it, and score
   its speaker similarity to the held-out real-Furby centroid (furbylib.centroid). It passes
   if the transcript matches (>= PASS) and it's no longer than CAP seconds. The best take
   is the most similar of those that pass.
2. A grid of Furby-ize settings over the picks: keep the one with the highest mean
   similarity whose transcripts all still pass (one setting for every line, so it doesn't
   fit noise). Skipped if furbyize.json exists, unless --regrid. The committed one: up a
   semitone with Praat, formants unchanged, band-limited.
3. Write build/cloned/<name>.wav, build/cloned/preview/<name>.wav (the A18 round trip),
   index.csv, ab_compare.wav (+ .txt), and build/voice_mimic/work2/report.txt.
Args: --regrid to redo step 2.
"""

import csv
import json
import os
import sys

from furbylib import (
    BUILD,
    CAP,
    CHOICE,
    CLONED,
    DATA,
    TRIM,
    a18_preview,
    dur,
    ff,
    finish,
    furbyize,
    lines,
    sim,
    text_score,
    transcript_ok,
    tx,
)

TAKES = os.path.join(DATA, "takes2")
WORK = os.path.join(DATA, "work2")
V1 = os.path.join(BUILD, "cloned_v1")
VARIANTS = (
    [("none", 0, 1.0, False), ("none", 0, 1.0, True)]
    + [("praat", st, f, True) for st in (1, 2, 3, 4) for f in (1.0, 1.1, 1.15)]
    + [("praat", 0, f, True) for f in (1.1, 1.15)]
    + [("chip", st, 1.0, True) for st in (1, 2, 3, 4)]
)
log = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.append(s)


def selectable(v):
    """The first two variants are baselines only (unprocessed; band-limited), so the report can separate the
    channel's effect from the pitch's. Only variants that actually pitch up can be chosen."""
    return v[0] != "none" and v[3] and v[1] > 0


def vname(v):
    return f"{v[0]}_st{v[1]}_f{v[2]}_{'band' if v[3] else 'full'}"


def trimmed_len(src):
    tmp = os.path.join(WORK, "_t.wav")
    ff("-i", src, "-af", TRIM, "-ac", "1", "-ar", "16000", tmp)
    return dur(tmp)


def main():
    import numpy as np

    for d in (WORK, os.path.join(WORK, "fin"), os.path.join(WORK, "grid"), os.path.join(CLONED, "preview")):
        os.makedirs(d, exist_ok=True)
    todo = lines()
    with open(os.path.join(TAKES, "manifest.json")) as f:
        manifest = json.load(f)
    text = {line["name"]: line["text"] for line in todo}

    # ---- 1. score every take (cached by file mtime) ---------------------------------------
    cpath = os.path.join(WORK, "scores.json")
    cache = {}
    if os.path.exists(cpath):
        with open(cpath) as f:
            cache = json.load(f)
    for key, info in manifest.items():
        if info["line"] not in text:
            continue
        raw = os.path.join(TAKES, key + ".wav")
        m = os.path.getmtime(raw)
        if cache.get(key, {}).get("mtime") == m:
            continue
        fin = os.path.join(WORK, "fin", key + ".wav")
        finish(raw, fin)
        t = tx(fin)
        cache[key] = {
            **info,
            "mtime": m,
            "len": trimmed_len(raw),
            "transcript": t,
            "text": text_score(text[info["line"]], t),
            "sim": sim(fin),
        }
        with open(cpath, "w") as f:
            json.dump(cache, f, indent=1)
    cache = {k: c for k, c in cache.items() if c["line"] in text}
    for c in cache.values():  # re-apply the pass rule (cheap) so ALIASES / PASS edits take effect
        c["text"] = text_score(text[c["line"]], c["transcript"])
        c["pass"] = transcript_ok(text[c["line"]], c["transcript"]) and c["len"] <= CAP
    picks = {}
    for line in todo:
        cands = [(k, c) for k, c in cache.items() if c["line"] == line["name"]]
        ok = [kc for kc in cands if kc[1]["pass"]]
        if not ok:
            say(f"WARNING {line['name']}: no take passed; using best transcript match")
            ok = [max(cands, key=lambda kc: (kc[1]["text"], kc[1]["sim"]))]
        picks[line["name"]] = max(ok, key=lambda kc: kc[1]["sim"])
        key, c = picks[line["name"]]
        say(f"{line['name']}: {len(ok)}/{len(cands)} pass; pick {key} sim={c['sim']:.3f}")

    say("\nper-ref: mean sim of passing takes | pass rate | lines won")
    refstats = {}
    for ref in sorted({c["ref"] for c in cache.values()}):
        rs = [c for c in cache.values() if c["ref"] == ref]
        ps = [c["sim"] for c in rs if c["pass"]]
        wins = sum(1 for _, c in picks.values() if c["ref"] == ref)
        say(f"  {ref:8s} {np.mean(ps) if ps else float('nan'):.3f} | {len(ps)}/{len(rs)} | {wins}")
        refstats[ref] = (wins, np.mean(ps) if ps else 0)
    # The ref to reuse: most lines won, then the highest mean similarity (Turbo refs need Turbo, so not those)
    best_ref = max((r for r in refstats if r != "turbo15"), key=lambda r: refstats[r])
    with open(os.path.join(DATA, "best_ref.json"), "w") as f:
        json.dump({"ref": best_ref}, f, indent=1)
    say(f"best ref: {best_ref}")

    # ---- 2. Furby-ize grid ------------------------------------------------------------------
    if "--regrid" in sys.argv or not os.path.exists(CHOICE):
        say(f"\nFurby-ize grid: mean sim over {len(picks)} lines | transcripts passing")
        rows = []
        for v in VARIANTS:
            sims, passes = [], 0
            for name, (key, _) in picks.items():
                tmp, dst = os.path.join(WORK, "grid", "_fz.wav"), os.path.join(WORK, "grid", f"{name}__{vname(v)}.wav")
                furbyize(os.path.join(TAKES, key + ".wav"), tmp, *v)
                finish(tmp, dst)
                sims.append(sim(dst))
                passes += transcript_ok(text[name], tx(dst))
            rows.append((v, float(np.mean(sims)), passes))
            say(f"  {vname(v):28s} {rows[-1][1]:.3f} | {passes}/{len(picks)}")
        sel = [r for r in rows if selectable(r[0])]
        need = max(r[2] for r in sel)
        # allow one Whisper miss: step 3 falls back to that line's next-best take
        best = max((r for r in sel if r[2] >= need - 1), key=lambda r: r[1])
        with open(CHOICE, "w") as f:
            json.dump(
                {
                    "method": best[0][0],
                    "st": best[0][1],
                    "formant": best[0][2],
                    "band": best[0][3],
                    "mean_sim": best[1],
                    "passes": best[2],
                },
                f,
                indent=1,
            )
    with open(CHOICE) as f:
        ch = json.load(f)
    V = (ch["method"], ch["st"], ch["formant"], ch["band"])
    say(f"\nchosen Furby-ize: {vname(V)} (grid mean sim {ch['mean_sim']:.3f}, {ch['passes']} pass)")

    # ---- 3. final lines, previews, index, A/B playlist -------------------------------------
    idx = []
    say("\nname | v1 sim | before | after | a18 | ref | transcript")
    tmp = os.path.join(WORK, "_fz.wav")
    for line in todo:
        name = line["name"]
        dst, prev = os.path.join(CLONED, name + ".wav"), os.path.join(CLONED, "preview", name + ".wav")
        # the best passing take whose transcript still passes after Furby-ize (fallback: the top pick)
        ranked = sorted(
            [(k, c) for k, c in cache.items() if c["line"] == name and c["pass"]], key=lambda kc: -kc[1]["sim"]
        ) or [picks[name]]
        for n, (key, c) in enumerate(ranked):  # noqa: B007 (both are used after the loop)
            furbyize(os.path.join(TAKES, key + ".wav"), tmp, *V)
            finish(tmp, dst)
            t_after = tx(dst)
            if transcript_ok(line["text"], t_after):
                break
        else:
            (key, c), n = ranked[0], 0
            furbyize(os.path.join(TAKES, key + ".wav"), tmp, *V)
            finish(tmp, dst)
            t_after = tx(dst)
        if n:
            say(f"  {name}: top take failed Whisper after Furby-ize; using #{n + 1} {key}")
        a18_preview(dst, prev)
        t_prev = tx(prev)
        v1 = os.path.join(V1, name + ".wav")
        s_v1 = sim(v1) if os.path.exists(v1) else float("nan")
        s_after, s_prev = sim(dst), sim(prev)
        settings = " ".join(f"{k}={c[k]}" for k in ("exaggeration", "cfg_weight", "temperature", "seed") if k in c)
        idx.append(
            {
                "name": name,
                "text": line["text"],
                "seconds": f"{dur(dst):.2f}",
                "transcript": t_after,
                "similarity_before": f"{c['sim']:.3f}",
                "similarity_after": f"{s_after:.3f}",
                "similarity_a18": f"{s_prev:.3f}",
                "similarity_v1": f"{s_v1:.3f}",
                "transcript_a18": t_prev,
                "ref": c["ref"],
                "settings": f"engine={c['engine']} take={key} {settings} furbyize={vname(V)}",
            }
        )
        flag = "" if transcript_ok(line["text"], t_after) else "  <-- transcript fails check, listen"
        say(f"{name} | {s_v1:.3f} | {c['sim']:.3f} | {s_after:.3f} | {s_prev:.3f} | {c['ref']} | {t_after}{flag}")
    with open(os.path.join(CLONED, "index.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(idx[0]))
        w.writeheader()
        w.writerows(idx)
    for k in ("similarity_v1", "similarity_before", "similarity_after", "similarity_a18"):
        say(f"mean {k}: {np.mean([float(r[k]) for r in idx]):.3f}")

    # A/B playlist: per line the previous clone, the new one, and its A18 preview, 0.7 s of silence between
    gap = os.path.join(WORK, "gap.wav")
    ff("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.7", "-c:a", "pcm_s16le", gap)
    seq, order, t0 = [], [], 0.0
    for line in todo:
        for label, p in (
            ("v1", os.path.join(V1, line["name"] + ".wav")),
            ("v2", os.path.join(CLONED, line["name"] + ".wav")),
            ("v2-a18", os.path.join(CLONED, "preview", line["name"] + ".wav")),
        ):
            if not os.path.exists(p):
                continue
            norm = os.path.join(WORK, f"ab_{len(seq)}.wav")
            ff("-i", p, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", norm)
            order.append(f"{t0:6.1f}s  {line['name']:14s} {label:7s} {os.path.relpath(p, BUILD)}")
            seq += [norm, gap]
            t0 += dur(norm) + 0.7
    listing = os.path.join(WORK, "ab.txt")
    with open(listing, "w") as f:
        f.writelines(f"file '{p}'\n" for p in seq[:-1])
    ff("-f", "concat", "-safe", "0", "-i", listing, "-c:a", "pcm_s16le", os.path.join(CLONED, "ab_compare.wav"))
    with open(os.path.join(CLONED, "ab_compare.txt"), "w") as f:
        f.write(
            "ab_compare.wav order (start time, line, version, file). v1 = previous clone, "
            "v2 = new pick + Furby-ize, v2-a18 = v2 after the A1800 16 kbit/s round trip "
            "(what the Furby plays). 0.7 s silence between clips.\n\n" + "\n".join(order) + "\n"
        )
    with open(os.path.join(WORK, "report.txt"), "w") as f:
        f.write("\n".join(log) + "\n")


if __name__ == "__main__":
    main()
