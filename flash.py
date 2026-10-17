#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Flash a DLC to a Furby Connect from this computer, without a browser.

The same upload FurBLE's "Upload Custom" does (benbalter/furby-web-bluetooth),
which is the one known to work: announce the file, stream it in 20-byte
packets paced at 15 ms and held back while the Furby has more than 10
unacknowledged, then check the stored checksum, load and activate it. The
antenna turns green when the DLC is active, red if anything failed.

USAGE:
    uv run flash.py build/halloween/pink.dlc
    uv run flash.py build/halloween/blue.dlc --address 6761885F-...   # when several Furbies are on
    uv run flash.py pink.dlc --packet-delay 30                         # if uploads time out

Only one Furby should be awake, unless you pass --address; --list shows the
ones in range and their DLCs. Before uploading, it deletes the DLCs already
on the Furby (FurBLE asks for a tongue-and-tail reset instead). If the upload
still fails, reset the Furby that way and run it again.
"""

import argparse
import asyncio
import os
import sys
import time
import zlib

import furbyshow

NORDIC_WRITE = "dab90757-b5a1-e29c-b041-bcd562613bde"
NORDIC_LISTEN = "dab90756-b5a1-e29c-b041-bcd562613bde"
FILE_WRITE = "dab90758-b5a1-e29c-b041-bcd562613bde"

CHUNK = 20
MAX_UNACKED = 10  # the Furby only acks while packets keep arriving, so don't pause below this
MAX_PAUSE_S = 2.0
TRANSFER = {1: "EndCurrentTransfer", 2: "ReadyToReceive", 3: "FileTransferTimeout", 4: "ReadyToAppend",
            5: "FileReceivedOk", 6: "FileReceivedErr"}  # fmt: skip


def furby_filename(path):
    """The 8.3 name the Furby stores, e.g. pink.dlc → ____PINK.DLC (how the show names it)."""
    stem = os.path.splitext(os.path.basename(path))[0].upper()
    if len(stem) > 8:
        raise SystemExit("%s: the Furby keeps 8.3 names, so use 8 letters or fewer" % path)
    return stem.rjust(8, "_") + ".DLC"


def announce_command(size, filename):
    """0x50: the file's size (24-bit, big-endian), slot 2 as FurBLE sends, the name, two zero bytes."""
    return bytes([0x50, 0x00, size >> 16 & 0xFF, size >> 8 & 0xFF, size & 0xFF, 2]) + filename.encode() + b"\0\0"


def slots(info):
    """(filled, active) slot numbers from a 0x72 (DLC info) response."""
    filled, active = (info[3] << 8) | info[4], (info[7] << 8) | info[8]
    return [s for s in range(14) if filled & (1 << s)], [s for s in range(14) if active & (1 << s)]


class Flasher:
    """Uploads over a connected client with bleak's write_gatt_char/start_notify."""

    def __init__(self, client, log=print, packet_delay=0.015):
        self.client = client
        self.log = log
        self.packet_delay = packet_delay
        self.replies = asyncio.Queue()
        self.unacked = 0
        self.caught_up = asyncio.Event()  # set while the Furby's buffer has room

    async def start(self):
        await self.client.start_notify(furbyshow.GP_LISTEN, lambda _, d: self.replies.put_nowait(bytes(d)))
        await self.client.start_notify(NORDIC_LISTEN, lambda _, d: self._nordic(bytes(d)))

    def _nordic(self, data):
        if data[:1] == b"\x09":  # packet ack: how many packets the Furby has buffered
            self.unacked = data[1]
            if self.unacked <= MAX_UNACKED:
                self.caught_up.set()

    async def gp(self, data):
        await self.client.write_gatt_char(furbyshow.GP_WRITE, bytes(data), response=False)

    async def reply(self, prefix, timeout=5):
        """The next GeneralPlus notification starting with prefix (others are dropped)."""
        end = time.monotonic() + timeout
        while (left := end - time.monotonic()) > 0:
            try:
                data = await asyncio.wait_for(self.replies.get(), left)
            except TimeoutError:
                break
            if data.startswith(bytes(prefix)):
                return data
        raise TimeoutError("no %s reply from the Furby" % bytes(prefix).hex())

    async def ask(self, data, prefix, timeout=5):
        while not self.replies.empty():
            self.replies.get_nowait()
        await self.gp(data)
        return await self.reply(prefix, timeout)

    async def clear_slots(self):
        """Delete the DLCs already stored, so the new one gets a slot (instead of a physical reset)."""
        filled, active = slots(await self.ask(furbyshow.DLC_INFO, furbyshow.DLC_INFO))
        for slot in active:
            await self.ask([0x62, slot], [0xDC])  # deactivate
        for slot in filled:
            await self.ask([0x74, slot], [0x74])
            self.log("Deleted the DLC in slot %d" % slot)

    async def upload(self, data, filename):
        await self.gp([0xCD, 0])  # eyes off while uploading, as FurBLE does
        await self.gp(furbyshow.antenna_command((0, 0, 0)))
        await self.client.write_gatt_char(NORDIC_WRITE, bytes([0x09, 1, 0]), response=False)  # packet acks on
        try:
            mode = (await self.ask(announce_command(len(data), filename), [0x24], timeout=10))[1]
            if mode != 2:
                raise RuntimeError("the Furby answered the upload with %s" % TRANSFER.get(mode, mode))
            started = time.monotonic()
            for pos in range(0, len(data), CHUNK):
                if self.unacked > MAX_UNACKED:
                    self.caught_up.clear()
                    try:  # it only acks while packets arrive, so carry on after a while regardless
                        await asyncio.wait_for(self.caught_up.wait(), MAX_PAUSE_S)
                    except TimeoutError:
                        self.unacked = 0
                await self.client.write_gatt_char(FILE_WRITE, data[pos : pos + CHUNK], response=False)
                await asyncio.sleep(self.packet_delay)
                if pos % (CHUNK * 1000) == 0:
                    self.log("  %3d%%" % (100 * pos // len(data)))
            self.log("Sent %d bytes in %.0f s" % (len(data), time.monotonic() - started))
            mode = (await self.reply([0x24], timeout=60))[1]
            if mode != 5:
                raise RuntimeError("upload failed: %s" % TRANSFER.get(mode, mode))
        finally:
            await self.client.write_gatt_char(NORDIC_WRITE, bytes([0x09, 0, 0]), response=False)
            await self.gp([0xCD, 1])

    async def activate(self, checksum):
        filled, active = slots(await self.ask(furbyshow.DLC_INFO, furbyshow.DLC_INFO))
        new = [s for s in filled if s not in active]
        if not new:
            raise RuntimeError("the upload finished but no slot holds it; reset the Furby and try again")
        slot = new[0]
        for old in active:
            await self.ask([0x62, old], [0xDC])
        info = await self.ask([0x73, slot], [0x73, slot])
        stored = furbyshow.slot_checksum(info)
        if stored != checksum:
            raise RuntimeError("stored checksum %#x doesn't match the file's %#x" % (stored, checksum))
        await self.ask([0x60, slot], [0xDC])
        await self.ask([0x61], [0xDC])
        if furbyshow.active_slot(await self.ask(furbyshow.DLC_INFO, furbyshow.DLC_INFO)) != slot:
            raise RuntimeError("the Furby didn't activate slot %d" % slot)
        self.log("Active in slot %d as %s, checksum %#x" % (slot, furbyshow.slot_name(info), checksum))

    async def flash(self, data, filename):
        checksum = zlib.adler32(data)
        await self.start()
        try:
            await self.clear_slots()
            await self.upload(data, filename)
            await self.activate(checksum)
        except Exception:
            await self.gp(furbyshow.antenna_command((255, 0, 0)))
            raise
        await self.gp(furbyshow.antenna_command((0, 255, 0)))


async def main(args):
    from bleak import BleakClient, BleakScanner

    if args.list or not args.dlc:
        import porch

        for furby in await porch.find([]):
            print("%s  active DLC: %s" % (furby.address, furby.name))
            await furby.disconnect()
        return
    found = [d for d in await BleakScanner.discover(timeout=8) if (d.name or "").startswith("Furby")]
    if args.address:
        found = [d for d in found if d.address.lower() == args.address.lower()]
    if len(found) != 1:
        raise SystemExit(
            "Found %d Furbies in range%s. Wake just the one to flash (and close FurBLE), or pass --address; "
            "--list shows them." % (len(found), "" if not args.address else " with that address")
        )
    with open(args.dlc, "rb") as f:
        data = f.read()
    filename = furby_filename(args.dlc)
    print("Flashing %s (%d KB) to %s as %s" % (args.dlc, len(data) // 1000, found[0].address, filename))
    async with BleakClient(found[0], timeout=20) as client:
        await Flasher(client, packet_delay=args.packet_delay / 1000).flash(data, filename)
    print("Done. The antenna is green.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dlc", nargs="?", help="the .dlc to flash")
    parser.add_argument("--address", help="which Furby, when more than one is awake")
    parser.add_argument("--packet-delay", type=float, default=15, help="ms between packets (default 15)")
    parser.add_argument("--list", action="store_true", help="list Furbies in range and their DLCs")
    try:
        asyncio.run(main(parser.parse_args()))
    except (RuntimeError, TimeoutError) as e:
        sys.exit("Flashing failed: %s" % e)
