#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
A virtual Furby Connect, to run the show (and flash.py's upload) with no Furbies.

It answers the GeneralPlus commands the way the hardware has been measured to:

- 0x13 (trigger): 20:0c when idle, then 20:0e when the action's sequence
  ends; 20:07 while the last sequence is still running, in which case the
  action plays without its audio (logged as a silent line).
- 0x72 / 0x73 (DLC info), 0x20 0x06 (keepalive), 0x14 (antenna), 0xcd
  (eyes on/off).
- The upload flash.py does: 0x50 announce → 0x24 02, the file over
  FileWrite with Nordic packet acks, 0x24 05 (or 03 past MAX_UPLOAD), then
  0x74 delete, 0x62 deactivate, 0x60 load and 0x61 activate, each → 0xdc.

A sequence runs as long as the longest of its audio (AMF bytes at 2 KB/s
plus APL pauses), its delay words, and its body movement. Only ranges have
been measured for movements (built-in 0xe0xx about 1-9 s, the DLC's own
0xc4xx 10-21 s), so an unmeasured one takes the bottom of its range, or the
top with --worst. Pass --durations with a JSON file of measured times to
replace them:

    {"motors": {"e005": 2.4, "c403": 18.0}, "actions": {"75-0-0-2": 3.1}}

Pause and delay words (0x1xxx) are read as 10 ms units, an assumption that
puts the stock sequences inside the measured ranges.

When a DLC goes active, its eyes are checked with eyecheck: one outside the
envelope keeps the previous DLC's cels, as probe.dlc did on a real Furby.

Everything runs on a virtual clock, so a whole show takes well under a second.

USAGE:
    python emulate.py                                    # every scene in build/halloween/show.json
    python emulate.py --scene 3 --wait 30                # one scene; wait between repeats
    python emulate.py --durations measured.json          # measured sequence times
    python emulate.py --engine old/furbyshow.py          # another version of the show engine
"""

import argparse
import asyncio
import contextlib
import importlib.util
import json
import os
import selectors
import sys
import zlib

import furbyshow

MAX_UPLOAD = 350_000  # uploads time out above about this
REPLY_S = 0.05  # how long a Furby takes to answer
A18_BYTES_PER_SECOND = 2000
DELAY_UNIT_S = 0.01  # a delay word's low 12 bits, in these units (assumed)
# Body movement by the motor word's top nibble, (shortest, longest) as timed on a Furby over three
# sweeps of the scene slots: built-in 0xe0xx about 1-9 s, the DLC's own 0xc4xx 10-21 s.
MOTOR_RANGE_S = {0xE: (1.0, 9.0), 0xC: (10.0, 21.0)}
TRANSFER_READY, TRANSFER_TIMEOUT, TRANSFER_OK, TRANSFER_ERR = 2, 3, 5, 6
NORDIC_ACK = 0x09


# ---- a virtual clock ---------------------------------------------------------


class _Clock:
    now = 0.0


class _InstantSelector(selectors.SelectSelector):
    """Instead of waiting for I/O, jump the clock to the next timer."""

    def __init__(self, clock):
        super().__init__()
        self.clock = clock

    def select(self, timeout=None):
        if timeout is None:
            raise RuntimeError("everything is waiting on something that will never happen")
        self.clock.now += max(timeout, 0)
        return []


class VirtualTimeLoop(asyncio.SelectorEventLoop):
    """An event loop whose time() is virtual: sleeps and timeouts take no real time."""

    def __init__(self):
        self.clock = _Clock()
        super().__init__(_InstantSelector(self.clock))

    def time(self):
        return self.clock.now


@contextlib.contextmanager
def virtual_time(*engines):
    """A VirtualTimeLoop, with each engine module's ticks_ms() following its clock."""
    loop = VirtualTimeLoop()
    saved = [(e, e.ticks_ms) for e in engines]
    for e in engines:
        e.ticks_ms = lambda: int(loop.time() * 1000)
    try:
        yield loop
    finally:
        for e, f in saved:
            e.ticks_ms = f
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()


def run(coro, *engines):
    """Run a coroutine on virtual time; returns (its result, virtual seconds it took)."""
    with virtual_time(*engines) as loop:
        result = loop.run_until_complete(coro)
        return result, loop.time()


# ---- sequence timing ---------------------------------------------------------


def load_durations(path=None, worst=False):
    """Measured times from a JSON file: {"motors": {"e005": s}, "actions": {"75-0-0-2": s}}.

    worst: unmeasured movements take the top of their measured range, not the bottom.
    """
    data = {}
    if path:
        with open(path) as f:
            data = json.load(f)
    return {
        "motors": {int(k, 16): v for k, v in data.get("motors", {}).items()},
        "actions": {tuple(int(x) for x in k.split("-")): v for k, v in data.get("actions", {}).items()},
        "worst": worst,
    }


def sequence_seconds(D, action, durations=None):
    """How long an action keeps a Furby busy, and how long its audio runs: (busy, audio)."""
    durations = durations or load_durations()
    action = tuple(action)
    seq_no = D.dlc_sections["XLS"].action_tree[action[0]][action[1]][action[2]][action[3]]["seq"]
    seq = D.dlc_sections["SEQ"].sequences[seq_no]
    apl = D.dlc_sections["APL"].playlists[seq[1] - D.dlc_sections["SEQ"].playlist_offset]
    tracks = D.dlc_sections["AMF"].tracks
    audio = sum(
        len(tracks[n]) / A18_BYTES_PER_SECOND
        if kind == "AUDIO"
        else (n & 0xFFF) * DELAY_UNIT_S
        if kind == "PAUSE"
        else 0
        for n, kind in apl
    )
    motor = seq[2]
    move = durations["motors"].get(motor, MOTOR_RANGE_S.get(motor >> 12, (0, 0))[1 if durations.get("worst") else 0])
    delays = sum((w & 0xFFF) * DELAY_UNIT_S for w in seq[3:-1] if w >> 12 == 0x1)
    busy = durations["actions"].get(action, max(audio, move, delays))
    return busy, audio


# ---- the Furby ----------------------------------------------------------------


class FurbyModel:
    """The Furby's side of the protocol, transport-free: feed it writes, it calls notify(uuid, data)."""

    def __init__(self, notify, durations=None, log=None):
        self.notify = notify  # notify(characteristic uuid, bytes), called on the loop
        self.durations = durations or load_durations()
        self.log = log if log is not None else []  # (time, event, detail) tuples
        self.slots = {}  # slot → {"name", "data", "dlc"}
        self.active = None
        self.loading = None
        self.antenna = (0, 0, 0)
        self.eyes_on = True
        self.cels = None  # the CEL the eyes draw with: the last DLC whose graphics loaded
        self.busy_until = 0.0
        self.end_handle = None
        self.upload = None  # {"size", "name", "data"} during an upload
        self.acks = False
        self.packets = 0

    def now(self):
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:  # set up before the show starts
            return 0.0

    def _say(self, data, uuid=furbyshow.GP_LISTEN, delay=REPLY_S):
        asyncio.get_running_loop().call_later(delay, self.notify, uuid, bytes(data))

    def _record(self, event, detail=None):
        self.log.append((round(self.now(), 3), event, detail))

    def dlc(self):
        return self.slots[self.active]["dlc"] if self.active is not None else None

    def info(self):
        filled = sum(1 << s for s in self.slots)
        active = 1 << self.active if self.active is not None else 0
        return bytes([0x72, 0, 0, filled >> 8, filled & 0xFF, 0, 0, active >> 8, active & 0xFF])

    def gp_write(self, data):
        cmd = data[0]
        if cmd == 0x13:
            self.trigger(tuple(data[2:6]))
        elif data[:2] == furbyshow.KEEPALIVE:
            self._record("keepalive")
        elif cmd == 0x14:
            self.antenna = tuple(data[1:4])
            self._record("antenna", self.antenna)
        elif cmd == 0xCD:
            self.eyes_on = bool(data[1])
        elif cmd == 0x72:
            self._say(self.info())
        elif cmd == 0x73:
            slot = data[1]
            name = self.slots[slot]["name"] if slot in self.slots else ""
            checksum = zlib.adler32(self.slots[slot]["data"]) if slot in self.slots else 0
            stem = name.split(".")[0].encode().ljust(8, b"\0")[:8]
            self._say(bytes([0x73, slot]) + stem + bytes(3) + checksum.to_bytes(4, "big"))
        elif cmd == 0x50:
            size = int.from_bytes(data[2:5], "big")
            self.upload = {"size": size, "name": bytes(data[6:18]).decode(errors="replace"), "data": bytearray()}
            self._record("upload", (self.upload["name"], size))
            self._say([0x24, TRANSFER_READY])
        elif cmd == 0x74:
            self.slots.pop(data[1], None)
            if self.active == data[1]:
                self.active = None
            self._say([0x74, data[1]])
        elif cmd == 0x62:
            if self.active == data[1]:
                self.active = None
            self._say([0xDC, data[1], 0])
        elif cmd == 0x60:
            self.loading = data[1]
            self._say([0xDC, data[1], 1])
        elif cmd == 0x61:
            self.activate(self.loading)
            self._say([0xDC, self.loading, 2])
        else:
            self._record("unknown", bytes(data).hex())

    def nordic_write(self, data):
        if data[:1] == bytes([NORDIC_ACK]):
            self.acks = bool(data[1])

    def file_write(self, data):
        up = self.upload
        if up is None:
            return
        up["data"] += data
        self.packets += 1
        if self.acks and self.packets % 5 == 0:
            self._say([NORDIC_ACK, 0], flash_nordic_listen())
        if len(up["data"]) > MAX_UPLOAD:
            self.upload = None
            self._record("upload timed out", len(up["data"]))
            self._say([0x24, TRANSFER_TIMEOUT])
        elif len(up["data"]) >= up["size"]:
            self.upload = None
            ok = len(up["data"]) == up["size"]
            if ok:
                slot = min(set(range(14)) - set(self.slots))
                self.slots[slot] = {"name": up["name"], "data": bytes(up["data"]), "dlc": _parse(bytes(up["data"]))}
            self._say([0x24, TRANSFER_OK if ok else TRANSFER_ERR])

    def activate(self, slot):
        self.active = slot
        D = self.dlc()
        self._record("active", self.slots[slot]["name"])
        if D is None:
            return
        import eyecheck

        errors, _ = eyecheck.envelope(D)
        if errors and self.cels is not None:
            self._record("eyes keep the previous DLC's cels", errors[0])
        else:
            self.cels = D.dlc_sections["CEL"].cels

    def eyes(self, word, eye="right"):
        """The frames eye word `word` shows now, cels and all (see eyecheck.compose)."""
        import eyecheck

        return eyecheck.compose(self.dlc(), word, eye, cels=self.cels)

    def trigger(self, action):
        D = self.dlc()
        busy, audio = sequence_seconds(D, action, self.durations) if D else (1.0, 0.0)
        if self.now() < self.busy_until:
            self._record("silent", action)  # the action runs, without its audio
            self._say(furbyshow.SPEECH_PLAYING)
            return
        self._record("played", (action, round(audio, 2), round(busy, 2)))
        self._say(furbyshow.SEQUENCE_PLAYING)
        self.busy_until = self.now() + busy
        self._say(furbyshow.SEQUENCE_ENDED, delay=busy)


def flash_nordic_listen():
    import flash

    return flash.NORDIC_LISTEN


def _parse(data):
    """A furby.dlc of these bytes (it only reads files), or None if they don't parse."""
    import tempfile

    from furby import dlc

    with tempfile.NamedTemporaryFile(suffix=".dlc", delete=False) as f:
        f.write(data)
    try:
        return dlc(f.name)
    except Exception:
        return None
    finally:
        os.unlink(f.name)


def furby_class(engine=furbyshow):
    """A Furby class for this show engine whose other end is a FurbyModel."""

    class VirtualFurby(engine.Furby):
        def __init__(self, address, dlc_path=None, name=None, durations=None, log=None):
            super().__init__(address)
            self.model = FurbyModel(self._notify, durations, log)
            self.is_connected = True
            if dlc_path:
                with open(dlc_path, "rb") as f:
                    data = f.read()
                self.model.slots[0] = {"name": name or os.path.basename(dlc_path), "data": data, "dlc": _parse(data)}
                self.model.activate(0)

        def _notify(self, uuid, data):
            if uuid == engine.GP_LISTEN and self.is_connected:
                self.on_response(data)

        def connected(self):
            return self.is_connected

        async def _write(self, data):
            self.model.gp_write(bytes(data))

        async def disconnect(self):
            self.is_connected = False

    return VirtualFurby


class VirtualClient:
    """A bleak BleakClient stand-in over a FurbyModel, for flash.Flasher."""

    def __init__(self, durations=None, log=None):
        self.callbacks = {}
        self.model = FurbyModel(self._notify, durations, log)

    def _notify(self, uuid, data):
        if uuid in self.callbacks:
            self.callbacks[uuid](None, bytearray(data))

    async def start_notify(self, uuid, callback):
        self.callbacks[uuid] = callback

    async def write_gatt_char(self, uuid, data, response=False):
        import flash

        data = bytes(data)
        if uuid == furbyshow.GP_WRITE:
            self.model.gp_write(data)
        elif uuid == flash.FILE_WRITE:
            self.model.file_write(data)
        elif uuid == flash.NORDIC_WRITE:
            self.model.nordic_write(data)


# ---- running a show -----------------------------------------------------------


def load_engine(path):
    """Another copy of furbyshow.py (say, an old version), as its own module."""
    spec = importlib.util.spec_from_file_location("furbyshow_%08x" % zlib.adler32(path.encode()), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def simulate(plan, dlc_paths, scenes=None, wait=None, durations=None, engine=furbyshow):
    """Play scenes on virtual Furbies; returns a report: a dict per scene, in order.

    dlc_paths: {furby name: its DLC}, for sequence timing. scenes: indices
    into plan["scenes"] (default all). wait: seconds between scenes (default
    the plan's shortest, "every"[0], the worst case for a Furby still busy).
    """
    durations = durations or load_durations()
    wait = plan["every"][0] if wait is None else wait
    lines = []
    VirtualFurby = furby_class(engine)
    furbies = [
        VirtualFurby("virtual-%s" % n, p, "%s.DLC" % n.upper().rjust(8, "_"), durations) for n, p in dlc_paths.items()
    ]

    async def find(known):
        found = []
        for f in furbies:
            if f.address not in known:
                await f.identify()
                found.append(f)
        return found

    report = []

    async def main():
        show = engine.Show(plan, find, log=lines.append)
        await show.connect_missing()
        for i in scenes if scenes is not None else range(len(plan["scenes"])):
            scene = plan["scenes"][i]
            start, said = asyncio.get_running_loop().time(), len(lines)
            await show.play_scene(scene)
            end = asyncio.get_running_loop().time()
            events = [(f, e, d) for f in furbies for (t, e, d) in f.model.log if start <= t <= end]
            # A line is silent if its action ran without audio and wasn't then played again with it.
            silent = []
            for k, (f, e, d) in enumerate(events):
                later = [(f2, d2) for f2, e2, d2 in events[k + 1 :] if e2 == "played"]
                if e == "silent" and (f, d) not in [(f2, d2[0]) for f2, d2 in later]:
                    silent.append("%s %s" % (f, "-".join(map(str, d))))
            report.append(
                {
                    "scene": i,
                    "steps": scene,
                    "seconds": round(end - start, 2),
                    "planned": round(_planned(plan, scene), 2),
                    "silent": silent,
                    "skipped": [line for line in lines[said:] if "skipped" in line],
                    "played": sum(e == "played" for _, e, _ in events),
                }
            )
            await asyncio.sleep(wait)
        for f in furbies:
            await f.disconnect()

    run(main(), *{furbyshow, engine})
    return report


def _planned(plan, scene):
    """A scene's length if every line plays at once: its clips, befores and gaps."""
    total = 0
    for step in scene:
        infos = [plan["furbies"][p.split(".")[0]]["clips"][p.split(".")[1]] for p in furbyshow.step_parts(step)]
        total += max(i.get("before", 0) for i in infos) + max(i["seconds"] for i in infos) + plan["gap"]
    return total


def print_report(report):
    total = sum(r["seconds"] for r in report)
    print(
        "%d scenes, %.0f s of show (%.0f s if no line waited)."
        % (len(report), total, sum(r["planned"] for r in report))
    )
    for r in report:
        late = r["seconds"] - r["planned"]
        flags = []
        if late > 0.5:
            flags.append("+%.1f s waiting for a busy Furby" % late)
        if r["silent"]:
            flags.append("silent: " + ", ".join(r["silent"]))
        if r["skipped"]:
            flags.append("skipped: %d" % len(r["skipped"]))
        print(
            "  %2d  %5.1f s  %s%s"
            % (r["scene"], r["seconds"], " -> ".join(r["steps"]), ("  [" + "; ".join(flags) + "]") if flags else "")
        )
    return sum(len(r["skipped"]) for r in report) + sum(len(r["silent"]) for r in report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("plan", nargs="?", default="./build/halloween/show.json")
    parser.add_argument("--scene", type=int, action="append", help="just this scene (repeatable)")
    parser.add_argument("--wait", type=float, help="seconds between scenes (default: the plan's shortest)")
    parser.add_argument("--durations", help="JSON of measured sequence times (see the top of this file)")
    parser.add_argument("--worst", action="store_true", help="unmeasured movements take their longest measured time")
    parser.add_argument("--engine", help="a furbyshow.py to run instead of this one")
    args = parser.parse_args(argv)
    if not os.path.exists(args.plan):
        raise SystemExit("No %s; build the show first (python halloween.py)." % args.plan)
    with open(args.plan) as f:
        plan = json.load(f)
    here = os.path.dirname(args.plan)
    dlcs = {name: os.path.join(here, "%s.dlc" % name) for name in plan["furbies"]}
    missing = [p for p in dlcs.values() if not os.path.exists(p)]
    if missing:
        raise SystemExit("No %s; build the show first (python halloween.py)." % ", ".join(missing))
    engine = load_engine(args.engine) if args.engine else furbyshow
    report = simulate(plan, dlcs, args.scene, args.wait, load_durations(args.durations, args.worst), engine)
    problems = print_report(report)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
