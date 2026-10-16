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
scene from show.json, which halloween.py writes.

USAGE:
    python porch.py                       # run the show (build/halloween/show.json);
                                          # press Enter to play a greeting
    python porch.py --scene 0             # play one scene now, then exit
    python porch.py --clip pink.cackle    # play one clip now, then exit
    python porch.py --list                # list Furbies in range and their DLCs
    python porch.py --rehearse            # play every scene on this computer's speakers
    python porch.py --rehearse --scene 2  # just one (or --clip)

--rehearse needs no Furbies: it plays each clip's source audio here, with the
show's timing, so you can tune lines and scenes before flashing anything.
Running the show needs bleak (pip install bleak).
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
        elif data[0] == 0x14 and any(data[1:4]):
            print("  %s antenna glows rgb%s" % (self, tuple(data[1:4])))


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

    show = furbyshow.Show(plan, find, log=lambda line: None if line.startswith("Connected") else print(line))
    await show.connect_missing()
    if args.clip:
        await show.play_step(args.clip)
        return
    scenes = [plan["scenes"][args.scene]] if args.scene is not None else plan["scenes"]
    for n, scene in enumerate(scenes):
        await show.play_scene(scene)
        if n < len(scenes) - 1:
            await asyncio.sleep(2)  # a short pause instead of the show's minute or so


def greet_on_enter(show):
    """Press Enter to play a greeting, like the board's button."""
    loop = asyncio.get_running_loop()

    def read():
        for _ in sys.stdin:
            loop.call_soon_threadsafe(show.trigger)

    # A daemon thread, so a blocked read doesn't stop Ctrl-C from ending the show
    threading.Thread(target=read, daemon=True).start()
    print("Press Enter to play a greeting when someone arrives.")


async def main(args):
    with open(args.show) as f:
        plan = json.load(f)
    if args.rehearse:
        await rehearse(plan, args)
        return
    show = furbyshow.Show(plan, find)
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
    asyncio.run(main(parser.parse_args()))
