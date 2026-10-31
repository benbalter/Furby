# SPDX-FileCopyrightText: 2021 Phil Burgess for Adafruit Industries
# SPDX-FileCopyrightText: 2026 Ben Balter
#
# SPDX-License-Identifier: MIT

"""
SOUND-REACTIVE DEMON EYES for Adafruit EyeLights (LED Glasses + Driver).

Adafruit's Blinky Eyes (EyeLights_Blinky_Eyes in Adafruit_Learning_System_Guides)
in pink Furby's demon and storm colours, and:
- a glowing iris with a dark slit pupil that widens as it gets louder, and
  rings with a heartbeat that swell (slowly, so they never flicker) with sound;
- double-tap the frame: a red flash, darkness, then the eyes snap back wide;
- the button steps through demon, storm (lightning), friendly (for little
  kids: orange, round pupils, winks, no scares) and walk (dim, no scares);
- quiet for a while and the lids droop; a loud sound startles them open;
- now and then the eyes roll up ("possessed"), and a loud sound makes them
  glance straight ahead, at whoever said "trick or treat";
- the eyes drift toward where you tilt your head.

Copy to the glasses' CIRCUITPY drive as code.py; see README.md.
"""

import math
import random
import time

# CONFIGURABLES ------------------------

DEMON = (255, 0, 0)  # halloween.THEME_LIGHTS["demon"], pink Furby's eyes; test_eyelights checks they match
STORM = (60, 80, 255)  # halloween.THEME_LIGHTS["storm"]
THEMES = ("demon", "storm", "friendly", "walk")  # the button steps through these
IRIS = {"demon": DEMON, "storm": STORM, "friendly": (255, 110, 0), "walk": (60, 40, 20)}
SPOOKY = ("demon", "storm")  # themes that scare (tap, possessed)
WALK_RING = (40, 30, 20)  # dim warm white: enough to be seen, not enough to wreck your night vision
WALK_MATRIX = 0.15  # walk mode's matrix brightness

CURRENT = 10  # glasses.global_current, 0-255 (Blinky used 20); lower lasts longer on a battery
I2C_HZ = 400_000  # the LIS3DH tops out at 400 kHz

# Sizes in "3X space", three times the LED grid (18x15 per eye), as in Blinky
IRIS_R = (8.0, 6.5)  # iris half-width, half-height: fills the 6x5 LEDs of an eye
SLIT = (1.5, 4.5)  # dark slit's half-width, quiet to loud
ROUND = 3.5  # friendly's round pupil, radius
GAZE = 3.0  # how far the iris wanders from centre
TILT_GAIN = 0.4  # 3X pixels of gaze per m/s2 of sideways tilt; make it negative if the eyes look the wrong way
DROOP = 0.5  # how far the lids close while dozing, 0-1

# Rings: brightness 0-1 is a heartbeat plus the sound. They follow sound with a
# 180 ms attack and 600 ms release, slower than syllables, so speech makes them
# swell instead of flickering (flicker at 3-30 Hz can trigger seizures).
RING_ATTACK, RING_RELEASE = 0.18, 0.6
PUPIL_ATTACK, PUPIL_RELEASE = 0.05, 0.4  # a size change, not a flash, so it can be quicker
RING_SOUND = 0.5  # how much loud sound adds to the heartbeat
HEART = (0.2, 0.5)  # ring brightness between beats, at the top of a beat
BPM = (60, 90, 45)  # quiet, loud, dozing; 90 bpm is 3 bumps a second, the most we allow

MIC_SAMPLES = 128  # 8 ms at 16 kHz
# Quietest sound span (RMS of 16-bit samples) that counts as loud. Unverified: raise it if silence reads as noise
MIN_RANGE = 300
WAKE_LEVEL = 0.35  # level 0-1 that counts as hearing something
GLANCE_LEVEL = 0.6
STARTLE_LEVEL, STARTLE_RATIO = 0.8, 2.5  # and this many times the room's quiet level
DOZE_S = 15  # this long without a sound over WAKE_LEVEL and the eyes doze
STARTLE_S, STARTLE_COOLDOWN_S = 0.8, 10
GLANCE_S, GLANCE_COOLDOWN_S = 1.0, 4
POSSESS_S, POSSESS_EVERY = 1.5, (60, 120)
SCARE_FLASH_S, SCARE_DARK_S, SCARE_SETTLE_S = 0.12, 1.2, 2.0
SCARE_LOCKOUT_S = 5  # one scare per 5 s, so taps can't make a strobe
TAP_THRESHOLD = 100  # LIS3DH double-tap threshold (the Tap example's single-tap value); raise if bumps set it off

LIGHTNING = (150, 180, 255)  # blue-white, not white
STRIKE_S, STRIKE_GAP_S = 0.1, 0.08  # about 12 fps on the glasses, so a strike spans at least a frame
BURST_EVERY = (6, 15)  # seconds between bursts of 1-3 strikes: under 3 flashes a second
WINK_CHANCE = 0.25  # friendly: share of blinks that are one-eyed winks

GAMMA = 2.6
DEBUG = False  # print frames per second every 5 s


# PURE LOGIC (no hardware, so test_eyelights can drive it) ---


def gammify(color, scale=1.0):
    """(R, G, B) to a gamma-corrected, packed 24-bit RGB integer."""
    r, g, b = (int(((min(c * scale, 255) / 255) ** GAMMA) * 255 + 0.5) for c in color)
    return (r << 16) | (g << 8) | b


def interp(color1, color2, blend):
    """Blinky's: color1 at blend 1.0, color2 at 0.0, packed and gamma-corrected."""
    inv = 1.0 - blend
    return gammify([color1[x] * blend + color2[x] * inv for x in range(3)])


def smooth(prev, target, dt, attack, release):
    """Move prev toward target with time constant attack (rising) or release (falling)."""
    tau = attack if target > prev else release
    return prev + (target - prev) * (1 - math.exp(-dt / tau))


def loudness(samples):
    """RMS of the samples about their mean (PDM samples sit around 32768)."""
    n = len(samples)
    mean = sum(samples) / n
    return (sum((s - mean) * (s - mean) for s in samples) / n) ** 0.5


class Level:
    """Raw loudness to 0 (this room's quiet) through 1 (loud), following the room like
    the Audio Spectrum example's dynamic_level. ratio is loudness over the quiet level."""

    def __init__(self):
        self.floor = self.peak = None
        self.ratio = 1.0

    def update(self, rms):
        if self.floor is None:
            self.floor, self.peak = rms, rms + MIN_RANGE
        # The floor drops at once and creeps up; the peak jumps up and sinks back
        self.floor = rms if rms < self.floor else self.floor + (rms - self.floor) * 0.002
        self.peak = rms if rms > self.peak else self.peak + (rms - self.peak) * 0.01
        self.ratio = rms / max(self.floor, 1)
        span = max(self.peak - self.floor, MIN_RANGE)
        return min(max((rms - self.floor) / span, 0.0), 1.0)


class Mood:
    """What the eyes are up to: awake, dozing, startled, glance, possessed or scared."""

    def __init__(self, now):
        self.state, self.since, self.heard = "awake", now, now
        self.last_scare = self.last_startle = self.last_glance = -1e9
        self.next_possess = now + random.uniform(*POSSESS_EVERY)

    def go(self, state, now):
        self.state, self.since = state, now
        if state == "awake":
            self.heard = now

    def update(self, now, level, ratio=1.0, tapped=False, theme="demon"):
        """Advance one frame: sound level 0-1, its ratio to the room's quiet, a double tap."""
        spooky, walking = theme in SPOOKY, theme == "walk"
        if level >= WAKE_LEVEL:
            self.heard = now
        state, t = self.state, now - self.since
        if tapped and spooky and now - self.last_scare >= SCARE_LOCKOUT_S:
            self.last_scare = now
            self.go("scared", now)
        elif state == "scared":
            if t >= SCARE_FLASH_S + SCARE_DARK_S + SCARE_SETTLE_S:
                self.go("awake", now)
        elif state in ("startled", "glance", "possessed"):
            if t >= {"startled": STARTLE_S, "glance": GLANCE_S, "possessed": POSSESS_S}[state]:
                self.go("awake", now)
        elif state == "dozing":
            if walking:
                self.go("awake", now)
            elif level >= STARTLE_LEVEL and ratio >= STARTLE_RATIO and now - self.last_startle >= STARTLE_COOLDOWN_S:
                self.last_startle = now
                self.go("startled", now)
            elif level >= WAKE_LEVEL:
                self.go("awake", now)
        elif not walking and now - self.heard >= DOZE_S:
            self.go("dozing", now)
        elif level >= GLANCE_LEVEL and now - self.last_glance >= GLANCE_COOLDOWN_S:
            self.last_glance = now
            self.go("glance", now)
        elif spooky and now >= self.next_possess:
            self.next_possess = now + random.uniform(*POSSESS_EVERY)
            self.go("possessed", now)
        if not spooky and self.state == "possessed":
            self.go("awake", now)
        return self.state

    def phase(self, now):
        """The state, with "scared" split into "flash", "dark" and "wide"."""
        if self.state != "scared":
            return self.state
        t = now - self.since
        return "flash" if t < SCARE_FLASH_S else "dark" if t < SCARE_FLASH_S + SCARE_DARK_S else "wide"

    def droop(self, now):
        """How far the lids rest closed, 0-1: easing shut over 2 s of dozing."""
        return DROOP * min((now - self.since) / 2, 1.0) if self.state == "dozing" else 0.0


class Heart:
    """Lub-dub: two bumps a beat, 0-1."""

    def __init__(self):
        self.beat = 0.0  # beats so far; the fraction is where we are in this one

    def step(self, dt, bpm):
        self.beat += dt * bpm / 60
        s = (self.beat % 1) * 60 / bpm  # seconds into this beat
        for start, height in ((0.0, 1.0), (0.32, 0.7)):
            if start <= s < start + 0.12:
                return height * math.sin(math.pi * (s - start) / 0.12)
        return 0.0


class Lightning:
    """Storm theme: bursts of 1-3 short strikes, BURST_EVERY seconds apart."""

    def __init__(self, now):
        self.strikes = []
        self.next_burst = now + random.uniform(*BURST_EVERY)

    def lit(self, now):
        if now >= self.next_burst:
            gap = STRIKE_S + STRIKE_GAP_S
            self.strikes = [now + i * gap for i in range(random.randint(1, 3))]
            self.next_burst = now + random.uniform(*BURST_EVERY)
        return any(start <= now < start + STRIKE_S for start in self.strikes)


def fire(b):
    """Blinky Fire's colour scale for brightness 0-1: black, red, then up to yellow."""
    n = b * 2
    return (min(n, 1) * 255, max(n - 1, 0) * 255, 0)


def ring_color(theme, b, lightning=False):
    if theme == "walk":
        return WALK_RING
    if theme == "storm" and lightning:
        return LIGHTNING
    if theme == "demon":
        return fire(b)
    return [c * b for c in IRIS[theme]]


def ellipse(bitmap, cx, cy, rx, ry, value, top=0, bottom=15):
    """Fill an axis-aligned ellipse into an 18x15 3X bitmap, rows top to bottom-1 only."""
    if rx <= 0 or ry <= 0:
        return
    for y in range(max(int(cy - ry), top, 0), min(int(cy + ry) + 1, bottom, 15)):
        dy = (y + 0.5 - cy) / ry
        if dy * dy >= 1:
            continue
        half = rx * (1 - dy * dy) ** 0.5
        row = bitmap[y]
        for x in range(max(int(cx - half + 0.5), 0), min(int(cx + half + 0.5), 18)):
            row[x] = value


# 2/3 of pixels set: Blinky's eyelid edge, stuffed into the 3X bitmap
EYELID = b"\x01\x01\x00" * 6
CENTRE = (9, 7.5)
_colormaps = {}


def colormap(color, scale=1.0):
    """The 10 colours a 3x3 block of the 3X bitmap averages to (0-9 pixels set)."""
    key = (tuple(color), scale)
    if key not in _colormaps:
        _colormaps[key] = [gammify([n / 9 * c for c in color], scale) for n in range(10)]
    return _colormaps[key]


def draw_eye(glasses, left, x_offset, gaze, upper, lower, pupil, theme):
    """One eye's 6x5 LEDs: lit iris, dark pupil, lids at upper/lower (3X rows)."""
    bitmap = [bytearray(18) for _ in range(15)]
    top, bottom = max(int(upper), 0), int(lower) + 1
    cx, cy = gaze[0] + x_offset, gaze[1]
    ellipse(bitmap, cx, cy, IRIS_R[0], IRIS_R[1], 1, top, bottom)
    if theme == "friendly":
        ellipse(bitmap, cx, cy, ROUND, ROUND, 0, top, bottom)
    elif theme != "walk":
        ellipse(bitmap, cx, cy, pupil, IRIS_R[1] + 3, 0, top, bottom)
    if 0 <= upper < 15:
        bitmap[int(upper)] = EYELID
    colors = colormap(IRIS[theme], WALK_MATRIX if theme == "walk" else 1.0)
    for y in range(5):
        r0, r1, r2 = bitmap[y * 3], bitmap[y * 3 + 1], bitmap[y * 3 + 2]
        for x in range(6):
            x3 = x * 3  # indexing, not slices, so no garbage per pixel
            n = r0[x3] + r0[x3 + 1] + r0[x3 + 2] + r1[x3] + r1[x3 + 1] + r1[x3 + 2] + r2[x3] + r2[x3 + 1] + r2[x3 + 2]
            glasses.pixel(left + x, y, colors[n])


# Y position (3X space) of half a ring's LEDs, top to bottom, to line ring lids up with the matrix
RING_Y = [10 - math.cos(n / 24 * math.pi * 2) * 12 for n in range(13)]


def draw_ring(ring, upper, lower, open_color, lid_color):
    if upper <= -4:
        ring.fill(gammify(open_color))
        return
    for i in range(13):
        a = min(max(RING_Y[i] - upper + 1, 0), 3)
        b = min(max(lower - RING_Y[i] + 1, 0), 3)
        ring[i] = packed = interp(open_color, lid_color, a * b / 9)
        if 0 < i < 12:
            ring[24 - i] = packed


def fill_all(glasses, packed):
    for y in range(5):
        for x in range(18):
            glasses.pixel(x, y, packed)
    glasses.left_ring.fill(packed)
    glasses.right_ring.fill(packed)


class Blink:
    """Blinky's blink timing, per eye so friendly can wink."""

    def __init__(self):
        self.state, self.start, self.duration, self.eyes = 0, 0, 0, (True, True)

    def lids(self, now, slow=False, wink=False):
        """(upper, lower) eyelid rows in 3X space for each eye, fully open being (-4, 23)."""
        elapsed = now - self.start
        if elapsed > self.duration:
            self.start, elapsed = now, 0
            self.state += 1
            if self.state == 1:
                self.duration = random.uniform(0.06, 0.12)
                one = wink and random.random() < WINK_CHANCE
                side = random.random() < 0.5
                self.eyes = (side, not side) if one else (True, True)
            elif self.state == 2:
                self.duration *= 2  # opens at half the speed
            else:
                self.state = 0
                self.duration = random.uniform(0.5, 4) * (3 if slow else 1)
        if not self.state:
            return [(-4, 23), (-4, 23)]
        ratio = elapsed / self.duration
        if self.state == 2:
            ratio = 1.0 - ratio
        shut = (ratio * 15 - 4, 23 - ratio * 8)
        return [shut if blinking else (-4, 23) for blinking in self.eyes]


class Gaze:
    """Blinky's eye movement: pause, then a quick eased move to a random spot."""

    def __init__(self):
        self.cur = self.next = CENTRE
        self.moving, self.start, self.duration = False, 0, 0

    def at(self, now, tilt=0.0):
        elapsed = now - self.start
        if self.moving:
            if elapsed > self.duration:
                self.moving, self.cur = False, self.next
                self.duration = random.uniform(0.5, 1.5)
                return self.cur
            e = elapsed / self.duration
            e = 3 * e * e - 2 * e * e * e
            return (self.cur[0] + (self.next[0] - self.cur[0]) * e, self.cur[1] + (self.next[1] - self.cur[1]) * e)
        if elapsed > self.duration:
            self.moving, self.start = True, now
            self.duration = random.uniform(0.15, 0.25)
            angle, dist = random.uniform(0, math.pi * 2), random.uniform(0, GAZE)
            x = min(max(CENTRE[0] + math.cos(angle) * dist + tilt * TILT_GAIN, CENTRE[0] - GAZE), CENTRE[0] + GAZE)
            self.next = (x, CENTRE[1] + math.sin(angle) * dist * 0.6)
        return self.cur


# HARDWARE -----------------------------


def setup():
    """The glasses, plus whatever of the mic, accelerometer and button started (None if not)."""
    import adafruit_is31fl3741
    import board
    import digitalio
    from adafruit_is31fl3741.adafruit_ledglasses import LED_Glasses
    from busio import I2C

    i2c = I2C(board.SCL, board.SDA, frequency=I2C_HZ)
    lis = mic = button = None
    try:  # before the glasses, as Adafruit's Tap example does
        import adafruit_lis3dh

        lis = adafruit_lis3dh.LIS3DH_I2C(i2c, int1=digitalio.DigitalInOut(board.ACCELEROMETER_INTERRUPT))
        lis.set_tap(2, TAP_THRESHOLD)
    except Exception as e:  # keep the eyes running without it
        print("No accelerometer, so no scares or tilt:", e)
    glasses = LED_Glasses(i2c, allocate=adafruit_is31fl3741.MUST_BUFFER)
    glasses.show()
    glasses.global_current = CURRENT
    try:
        from audiobusio import PDMIn

        mic = PDMIn(board.MICROPHONE_CLOCK, board.MICROPHONE_DATA, sample_rate=16000, bit_depth=16)
    except Exception as e:
        print("No microphone, so the eyes won't hear:", e)
    try:
        button = digitalio.DigitalInOut(board.SWITCH)
        button.switch_to_input(pull=digitalio.Pull.UP)
    except Exception as e:
        print("No button, so the theme stays demon:", e)
    return glasses, mic, lis, button


def boot_sweep(glasses, ok, sleep):
    """Light the rings round one LED at a time: red if everything started, amber if not."""
    packed = gammify(DEMON if ok else (255, 100, 0))
    for i in range(24):
        glasses.left_ring[i] = glasses.right_ring[i] = packed
        glasses.show()
        sleep(0.02)
    fill_all(glasses, 0)
    glasses.show()


def main(frames=None, clock=None, sleep=time.sleep):
    from array import array

    from supervisor import reload

    clock = clock or time.monotonic
    glasses, mic, lis, button = setup()
    boot_sweep(glasses, mic is not None and lis is not None, sleep)
    buf = array("H", [0] * MIC_SAMPLES)
    now = clock()
    level_of, mood, heart, lightning = Level(), Mood(now), Heart(), Lightning(now)
    blink, gaze = Blink(), Gaze()
    theme, pressed, last_press = 0, False, 0
    ring, pupil, tilt, last_phase = HEART[0], SLIT[0], 0.0, None
    count, fps_frames, fps_start = 0, 0, now

    while frames is None or count < frames:
        try:
            last, now = now, clock()
            dt = max(now - last, 0.001)
            name = THEMES[theme]

            level = 0.0
            if mic is not None:
                mic.record(buf, MIC_SAMPLES)
                level = level_of.update(loudness(buf))
            tapped = False
            if lis is not None:
                tapped = lis.tapped
                tilt = tilt * 0.85 + lis.acceleration[0] * 0.15
            if button is not None:
                down = not button.value
                if down and not pressed and now - last_press > 0.3:
                    theme, last_press = (theme + 1) % len(THEMES), now
                    name = THEMES[theme]
                    print("Theme:", name)
                pressed = down

            state = mood.update(now, level, level_of.ratio, tapped, name)
            phase = mood.phase(now)
            if phase == "flash":
                fill_all(glasses, gammify(DEMON))
            elif phase == "dark":
                fill_all(glasses, 0)
            else:
                if phase != last_phase and phase in ("wide", "startled"):
                    ring = 1.0  # snap back, then settle
                pupil = smooth(pupil, SLIT[0] + (SLIT[1] - SLIT[0]) * level, dt, PUPIL_ATTACK, PUPIL_RELEASE)
                bpm = BPM[2] if state == "dozing" else BPM[0] + (BPM[1] - BPM[0]) * level
                beat = HEART[0] + (HEART[1] - HEART[0]) * heart.step(dt, bpm)
                target = 1.0 if state == "possessed" else min(beat + RING_SOUND * level, 1.0)
                ring = smooth(ring, target, dt, RING_ATTACK, RING_RELEASE)

                if state in ("glance", "startled") or phase == "wide":
                    where = CENTRE
                elif state == "possessed":
                    where = (CENTRE[0], CENTRE[1] - 14)  # rolled up, out of sight
                else:
                    where = gaze.at(now, tilt)
                lids = blink.lids(now, slow=state == "dozing", wink=name == "friendly")
                rest = -4 + mood.droop(now) * 15
                lids = [(max(upper, rest), lower) for upper, lower in lids]
                # Columns 1 and 11, pupils offset toward each other so they converge (Blinky)
                draw_eye(glasses, 1, 2, where, lids[0][0], lids[0][1], pupil, name)
                draw_eye(glasses, 11, -2, where, lids[1][0], lids[1][1], pupil, name)
                open_color = ring_color(name, ring, name == "storm" and lightning.lit(now))
                lid_color = [c * 0.15 for c in IRIS[name]]
                draw_ring(glasses.left_ring, lids[0][0], lids[0][1], open_color, lid_color)
                draw_ring(glasses.right_ring, lids[1][0], lids[1][1], open_color, lid_color)
            last_phase = phase
            glasses.show()
        except OSError:  # Blinky's note: very rarely the I2C bus wedges, and a restart clears it
            print("Restarting")
            reload()

        count += 1
        fps_frames += 1
        if DEBUG and now - fps_start > 5:
            print("fps", fps_frames / (now - fps_start))
            fps_frames, fps_start = 0, now


if __name__ == "__main__":
    main()
