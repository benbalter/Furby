# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Run the Halloween show from an ESP32 (MicroPython), with no computer.

The same show engine as porch.py (furbyshow.py), over aioble, MicroPython's
Bluetooth library. On power-up it finds both Furbies, tells them apart by
their active DLC, keeps them awake and plays a scene every so often. The
board's button, or a motion sensor if you wire one (PIR_PIN below), plays a
greeting right away. Wi-Fi stays off.

Two Furbies woken together sing to each other and can't be found, so the
show asks for them one at a time, and the LED says which (see led_pattern):

    1 blink, pause      power up the first Furby in show.json (pink)
    2 blinks, pause     it's connected: now power up the second (blue)
    fast flicker        nobody has turned up for a while: if they're singing
                        together, take the batteries out of one and power
                        them up one at a time
    solid               a scene is playing
    off                 every Furby is connected, between scenes

The same goes for a Furby that drops mid-show. The show also prints what to
do over USB serial (mpremote), and keeps the same log in log.txt on the board,
with why it started, connect errors and a status line every five minutes.

Safe boot: hold the button while plugging the board in to skip the show and
stay at the REPL, e.g. to copy new files. Otherwise a watchdog reboots the
board if the show ever hangs, which also means you have about two minutes
after interrupting the show before it reboots.

If the show can't start at all (a bad show.json, a missing aioble, an old
furbyshow.py left on the board), the LED blinks three long blinks, over and
over, for about 30 s, and the board restarts; the error is on USB serial.

Copy everything to the board with firmware/deploy.sh.
"""

import io
import os
import sys
import time

import machine

BUTTON_PIN = 47  # the FireBeetle 2 ESP32-S3's onboard button
LED_PIN = 21  # and its onboard LED
# A PIR motion sensor (e.g. an HC-SR501) plays a greeting when someone walks
# up. Put the GPIO its OUT pin is wired to here; None leaves it off.
#   - Power it from the board's VCC pin, which is 5 V from USB (on a LiPo it's
#     the battery's 3.7 V, below the HC-SR501's rated 4.5 V), and GND.
#   - Don't use GPIO 0, 3, 45 or 46 (the ESP32-S3's strapping pins), 19 or 20
#     (USB), 26-37 (flash and octal PSRAM), or 21 and 47 (the LED and
#     button). Any other header pin will do.
#   - On the sensor: jumper on H (repeat trigger), the time pot all the way
#     down (about 3 s), and allow it a minute to settle after power-up.
PIR_PIN = 4  # A0/IO4 on the FireBeetle header
CRASH_BLINKS = (1, 1, 1, 1, 0) * 3 + (0,) * 6  # three long blinks: the show couldn't start
CRASH_MS = 30_000  # how long to blink that before restarting
BLINK_MS = 100  # the status LED's pattern steps (see led_pattern)
WATCHDOG_MS = 120_000  # reboot if not fed for this long
STALL_MS = 300_000  # stop feeding the watchdog if the show makes no progress for this long
# A just-woken Furby can ignore the DLC question for over 15 s (3 tries, 5 s
# each), and giving up costs a whole rescan, so ask for up to 40 s.
IDENTIFY_ATTEMPTS = 8
# Everything the board prints also goes to log.txt on the board, so a run on
# battery can be read afterwards with firmware/getlog.sh.
# Past LOG_MAX it moves to log.txt.old. Only on the board, so tests write nothing.
LOG_PATH = "log.txt" if sys.implementation.name == "micropython" else None
LOG_MAX = 100_000
STATUS_S = 300  # how often to log a status line (uptime, Furbies, scenes, memory)


def uptime_s():
    return time.ticks_ms() // 1000 if hasattr(time, "ticks_ms") else int(time.monotonic())


def say(line):
    """Print a line with the seconds since boot, and append it to LOG_PATH."""
    line = "[%6d] %s" % (uptime_s(), line)
    print(line)
    if not LOG_PATH:
        return
    try:
        try:
            if os.stat(LOG_PATH)[6] > LOG_MAX:
                os.rename(LOG_PATH, LOG_PATH + ".old")
        except OSError:  # no log yet
            pass
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:  # a full or failing filesystem mustn't stop the show
        pass


def exception_text(error):
    """An exception's traceback where MicroPython gives one, else its repr."""
    if not hasattr(sys, "print_exception"):
        return repr(error)
    buf = io.StringIO()
    sys.print_exception(error, buf)
    return buf.getvalue().rstrip()


def crashed(error):
    """Say why the show couldn't start, blink it on the LED, then restart and try again.

    Needs nothing but machine, so it works even when an import is what failed.
    Holding the button (safe boot) stops at the REPL instead, to fix the files.
    """
    say("The show couldn't start:\n" + exception_text(error))
    if machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP).value() == 0:
        say("Button held: safe boot, staying at the REPL")
        raise error
    led = machine.Pin(LED_PIN, machine.Pin.OUT)
    for i in range(CRASH_MS // BLINK_MS):
        led.value(CRASH_BLINKS[i % len(CRASH_BLINKS)])
        time.sleep(BLINK_MS / 1000)
    machine.reset()


try:  # everything that can fail to load: an old furbyshow.py, a missing aioble
    import asyncio
    import binascii
    import gc
    import json
    from collections import deque

    import aioble
    import bluetooth

    import furbyshow
except Exception as e:
    crashed(e)

SERVICE = bluetooth.UUID(furbyshow.GP_SERVICE)
WRITE = bluetooth.UUID(furbyshow.GP_WRITE)
LISTEN = bluetooth.UUID(furbyshow.GP_LISTEN)


class AiobleFurby(furbyshow.Furby):
    def __init__(self, device):
        super().__init__(device.addr_hex())
        self.device = device
        self.connection = None
        self.step = "connecting"  # how far connect() got, for its error message
        self.rssi = None  # signal strength in the scan, dBm
        self.heard, self.last_heard = 0, None  # notifications since connecting, for errors

    def connected(self):
        return self.connection is not None and self.connection.is_connected()

    async def _write(self, data):
        await self.tx.write(data, False)

    async def disconnect(self):
        if self.connected():
            await self.connection.disconnect()

    async def connect(self):
        self.step = "connecting"
        self.heard, self.last_heard = 0, None
        self.connection = await self.device.connect(timeout_ms=20000)
        try:
            self.step = "finding its Bluetooth service"
            service = await self.connection.service(SERVICE)
            self.tx = await service.characteristic(WRITE)
            self.rx = await service.characteristic(LISTEN)
            # aioble keeps only the latest notification by default, and sensor
            # reports arrive several times a second, so they'd crowd out the
            # 20:0c / 20:07 / 20:0e replies that play() waits on. Keep them all.
            self.rx._notify_queue = deque((), 32)
            await self.rx.subscribe(notify=True)
            asyncio.create_task(self.listen())
            self.step = "asking which DLC it has"
            asked = furbyshow.ticks_ms()
            await self.identify(attempts=IDENTIFY_ATTEMPTS)
            waited = furbyshow.ticks_diff(furbyshow.ticks_ms(), asked)
            if waited > 5000:  # it missed the first try: say so, to learn how long Furbies take
                say("%s took %d s to say which DLC it has" % (self.name, waited // 1000))
        except Exception:
            await self.disconnect()
            raise

    async def listen(self):
        while self.connected():
            try:
                data = await self.rx.notified(timeout_ms=5000)
                self.heard, self.last_heard = self.heard + 1, data
                self.on_response(data)
            except asyncio.TimeoutError:
                pass
            except Exception:  # disconnected; the show reconnects
                return


async def find(known, scan_ms=5000):
    """Connect to Furbies in range that aren't already connected."""
    devices, rssi = [], {}
    async with aioble.scan(scan_ms, interval_us=30000, window_us=30000, active=True) as scanner:
        async for result in scanner:
            name = result.name() or ""
            if name.startswith("Furby") and result.device.addr_hex() not in known:
                rssi[result.device.addr_hex()] = max(result.rssi, rssi.get(result.device.addr_hex(), -999))
                if result.device not in devices:
                    devices.append(result.device)
    furbies = []
    for device in devices:  # one at a time: aioble cancels scans and pending connects on each connect
        furby = AiobleFurby(device)
        furby.rssi = rssi.get(furby.address)
        try:
            await furby.connect()
        except Exception as e:
            # repr: aioble's errors often have no message. Signal under about -85 dBm is weak.
            # Nothing heard means the connection never worked; heard but no answer, a busy Furby.
            heard = ""
            if furby.step == "asking which DLC it has":
                last = binascii.hexlify(bytes(furby.last_heard)).decode() if furby.last_heard else None
                heard = ", heard %d message%s" % (furby.heard, "" if furby.heard == 1 else "s")
                heard += ", the last %s" % last if last else ""
            say("Couldn't connect to %s (%s dBm) while %s: %r%s" % (furby.address, furby.rssi, furby.step, e, heard))
            continue
        furbies.append(furby)
    return furbies


async def watchdog(show, wdt):
    """Feed the watchdog while the show is making progress."""
    while show.stalled_ms() < STALL_MS:
        wdt.feed()
        await asyncio.sleep(5)
    say("Show stalled; the watchdog will reboot the board")


SOLID = (1,)
OFF = (0,)
FLICKER = (1, 0)


def led_pattern(show):
    """The status LED's levels, one per BLINK_MS, repeated (see the table at the top).

    N blinks then a pause means "power up Furby number N" (in show.json order).
    """
    if show.playing:
        return SOLID
    n = show.waiting_index()
    if n is None:
        return OFF
    if show.stuck():
        return FLICKER
    return (1, 1, 0, 0) * (n + 1) + (0,) * 8


async def status_light(show, led):
    pattern, step = None, 0
    while True:
        now = led_pattern(show)
        if now != pattern:  # start a new pattern from its first blink, so the count reads right
            pattern, step = now, 0
        led.value(pattern[step % len(pattern)])
        step += 1
        await asyncio.sleep(BLINK_MS / 1000)


scenes_played = 0


def log(line):
    """The show's log: say() it, counting scenes for the status line."""
    global scenes_played
    if line.startswith("Scene: "):
        scenes_played += 1
    say(line)


def trace(error):
    """Log where an error came from, as well as the one line the show logs about it."""
    if hasattr(sys, "print_exception"):
        say(exception_text(error))


async def status(show, every_s=STATUS_S):
    """Log a line every so often, so a quiet log reads as alive rather than hung,
    and a slow leak shows up as falling free memory before it crashes the show."""
    while True:
        await asyncio.sleep(every_s)
        gc.collect()
        free = "%d KB free" % (gc.mem_free() // 1024) if hasattr(gc, "mem_free") else "memory unknown"
        here = ", ".join(n for n in show.order if n in show.present()) or "no Furbies"
        say("Status: up %d min, %s connected, %d scenes, %s" % (uptime_s() // 60, here, scenes_played, free))


def reset_reason():
    """Why the board last started. On the ESP32 a hard reset covers a crash, a power dip and the reset button."""
    names = (
        ("PWRON_RESET", "power-on"),
        ("HARD_RESET", "a hard reset (a crash, a power dip or the reset button)"),
        ("WDT_RESET", "the watchdog (the show hung)"),
        ("DEEPSLEEP_RESET", "waking from deep sleep"),
        ("SOFT_RESET", "a soft reset (e.g. deploy.sh)"),
    )
    cause = machine.reset_cause()
    for attr, name in names:
        if cause == getattr(machine, attr, None):
            return name
    return "reset cause %s" % cause


async def main(plan_path="show.json"):
    with open(plan_path) as f:
        text = f.read()
    plan = json.loads(text)
    # MicroPython's dicts forget show.json's order, which says who to power up first
    order = furbyshow.plan_order(text, plan["furbies"])
    del text
    show = furbyshow.Show(plan, find, log=log, wake=asyncio.ThreadSafeFlag(), order=order, trace=trace)
    button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
    # ThreadSafeFlag is safe to set from an interrupt and wakes the show at once.
    button.irq(lambda _: show.trigger(), machine.Pin.IRQ_FALLING)
    if PIR_PIN is not None:
        pir = machine.Pin(PIR_PIN, machine.Pin.IN, machine.Pin.PULL_DOWN)  # a loose wire reads as no motion
        pir.irq(lambda _: show.trigger(sensor=True), machine.Pin.IRQ_RISING)
    asyncio.create_task(watchdog(show, machine.WDT(timeout=WATCHDOG_MS)))
    asyncio.create_task(status_light(show, machine.Pin(LED_PIN, machine.Pin.OUT)))
    asyncio.create_task(status(show))
    await show.run()


def safe_boot():
    """True if the button is held at power-up: skip the show and stay at the REPL."""
    return machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP).value() == 0


if __name__ == "__main__":
    if safe_boot():
        say("Button held: safe boot, show not started")
    else:
        say("Starting the show after %s" % reset_reason())
        try:
            asyncio.run(main())
        except Exception as e:
            crashed(e)
