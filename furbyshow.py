# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
The Halloween show engine, shared by porch.py (a computer, over bleak) and
firmware/main.py (an ESP32 running MicroPython, over aioble).

Everything here runs unchanged on CPython and MicroPython, so it avoids
typing, dataclasses and time.monotonic(). The Bluetooth layer is the only
part each side writes for itself: a Furby subclass with connected() and
_write(), which feeds every notification to on_response(), plus a find()
coroutine that connects to Furbies in range.

The commands are the ones FurBLE sends (https://github.com/pdjstone/furby-web-bluetooth).
"""

import asyncio
import random
import time

GP_SERVICE = "dab91435-b5a1-e29c-b041-bcd562613bde"
GP_WRITE = "dab91383-b5a1-e29c-b041-bcd562613bde"
GP_LISTEN = "dab91382-b5a1-e29c-b041-bcd562613bde"

KEEPALIVE = b"\x20\x06"  # "I'm here", which keeps a connected Furby awake
KEEPALIVE_AFTER_MS = 3000  # ping after this long without a command, as FurBLE does
DLC_INFO = b"\x72"
RETRY_FIND_S = 15  # how often to look again for a missing Furby


def ticks_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def ticks_diff(a, b):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(a, b)
    return a - b


def trigger_command(action):
    """Bytes that make a Furby play a fully specified action, e.g. (75, 0, 0, 2)."""
    return bytes([0x13, 0] + list(action))


def antenna_command(rgb):
    """Bytes that set the antenna light, e.g. (255, 0, 0) for red; (0, 0, 0) turns it off."""
    return bytes([0x14] + list(rgb))


def active_slot(info):
    """Active DLC slot from a 0x72 (DLC info) response, or None."""
    active = (info[7] << 8) | info[8]
    for slot in range(14):
        if active & (1 << slot):
            return slot
    return None


def slot_name(info):
    """DLC name from a 0x73 (slot info) response, without padding: b'____PINK' → 'PINK'."""
    return bytes(info[2:10]).decode().strip("_\x00 ")


def slot_checksum(info):
    """Adler-32 checksum of the active DLC, from a 0x73 (slot info) response."""
    return int.from_bytes(bytes(info[13:17]), "big")


def step_parts(step):
    """The clips one scene step plays together: "pink.a + blue.a" → ["pink.a", "blue.a"]."""
    return [part.strip() for part in step.split("+")]


def pick_scene(scenes, present, last=None):
    """A random scene whose Furbies are all connected, avoiding a repeat if possible."""
    ready = [s for s in scenes if all(p.split(".")[0] in present for step in s for p in step_parts(step))]
    fresh = [s for s in ready if s != last] or ready
    return random.choice(fresh) if fresh else None


class Furby:
    """One Furby. Subclasses provide connected() and _write(data), and pass
    every notification from the GeneralPlus listen characteristic to on_response()."""

    def __init__(self, address):
        self.address = address
        self.name = None
        self.checksum = None
        self.waiting = []  # [prefix, response, event] for commands awaiting a reply
        self.last_sent = ticks_ms()

    def __str__(self):
        return self.name or str(self.address)

    def connected(self):
        raise NotImplementedError

    async def _write(self, data):
        raise NotImplementedError

    async def disconnect(self):
        """Let go of the Furby, so it can advertise again and frees a connection slot."""
        raise NotImplementedError

    def on_response(self, data):
        for entry in self.waiting:
            if entry[1] is None and bytes(data[: len(entry[0])]) == entry[0]:
                entry[1] = bytes(data)
                entry[2].set()

    async def command(self, data, expect=None, timeout=5):
        entry = [bytes(expect), None, asyncio.Event()] if expect else None
        if entry:
            self.waiting.append(entry)
        self.last_sent = ticks_ms()
        try:
            await self._write(bytes(data))
            if entry:
                await asyncio.wait_for(entry[2].wait(), timeout)
                return entry[1]
        finally:
            if entry:
                self.waiting.remove(entry)

    async def identify(self, attempts=3):
        """Name this Furby after its active DLC (pink.dlc → "pink"), and note its checksum.

        Retries because a sensor report arriving at the same moment can crowd out
        the reply (aioble keeps only the latest notification).
        """
        for attempt in range(attempts):
            try:
                slot = active_slot(await self.command(DLC_INFO, expect=DLC_INFO))
                if slot is None:
                    raise ValueError("%s has no active DLC; flash pink.dlc or blue.dlc to it first" % self.address)
                info = await self.command(bytes([0x73, slot]), expect=bytes([0x73, slot]))
                self.name, self.checksum = slot_name(info).lower(), slot_checksum(info)
                return self.name
            except asyncio.TimeoutError:
                if attempt == attempts - 1:
                    raise

    async def play(self, action):
        await self.command(trigger_command(action))

    async def set_antenna(self, rgb):
        await self.command(antenna_command(rgb))

    async def keep_alive(self):
        while self.connected():
            if ticks_diff(ticks_ms(), self.last_sent) > KEEPALIVE_AFTER_MS:
                try:
                    await self.command(KEEPALIVE)
                except Exception as e:
                    print("Keepalive to %s failed: %s" % (self, e))
            await asyncio.sleep(1)


class Show:
    """Plays scenes from show.json (written by halloween.py) on whichever Furbies are connected.

    find(known_addresses) connects to Furbies in range and returns them, identified.
    Call trigger() to play one of the plan's "greetings" right away, e.g. from
    a button; the timer plays the other scenes. A motion sensor calls
    trigger(sensor=True), which is ignored for "cooldown" seconds after a
    greeting so a crowd on the porch doesn't set off greeting after greeting.
    On MicroPython, pass wake=asyncio.ThreadSafeFlag() so a pin interrupt can
    call trigger() and wake the show at once.
    """

    def __init__(self, plan, find, sleep=asyncio.sleep, log=print, wake=None):
        self.plan = plan
        self.find = find
        self.sleep = sleep
        self.log = log
        self.furbies = {}  # name → Furby
        self.wake = wake or asyncio.Event()
        self.last = None
        self.greeted = None  # ticks_ms() when the last greeting ended, for the sensor cooldown
        self.pressed = False  # a trigger that isn't from the sensor, which always counts
        self.playing = False  # true during a scene, e.g. to light an LED
        self.heartbeat = ticks_ms()  # last sign of progress, for a watchdog

    def stalled_ms(self):
        """How long since the show last made progress."""
        return ticks_diff(ticks_ms(), self.heartbeat)

    def present(self):
        return {name for name, f in self.furbies.items() if f.connected()}

    def trigger(self, sensor=False):
        if not sensor:
            self.pressed = True
        self.wake.set()

    def scenes(self, greeting=False):
        """The scenes to pick from: greetings when someone arrives, the rest on the timer."""
        greetings = self.plan.get("greetings", [])
        if greeting:
            return greetings or self.plan["scenes"]
        return [s for s in self.plan["scenes"] if s not in greetings] or self.plan["scenes"]

    async def connect_missing(self):
        known = [f.address for f in self.furbies.values() if f.connected()]
        for furby in await self.find(known):
            expected = self.plan["furbies"].get(furby.name)
            if expected is None:
                self.log("Ignoring %s: its DLC isn't one of %s" % (furby, sorted(self.plan["furbies"])))
                await furby.disconnect()
                continue
            if expected.get("checksum") not in (None, furby.checksum):
                self.log("%s.dlc on the Furby doesn't match this show; reflash it (clips may be wrong)" % furby)
            self.furbies[furby.name] = furby
            self.log("Connected to %s" % furby)
            asyncio.create_task(furby.keep_alive())

    async def play_step(self, step):
        """Play one step: a clip, or several at once ("pink.a + blue.a") for a duet."""
        self.heartbeat = ticks_ms()
        lines = []
        for part in step_parts(step):
            name, clip = part.split(".")
            plan = self.plan["furbies"][name]
            lines.append((self.furbies[name], plan["clips"][clip], plan.get("antenna")))
        # A clip's "before" holds an extra beat first, e.g. before a punchline.
        before = max(info.get("before", 0) for _, info, _ in lines)
        if before:
            await self.sleep(before)
        # Each speaking Furby's antenna glows its color for the line. Light them
        # all first, then trigger the clips back to back so duets start together.
        for furby, _, antenna in lines:
            if antenna:
                await furby.set_antenna(antenna)
        for furby, info, _ in lines:
            await furby.play(info["action"])
        await self.sleep(max(info["seconds"] for _, info, _ in lines))
        for furby, _, antenna in lines:
            if antenna:
                await furby.set_antenna((0, 0, 0))
        await self.sleep(self.plan["gap"])

    async def play_scene(self, scene):
        self.log("Scene: %s" % " -> ".join(scene))
        self.playing = True
        try:
            for step in scene:
                await self.play_step(step)
        finally:
            self.playing = False

    async def wait(self, seconds):
        """Sleep, but wake early if trigger() is called; returns True if it was.

        A trigger that came in during the last scene counts too, so someone who
        arrived mid-scene is greeted as soon as it ends.
        """
        start = ticks_ms()
        while True:
            left = seconds - ticks_diff(ticks_ms(), start) / 1000
            if left <= 0:
                return False
            try:
                await asyncio.wait_for(self.wake.wait(), left)
            except asyncio.TimeoutError:
                return False
            self.wake.clear()
            if self.pressed:
                self.pressed = False
                return True
            cooldown = self.plan.get("cooldown", 0)
            if self.greeted is None or ticks_diff(ticks_ms(), self.greeted) >= cooldown * 1000:
                return True
            self.log("Motion ignored: a greeting just played")

    async def run_once(self, greeting=False):
        """Connect what's missing, play one scene if possible; returns how long to wait.

        greeting picks from the greetings, for when someone has just arrived.
        """
        if self.present() != set(self.plan["furbies"]):
            await self.connect_missing()
        scene = pick_scene(self.scenes(greeting), self.present(), self.last)
        if not scene and greeting:  # no greeting playable with who's here: anything will do
            scene = pick_scene(self.plan["scenes"], self.present(), self.last)
        if not scene:
            self.log("Waiting for Furbies: have %s, need %s" % (sorted(self.present()), sorted(self.plan["furbies"])))
            return RETRY_FIND_S
        try:
            await self.play_scene(scene)
        except Exception as e:
            self.log("Scene interrupted: %s" % e)
        self.last = scene
        if scene in self.plan.get("greetings", []):
            self.greeted = ticks_ms()
        return random.uniform(self.plan["every"][0], self.plan["every"][1])

    async def run(self):
        greeting = False
        while True:
            self.heartbeat = ticks_ms()
            try:
                wait = await self.run_once(greeting)
            except Exception as e:  # never let one bad scan end the show
                self.log("Show error, retrying: %s" % e)
                wait = RETRY_FIND_S
            greeting = await self.wait(wait)
