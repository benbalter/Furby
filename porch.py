#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Run the Halloween show from a computer: connect to every Furby in range and play scenes.

Handy for testing scenes from a laptop; on the night, firmware/main.py runs
the same show from an ESP32 with no computer. Both use the show engine in
furbyshow.py, so they behave the same. It finds each Furby, works out which
one it is from the name of its active DLC (pink.dlc → pink), keeps the
connection alive so the Furby stays awake, and every so often plays a random
scene from show.json, which halloween.py writes. Two Furbies woken together
sing to each other and can't be found, so it says which one to power up
next, one at a time (see furbyshow.Show.guide).

USAGE:
    python porch.py                       # run the show (build/halloween/show.json);
                                          # press Enter to play a greeting
    python porch.py --scene 0             # play one scene now, then exit
    python porch.py --clip pink.cackle    # play one clip now, then exit
    python porch.py --list                # list Furbies in range and their DLCs
    python porch.py --rehearse            # play every scene on this computer's speakers
    python porch.py --rehearse --scene 2  # just one (or --clip)
    python porch.py --check               # play every clip once per Furby, report what
                                          # played, and write timings.json beside show.json

--rehearse needs no Furbies: it plays each clip's source audio here, with the
show's timing, so you can tune lines and scenes before flashing anything. In
a terminal it also draws each antenna's light as a coloured block, live.
Running the show needs bleak, which `uv run porch.py` installs.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback

import furbyshow


class BleakFurby(furbyshow.Furby):
    def __init__(self, device):
        from bleak import BleakClient

        super().__init__(device.address)
        self.client = BleakClient(device, disconnected_callback=lambda _: print("%s disconnected" % self))

    def connected(self):
        return self.client.is_connected

    async def _write(self, data):
        await self.client.write_gatt_char(furbyshow.GP_WRITE, data, response=False)

    async def disconnect(self):
        await self.client.disconnect()

    async def connect(self):
        await self.client.connect(timeout=20)
        try:
            await self.client.start_notify(furbyshow.GP_LISTEN, lambda _, data: self.on_response(bytes(data)))
            await self.identify()
        except Exception:
            await self.disconnect()
            raise


async def find(known, timeout=10):
    """Connect to Furbies in range that aren't already connected."""
    from bleak import BleakScanner

    furbies = []
    for device in await BleakScanner.discover(timeout=timeout):
        if not (device.name or "").startswith("Furby") or device.address in known:
            continue
        furby = BleakFurby(device)
        try:
            await furby.connect()
        except Exception as e:  # a Furby that's asleep or busy; the show tries again later
            print("Couldn't connect to %s: %s" % (device.address, e))
            continue
        furbies.append(furby)
    return furbies


class RehearsalFurby(furbyshow.Furby):
    """Stands in for a Furby: plays each clip on this computer instead."""

    def __init__(self, name, furby):
        super().__init__(name)
        self.name, self.checksum = name, furby.get("checksum")
        self.sources = {tuple(c["action"]): c["source"] for c in furby["clips"].values()}

    def connected(self):
        return True

    async def disconnect(self):
        pass

    async def keep_alive(self):
        pass

    async def _write(self, data):
        if data[0] == 0x13:
            play_audio(self.sources[tuple(data[2:6])])
            self.on_response(furbyshow.SEQUENCE_PLAYING)  # answer like a Furby, so play() doesn't wait
        elif data[0] == 0x14:
            show_antenna(self.name, tuple(data[1:4]))


_antennas = {}  # name → colour, for the rehearsal's light line


def show_antenna(name, rgb):
    """Draw every lit antenna as a coloured block on one line, redrawn in place.

    The light changes up to 15 times a second, so this only draws in a
    terminal that can redraw a line (and show 24-bit colour); piped output
    gets nothing rather than a flood.
    """
    if any(rgb):
        _antennas[name] = rgb
    else:
        _antennas.pop(name, None)
    if not sys.stdout.isatty():
        return
    blocks = ["%s \033[48;2;%d;%d;%dm      \033[0m %3d,%3d,%3d" % ((n,) + c + c) for n, c in sorted(_antennas.items())]
    sys.stdout.write("\r\033[K  " + "   ".join(blocks))
    sys.stdout.flush()


def rehearsal_log(line):
    if line.startswith("Connected"):
        return
    if sys.stdout.isatty():
        sys.stdout.write("\r\033[K")  # clear the light line first
    print(line)


def play_audio(path):
    """Start playing a clip without waiting, the way a Furby does."""
    if path.endswith(".a18"):  # decode it first, with the codec halloween.py uses
        import wave

        import a1800_codec

        with open(path, "rb") as f:
            pcm = bytes(a1800_codec.decode(f.read()))
        path = os.path.join(tempfile.mkdtemp(), "clip.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm)
    if shutil.which("afplay"):
        subprocess.Popen(["afplay", path])
    elif shutil.which("ffplay"):
        subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
    else:
        raise SystemExit("--rehearse needs afplay (macOS) or ffplay (ffmpeg) to play audio")


async def rehearse(plan, args):
    furbies = [RehearsalFurby(name, f) for name, f in plan["furbies"].items()]

    async def find(known):
        return [f for f in furbies if f.address not in known]

    show = furbyshow.Show(plan, find, log=rehearsal_log)
    await show.connect_missing()
    if args.clip:
        await show.play_step(args.clip)
        return
    scenes = [plan["scenes"][args.scene]] if args.scene is not None else plan["scenes"]
    for n, scene in enumerate(scenes):
        await show.play_scene(scene)
        if n < len(scenes) - 1:
            await asyncio.sleep(2)  # a short pause instead of the show's minute or so


async def check_clip(furby, action, patience_s, attempts=2):
    """Trigger one action and time its sequence; returns (result, seconds from 20:0c to 20:0e or None).

    result is "played" (20:0c, audio and all), "skipped" (20:07: busy, so no
    audio, even after waiting for the busy sequence to end and trying again)
    or "no reply". This uses command() rather than Furby.play(), which retries
    on 20:07 and so hides exactly what this measures.
    """
    reply_s = furbyshow.PLAY_REPLY_MS / 1000
    for _ in range(attempts):
        # Listen for the end before triggering: a short sequence can end before a later wait would start
        ended = asyncio.create_task(
            furby.command(None, expect=(furbyshow.SEQUENCE_ENDED, furbyshow.SEQUENCE_CANCELLED), timeout=patience_s)
        )
        await asyncio.sleep(0)
        try:
            reply = await furby.command(
                furbyshow.trigger_command(action),
                expect=(furbyshow.SEQUENCE_PLAYING, furbyshow.SPEECH_PLAYING),
                timeout=reply_s,
            )
        except TimeoutError:
            ended.cancel()
            return "no reply", None
        started = furbyshow.ticks_ms()
        try:
            await ended
            seconds = furbyshow.ticks_diff(furbyshow.ticks_ms(), started) / 1000
        except TimeoutError:
            seconds = None
        if reply[:2] == furbyshow.SEQUENCE_PLAYING:
            return "played", seconds
    return "skipped", None


async def check(plan, find, log=print, timings_path=None, patience_s=furbyshow.PLAY_PATIENCE_MS / 1000,
                long_tail_s=3, settle_s=3, pause_s=0.5, find_passes=3):  # fmt: skip
    """Play every clip once on each Furby and report what the Furby says happened; returns the failures.

    A sequence that runs long_tail_s or more past its clip is flagged but not
    a failure: the next line on that Furby just waits for it (see Furby.play()).
    """
    show = furbyshow.Show(plan, find, log=lambda line: None if line.startswith("Connected") else log(line))
    # Identical Furbies that see each other pair up and stop advertising, so give them a few scans to turn up
    for attempt in range(find_passes):
        await show.connect_missing()
        missing = sorted(set(plan["furbies"]) - show.present())
        if not missing:
            break
        if attempt < find_passes - 1:
            log("Waiting for %s: wake it now (one at a time works best)." % ", ".join(missing))
    failures, timings = [], {}
    for name, spec in plan["furbies"].items():
        furby = show.furbies.get(name)
        if furby is None or not furby.connected():
            failures.append("%s: not connected. Is it awake, nearby and free of FurBLE?" % name)
            continue
        log("\n%s (%s)" % (name, furby.address))
        if spec.get("checksum") not in (None, furby.checksum):
            failures.append("%s: its DLC doesn't match show.json; reflash it with: uv run deploy.py --only %s"
                            % (name, name))  # fmt: skip
            log("  checksum %s, show.json expects %#x: reflash it" % (furby.checksum and hex(furby.checksum),
                                                                     spec["checksum"]))  # fmt: skip
        else:
            log("  checksum matches show.json")
        try:  # let a sequence from connecting or the Furby's own antics finish first
            await furby.command(None, expect=(furbyshow.SEQUENCE_ENDED, furbyshow.SEQUENCE_CANCELLED), timeout=settle_s)
        except TimeoutError:
            pass
        log("  %-16s %-12s %-9s %6s %9s  %s" % ("clip", "action", "result", "audio", "sequence", ""))
        timings[name] = {}
        for clip, info in sorted(spec["clips"].items()):
            result, seconds = await check_clip(furby, info["action"], patience_s)
            note = ""
            if result != "played":
                failures.append("%s.%s: %s" % (name, clip, result))
            elif seconds is None:
                note = "no end signal within %.0f s" % patience_s
            elif seconds - info["seconds"] >= long_tail_s:
                note = "runs %.1f s past its audio" % (seconds - info["seconds"])
            log("  %-16s %-12s %-9s %5.1fs %9s  %s" % (clip, ".".join(map(str, info["action"])), result,
                info["seconds"], "-" if seconds is None else "%.1fs" % seconds, note))  # fmt: skip
            timings[name][clip] = {"action": info["action"], "result": result, "audio_seconds": info["seconds"],
                                   "sequence_seconds": seconds}  # fmt: skip
            if result == "no reply":
                await asyncio.sleep(info["seconds"])  # in case it's playing anyway
            await asyncio.sleep(pause_s)
    for furby in show.furbies.values():
        await furby.disconnect()
    if timings_path:
        with open(timings_path, "w") as f:
            json.dump(timings, f, indent=2)
        log("\nWrote %s" % timings_path)
    if failures:
        log("\n%d problem%s:" % (len(failures), "" if len(failures) == 1 else "s"))
        for failure in failures:
            log("  " + failure)
    else:
        log("\nEvery clip played.")
    return failures


def greet_on_enter(show):
    """Press Enter to play a greeting, like the board's button."""
    loop = asyncio.get_running_loop()

    def read():
        for _ in sys.stdin:
            loop.call_soon_threadsafe(show.trigger)

    # A daemon thread, so a blocked read doesn't stop Ctrl-C from ending the show
    threading.Thread(target=read, daemon=True).start()
    print("Press Enter to play a greeting when someone arrives.")


def check_choice(plan, args):
    """Turn a --scene or --clip that isn't in the built show into a list of what is, not a traceback."""
    if args.scene is not None and not 0 <= args.scene < len(plan["scenes"]):
        listing = "\n".join("  %d  %s" % (n, " -> ".join(s)) for n, s in enumerate(plan["scenes"]))
        raise SystemExit("There's no scene %d. The built show has %d:\n%s" % (args.scene, len(plan["scenes"]), listing))
    if args.clip:
        for part in furbyshow.step_parts(args.clip):
            name, _, clip = part.partition(".")
            if clip not in plan["furbies"].get(name, {}).get("clips", {}):
                clips = sorted("%s.%s" % (n, c) for n, f in plan["furbies"].items() for c in f["clips"])
                raise SystemExit("There's no clip %r in the built show. It has: %s" % (part, ", ".join(clips)))


async def main(args):
    with open(args.show) as f:
        plan = json.load(f)
    check_choice(plan, args)
    if args.rehearse:
        await rehearse(plan, args)
        return
    try:
        import bleak  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Talking to the Furbies needs bleak. Run this with uv, which installs it:\n"
            "  uv run porch.py %s\n"
            "(--rehearse works without it)." % " ".join(sys.argv[1:])
        ) from None
    if args.check:
        timings = os.path.join(os.path.dirname(args.show), "timings.json")
        if await check(plan, find, timings_path=timings):
            raise SystemExit(1)
        return
    show = furbyshow.Show(plan, find, trace=traceback.print_exception)
    if args.list:
        for furby in await find([]):
            print("%s  %s" % (furby.name, furby.address))
        return
    if args.scene is not None or args.clip:
        await show.connect_missing()
        steps = [args.clip] if args.clip else plan["scenes"][args.scene]
        missing = sorted({p.split(".")[0] for step in steps for p in furbyshow.step_parts(step)} - show.present())
        if missing:
            raise SystemExit("Not connected: %s. Is it awake, nearby and free of FurBLE?" % ", ".join(missing))
        await (show.play_step(args.clip) if args.clip else show.play_scene(plan["scenes"][args.scene]))
        return
    greet_on_enter(show)
    await show.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--show", default="./build/halloween/show.json")
    parser.add_argument("--scene", type=int, help="play this scene once (0 = first) and exit")
    parser.add_argument("--clip", help='play one clip once, e.g. "pink.cackle", and exit')
    parser.add_argument("--list", action="store_true", help="list Furbies in range and exit")
    parser.add_argument("--rehearse", action="store_true", help="play scenes on this computer, no Furbies needed")
    parser.add_argument("--check", action="store_true", help="play every clip once per Furby and report what played")
    asyncio.run(main(parser.parse_args()))
