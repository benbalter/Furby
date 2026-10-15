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
    python porch.py                       # run the show (build/halloween/show.json)
    python porch.py --scene 0             # play one scene now, then exit
    python porch.py --clip pink.cackle    # play one clip now, then exit
    python porch.py --list                # list Furbies in range and their DLCs

Needs bleak (pip install bleak).
"""

import argparse
import asyncio
import json

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


async def main(args):
    with open(args.show) as f:
        plan = json.load(f)
    show = furbyshow.Show(plan, find)
    if args.list:
        for furby in await find([]):
            print("%s  %s" % (furby.name, furby.address))
        return
    if args.scene is not None or args.clip:
        await show.connect_missing()
        steps = [args.clip] if args.clip else plan["scenes"][args.scene]
        missing = sorted({step.split(".")[0] for step in steps} - show.present())
        if missing:
            raise SystemExit("Not connected: %s. Is it awake, nearby and free of FurBLE?" % ", ".join(missing))
        await (show.play_step(args.clip) if args.clip else show.play_scene(plan["scenes"][args.scene]))
        return
    await show.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--show", default="./build/halloween/show.json")
    parser.add_argument("--scene", type=int, help="play this scene once (0 = first) and exit")
    parser.add_argument("--clip", help='play one clip once, e.g. "pink.cackle", and exit')
    parser.add_argument("--list", action="store_true", help="list Furbies in range and exit")
    asyncio.run(main(parser.parse_args()))
