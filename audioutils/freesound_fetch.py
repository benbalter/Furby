#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Fetch public-domain (CC0) sound effects from Freesound, trimmed for a Furby.

Searches https://freesound.org for CC0 sounds only, so nothing needs
attribution, downloads each one's high-quality preview, and uses ffmpeg to
trim it, fade it out and normalize its loudness. The results are WAVs that
spooky_eyes.py converts to .a18 when it builds.

Needs a free Freesound API key (https://freesound.org/apiv2/apply) in
FREESOUND_API_KEY. With 1Password, keep it out of your shell and off disk:

    FREESOUND_API_KEY="op://<vault>/<item>/<field>" \\
        op run -- python audioutils/freesound_fetch.py "witch cackle" scream

Writes build/sfx/<query>-<n>.wav and build/sfx/credits.csv.
"""

import argparse
import csv
import json
import os
import subprocess
import urllib.parse
import urllib.request

API = "https://freesound.org/apiv2/search/text/"


def search(query, key, count=3, max_seconds=6):
    params = {
        "query": query,
        "filter": 'license:"Creative Commons 0" duration:[0.3 TO %d]' % max_seconds,
        "fields": "id,name,username,url,duration,previews",
        "sort": "rating_desc",
        "page_size": count,
        "token": key,
    }
    with urllib.request.urlopen(API + "?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.load(r)["results"]


def trim(src, dst, seconds, loudness):
    """Trim, fade out the last 0.3 s, and normalize to a target loudness (LUFS)."""
    fade = max(seconds - 0.3, 0)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            src,
            "-t",
            str(seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "afade=t=out:st=%s:d=0.3,loudnorm=I=%s:TP=-1" % (fade, loudness),
            dst,
        ],
        check=True,
    )


def fetch(queries, out_dir="./build/sfx", count=3, seconds=3.0, loudness=-14):
    key = os.environ.get("FREESOUND_API_KEY")
    if not key:
        raise SystemExit("Set FREESOUND_API_KEY (see --help for running it with 1Password).")
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for query in queries:
        slug = "-".join(query.lower().split())
        for n, sound in enumerate(search(query, key, count)):
            raw = os.path.join(out_dir, "%s-%d.mp3" % (slug, n))
            urllib.request.urlretrieve(sound["previews"]["preview-hq-mp3"], raw)
            wav = raw[:-4] + ".wav"
            trim(raw, wav, min(seconds, sound["duration"]), loudness)
            os.remove(raw)
            rows.append([os.path.basename(wav), sound["name"], sound["username"], sound["url"]])
            print("%s  ←  %s by %s" % (wav, sound["name"], sound["username"]))
    with open(os.path.join(out_dir, "credits.csv"), "a", newline="") as f:
        csv.writer(f).writerows(rows)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("queries", nargs="+", help='searches, e.g. "witch cackle" scream')
    parser.add_argument("-n", "--count", type=int, default=3, help="sounds per search")
    parser.add_argument("-s", "--seconds", type=float, default=3.0, help="trim each to this length")
    parser.add_argument("--loudness", type=float, default=-14, help="target LUFS; louder is closer to 0")
    parser.add_argument("-o", "--out-dir", default="./build/sfx")
    args = parser.parse_args()
    fetch(args.queries, args.out_dir, args.count, args.seconds, args.loudness)
