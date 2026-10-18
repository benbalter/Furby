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
import math
import random
import time

GP_SERVICE = "dab91435-b5a1-e29c-b041-bcd562613bde"
GP_WRITE = "dab91383-b5a1-e29c-b041-bcd562613bde"
GP_LISTEN = "dab91382-b5a1-e29c-b041-bcd562613bde"

KEEPALIVE = b"\x20\x06"  # "I'm here", which keeps a connected Furby awake
KEEPALIVE_AFTER_MS = 3000  # ping after this long without a command, as FurBLE does
DLC_INFO = b"\x72"
# Status notifications ("FurbyMessage", as PyFluff names them)
SPEECH_PLAYING = b"\x20\x07"  # still busy with the last sequence: the action runs, but without its audio
SEQUENCE_PLAYING = b"\x20\x0c"  # the action started, audio and all
SEQUENCE_CANCELLED = b"\x20\x0d"
SEQUENCE_ENDED = b"\x20\x0e"
PLAY_REPLY_MS = 1000  # a Furby answers a trigger within about 0.1 s
PLAY_PATIENCE_MS = 25000  # the longest stock sequence in a scene slot runs about 21 s
RETRY_FIND_S = 15  # how often to look again for a missing Furby
HINT_AFTER_SCANS = 3  # empty scans in a row before suggesting the Furbies are singing together
OFF = (0, 0, 0)
LIGHT_HZ = 10  # antenna updates a second while a line plays: show.toml's light_hz
LIGHT_MAX_HZ = 15  # don't flood the Furby, or an ESP32 radio shared by two, with writes
ENVELOPE_HZ = 10  # loudness levels a second in a clip's envelope (see halloween.envelope)
# What an antenna can do while its Furby speaks (see light_rgb)
EFFECTS = ("off", "steady", "voice", "candle", "pulse", "wisp", "lightning", "cycle")


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


def _byte(x):
    return max(0, min(255, int(x + 0.5)))


def scale(rgb, k):
    """rgb dimmed (or brightened) by k, as a tuple of bytes."""
    return (_byte(rgb[0] * k), _byte(rgb[1] * k), _byte(rgb[2] * k))


def hue_rgb(h):
    """A fully saturated colour for hue h (0 to 1 goes once round the wheel)."""
    h = (h % 1) * 6
    i, f = int(h) % 6, h - int(h)
    r, g, b = ((1, f, 0), (1 - f, 1, 0), (0, 1, f), (0, 1 - f, 1), (f, 0, 1), (1, 0, 1 - f))[i]
    return (_byte(r * 255), _byte(g * 255), _byte(b * 255))


def _noise(n, seed):
    """Repeatable noise in 0-1 for frame n, so rehearsals and tests see the same flicker.

    Small-int arithmetic only, so it allocates nothing on MicroPython.
    """
    x = (n * 7919 + seed * 104729 + 12345) & 0xFFFF
    x ^= x >> 7
    x = (x * 2053 + 13849) & 0xFFFF
    x ^= x >> 9
    return x / 0xFFFF


def envelope_level(envelope, t_ms, hz=ENVELOPE_HZ):
    """How loud a clip is t_ms in, 0-1, from its envelope ("0379...", a digit per 1/hz s).

    No envelope (a show.json from before lights followed the sound) counts as
    full volume, and past the end as silence.
    """
    if not envelope:
        return 1.0
    i = t_ms * hz // 1000
    return (ord(envelope[i]) - 48) / 9 if 0 <= i < len(envelope) else 0.0


def light_rgb(light, t_ms, level, seed=0, hz=LIGHT_HZ):
    """The antenna colour t_ms into a line, for a clip's light ({"effect", "color"}).

    level is how loud the clip is then (envelope_level), so every effect but
    steady swells with the sound. seed varies the flicker from clip to clip.
    An effect this engine doesn't know glows steady, so a newer show.json
    still lights up.
    """
    effect, rgb = light.get("effect", "steady"), light.get("color") or OFF
    n = t_ms * hz // 1000  # frame number, so noise changes once a frame
    if effect == "off":
        return OFF
    if effect == "voice":  # brightness follows the sound
        return scale(rgb, 0.15 + 0.85 * level)
    if effect == "candle":  # a jack-o'-lantern's flicker, livelier when loud
        return scale(rgb, 0.35 + 0.35 * level + 0.3 * _noise(n, seed))
    if effect == "pulse":  # a slow throb, pushed brighter by the voice
        wave = 0.5 + 0.5 * math.sin(2 * math.pi * t_ms / 1200)
        return scale(rgb, max(0.2 + 0.5 * wave, level))
    if effect == "wisp":  # a faint, slow breath
        wave = 0.5 + 0.5 * math.sin(2 * math.pi * t_ms / 3000)
        return scale(rgb, 0.15 + 0.3 * wave + 0.45 * level)
    if effect == "lightning":  # a dim glow with white flashes, more of them when loud
        if _noise(n, seed) < 0.04 + 0.3 * level * level:
            return (255, 255, 255)
        return scale(rgb, 0.1 + 0.5 * level)
    if effect == "cycle":  # round the colour wheel, brighter and further when loud
        return scale(hue_rgb(t_ms / 2500 + seed / 7 + 0.3 * level), 0.4 + 0.6 * level)
    return scale(rgb, 1)


def clip_light(furby_plan, info):
    """A clip's light from show.json, or None for none.

    A show.json from before lights followed the eyes has no light, so the
    Furby's antenna colour glows steady, as it used to.
    """
    light = info.get("light")
    if light is None and furby_plan.get("antenna"):
        light = {"effect": "steady", "color": furby_plan["antenna"]}
    if not light or light.get("effect") == "off":
        return None
    return light


def plan_order(text, names):
    """The Furbies' names in the order show.json lists them, from its text.

    MicroPython's dicts don't keep key order, so the board can't take it
    from json.loads(). Each name is ranked by where its key first appears
    after "furbies"; a name that can't be found goes last.
    """
    start = max(0, text.find('"furbies"'))

    def where(name):
        i = text.find('"%s":' % name, start)
        return (i if i >= 0 else len(text), name)

    return sorted(names, key=where)


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
        self.antenna = None  # the colour last sent, or None if unknown

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
            if entry[1] is None and any(bytes(data[: len(p)]) == p for p in entry[0]):
                entry[1] = bytes(data)
                entry[2].set()

    async def command(self, data, expect=None, timeout=5):
        """Send data (None sends nothing) and, given expect, return the reply that starts with it.

        expect can be a tuple of prefixes, to take whichever reply comes first.
        """
        prefixes = expect if isinstance(expect, tuple) else (expect,)
        entry = [[bytes(p) for p in prefixes], None, asyncio.Event()] if expect else None
        if entry:
            self.waiting.append(entry)
        try:
            if data is not None:
                self.last_sent = ticks_ms()
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

    async def play(self, action, patience_ms=PLAY_PATIENCE_MS):
        """Trigger an action; returns False if the Furby stayed too busy to play its audio.

        A sequence's body movement and eye delays often outlast its clip, by up
        to 20 s. A Furby still running one answers a new trigger with 20:07 and
        plays the action without its audio. So on 20:07, wait for the running
        sequence to end (20:0e) and trigger again. No reply at all counts as
        played, so a missed notification can't stall the show.
        """
        start = ticks_ms()
        while True:
            try:
                reply = await self.command(
                    trigger_command(action), expect=(SEQUENCE_PLAYING, SPEECH_PLAYING), timeout=PLAY_REPLY_MS / 1000
                )
            except asyncio.TimeoutError:
                return True
            if reply[:2] == SEQUENCE_PLAYING:
                return True
            left = patience_ms - ticks_diff(ticks_ms(), start)
            if left <= 0:
                return False
            try:  # 20:0e can slip past between the replies, so don't wait on it for long
                await self.command(None, expect=(SEQUENCE_ENDED, SEQUENCE_CANCELLED), timeout=min(left, 2000) / 1000)
            except asyncio.TimeoutError:
                pass

    async def set_antenna(self, rgb):
        self.antenna = None  # unknown until the write goes through
        await self.command(antenna_command(rgb))
        self.antenna = tuple(rgb)

    async def glow(self, rgb):
        """Set the antenna unless it already shows rgb, to keep Bluetooth traffic down."""
        if tuple(rgb) != self.antenna:
            await self.set_antenna(rgb)

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

    Two Furbies woken together start singing to each other and stop
    advertising, so the show asks for them one at a time, in order (show.json's,
    or pass order, e.g. from plan_order() on MicroPython): waiting_for() is
    the next one to power up, and run() logs what to do whenever that changes.
    """

    def __init__(self, plan, find, sleep=asyncio.sleep, log=print, wake=None, order=None, trace=None):
        self.plan = plan
        self.order = list(order or plan.get("order") or plan["furbies"])
        self.find = find
        self.sleep = sleep
        self.log = log
        self.trace = trace  # trace(error) prints a traceback, e.g. sys.print_exception on the board
        self.furbies = {}  # name → Furby
        self.wake = wake or asyncio.Event()
        self.last = None
        self.greeted = None  # ticks_ms() when the last greeting ended, for the sensor cooldown
        self.pressed = False  # a trigger that isn't from the sensor, which always counts
        self.playing = False  # true during a scene, e.g. to light an LED
        self.heartbeat = ticks_ms()  # last sign of progress, for a watchdog
        self.seen = set()  # every Furby that has connected, to tell a drop from a first power-up
        self.empty_scans = 0  # scans in a row that connected nobody new
        self.guided = None  # the power-up state last logged by guide()
        self.cut_short = False  # a Furby dropped during the last scene

    def stalled_ms(self):
        """How long since the show last made progress."""
        return ticks_diff(ticks_ms(), self.heartbeat)

    def present(self):
        return {name for name, f in self.furbies.items() if f.connected()}

    def waiting_for(self):
        """The next Furby to power up: the first in order that isn't connected, or None."""
        present = self.present()
        for name in self.order:
            if name not in present:
                return name
        return None

    def waiting_index(self):
        """waiting_for()'s place in the order (0 for the first Furby), or None."""
        name = self.waiting_for()
        return None if name is None else self.order.index(name)

    def stuck(self):
        """True if the Furbies might be singing together: a missing Furby hasn't turned
        up for a few scans, or every Furby has dropped and none came back."""
        if self.waiting_for() is None or not self.empty_scans:
            return False
        return self.empty_scans >= HINT_AFTER_SCANS or bool(self.seen and not self.present())

    def guidance(self):
        """What to do next, for whoever's setting up: which Furby to power up."""
        name = self.waiting_for()
        if name is None:
            return "All Furbies connected: %s." % ", ".join(self.order)
        here = [n for n in self.order if n in self.present()]
        if self.stuck():
            if here:
                return "Still no %s. Take its batteries out and put them back to wake it." % name
            return "If they're singing together, take the batteries out of one and power them up one at a time."
        if not here:
            return "Put batteries in (or wake) only the %s Furby. Wake the others once it connects." % name
        others = "%s %s" % (" and ".join(n.capitalize() for n in here), "is" if len(here) == 1 else "are")
        if name in self.seen:  # it dropped mid-show
            return "%s dropped. %s still connected; wake %s again." % (name.capitalize(), others, name)
        return "%s connected. Now power up %s." % (others, name)

    def guide(self):
        """Log guidance() when the power-up state changes, so it prints once per change."""
        state = (self.waiting_for(), self.stuck(), len(self.present()))
        if state != self.guided:
            self.guided = state
            self.log(self.guidance())

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
        added = 0
        for furby in await self.find(known):
            expected = self.plan["furbies"].get(furby.name)
            if expected is None:
                self.log("Ignoring %s: its DLC isn't one of %s" % (furby, sorted(self.plan["furbies"])))
                await furby.disconnect()
                continue
            if expected.get("checksum") not in (None, furby.checksum):
                self.log("%s.dlc on the Furby doesn't match this show; reflash it (clips may be wrong)" % furby)
            other = self.furbies.get(furby.name)
            if other is not None and other.connected() and other.address != furby.address:
                # Easy to do in FurBLE, which keeps the last file you picked
                self.log("Two Furbies have %s.dlc; flash the right DLC to one of them" % furby)
                await furby.disconnect()
                continue
            self.furbies[furby.name] = furby
            self.seen.add(furby.name)
            added += 1
            self.log("Connected to %s" % furby)
            asyncio.create_task(furby.keep_alive())
        self.empty_scans = 0 if added else self.empty_scans + 1

    def light_hz(self):
        """Antenna updates a second during a line, from show.json, kept to 1-15."""
        return max(1, min(LIGHT_MAX_HZ, int(self.plan.get("light_hz", LIGHT_HZ))))

    def rest(self, name):
        """A Furby's antenna between its lines: its idle glow during a scene, otherwise off."""
        return (self.playing and self.plan["furbies"][name].get("idle")) or OFF

    async def quietly(self, furby, rgb):
        """Set the antenna if possible; a Furby that just dropped mustn't hide the real error."""
        try:
            await furby.glow(rgb)
        except Exception:
            pass

    async def light_line(self, furby, info, light, rest, stop):
        """Animate a Furby's antenna for its line, until the clip ends or stop is set.

        Runs alongside the line rather than in front of it, so it never delays
        a trigger. Frames go by the clock, not a frame count, so a slow write
        doesn't put the light behind the sound, and an unchanged colour isn't
        resent. At the clip's own end (the shorter half of a duet, say) the
        antenna goes back to rest.
        """
        hz = self.light_hz()
        seed = info["action"][2] * 31 + info["action"][3]  # so two Furbies don't flicker in step
        envelope, envelope_hz = info.get("envelope"), self.plan.get("envelope_hz", ENVELOPE_HZ)
        start = ticks_ms()
        while not stop.is_set():
            t = ticks_diff(ticks_ms(), start)
            if t >= info["seconds"] * 1000:
                await self.quietly(furby, rest)
                return
            try:
                rgb = light_rgb(light, t, envelope_level(envelope, t, envelope_hz), seed, hz)
            except Exception as e:  # a bad light in show.json: say so rather than go quietly dark
                self.log("%s's light stopped: %s" % (furby, e))
                return
            try:
                await furby.glow(rgb)
            except Exception:  # it dropped mid-line; the show reconnects later
                return
            try:
                await asyncio.wait_for(stop.wait(), 1 / hz)
            except asyncio.TimeoutError:
                pass

    async def play_step(self, step):
        """Play one step: a clip, or several at once ("pink.a + blue.a") for a duet."""
        self.heartbeat = ticks_ms()
        lines = []
        for part in step_parts(step):
            name, clip = part.split(".")
            furby = self.furbies.get(name)
            if furby is None or not furby.connected():  # the others carry on without it
                self.skip(part, name)
                continue
            plan = self.plan["furbies"][name]
            info = plan["clips"][clip]
            lines.append((furby, info, clip_light(plan, info), name, part))
        if not lines:
            return
        # A clip's "before" holds an extra beat first, e.g. before a punchline.
        before = max(line[1].get("before", 0) for line in lines)
        if before:
            await self.sleep(before)
        # Each speaking Furby's antenna lights for its line (see light_rgb). Light
        # them all first, then trigger the clips back to back so duets start
        # together; each light then follows its own line from when it starts.
        for furby, info, light, _, _ in lines:
            if light:
                level = envelope_level(info.get("envelope"), 0)
                await self.quietly(furby, light_rgb(light, 0, level, info["action"][2] * 31 + info["action"][3]))
        stop = asyncio.Event()
        tasks = []
        try:
            for furby, info, light, name, part in lines:
                try:
                    played = await furby.play(info["action"])
                except Exception as e:  # it dropped mid-write
                    self.skip(part, name, e)
                    continue
                if not played:
                    self.log("%s skipped: %s stayed busy with its last sequence" % (part, furby))
                elif light:
                    tasks.append(asyncio.create_task(self.light_line(furby, info, light, self.rest(name), stop)))
            await self.sleep(max(line[1]["seconds"] for line in lines))
        finally:
            # However the step ends, even interrupted, every light stops and goes back to rest
            stop.set()
            for task in tasks:
                try:
                    await task
                except Exception:
                    pass
            for furby, _, light, name, _ in lines:
                if light:
                    await self.quietly(furby, self.rest(name))
        await self.sleep(self.plan["gap"])

    def skip(self, part, name, error=None):
        """Note a line that can't play because its Furby dropped; the show looks for it sooner."""
        self.cut_short = True
        self.log("Skipping %s: %s dropped%s" % (part, name, " (%s)" % error if error else ""))

    async def play_scene(self, scene):
        self.log("Scene: %s" % " -> ".join(scene))
        names = sorted({p.split(".")[0] for step in scene for p in step_parts(step)})
        self.playing = True
        try:
            # With [show] idle_glow, everyone in the scene glows dimly while the others speak
            for name in names:
                if self.plan["furbies"][name].get("idle") and name in self.furbies:
                    await self.quietly(self.furbies[name], self.rest(name))
            for step in scene:
                await self.play_step(step)
        finally:
            self.playing = False
            for name in names:
                furby = self.furbies.get(name)
                if furby is not None and furby.antenna not in (None, OFF):
                    await self.quietly(furby, OFF)

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
        Someone at the door is greeted by whoever's connected, without waiting
        on a scan for a Furby that's missing; the timed scenes look for it.
        """
        scene = pick_scene(self.scenes(True), self.present(), self.last) if greeting else None
        if not scene and self.present() != set(self.plan["furbies"]):
            self.guide()  # say who to power up before the scan, which takes a while
            try:
                await self.connect_missing()
            finally:
                self.guide()
        scene = scene or pick_scene(self.scenes(greeting), self.present(), self.last)
        if not scene and greeting:  # no greeting playable with who's here: anything will do
            scene = pick_scene(self.plan["scenes"], self.present(), self.last)
        if not scene:  # guide() has already said who's missing
            if self.waiting_for() is None:
                self.log("No scene to play with %s" % ", ".join(self.order))
            return RETRY_FIND_S
        self.cut_short = False
        try:
            await self.play_scene(scene)
        except Exception as e:
            self.log("Scene interrupted: %s" % e)
            if self.trace:
                self.trace(e)
            self.cut_short = True
        self.last = scene
        if greeting:  # even one that fell back to an ordinary scene starts the cooldown
            self.greeted = ticks_ms()
        if self.cut_short:  # someone dropped: look for them soon, not after a whole wait
            return RETRY_FIND_S
        return random.uniform(self.plan["every"][0], self.plan["every"][1])

    async def run(self):
        greeting = False
        while True:
            self.heartbeat = ticks_ms()
            try:
                wait = await self.run_once(greeting)
            except Exception as e:  # never let one bad scan end the show
                self.log("Show error, retrying: %s" % e)
                if self.trace:
                    self.trace(e)
                wait = RETRY_FIND_S
            greeting = await self.wait(wait)
