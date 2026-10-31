# SPDX-FileCopyrightText: 2026 Ben Balter
#
# SPDX-License-Identifier: MIT

"""Tests for eyelights/code.py, run on CPython against stand-ins for the CircuitPython modules."""

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))


class Ring(list):
    def fill(self, color):
        self[:] = [color] * len(self)


class Glasses:
    width, height = 18, 5

    def __init__(self, i2c, allocate=None):
        self.matrix = {}
        self.left_ring, self.right_ring = Ring([0] * 24), Ring([0] * 24)
        self.global_current = 0
        self.frames = []  # (matrix, left ring, right ring) at each show()

    def pixel(self, x, y, color):
        assert 0 <= x < 18 and 0 <= y < 5, (x, y)
        self.matrix[x, y] = color

    def show(self):
        self.frames.append((dict(self.matrix), list(self.left_ring), list(self.right_ring)))


class Mic:
    def __init__(self, *args, **kwargs):
        self.loud = False

    def record(self, buf, n):
        swing = 8000 if self.loud else 20
        for i in range(n):
            buf[i] = 32768 + (swing if i % 2 else -swing)


class Accel:
    def __init__(self, i2c, int1=None):
        self.taps, self.acceleration = [], (0.0, 0.0, 9.8)

    def set_tap(self, taps, threshold):
        self.tap_config = (taps, threshold)

    @property
    def tapped(self):
        return self.taps.pop(0) if self.taps else False


class Pin:
    def __init__(self, pin):
        self.value = True

    def switch_to_input(self, pull=None):
        pass


def fakes(state):
    """CircuitPython's modules, recording the hardware objects in state."""
    board = types.SimpleNamespace(
        SCL=1, SDA=2, MICROPHONE_CLOCK=3, MICROPHONE_DATA=4, ACCELEROMETER_INTERRUPT=5, SWITCH=6
    )

    def make(cls, key):
        def build(*args, **kwargs):
            state[key] = cls(*args, **kwargs)
            return state[key]

        return build

    is31 = types.ModuleType("adafruit_is31fl3741")
    is31.MUST_BUFFER = 1
    return {
        "board": board,
        "busio": types.SimpleNamespace(I2C=lambda *a, **k: object()),
        "digitalio": types.SimpleNamespace(DigitalInOut=make(Pin, "pin"), Pull=types.SimpleNamespace(UP=1)),
        "audiobusio": types.SimpleNamespace(PDMIn=make(Mic, "mic")),
        "supervisor": types.SimpleNamespace(reload=lambda: None),
        "adafruit_is31fl3741": is31,
        "adafruit_is31fl3741.adafruit_ledglasses": types.SimpleNamespace(LED_Glasses=make(Glasses, "glasses")),
        "adafruit_lis3dh": types.SimpleNamespace(LIS3DH_I2C=make(Accel, "accel")),
    }


class TestEyeLights(unittest.TestCase):
    def setUp(self):
        self.state = {}
        patcher = mock.patch.dict(sys.modules, fakes(self.state))
        patcher.start()
        self.addCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location("eyelights_code", os.path.join(HERE, "eyelights", "code.py"))
        self.eyes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.eyes)

    def run_frames(self, frames, fps=30, before=None):
        """main() for this many frames on a fake clock; before(n) runs ahead of frame n's clock read."""
        clock = {"t": 1000.0, "n": 0}

        def tick():
            if before:
                before(clock["n"])
            clock["n"] += 1
            clock["t"] += 1 / fps
            return clock["t"]

        self.eyes.main(frames=frames, clock=tick, sleep=lambda s: None)
        return self.state["glasses"]

    def test_colours_match_the_furby_show(self):
        import halloween

        self.assertEqual(list(self.eyes.DEMON), halloween.THEME_LIGHTS["demon"]["color"])
        self.assertEqual(list(self.eyes.STORM), halloween.THEME_LIGHTS["storm"]["color"])

    def test_loudness(self):
        self.assertEqual(self.eyes.loudness([5, 5, 5, 5]), 0)
        self.assertEqual(self.eyes.loudness([0, 10, 0, 10]), 5)

    def test_level_follows_the_room(self):
        level = self.eyes.Level()
        for _ in range(50):
            quiet = level.update(20)
        self.assertLess(quiet, 0.05)
        self.assertGreater(level.update(5000), 0.9)
        self.assertGreater(level.ratio, 100)

    def test_rings_swell_instead_of_flickering(self):
        """A 6 Hz loud/quiet square (syllables) barely moves the rings once they settle."""
        smooth, v, seen = self.eyes.smooth, 0.0, []
        for frame in range(300):  # 10 s at 30 fps
            target = 1.0 if (frame // 2.5) % 2 else 0.0
            v = smooth(v, target, 1 / 30, self.eyes.RING_ATTACK, self.eyes.RING_RELEASE)
            seen.append(v)
        self.assertLess(max(seen[-60:]) - min(seen[-60:]), 0.2)

    def test_heartbeat_stays_under_three_bumps_a_second(self):
        self.assertLessEqual(max(self.eyes.BPM) * 2 / 60, 3)

    def test_lightning_bursts_are_short_and_rare(self):
        lightning, starts, was = self.eyes.Lightning(0), [], False
        for frame in range(120 * 100):  # 2 minutes at 100 fps
            now = frame / 100
            lit = lightning.lit(now)
            if lit and not was:
                starts.append(now)
            was = lit
        self.assertTrue(starts)
        for i, start in enumerate(starts):
            in_second = [s for s in starts[i:] if s < start + 1]
            self.assertLessEqual(len(in_second), 3)
        bursts = [b for a, b in zip(starts, starts[1:], strict=False) if b - a > 1]
        for a, b in zip(starts, starts[1:], strict=False):
            self.assertTrue(b - a < 0.5 or b - a >= self.eyes.BURST_EVERY[0] - 0.5, (a, b))
        self.assertTrue(bursts)

    def test_double_tap_scares_once_per_lockout(self):
        mood = self.eyes.Mood(0)
        self.assertEqual(mood.update(1, 0, tapped=True), "scared")
        self.assertEqual(mood.phase(1.05), "flash")
        self.assertEqual(mood.phase(1.5), "dark")
        self.assertEqual(mood.phase(2.5), "wide")
        self.assertEqual(mood.update(5, 0), "awake")
        self.assertEqual(mood.update(5.5, 0, tapped=True), "awake")  # inside the lockout
        self.assertEqual(mood.update(6.5, 0, tapped=True), "scared")

    def test_friendly_and_walk_never_scare(self):
        for theme in ("friendly", "walk"):
            mood = self.eyes.Mood(0)
            mood.next_possess = 1
            self.assertEqual(mood.update(2, 0, tapped=True, theme=theme), "awake")

    def test_dozes_then_startles_with_a_cooldown(self):
        e, mood = self.eyes, self.eyes.Mood(0)
        mood.next_possess = 1e9
        self.assertEqual(mood.update(e.DOZE_S + 1, 0), "dozing")
        self.assertGreater(mood.droop(e.DOZE_S + 4), 0.4)
        self.assertEqual(mood.update(e.DOZE_S + 5, 1.0, ratio=1.5), "awake")  # loud, but not over the room
        mood.go("dozing", 40)
        self.assertEqual(mood.update(41, 1.0, ratio=10), "startled")
        self.assertEqual(mood.update(42, 0), "awake")
        mood.go("dozing", 43)
        self.assertEqual(mood.update(44, 1.0, ratio=10), "awake")  # cooldown: wakes without the flash

    def test_walk_never_dozes(self):
        mood = self.eyes.Mood(0)
        self.assertEqual(mood.update(100, 0, theme="walk"), "awake")

    def test_runs_and_reacts_to_sound(self):
        def before(n):
            if n == 150:
                self.state["mic"].loud = True

        glasses = self.run_frames(300, before=before)
        self.assertEqual(self.state["accel"].tap_config[0], 2)  # double tap
        self.assertEqual(glasses.global_current, self.eyes.CURRENT)

        def ring_sum(frame):
            return sum((c >> 16) + ((c >> 8) & 255) for c in frame[1])

        quiet = max(ring_sum(f) for f in glasses.frames[100:150])
        loud = max(ring_sum(f) for f in glasses.frames[250:300])
        self.assertGreater(loud, quiet)

    def test_button_steps_through_themes(self):
        def before(n):
            if n in (20, 40, 60):
                self.state["pin"].value = False
            elif n in (21, 41, 61):
                self.state["pin"].value = True

        glasses = self.run_frames(80, before=before)
        left_eye = [c for (x, _), c in glasses.frames[-1][0].items() if x < 9]
        # Walk mode: a dim warm iris, no bright red
        self.assertTrue(all((c >> 16) < 40 for c in left_eye), left_eye)

    def test_tap_flashes_red_then_goes_dark(self):
        def before(n):
            if n == 30:
                self.state["accel"].taps.append(True)

        glasses = self.run_frames(60, before=before)
        red = self.eyes.gammify(self.eyes.DEMON)
        flash = [f for f in glasses.frames if set(f[0].values()) == {red}]
        dark = [f for f in glasses.frames if not any(f[0].values()) and not any(f[1])]
        self.assertTrue(flash)
        self.assertTrue(dark)


if __name__ == "__main__":
    unittest.main()
