<!--
SPDX-FileCopyrightText: 2026 Ben Balter
SPDX-License-Identifier: MIT
-->

# Blog shot list: Halloween night

Footage only a person on the porch can shoot. Everything else (eyes, diagrams, pacing chart, terminal output) comes from `uv run tools/blog_media.py --out <dir>`.

## Ground rules for every shot

- **Muted.** Porch footage ships with the sound off and the lines as captions, because the Furbies' voices are cloned from Hasbro's audio. Record with sound if it's easier, but expect it to be stripped.
- **No faces.** Kids from behind, below the shoulders, or just hands and candy buckets. Same for neighbors and other adults.
- **Nothing that locates the house:** no house number, street sign, mailbox, car plates, or neighbors' houses in frame.
- **No screens with private details.** If a laptop or phone is in frame, close the terminal and notifications first; the iPhone remote's log is fine.
- Shoot landscape at 1080p, 30 fps. Hold each shot a few seconds longer than listed, so there's room to trim to a loop.
- Note which scene played (or read it off the iPhone remote's log afterwards), so the captions match.

## Shots

| id | duration | framing | what it illustrates |
| --- | --- | --- | --- |
| `porch-wide` | 15–20 s | Wide from the walkway, tripod at kid height: both Furbies, the candy bowl, porch decorations. Dusk if possible, so the eyes and antennas glow. | The setup as trick-or-treaters see it. The opening image. |
| `pink-mid-scene` | 8–12 s | Tight on pink, eye level, while she delivers a line (`pink.scariest` or `pink.dare` are the longest). Fill the frame with the face so the demon eyes read. | Custom eyes on real hardware, and the antenna light following the voice. |
| `blue-mid-scene` | 8–12 s | Same framing on blue during a reply (`blue.hascandy`, `blue.gotcha`). | The pumpkin eyes, and the two-character banter. |
| `both-exchange` | 10–15 s | Two-shot, both Furbies in frame, through one whole scene (call and answer). Locked off. | The scene engine: two Furbies taking turns without stepping on each other. Caption each line with its timestamp. |
| `esp32-hidden` | 5–8 s | Start on where the board hides, then reveal it: the FireBeetle, its external antenna, battery, and the motion sensor's dome. Close-up, good light. | That the show runs from a small board, not a laptop. |
| `pir-trigger` | 8–10 s | Over the shoulder of someone walking up (from behind, no face), with the Furbies in frame as they start a greeting. | The motion sensor starting a greeting on arrival. |
| `iphone-remote` | 8–12 s | The phone in hand, Furbies soft in the background. Tap "Greet" or a scene, then tilt up to the Furbies reacting. | The iPhone remote: status, log, and playing a scene on demand. |
| `eyelights` | 6–10 s | Someone wearing the EyeLights glasses, framed from the nose down or from behind at an angle where the LEDs show and the face doesn't. Tap the frame or make a noise so the demon eyes react. | The sound-reactive glasses, the side project. |
| `kids-reaction` | 10–20 s, several takes | From behind or below: a kid leaning in, pointing, or jumping at `blue.door` → `pink.scream`. Hands in the candy bowl work too. | Why this was worth building. The closing image. |
| `detail-candy` (optional) | 4–6 s | Overhead of the bowl with both Furbies' feet at the edge. | B-roll for transitions. |
| `teardown` (optional) | 5–8 s | End of night: the board's LED, a Furby powered off, the bowl empty. | A closing beat. |

## After the night

- `firmware/getlog.sh` copies the board's log to `build/board-log/`, which has the scene timings and any dropped connections, for the post's numbers.
- Footage stays out of this repo. Put it wherever the blog's media goes.
