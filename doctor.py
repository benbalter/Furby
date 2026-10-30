#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Check that everything the Halloween show needs is in place, and say how to fix what isn't.

USAGE:
    uv run doctor.py             # tools, Bluetooth, show.toml's clips, the built DLCs
    uv run doctor.py --furbies   # also check the awake Furby (wake one at a time)
    uv run doctor.py --board     # also check the ESP32 on USB has the current show (restarts it)

It checks, in order: Python and uv; ffmpeg; the Python packages; that this
computer can scan for Bluetooth devices; that every clip in show.toml exists;
that build/halloween has a DLC per Furby, small enough to upload and matching
show.json; and, with --furbies, that the awake Furby has the right DLC
active (wake one at a time: two awake together can't be found); and, with
--board, that the ESP32 on USB has this main.py, furbyshow and show.json, the
aioble that deploy.sh pins, and room for its log. Each problem
gets a ❌ and a one-line fix. It exits non-zero if anything needs fixing, so
scripts can use it too.
"""

import argparse
import asyncio
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zlib

MAC = sys.platform == "darwin"
BLUETOOTH_PERMISSION = (
    "Open System Settings → Privacy & Security → Bluetooth and turn on the app you're running this in "
    "(Terminal, iTerm, VS Code...), then quit and reopen that app and run this again."
)
# Run in a separate process: on macOS, a terminal without Bluetooth permission
# can hang or be killed outright the moment it scans.
SCAN = """
import asyncio
from bleak import BleakScanner
devices = asyncio.run(BleakScanner.discover(timeout=5))
print(len(devices), sum(1 for d in devices if (d.name or "").startswith("Furby")))
"""
PACKAGES = {"PIL": "pillow", "a1800_codec": "a1800-codec", "bleak": "bleak"}
# Runs on the board (MicroPython) via mpremote exec: hashes of the show's files
# and aioble's, the log's size and the free flash, as one line of JSON.
BOARD_PROBE = """
import os, sys, json, hashlib, binascii
def h(p):
    try:
        d = hashlib.sha256()
        with open(p, 'rb') as f:
            while True:
                b = f.read(1024)
                if not b:
                    break
                d.update(b)
        return binascii.hexlify(d.digest()).decode()
    except OSError:
        return None
def size(p):
    try:
        return os.stat(p)[6]
    except OSError:
        return None
try:
    lib = ['lib/aioble/' + n for n in os.listdir('/lib/aioble')]
except OSError:
    lib = []
st = os.statvfs('/')
print(json.dumps({'files': {p: h(p) for p in ['main.py', 'furbyshow.mpy', 'furbyshow.py', 'show.json'] + lib},
    'log': size('log.txt'), 'free': st[0] * st[3], 'mpy': sys.implementation._mpy & 0xff}))
"""
LOW_FLASH = 200_000  # bytes free on the board below which its log may stop being written


class Report:
    """Prints each check's result and counts the failures."""

    def __init__(self, out=print):
        self.out = out
        self.failures = 0
        self.warnings = 0

    def ok(self, message):
        self.out("✅ " + message)

    def warn(self, message, fix=None):
        self.warnings += 1
        self.out("⚠️  " + message + ("\n   → " + fix if fix else ""))

    def fail(self, message, fix):
        self.failures += 1
        self.out("❌ " + message + "\n   → " + fix)


def install_hint(mac, other):
    return mac if MAC else other


def check_tools(r):
    v = sys.version_info
    if v >= (3, 11):
        r.ok("Python %d.%d" % v[:2])
    else:
        r.fail("Python %d.%d is too old; the show needs 3.11 or newer." % v[:2], "Run it with uv: uv run doctor.py")
    if shutil.which("uv"):
        r.ok("uv is installed")
    else:
        r.fail(
            "uv isn't installed. It runs these scripts and installs what they need.",
            install_hint("brew install uv", "curl -LsSf https://astral.sh/uv/install.sh | sh"),
        )
    if shutil.which("ffmpeg"):
        r.ok("ffmpeg is installed")
    else:
        r.fail(
            "ffmpeg isn't installed. It turns your clips into the Furby's audio format.",
            install_hint("brew install ffmpeg", "Install it with your package manager, e.g. sudo apt install ffmpeg"),
        )


def check_packages(r, find_spec=importlib.util.find_spec):
    """True if the packages are there, so the checks that import them can run."""
    missing = [pip for mod, pip in PACKAGES.items() if find_spec(mod) is None]
    if missing:
        r.fail("Missing Python packages: %s." % ", ".join(missing), "uv installs them: uv run doctor.py")
        return False
    r.ok("Python packages: %s" % ", ".join(PACKAGES.values()))
    return True


def check_bluetooth(r, run=subprocess.run, timeout=30):
    try:
        p = run([sys.executable, "-c", SCAN], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        fix = BLUETOOTH_PERMISSION if MAC else "Check that Bluetooth is on and working (bluetoothctl show)."
        r.fail("Scanning for Bluetooth devices hung.", fix)
        return
    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        last = err[-1] if err else "it stopped with code %d" % p.returncode
        low = (p.stderr or "").lower()
        if "turned off" in low or "powered off" in low or "poweredoff" in low:
            fix = "Turn Bluetooth on" + (" (Control Center → Bluetooth)." if MAC else ".")
        elif MAC:  # unauthorized, or killed by macOS for asking: both mean the permission
            fix = BLUETOOTH_PERMISSION
        else:
            fix = "Check that Bluetooth is on and that you may use it (sudo systemctl start bluetooth)."
        r.fail("Can't scan for Bluetooth devices: %s" % last, fix)
        return
    devices, furbies = (int(x) for x in p.stdout.split()[-2:])
    if devices == 0:
        r.warn(
            "Bluetooth scanned but found nothing at all, not even a phone.",
            BLUETOOTH_PERMISSION if MAC else "Check that Bluetooth is on.",
        )
    else:
        r.ok("Bluetooth works: %d devices in range, %d of them Furbies" % (devices, furbies))


def missing_clips(r, missing):
    """Report missing clips grouped by where they come from, with one fix per group."""
    groups = {}
    for clip, path in missing:
        kind = next((k for k in ("sfx", "voice", "cloned") if "/%s/" % k in path), path)
        groups.setdefault(kind, []).append((clip, path))
    for kind, clips in groups.items():
        names = ", ".join(c for c, _ in clips)
        if kind == "sfx":
            stems = [os.path.splitext(os.path.basename(p))[0].rsplit("-", 1) for _, p in clips]
            queries = sorted({stem[0].replace("-", " ") for stem in stems})
            most = max((int(stem[1]) + 1 for stem in stems if len(stem) == 2 and stem[1].isdigit()), default=0)
            count = " --count %d" % most if most > 3 else ""  # freesound_fetch.py fetches 3 per search
            r.fail(
                "Sound effects missing: %s." % names,
                "Fetch them (needs a free Freesound API key in FREESOUND_API_KEY): "
                "uv run audioutils/freesound_fetch.py%s %s" % (count, " ".join('"%s"' % q for q in queries)),
            )
        elif kind == "voice":
            r.fail("Furby voice clips missing: %s." % names, "Unpack them: uv run audioutils/extract_voice.py")
        elif kind == "cloned":
            r.fail(
                "Voice lines missing: %s." % names,
                "Make stand-ins with this computer's voice: uv run voices.py. "
                "Or record each line and save it where show.toml says, e.g. %s" % clips[0][1],
            )
        else:
            r.fail("Clip missing: %s." % names, "Put the audio file at %s (any format ffmpeg reads)" % kind)
    if missing:
        r.out("   (or build without them for now: uv run halloween.py --skip-missing)")


def check_show(r, toml):
    """Check show.toml and its clips; returns the parsed show, or None."""
    import halloween

    if not os.path.exists(toml):
        r.fail("No %s." % toml, "Check you're running this from the Furby folder.")
        return None
    notes = io.StringIO()
    try:
        with contextlib.redirect_stdout(notes):
            show = halloween.load_show(toml)
    except SystemExit as e:
        r.fail("show.toml has a mistake: %s" % e, "Fix that line in %s" % toml)
        return None
    except Exception as e:  # a TOML syntax error, most likely
        r.fail("Can't read %s: %s" % (toml, e), "Fix the line it names")
        return None
    for line in notes.getvalue().splitlines():
        r.warn(line.split(": ", 1)[-1])
    missing = []
    for name, furby in show["furbies"].items():
        specs = {k: halloween.clip_spec(v) for k, v in furby.get("clips", {}).items()}
        absent = [k for k in sorted(specs) if not os.path.exists(specs[k]["path"])]
        if not absent:
            r.ok("%s: all %d clips are there" % (name, len(specs)))
        for k in absent:
            path = specs[k]["path"]
            if specs[k]["optional"]:
                r.warn("%s.%s is optional and missing (%s), so its scenes are left out." % (name, k, path))
            else:
                missing.append(("%s.%s" % (name, k), path))
    missing_clips(r, missing)
    return show


def check_build(r, show, build_dir, toml):
    """Check show.json and each Furby's DLC; returns the plan, or None."""
    from spooky_eyes import MAX_UPLOAD

    plan_path = os.path.join(build_dir, "show.json")
    if not os.path.exists(plan_path):
        r.fail("The show isn't built yet (no %s)." % plan_path, "uv run halloween.py")
        return None
    with open(plan_path) as f:
        plan = json.load(f)
    if os.path.exists(toml) and os.path.getmtime(toml) > os.path.getmtime(plan_path):
        r.warn(
            "show.toml changed after the show was built.",
            "Rebuild (uv run halloween.py), then reflash both Furbies and redeploy",
        )
    if show is not None and set(show["furbies"]) != set(plan["furbies"]):
        r.warn(
            "show.toml has Furbies %s, but the built show has %s." % (sorted(show["furbies"]), sorted(plan["furbies"])),
            "uv run halloween.py",
        )
    for name, furby in sorted(plan["furbies"].items()):
        path = os.path.join(build_dir, name + ".dlc")
        if not os.path.exists(path):
            r.fail("No %s." % path, "uv run halloween.py")
            continue
        with open(path, "rb") as f:
            data = f.read()
        if len(data) > MAX_UPLOAD:
            r.fail(
                "%s is %d KB; uploads time out above about %d KB." % (path, len(data) // 1000, MAX_UPLOAD // 1000),
                "Use shorter or fewer clips, or fewer eye themes, in show.toml, then rebuild",
            )
        elif zlib.adler32(data) != furby.get("checksum"):
            r.fail("%s doesn't match show.json." % path, "Rebuild both together: uv run halloween.py")
        else:
            r.ok("%s.dlc is built (%d KB) and matches show.json" % (name, len(data) // 1000))
    return plan


async def check_furbies(r, plan, find=None):
    """Look for each Furby in range and check its active DLC against show.json."""
    if find is None:
        import porch

        find = porch.find
    try:
        found = await find([])
    except Exception as e:
        r.fail("Couldn't scan for Furbies: %s" % e, BLUETOOTH_PERMISSION if MAC else "Check that Bluetooth is on.")
        return
    seen = set()
    for furby in found:
        try:
            expected = plan["furbies"].get(furby.name)
            if expected is None:
                r.fail(
                    "A Furby (%s) has %s.dlc active, which isn't in this show." % (furby.address, furby.name),
                    "Flash it with one of: %s"
                    % ", ".join("uv run flash.py build/halloween/%s.dlc" % n for n in sorted(plan["furbies"])),
                )
            elif furby.name in seen:
                r.fail("Two Furbies have %s.dlc active." % furby.name, "Flash the other DLC to one of them")
            elif expected.get("checksum") not in (None, furby.checksum):
                r.fail(
                    "%s has an older %s.dlc than show.json." % (furby.name, furby.name),
                    "Reflash it: uv run flash.py build/halloween/%s.dlc" % furby.name,
                )
            else:
                r.ok("%s is in range with the right DLC" % furby.name)
            seen.add(furby.name)
        finally:
            await furby.disconnect()
    missing = sorted(set(plan["furbies"]) - seen)
    if missing and seen:  # expected: check one Furby at a time
        r.warn(
            "Didn't see %s." % " or ".join(missing),
            "To check it too, put %s to sleep (or take the batteries out), wake only %s, and run this again: "
            "two awake together sing and stop answering" % (" and ".join(sorted(seen)), missing[0]),
        )
    elif missing:
        r.fail(
            "Can't find a Furby.",
            "Wake only one (%s), close FurBLE, and run this again: two awake together sing and stop answering"
            % " or ".join(missing),
        )


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def compile_mpy(source):
    """furbyshow.mpy as deploy.sh builds it, or None if mpy-cross can't run."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "furbyshow.mpy")
        try:
            subprocess.run(
                ["uvx", "--from", "mpy-cross", "mpy-cross", "-o", out, source],
                capture_output=True,
                check=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return sha256_file(out)


def aioble_manifest(deploy_sh, mpy):
    """{path: short hash} for the aioble deploy.sh pins, from micropython.org, or None offline."""
    with open(deploy_sh) as f:
        pin = re.search(r"AIOBLE=\(aioble@([\d.]+)\)", f.read())
    if not pin:
        return None
    url = "https://micropython.org/pi/v2/package/%d/aioble/%s.json" % (mpy, pin.group(1))
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return {path: short for path, short in json.load(response)["hashes"]}
    except (OSError, ValueError, KeyError):
        return None


def probe_board(port="auto", run=subprocess.run):
    """Run BOARD_PROBE on the board and restart its show; returns the probe's dict, or an error string."""
    try:
        result = run(
            ["uvx", "mpremote", "connect", port, "exec", BOARD_PROBE, "+", "reset"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    said = (result.stderr or result.stdout).strip().splitlines()
    return said[-1] if said else "no reply"  # e.g. mpremote's "no device found"


def check_board(r, plan_path, port="auto", probe=probe_board, compile=compile_mpy, manifest=aioble_manifest):
    """Check the ESP32 on USB runs this checkout's show: its files, aioble, and room for its log."""
    board = probe(port)
    if isinstance(board, str):
        r.fail(
            "Couldn't reach the board on USB (%s)." % board,
            "Plug it in with a data cable (not charge-only), close any mpremote or watch_board.py, and run this again",
        )
        return
    files = board["files"]
    deploy = "firmware/deploy.sh"
    expected = {
        "main.py": sha256_file("firmware/main.py"),
        "show.json": sha256_file(plan_path),
        "furbyshow.mpy": compile("furbyshow.py"),
    }
    for name, want in expected.items():
        have = files.get(name)
        if have is None:
            r.fail("The board has no %s." % name, deploy)
        elif want is None:
            r.warn("Couldn't build furbyshow.mpy here to compare with the board's.", "Check that uv can run mpy-cross")
        elif have != want:
            r.fail("The board's %s isn't this checkout's." % name, deploy)
        else:
            r.ok("The board's %s is current" % name)
    if files.get("furbyshow.py"):
        r.fail("The board has an old furbyshow.py, which MicroPython loads instead of furbyshow.mpy.", deploy)
    lib = {path[len("lib/") :]: digest for path, digest in files.items() if path.startswith("lib/")}
    known = manifest(deploy, board.get("mpy", 6))
    if not lib:
        r.fail("The board has no aioble.", deploy)
    elif known is None:
        r.warn("Couldn't check the board's aioble against micropython.org (offline?).")
    else:
        wrong = sorted(path for path, short in known.items() if (lib.get(path) or "")[: len(short)] != short)
        if wrong:
            r.fail("The board's aioble doesn't match what deploy.sh pins: %s." % ", ".join(wrong), deploy)
        else:
            r.ok("The board's aioble matches deploy.sh")
    free = board.get("free") or 0
    log = board.get("log")
    message = "%d KB free on the board, log.txt %s" % (
        free // 1000,
        "%d KB" % (log // 1000) if log is not None else "not started",
    )
    if free < LOW_FLASH:
        r.warn(message, "Copy the log off with firmware/getlog.sh, then delete it: uvx mpremote rm :log.txt")
    else:
        r.ok(message)


def main(argv=None, out=print):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--toml", default="./halloween/show.toml")
    parser.add_argument("--build-dir", default="./build/halloween")
    parser.add_argument("--furbies", action="store_true", help="also check the Furby that's awake (wake one at a time)")
    parser.add_argument("--no-bluetooth", action="store_true", help="skip the Bluetooth scan")
    parser.add_argument(
        "--board", action="store_true", help="also check the ESP32 on USB has this show (stops and restarts its show)"
    )
    parser.add_argument("--port", default="auto", help="the board's serial port, with --board (default: auto)")
    args = parser.parse_args(argv)
    r = Report(out)
    check_tools(r)
    if check_packages(r):
        if not args.no_bluetooth:
            check_bluetooth(r)
        show = check_show(r, args.toml)
        plan = check_build(r, show, args.build_dir, args.toml)
        if args.furbies and plan:
            asyncio.run(check_furbies(r, plan))
        if args.board and plan:
            check_board(r, os.path.join(args.build_dir, "show.json"), args.port)
    else:
        out("   (skipped the Bluetooth, clip and build checks until the packages are installed)")
    if r.failures:
        out("\n%d thing%s to fix." % (r.failures, "" if r.failures == 1 else "s"))
    else:
        out("\nAll set%s." % (" (see the notes above)" if r.warnings else ""))
        if not args.furbies:
            out("Wake one Furby and run `uv run doctor.py --furbies` to check it too; then the other.")
    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main())
