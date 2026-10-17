#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Put the Halloween show on both Furbies, one guided step at a time.

Builds the show (halloween.py), then for each Furby in show.json asks you to
wake just that one, finds it, says which DLC it has now, blinks its antenna
in its show colour so you can see which one it is, and flashes its DLC
(flash.py). It won't put the same DLC on both, and with --esp32 copies the
show to the ESP32 afterwards (firmware/deploy.sh).

USAGE:
    uv run deploy.py                 # build, then flash pink and blue
    uv run deploy.py --only blue     # just one Furby
    uv run deploy.py --no-build      # flash what's already in build/halloween
    uv run deploy.py --esp32         # also copy the show to the ESP32 over USB
    uv run deploy.py --yes --only pink   # no questions: for scripts

Wake one Furby at a time: two identical Furbies that can see each other pair
up and stop showing up to the computer. Close FurBLE and anything else
connected to them first.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import zlib

import flash
import furbyshow

HERE = os.path.dirname(os.path.abspath(__file__))
WHITE = (255, 255, 255)  # for a Furby whose show.toml entry has no antenna colour
BLINKS = 3
BLINK_S = 0.3


class DeployError(Exception):
    """Something the person needs to fix before the deploy can go on."""


async def connect(device):
    """Connect to a Furby and identify its DLC, which may be none (a new or reset Furby)."""
    import porch

    furby = porch.BleakFurby(device)
    await furby.client.connect(timeout=20)
    try:
        await furby.client.start_notify(furbyshow.GP_LISTEN, lambda _, data: furby.on_response(bytes(data)))
        try:
            await furby.identify()
        except ValueError:  # no active DLC
            furby.name = furby.checksum = None
    except Exception:
        await furby.disconnect()
        raise
    return furby


class Deployer:
    """Finds, confirms and flashes each Furby; ask, scan and connect can be swapped out for tests."""

    def __init__(self, plan, dlc_dir, ask=input, log=print, scan=flash.scan, connect=connect, yes=False,
                 packet_delay=0.015, sleep=asyncio.sleep):  # fmt: skip
        self.plan = plan
        self.dlc_dir = dlc_dir
        self.ask = ask
        self.log = log
        self.scan = scan
        self.connect = connect
        self.yes = yes
        self.packet_delay = packet_delay
        self.sleep = sleep
        self.flashed = {}  # name → address, this run
        self.results = {}  # name → what happened, for the summary

    async def question(self, prompt):
        # In a thread, so the Furby's keepalive carries on while someone reads the prompt
        return (await asyncio.to_thread(self.ask, prompt)).strip().lower()

    async def confirm(self, prompt):
        return not self.yes and (await self.question(prompt + " [y/N] ")).startswith("y")

    def problem(self, message):
        """Stop when nobody's there to fix it; otherwise say what's wrong and try again."""
        if self.yes:
            raise DeployError(message)
        self.log(message)

    def dlc(self, name):
        """The DLC's bytes, checked against show.json so the show and the Furby agree."""
        path = os.path.join(self.dlc_dir, name + ".dlc")
        if not os.path.exists(path):
            raise DeployError("%s doesn't exist. Build the show first: run this without --no-build." % path)
        with open(path, "rb") as f:
            data = f.read()
        if zlib.adler32(data) != self.plan["furbies"][name].get("checksum"):
            raise DeployError(
                "%s doesn't match show.json, so the show would play the wrong clips. "
                "Rebuild both: run this without --no-build." % path
            )
        from spooky_eyes import MAX_UPLOAD

        if len(data) > MAX_UPLOAD:
            self.log("Warning: %s is %d KB; uploads tend to time out above %d KB." % (path, len(data) // 1000,
                                                                                     MAX_UPLOAD // 1000))  # fmt: skip
        return path, data

    def describe(self, furby):
        """What the Furby has now, e.g. "pink.dlc (this show's)"."""
        if furby.name is None:
            return "no DLC active"
        current = self.plan["furbies"].get(furby.name, {}).get("checksum") == furby.checksum
        return "%s.dlc active%s" % (furby.name, " (this show's)" if current else "")

    async def blink(self, furby, color):
        for _ in range(BLINKS):
            await furby.set_antenna(color)
            await self.sleep(BLINK_S)
            await furby.set_antenna((0, 0, 0))
            await self.sleep(BLINK_S)
        await furby.set_antenna(color)  # stays lit while you look

    async def find(self, name):
        """The one awake Furby, connected, once someone confirms it's the right one."""
        others = [n for n in self.flashed if n != name]
        while True:
            if not self.yes:
                asleep = " Put the %s Furby to sleep first (or take its batteries out)." % others[-1] if others else ""
                await self.question("\nWake only the %s Furby.%s Then press Enter. " % (name, asleep))
            self.log("Looking for a Furby...")
            found = await self.scan()
            if not found:
                self.problem(
                    "No Furby found. Wake it up (pet it or pick it up), keep it near this computer, "
                    "and close FurBLE or anything else connected to it."
                )
                continue
            if len(found) > 1:
                self.problem(
                    "Found %d Furbies, but only the %s one should be awake. Identical Furbies that see each other "
                    "pair up and stop showing up, so put the others to sleep or take their batteries out."
                    % (len(found), name)
                )
                continue
            device = found[0]
            for other in others:
                if self.flashed[other] == device.address:
                    raise DeployError(
                        "The Furby that's awake is the one just flashed as %s, so it would end up with %s.dlc "
                        "instead. Nothing was changed. Put it to sleep, wake the other Furby, and run: "
                        "uv run deploy.py --no-build --only %s" % (other, name, name)
                    )
            try:
                furby = await self.connect(device)
            except Exception as e:
                self.problem("Couldn't connect to the Furby (%s). Is it still awake? Close FurBLE, then try again." % e)
                continue
            self.log("Found a Furby with %s." % self.describe(furby))
            keepalive = asyncio.create_task(furby.keep_alive())
            try:
                if await self.right_one(name, furby):
                    return furby
                await furby.set_antenna((0, 0, 0))
            except DeployError:
                await furby.disconnect()
                raise
            except Exception as e:  # it fell asleep or wandered off mid-question
                await furby.disconnect()
                self.problem("Lost the connection to the Furby (%s). Wake it again and try once more." % e)
                continue
            finally:
                keepalive.cancel()  # Flasher drives the connection from here
            await furby.disconnect()

    async def right_one(self, name, furby):
        """Blink it and ask; refuse a Furby that carries another one's DLC from this show."""
        theirs = furby.name if furby.name != name else None
        if theirs in self.plan["furbies"] and self.plan["furbies"][theirs].get("checksum") == furby.checksum:
            if self.yes:
                raise DeployError(
                    "This Furby has this show's %s.dlc. Flashing %s.dlc over it would leave the show without %s. "
                    "Wake the other one, or run without --yes to confirm." % (theirs, name, theirs)
                )
            if not await self.confirm("It already has this show's %s.dlc. Replace it with %s.dlc?" % (theirs, name)):
                return False
        await self.blink(furby, self.plan["furbies"][name].get("antenna") or WHITE)
        if self.yes:
            return True
        if await self.confirm("Its antenna is lit. Is this the %s one?" % name):
            return True
        self.log("OK, let's try again.")
        return False

    async def flash_one(self, name):
        path, data = self.dlc(name)
        furby = await self.find(name)
        try:
            if furby.name == name and furby.checksum == zlib.adler32(data):
                if not await self.confirm("It already has this show's %s.dlc. Flash it again anyway?" % name):
                    self.log("Leaving %s as it is." % name)
                    await furby.set_antenna((0, 0, 0))
                    self.flashed[name] = furby.address
                    self.results[name] = "already up to date"
                    return
            self.log("Flashing %s (%d KB). This takes a couple of minutes; keep it close." % (path, len(data) // 1000))
            await furby.client.stop_notify(furbyshow.GP_LISTEN)  # the Flasher listens for itself
            try:
                await flash.Flasher(furby.client, log=self.log, packet_delay=self.packet_delay).flash(
                    data, flash.furby_filename(path)
                )
            except (RuntimeError, TimeoutError) as e:
                raise DeployError(
                    "Flashing %s failed: %s. Its antenna is red. Reset it (hold it upside down, hold the "
                    "tongue and pull the tail until the eyes go dark), then run: "
                    "uv run deploy.py --no-build --only %s (add --packet-delay 30 if it timed out)." % (name, e, name)
                ) from e
            self.flashed[name] = furby.address
            self.results[name] = "flashed %s.dlc, checksum %#x" % (name, zlib.adler32(data))
            self.log("%s is done: its antenna is green." % name)
        finally:
            await furby.disconnect()

    async def run(self, names):
        for name in names:
            self.log("\n== %s ==" % name)
            await self.flash_one(name)
        return self.results


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--show", default="./build/halloween/show.json", help="show.json, with the DLCs beside it")
    parser.add_argument("--toml", default="./halloween/show.toml", help="the show to build")
    parser.add_argument("--no-build", action="store_true", help="flash the DLCs already built")
    parser.add_argument("--skip-missing", action="store_true", help="build without clips that don't exist yet")
    parser.add_argument("--only", action="append", metavar="NAME", help="just this Furby (repeatable)")
    parser.add_argument("-y", "--yes", action="store_true", help="ask nothing: stop instead of asking again")
    parser.add_argument("--esp32", action="store_true", help="then copy the show to the ESP32 (firmware/deploy.sh)")
    parser.add_argument("--packet-delay", type=float, default=15, help="ms between packets (default 15)")
    return parser.parse_args(argv)


def main(args, ask=input, log=print, scan=flash.scan, connect=connect, run=subprocess.run):
    if not args.no_build:
        import halloween

        halloween.build_show(halloween.load_show(args.toml), os.path.dirname(args.show), args.skip_missing)
    if not os.path.exists(args.show):
        raise DeployError("No %s yet. Run this without --no-build to build the show." % args.show)
    with open(args.show) as f:
        plan = json.load(f)
    names = list(plan["furbies"])
    unknown = sorted(set(args.only or []) - set(names))
    if unknown:
        raise DeployError("This show has no %s Furby; it has %s." % (", ".join(unknown), ", ".join(names)))
    if args.only:
        names = [n for n in names if n in args.only]
    if scan is flash.scan:
        try:
            import bleak  # noqa: F401
        except ImportError:
            raise DeployError("Talking to the Furbies needs bleak. Run this with uv, which installs it: "
                              "uv run deploy.py %s" % " ".join(sys.argv[1:])) from None  # fmt: skip
    deployer = Deployer(plan, os.path.dirname(args.show), ask=ask, log=log, scan=scan, connect=connect,
                        yes=args.yes, packet_delay=args.packet_delay / 1000)  # fmt: skip
    results = asyncio.run(deployer.run(names))
    if args.esp32:
        if os.path.abspath(args.show) != os.path.join(HERE, "build", "halloween", "show.json"):
            log("Note: firmware/deploy.sh copies build/halloween/show.json, not %s." % args.show)
        log("\nCopying the show to the ESP32...")
        if run([os.path.join(HERE, "firmware", "deploy.sh")]).returncode:
            raise DeployError(
                "The Furbies are done, but copying to the ESP32 failed. Plug it in over USB and run "
                "firmware/deploy.sh (PORT=/dev/cu.usbmodem... if there's more than one board)."
            )
        results["esp32"] = "show copied"
    log("\nAll done:")
    for name, result in results.items():
        log("  %-6s %s" % (name, result))
    log("Next, wake both Furbies and test every clip: uv run porch.py --check")
    return results


if __name__ == "__main__":
    try:
        main(parse_args())
    except DeployError as e:
        sys.exit("\n%s" % e)
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
