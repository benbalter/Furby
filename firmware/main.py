# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Run the Halloween show from an ESP32 (MicroPython), with no computer.

The same show engine as porch.py (furbyshow.py), over aioble, MicroPython's
Bluetooth library. On power-up it finds both Furbies, tells them apart by
their active DLC, keeps them awake and plays a scene every so often. The
board's button, or a motion sensor if you wire one (PIR_PIN below), plays a
greeting right away, and its LED lights during scenes
(blinking while it waits for a Furby). Wi-Fi stays off.

Safe boot: hold the button while plugging the board in to skip the show and
stay at the REPL, e.g. to copy new files. Otherwise a watchdog reboots the
board if the show ever hangs, which also means you have about two minutes
after interrupting the show before it reboots.

Copy everything to the board with firmware/deploy.sh.
"""

import asyncio
import json

import aioble
import bluetooth
import machine

import furbyshow

BUTTON_PIN = 47  # the FireBeetle 2 ESP32-S3's onboard button
LED_PIN = 21  # and its onboard LED
# A PIR motion sensor (e.g. an HC-SR501) plays a greeting when someone walks
# up. Wire its output to a free GPIO and put the pin number here; None leaves
# it off. The sensor drives the pin high on motion, so it needs no pull-up.
PIR_PIN = None
WATCHDOG_MS = 120_000  # reboot if not fed for this long
STALL_MS = 300_000  # stop feeding the watchdog if the show makes no progress for this long
SERVICE = bluetooth.UUID(furbyshow.GP_SERVICE)
WRITE = bluetooth.UUID(furbyshow.GP_WRITE)
LISTEN = bluetooth.UUID(furbyshow.GP_LISTEN)


class AiobleFurby(furbyshow.Furby):
    def __init__(self, device):
        super().__init__(device.addr_hex())
        self.device = device
        self.connection = None

    def connected(self):
        return self.connection is not None and self.connection.is_connected()

    async def _write(self, data):
        await self.tx.write(data, False)

    async def disconnect(self):
        if self.connected():
            await self.connection.disconnect()

    async def connect(self):
        self.connection = await self.device.connect(timeout_ms=20000)
        try:
            service = await self.connection.service(SERVICE)
            self.tx = await service.characteristic(WRITE)
            self.rx = await service.characteristic(LISTEN)
            await self.rx.subscribe(notify=True)
            asyncio.create_task(self.listen())
            await self.identify()
        except Exception:
            await self.disconnect()
            raise

    async def listen(self):
        while self.connected():
            try:
                self.on_response(await self.rx.notified(timeout_ms=5000))
            except asyncio.TimeoutError:
                pass
            except Exception:  # disconnected; the show reconnects
                return


async def find(known, scan_ms=5000):
    """Connect to Furbies in range that aren't already connected."""
    devices = []
    async with aioble.scan(scan_ms, interval_us=30000, window_us=30000, active=True) as scanner:
        async for result in scanner:
            name = result.name() or ""
            if name.startswith("Furby") and result.device.addr_hex() not in known and result.device not in devices:
                devices.append(result.device)
    furbies = []
    for device in devices:  # one at a time: aioble cancels scans and pending connects on each connect
        furby = AiobleFurby(device)
        try:
            await furby.connect()
        except Exception as e:
            print("Couldn't connect to %s: %s" % (furby.address, e))
            continue
        furbies.append(furby)
    return furbies


async def watchdog(show, wdt):
    """Feed the watchdog while the show is making progress."""
    while show.stalled_ms() < STALL_MS:
        wdt.feed()
        await asyncio.sleep(5)
    print("Show stalled; the watchdog will reboot the board")


async def status_light(show, led):
    """Solid during a scene, blinking while a Furby is missing, off otherwise."""
    blink = 0
    while True:
        blink ^= 1
        missing = show.present() != set(show.plan["furbies"])
        led.value(1 if show.playing else blink if missing else 0)
        await asyncio.sleep(0.5)


async def main(plan_path="show.json"):
    with open(plan_path) as f:
        show = furbyshow.Show(json.load(f), find, wake=asyncio.ThreadSafeFlag())
    button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
    # ThreadSafeFlag is safe to set from an interrupt and wakes the show at once.
    button.irq(lambda _: show.trigger(), machine.Pin.IRQ_FALLING)
    if PIR_PIN is not None:
        pir = machine.Pin(PIR_PIN, machine.Pin.IN)
        pir.irq(lambda _: show.trigger(sensor=True), machine.Pin.IRQ_RISING)
    asyncio.create_task(watchdog(show, machine.WDT(timeout=WATCHDOG_MS)))
    asyncio.create_task(status_light(show, machine.Pin(LED_PIN, machine.Pin.OUT)))
    await show.run()


def safe_boot():
    """True if the button is held at power-up: skip the show and stay at the REPL."""
    return machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP).value() == 0


if __name__ == "__main__":
    if safe_boot():
        print("Button held: safe boot, show not started")
    else:
        asyncio.run(main())
