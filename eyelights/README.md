# Demon eyes for EyeLights glasses

Sound-reactive demon eyes for [Adafruit EyeLights LED glasses](https://learn.adafruit.com/adafruit-eyelights-led-glasses-and-driver), in pink Furby's colours. They're built on Adafruit's [Blinky Eyes](https://learn.adafruit.com/adafruit-eyelights-led-glasses-and-driver/blinky-eyes).

## What they do

- **Glowing eyes with a dark slit pupil.** The slit widens as it gets louder. The rings around each eye beat like a heart and swell when you talk.
- **Double-tap the frame for a jump scare:** a red flash, a moment of darkness, then the eyes snap back wide. It can happen once every 5 seconds.
- **The button changes the look:**
  1. **demon** (red, the default)
  2. **storm** (blue, with lightning)
  3. **friendly** (orange, round pupils, the odd wink, no scares; for little kids)
  4. **walk** (dim, no scares; for walking around)
- **Leave them in a quiet room** and after 15 seconds the lids droop. A loud "BOO" startles them awake.
- **Now and then** the eyes roll up out of sight (demon and storm only). After a loud sound they look straight ahead.
- **Tilt your head** and the eyes drift that way.

## Put it on the glasses

1. **Install CircuitPython** (one time). Plug the glasses' driver board into your computer by USB-C and double-click its reset button. A drive whose name ends in `BOOT` appears. Download CircuitPython for the [LED Glasses Driver nRF52840](https://circuitpython.org/board/adafruit_led_glasses_nrf52840/) and drag the `.uf2` file onto that drive. It restarts as a drive called `CIRCUITPY`.
2. **Install the libraries** (one time). In this folder, run:

   ```sh
   uvx circup install adafruit_is31fl3741 adafruit_lis3dh
   ```

3. **Copy the code:**

   ```sh
   cp eyelights/code.py /Volumes/CIRCUITPY/code.py
   ```

   Eject `CIRCUITPY` in Finder before unplugging. macOS holds back writes to small drives like this one, and pulling the cable too early can corrupt it ([circuitpython#8449](https://github.com/adafruit/circuitpython/issues/8449)). The glasses restart on their own. The rings light up one LED at a time, then the eyes open. **Red** means everything started. **Amber** means the microphone or the motion sensor didn't, and the eyes run without them.

To see what the glasses print (theme changes, errors), run `ls /dev/tty.usbmodem*` before and after plugging them in. The new name is the glasses (the show's ESP32 board shows up there too). Then run `screen /dev/tty.usbmodemNNNN 115200` with that name, and quit with Ctrl-A, then K. To see the frame rate, set `DEBUG = True` in code.py.

## Tweak them

Every colour, timing, and threshold is in the block at the top of [code.py](code.py). The ones you're most likely to change:

| Setting | What it does |
|---|---|
| `CURRENT` | Overall brightness (10 out of 255). Lower lasts longer on a battery. |
| `TAP_THRESHOLD` | Raise it if bumps set off the scare. Lower it if double taps don't. |
| `MIN_RANGE` | Raise it if the eyes react to a quiet room. |
| `TILT_GAIN` | Make it negative if the eyes drift the wrong way when you tilt your head. |
| `DOZE_S` | Seconds of quiet before the lids droop. |

The demon and storm colours match the Furbies' (`THEME_LIGHTS` in [halloween.py](../halloween.py)). [test_eyelights.py](../test_eyelights.py) checks that they stay in sync.

## Safety

- The rings swell slowly with sound and never flicker with speech. Lightning comes in short, rare bursts. Both are meant to stay under 3 flashes a second, the usual limit for photosensitive viewers. Keep it that way if you change the timings.
- You're looking through the lit LEDs. Use walk mode on steps, and carry a real flashlight.
- Check the battery before you go out. The board charges over USB-C, so a phone power bank in a pocket works as a backup.

Not yet tried on the glasses themselves: the sound thresholds, which way tilt goes, the double-tap sensitivity, and the button. Start with the settings above if something feels off. The glasses run at about 12 frames a second, so lightning strikes last 100 ms to be sure they show.
