# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
A phone remote for the show, over Bluetooth: status, the log, errors, and buttons.

main.py loads this only when REMOTE is True. The board then also advertises as
"Furby Show" with the Nordic UART Service (NUS), the common "serial over
Bluetooth" service, so the iOS app in ios/ or any NUS app (nRF Connect,
Bluefruit Connect) can connect. One phone at a time; the Furbies' own links
come first, and anything that goes wrong here is logged and retried, never
raised into the show.

Protocol: newline-terminated UTF-8 JSON, split into notifications that fit the
connection (the app joins them back up at each newline). The phone negotiates
the size; the board doesn't set one, since that setting would apply to the
Furbies' links too.

Board → phone (TX, notify):
    {"t": "hello", "plan": {"order": [...], "scenes": [[...]], "greetings": [[...]],
                            "clips": {"pink": [...], ...}}}       once, on connect
    {"t": "errors", "lines": [...]}                                once, on connect
    {"t": "log", "line": "[  123] ...", "error": false}            backlog, then live
    {"t": "status", "up": s, "order": [...], "on": [...], "waiting": "blue" or null,
     "stuck": false, "playing": false, "scenes": n, "free_kb": n, "reset": "..."}
                                                                   on change, and every STATUS_EVERY_S
    {"t": "ack", "cmd": "...", "ok": true, "error": null}          after each command

Phone → board (RX, write):
    greet              play a greeting now, as the button does
    scene <n>          play plan["scenes"][n] next
    clip <furby.clip>  play one clip next, e.g. "clip pink.cackle"
    status             send status now
"""

import asyncio
import json
from collections import deque

import aioble
import bluetooth

import furbyshow

NAME = "Furby Show"
NUS = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
NUS_RX = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # the phone writes commands here
NUS_TX = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # the board notifies messages here
ADV_INTERVAL_US = 500_000  # slow advertising leaves the radio to the Furbies
STATUS_EVERY_S = 5
BACKLOG = 50  # log lines kept for a phone that connects later
ERRORS = 10
ERROR_WORDS = ("Couldn't", "couldn't", "error", "dropped", "skipped", "interrupted", "stalled", "Can't")
CHUNK_PAUSE_S = 0.01  # between notifications, so a long message doesn't overrun the stack's queue
SEND_TRIES = 5

backlog = deque((), BACKLOG)
errors = deque((), ERRORS)
outbox = deque((), 100)  # log lines waiting to go to the connected phone
link = None  # the connected phone, or None
wake = asyncio.Event()  # set when outbox has something
tx = rx = None
say = print  # main.py passes its say() to register()


def is_error(line):
    return any(word in line for word in ERROR_WORDS)


def feed(line):
    """Every line the board logs: keep it for later phones, and send it to this one."""
    backlog.append(line)
    if is_error(line):
        errors.append(line)
    if link is not None:
        outbox.append(line)
        wake.set()


def register(log=print):
    """Set up the service. Call before any Furby connects: services can't change after."""
    global tx, rx, say
    say = log
    service = aioble.Service(NUS)
    tx = aioble.Characteristic(service, NUS_TX, read=True, notify=True)
    rx = aioble.BufferedCharacteristic(service, NUS_RX, write=True, write_no_response=True, max_len=128, capture=True)
    aioble.register_services(service)


async def send(connection, message):
    """Send one message as newline-terminated JSON, in pieces that fit the connection.

    A full Bluetooth queue raises OSError: wait and retry, and drop the message
    rather than end the phone's session over it.
    """
    data = (json.dumps(message) + "\n").encode()
    size = max(20, (connection.mtu or 23) - 3)
    for i in range(0, len(data), size):
        for attempt in range(SEND_TRIES):
            try:
                tx.notify(connection, data[i : i + size])
                break
            except OSError:
                if attempt == SEND_TRIES - 1 or not connection.is_connected():
                    return
                await asyncio.sleep(0.1)
        await asyncio.sleep(CHUNK_PAUSE_S)


def plan_summary(show):
    plan = show.plan
    return {
        "order": show.order,
        "scenes": plan["scenes"],
        "greetings": plan.get("greetings", []),
        "clips": {name: sorted(furby.get("clips", {})) for name, furby in plan["furbies"].items()},
    }


def command(show, text):
    """Do what the phone asked; returns an error message, or None if it worked."""
    verb, _, arg = text.strip().partition(" ")
    try:
        if verb == "greet":
            show.trigger()
        elif verb == "scene":
            show.request(show.plan["scenes"][int(arg)])
        elif verb == "clip":
            show.request([arg.strip()])
        elif verb != "status":
            return "Unknown command %r" % verb
    except (ValueError, IndexError) as e:
        return str(e) or "No such scene"
    return None


async def read_commands(show, connection, push_status):
    while connection.is_connected():
        _, data = await rx.written()
        text = bytes(data).decode().strip()
        error = command(show, text)
        say("Phone: %s%s" % (text, " (%s)" % error if error else ""))
        await send(connection, {"t": "ack", "cmd": text, "ok": error is None, "error": error})
        push_status.set()  # e.g. "status", or the scene starting


async def send_log(connection):
    while connection.is_connected():
        await wake.wait()
        wake.clear()
        while outbox:
            line = outbox.popleft()
            await send(connection, {"t": "log", "line": line, "error": is_error(line)})


async def send_status(connection, status, push_status):
    last, sent = None, None
    while connection.is_connected():
        now = status()
        state = (now["on"], now["waiting"], now["stuck"], now["playing"], now["scenes"])
        due = sent is None or furbyshow.ticks_diff(furbyshow.ticks_ms(), sent) >= STATUS_EVERY_S * 1000
        if state != last or push_status.is_set() or due:
            push_status.clear()
            last, sent = state, furbyshow.ticks_ms()
            now["t"] = "status"
            await send(connection, now)
        try:  # wake at once for a command, else look for changes twice a second
            await asyncio.wait_for(push_status.wait(), 0.5)
        except asyncio.TimeoutError:
            pass


async def serve(show, connection, status):
    """Everything for one connected phone, until it goes away."""
    global link
    await send(connection, {"t": "hello", "plan": plan_summary(show)})
    await send(connection, {"t": "errors", "lines": list(errors)})
    for line in list(backlog):
        await send(connection, {"t": "log", "line": line, "error": is_error(line)})
    while outbox:  # MicroPython's deque has no clear()
        outbox.popleft()
    link = connection
    push_status = asyncio.Event()
    tasks = [
        asyncio.create_task(read_commands(show, connection, push_status)),
        asyncio.create_task(send_log(connection)),
        asyncio.create_task(send_status(connection, status, push_status)),
    ]
    try:
        await connection.disconnected(timeout_ms=None)
    finally:
        link = None
        for task in tasks:
            task.cancel()


async def run(show, status):
    """Advertise, serve a phone, and advertise again once it's gone. Never raises."""
    while True:
        try:
            connection = await aioble.advertise(ADV_INTERVAL_US, name=NAME, services=[NUS])
        except Exception as e:  # e.g. the stack is busy; try again shortly
            say("Phone remote couldn't advertise: %r" % e)
            await asyncio.sleep(5)
            continue
        say("Phone connected")
        try:
            await serve(show, connection, status)
        except Exception as e:
            say("Phone link error: %r" % e)
        say("Phone disconnected")
