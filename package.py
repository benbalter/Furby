#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Zip up a built Halloween show for a friend to flash and run without building it.

The zip holds build/halloween/show.json and each Furby's DLC, at the paths
deploy.py and porch.py look for, plus README_FIRST.txt with the commands. Your
friend gets this repository, unzips the bundle into it, and runs
uv run deploy.py --no-build, then uv run porch.py. They need neither ffmpeg
nor the audio. Before zipping, this checks each DLC against the checksum in
show.json, so the show and the Furbies will agree.

The DLCs are built from the Furby's stock DLC, which is Hasbro's, so the zip
is for sharing privately with a friend: never publish it or commit it.

USAGE:
    uv run package.py                  # build/furby-show.zip
    uv run package.py --rehearsal      # with each clip's audio, for porch.py --rehearse
    uv run package.py --out build/for-sam.zip
"""

import argparse
import json
import os
import subprocess
import zipfile
import zlib

SHOW_DIR = "build/halloween"  # where deploy.py and porch.py look, from the repo root

WARNING = (
    "PRIVATE: %s is built from Hasbro's Furby audio and DLC. Share it only privately, "
    "with a friend who has the Furbies. Never publish it, post it, or commit it to a repository."
)

README = """\
Furby Halloween show, ready to flash
====================================

PRIVATE: these files are built from Hasbro's Furby audio. Keep them to
yourself: don't post, publish or commit them.

Everything below runs in Terminal (on a Mac, press Command-Space and type
"Terminal").

1. Install uv, which runs the scripts:

       curl -LsSf https://astral.sh/uv/install.sh | sh

   Then close Terminal and open it again.

2. Get the show's code and go into its folder:

       git clone https://github.com/benbalter/Furby.git
       cd Furby{checkout}

   (Or download https://github.com/benbalter/Furby/archive/{ref}.zip,
   unzip it, and cd into that folder.){pinned}

3. Unzip this bundle into that folder, so show.json lands at
   Furby/build/halloween/show.json. If the bundle is in Downloads:

       unzip -o ~/Downloads/{zip_name}

4. Flash both Furbies. It walks you through it, one Furby awake at a time:

       uv run deploy.py --no-build

   Your Mac asks whether Terminal may use Bluetooth: click Allow.
{rehearse}
{run_step}. Run the show. Start it with both Furbies' batteries out:

       uv run porch.py

   Put the batteries in the pink Furby and wait for "Connected to pink",
   then the blue one and wait for "Connected to blue". Press Enter when
   trick-or-treaters walk up, and Ctrl-C to stop.

Stuck? Send whoever gave you this bundle what Terminal says.
Built from show.json with checksums: {checksums}.
"""

REHEARSE = """
5. Hear the show on your computer first, no Furbies needed:

       uv run porch.py --rehearse
"""


def bundle_files(show_dir=SHOW_DIR, rehearsal=False, log=print):
    """{name in the zip: path on disk} for the show; refuses DLCs that don't match show.json."""
    show_json = os.path.join(show_dir, "show.json")
    if not os.path.exists(show_json):
        raise SystemExit("No %s yet. Build the show first: uv run halloween.py" % show_json)
    with open(show_json) as f:
        plan = json.load(f)
    files = {SHOW_DIR + "/show.json": show_json}
    for name, furby in plan["furbies"].items():
        path = os.path.join(show_dir, name + ".dlc")
        if not os.path.exists(path):
            raise SystemExit("No %s, though show.json has a %s Furby. Rebuild: uv run halloween.py" % (path, name))
        with open(path, "rb") as f:
            if zlib.adler32(f.read()) != furby.get("checksum"):
                raise SystemExit(
                    "%s doesn't match show.json, so the show would play the wrong clips. "
                    "Rebuild both: uv run halloween.py" % path
                )
        files["%s/%s.dlc" % (SHOW_DIR, name)] = path
    if rehearsal:
        for name, furby in plan["furbies"].items():
            for clip, info in furby["clips"].items():
                source = info.get("source")
                if not source:
                    continue
                rel = os.path.normpath(source)
                if os.path.isabs(rel) or rel.startswith(".."):
                    log("%s.%s: %s is outside this folder, so it's left out of the rehearsal." % (name, clip, source))
                elif not rel.startswith("build" + os.sep):
                    continue  # in the repository already, like the Toccata
                elif not os.path.exists(rel):
                    log("%s.%s: no %s, so it's left out of the rehearsal." % (name, clip, source))
                else:
                    files[rel.replace(os.sep, "/")] = rel
    return plan, files


def published_commit(run=subprocess.run):
    """This checkout's commit if GitHub has it, so the friend can get the code that built the show; else None."""
    try:
        sha = run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        pushed = sha and run(["git", "branch", "-r", "--contains", sha], capture_output=True, text=True).stdout.strip()
    except OSError:  # no git
        return None
    return sha if pushed else None


def package(out, show_dir=SHOW_DIR, rehearsal=False, log=print, commit=None):
    """Write the zip; returns the names in it. commit points the friend at the code that built it."""
    plan, files = bundle_files(show_dir, rehearsal, log)
    checksums = ", ".join("%s %d" % (n, f["checksum"]) for n, f in plan["furbies"].items())
    readme = README.format(
        zip_name=os.path.basename(out),
        rehearse=REHEARSE if rehearsal else "",
        run_step=6 if rehearsal else 5,
        checksums=checksums,
        checkout="\n       git checkout %s" % commit if commit else "",
        ref=commit or "refs/heads/master",
        pinned="\n   That's the version this bundle was built with, so the code and the\n   show agree."
        if commit
        else "",
    )
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README_FIRST.txt", readme)
        for name in sorted(files):
            z.write(files[name], name)
    return ["README_FIRST.txt"] + sorted(files)


def main(argv=None, log=print, run=subprocess.run):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default="build/furby-show.zip", help="the zip to write (default: %(default)s)")
    parser.add_argument("--show-dir", default=SHOW_DIR, help="the built show (default: %(default)s)")
    parser.add_argument("--rehearsal", action="store_true", help="add each clip's audio, for porch.py --rehearse")
    args = parser.parse_args(argv)
    commit = published_commit(run)
    names = package(args.out, args.show_dir, args.rehearsal, log, commit)
    size = os.path.getsize(args.out)
    log("Wrote %s (%d files, %d KB):" % (args.out, len(names), round(size / 1024)))
    for name in names:
        log("  " + name)
    if not os.path.normpath(args.out).startswith("build" + os.sep):
        log("\nIt's outside build/, which git ignores, so take care not to commit it.")
    log("\n" + WARNING % args.out)
    log("Your friend unzips it into their copy of the repository and follows README_FIRST.txt.")
    if not commit:
        log("(This commit isn't on GitHub, so README_FIRST.txt has them get the latest code, which may not match.)")


if __name__ == "__main__":
    main()
