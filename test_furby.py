#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for Furby Connect DLC tools

This test suite validates the Python 3 migration and core functionality
of the Furby Connect DLC file parser and builder.
"""

import os
import shutil
import tempfile
import unittest

from furby import dlc


class TestDLCLoading(unittest.TestCase):
    """Test DLC file loading functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dlc_path = "./dlc/dlc2/tu003410.dlc"
        if not os.path.exists(self.test_dlc_path):
            self.skipTest("Test DLC file not found")

    def test_import(self):
        """Test that the dlc module can be imported"""
        from furby import dlc
        self.assertIsNotNone(dlc)

    def test_load_dlc(self):
        """Test loading a DLC file"""
        D = dlc(self.test_dlc_path)
        self.assertIsNotNone(D)
        self.assertIsNotNone(D.dlc_header)
        self.assertIsNotNone(D.dlc_sections)

    def test_dlc_sections(self):
        """Test that all expected sections are loaded"""
        D = dlc(self.test_dlc_path)
        expected_sections = ['PAL', 'SPR', 'CEL', 'XLS', 'AMF', 'APL', 'LPS', 'SEQ', 'MTR']
        self.assertEqual(list(D.dlc_sections.keys()), expected_sections)

    def test_section_count(self):
        """Test that the correct number of sections is loaded"""
        D = dlc(self.test_dlc_path)
        self.assertEqual(len(D.dlc_sections), 9)


class TestDLCBuilding(unittest.TestCase):
    """Test DLC file building functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dlc_path = "./dlc/dlc2/tu003410.dlc"
        if not os.path.exists(self.test_dlc_path):
            self.skipTest("Test DLC file not found")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_build_dlc(self):
        """Test building a DLC file"""
        D = dlc(self.test_dlc_path)
        output_path = os.path.join(self.temp_dir, "output.dlc")
        D.build(output_path)
        self.assertTrue(os.path.exists(output_path))

    def test_build_file_size(self):
        """Test that built DLC has correct file size"""
        D = dlc(self.test_dlc_path)
        output_path = os.path.join(self.temp_dir, "output.dlc")
        D.build(output_path)

        original_size = os.path.getsize(self.test_dlc_path)
        output_size = os.path.getsize(output_path)
        self.assertEqual(original_size, output_size)

    def test_roundtrip(self):
        """Test that a built DLC can be loaded again"""
        D1 = dlc(self.test_dlc_path)
        output_path = os.path.join(self.temp_dir, "output.dlc")
        D1.build(output_path)

        # Load the built file
        D2 = dlc(output_path)
        self.assertIsNotNone(D2)
        self.assertEqual(len(D2.dlc_sections), len(D1.dlc_sections))

    def test_roundtrip_sections(self):
        """Test that sections are preserved in roundtrip"""
        D1 = dlc(self.test_dlc_path)
        output_path = os.path.join(self.temp_dir, "output.dlc")
        D1.build(output_path)

        D2 = dlc(output_path)
        self.assertEqual(list(D1.dlc_sections.keys()), list(D2.dlc_sections.keys()))

    def test_roundtrip_identical(self):
        """The stock DLC rebuilds byte for byte (SPR counts its playlists rather than assuming 16)"""
        D = dlc(self.test_dlc_path)
        self.assertEqual(len(D.dlc_sections["SPR"].frame_playlists), 16)
        output_path = os.path.join(self.temp_dir, "output.dlc")
        D.build(output_path)
        with open(self.test_dlc_path, "rb") as f1, open(output_path, "rb") as f2:
            self.assertEqual(f1.read(), f2.read())


class TestPython3Compatibility(unittest.TestCase):
    """Test Python 3 specific compatibility"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dlc_path = "./dlc/dlc2/tu003410.dlc"
        if not os.path.exists(self.test_dlc_path):
            self.skipTest("Test DLC file not found")

    def test_bytes_handling(self):
        """Test that bytes are handled correctly in Python 3"""
        D = dlc(self.test_dlc_path)
        # rawbytes should be bytes type in Python 3
        self.assertIsInstance(D.dlc_header.rawbytes, bytes)

    def test_section_rawbytes(self):
        """Test that section rawbytes are bytes type"""
        D = dlc(self.test_dlc_path)
        for section_name, section in D.dlc_sections.items():
            self.assertIsInstance(section.rawbytes, bytes,
                                f"Section {section_name} rawbytes should be bytes type")

    def test_integer_division(self):
        """Test that integer division works correctly"""
        # This is implicitly tested by loading, but we can check explicitly
        D = dlc(self.test_dlc_path)
        # If integer division failed, the DLC wouldn't load properly
        self.assertIsNotNone(D.dlc_sections)


class TestSectionAccess(unittest.TestCase):
    """Test accessing and working with DLC sections"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dlc_path = "./dlc/dlc2/tu003410.dlc"
        if not os.path.exists(self.test_dlc_path):
            self.skipTest("Test DLC file not found")
        self.D = dlc(self.test_dlc_path)

    def test_palette_section(self):
        """Test accessing palette section"""
        pal_section = self.D.dlc_sections.get('PAL')
        self.assertIsNotNone(pal_section)
        self.assertTrue(hasattr(pal_section, 'palettes'))

    def test_sprite_section(self):
        """Test accessing sprite section"""
        spr_section = self.D.dlc_sections.get('SPR')
        self.assertIsNotNone(spr_section)

    def test_cel_section(self):
        """Test accessing cel section"""
        cel_section = self.D.dlc_sections.get('CEL')
        self.assertIsNotNone(cel_section)

    def test_audio_section(self):
        """Test accessing audio section"""
        amf_section = self.D.dlc_sections.get('AMF')
        self.assertIsNotNone(amf_section)
        self.assertTrue(hasattr(amf_section, 'tracks'))


class TestCustomEyes(unittest.TestCase):
    """Test building DLCs with custom eye graphics"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dlc_path = "./dlc/dlc2/tu003410.dlc"
        if not os.path.exists(self.test_dlc_path):
            self.skipTest("Test DLC file not found")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_demo_eyes(self):
        """Context's demo builds: palettes, both GIF frames, and SEQ edits"""
        import demo
        output_path = os.path.join(self.temp_dir, "demo.dlc")
        demo.make_hacked_inverting(dlc_out=output_path)
        D = dlc(output_path)
        # transparent + blank cels, then 2 frames x 4 quarters per eye
        self.assertEqual(len(D.dlc_sections["CEL"].cels), 18)
        # FurBLE's hacked.dlc, the same build, is about 141 KB
        self.assertLess(os.path.getsize(output_path), 150000)

    def test_spooky_eyes(self):
        """spooky_eyes builds each theme small enough to upload"""
        import spooky_eyes
        for theme in spooky_eyes.THEMES:
            output_path = spooky_eyes.build(theme, out_dir=self.temp_dir)
            self.assertLess(os.path.getsize(output_path), spooky_eyes.MAX_UPLOAD)
            # transparent + blank cels, then at most 4 quarters per keyframe (both eyes share them)
            cels = len(dlc(output_path).dlc_sections["CEL"].cels)
            self.assertLessEqual(cels, 2 + 4 * len(spooky_eyes.THEMES[theme]["keys"]))
            self.assertTrue(os.path.exists(os.path.join(self.temp_dir, theme, "eyes_%s.gif" % theme)))

    def test_one_animation_keeps_demo_layout(self):
        """One theme lays out animation 1 exactly as demo.install_eyes() does, which has run on a Furby"""
        import spooky_eyes
        stock = dlc(self.test_dlc_path)
        D = dlc(spooky_eyes.build("demon", out_dir=self.temp_dir))
        S, S0 = D.dlc_sections["SPR"], stock.dlc_sections["SPR"]
        self.assertEqual(len(S.frame_playlists), 16)
        self.assertEqual([p["layer"] for p in S.frame_playlists], [p["layer"] for p in S0.frame_playlists])
        for p in list(range(8)) + [14, 15]:  # animation 0 and the top layer are untouched
            self.assertEqual([S.frames[f] for f in S.frame_playlists[p]["frame_indices"]],
                             [S0.frames[f] for f in S0.frame_playlists[p]["frame_indices"]])
        for p, ref in ((8, 4338), (9, 4338), (10, 4338), (11, 4338), (12, 6386), (13, 5362)):
            frames = [S.frames[f] for f in S.frame_playlists[p]["frame_indices"]]
            self.assertEqual(len(frames), 38)
            self.assertEqual({w for f in frames for w in f[1:8:2]}, {ref})
            if p < 12:
                self.assertEqual({w for f in frames for w in f[0:8:2]}, {1})  # blanked
        # the frames follow the timeline, and both eyes show the same cels
        right = [S.frames[f][0:8:2] for f in S.frame_playlists[12]["frame_indices"]]
        left = [S.frames[f][0:8:2] for f in S.frame_playlists[13]["frame_indices"]]
        self.assertEqual(right, left)
        self.assertEqual(len({tuple(f) for f in right}), 3)
        self.assertEqual(D.dlc_sections["PAL"].palettes[4], D.dlc_sections["PAL"].palettes[5])
        for code in spooky_eyes.DEMO_ACTIONS:
            self.assertEqual(set(spooky_eyes.eye_words(D, code)), {0x8401})

    def test_several_animations(self):
        """Each theme gets its own animation, a copy of animation 1's layout, and each clip shows its own"""
        import spooky_eyes
        stock = dlc(self.test_dlc_path)
        slots = spooky_eyes.scene_slots(stock)
        clip = "./audio/new_audio/darkside_wav.a18"
        eyes = {slots[0]: "storm", slots[1]: "ghost", slots[2]: "demon"}
        path = spooky_eyes.build("demon", clips=dict.fromkeys(slots[:4], clip), eyes=eyes, out_dir=self.temp_dir)
        self.assertLess(os.path.getsize(path), spooky_eyes.MAX_UPLOAD)
        D = dlc(path)
        S = D.dlc_sections["SPR"]
        self.assertEqual(len(S.frame_playlists), 8 + 3 * 8)  # animation 0, then demon, ghost, storm
        stock_layers = [p["layer"] for p in stock.dlc_sections["SPR"].frame_playlists[8:16]]
        for n in range(3):
            group = S.frame_playlists[8 + 8 * n:16 + 8 * n]
            self.assertEqual([p["layer"] for p in group], stock_layers)
            self.assertEqual([p["framecount"] for p in group], [38] * 6 + [1, 1])
        # demon is animation 1 (0x8401), the main theme; the rest follow in name order
        expected = {slots[0]: 0x8403, slots[1]: 0x8402, slots[2]: 0x8401, slots[3]: 0x8401}
        for code, word in expected.items():
            self.assertEqual(set(spooky_eyes.eye_words(D, code)), {word})
        # three different animations, each following its theme's timeline
        rendered = {w: spooky_eyes.render(D, w) for w in (0x8401, 0x8402, 0x8403)}
        self.assertEqual(len({f.tobytes() for frames in rendered.values() for f in frames}), 9)
        for word, theme in ((0x8401, "demon"), (0x8402, "ghost"), (0x8403, "storm")):
            order = spooky_eyes.timeline(theme)
            for i, j in enumerate(order):
                self.assertEqual(rendered[word][i].tobytes(), rendered[word][order.index(j)].tobytes())
            self.assertEqual(len({f.tobytes() for f in rendered[word]}), len(set(order)))

    def test_eye_frames(self):
        """Animations can be longer than the stock 38 frames, up to the firmware's longest"""
        import spooky_eyes
        D = dlc(spooky_eyes.build("storm", out_dir=self.temp_dir, frames=76))
        for p in range(8, 14):
            self.assertEqual(D.dlc_sections["SPR"].frame_playlists[p]["framecount"], 76)
        self.assertEqual(len(spooky_eyes.render(D)), 76)
        with self.assertRaises(SystemExit):
            spooky_eyes.build("storm", out_dir=self.temp_dir, frames=200)
        with self.assertRaises(SystemExit):
            spooky_eyes.build("nope", out_dir=self.temp_dir)

    def test_probe(self):
        """The probe DLCs put numbered test animations on the actions they say to trigger"""
        import spooky_eyes
        paths = spooky_eyes.build_probe(out_dir=self.temp_dir)
        self.assertEqual([os.path.basename(p) for p in paths], list(spooky_eyes.PROBE))
        for path, (anims, actions) in zip(paths, spooky_eyes.PROBE.values(), strict=True):
            self.assertLess(os.path.getsize(path), spooky_eyes.MAX_UPLOAD)
            D = dlc(path)
            self.assertEqual(len(D.dlc_sections["SPR"].frame_playlists), 8 + 8 * len(anims))
            for code, n in actions.items():
                digits, frames, _ = anims[n]
                self.assertEqual(set(spooky_eyes.eye_words(D, code)), {0x8401 + n})
                rendered = spooky_eyes.render(D, 0x8401 + n)
                self.assertEqual(len(rendered), frames)
                self.assertEqual(len({f.tobytes() for f in rendered}), len(digits))
        # every animation in probe.dlc looks different, so one can't pass for another
        D = dlc(paths[0])
        frames = [{f.tobytes() for f in spooky_eyes.render(D, 0x8401 + n)} for n in range(3)]
        self.assertFalse(frames[0] & frames[1] or frames[0] & frames[2] or frames[1] & frames[2])

    def test_previews(self):
        """--preview writes a GIF of the timeline and a sheet of the keyframes"""
        import spooky_eyes
        path = spooky_eyes.preview("hypno", self.temp_dir)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "hypno.png")))

    def test_spooky_eyes_with_audio(self):
        """The default song and sting still fit under the upload limit"""
        import spooky_eyes
        output_path = spooky_eyes.build(
            "demon",
            "./audio/new_audio/imperial_march-16000_wav.a18",
            "./audio/new_audio/darkside_wav.a18",
            out_dir=self.temp_dir,
        )
        self.assertLess(os.path.getsize(output_path), spooky_eyes.MAX_UPLOAD)


class TestHalloween(unittest.TestCase):
    """Test the two-Furby show build and the porch controller's parsing"""

    def setUp(self):
        """Set up test fixtures"""
        if not os.path.exists("./dlc/dlc2/tu003410.dlc"):
            self.skipTest("Test DLC file not found")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_scene_slots_are_exclusive(self):
        """Each scene slot plays one track that no other 75 action plays"""
        import spooky_eyes
        D = dlc("./dlc/dlc2/tu003410.dlc")
        slots = spooky_eyes.scene_slots(D)
        self.assertGreaterEqual(len(slots), 20)
        others = [t for c in spooky_eyes._actions(D, [75]) for t in spooky_eyes._tracks(D, c)]
        for code in slots:
            self.assertEqual(others.count(spooky_eyes._tracks(D, code)[0]), 1)

    def test_build_show(self):
        """Each Furby's clips land on their own actions, with eyes, and show.json maps them"""
        import json

        import halloween
        import spooky_eyes
        clip = "./audio/new_audio/darkside_wav.a18"
        show = {
            "show": {"gap": 0.5, "every": [30, 60], "cooldown": 20},
            "furbies": {
                "pink": {"theme": "demon", "clips": {"a": clip, "b": "./audio/new_audio/imperial_march-16000_wav.a18"}},
                "blue": {"theme": "pumpkin", "clips": {"c": {"path": clip, "before": 1.0}, "gone": "./no/such/clip.wav"}},
            },
            "scenes": [{"steps": ["pink.a", "blue.c"], "greeting": True}, {"steps": ["blue.gone"], "greeting": True}],
        }
        with self.assertRaises(SystemExit):
            halloween.build_show(show, self.temp_dir)
        with open(halloween.build_show(show, self.temp_dir, skip_missing=True)) as f:
            plan = json.load(f)
        self.assertEqual(plan["scenes"], [["pink.a", "blue.c"]])
        self.assertEqual(plan["greetings"], [["pink.a", "blue.c"]])  # only playable ones
        self.assertEqual(plan["cooldown"], 20)
        self.assertEqual(plan["furbies"]["blue"]["clips"]["c"]["before"], 1.0)
        self.assertNotIn("before", plan["furbies"]["pink"]["clips"]["a"])
        for name in ("pink", "blue"):
            D = dlc(os.path.join(self.temp_dir, "%s.dlc" % name))
            self.assertLess(os.path.getsize(os.path.join(self.temp_dir, "%s.dlc" % name)), spooky_eyes.MAX_UPLOAD)
            for info in plan["furbies"][name]["clips"].values():
                code = tuple(info["action"])
                self.assertIn(code, spooky_eyes.scene_slots(D))
                self.assertIn(code, halloween.quick_slots(D))  # not one that runs 10-21 s
                seq = D.dlc_sections["XLS"].action_tree[code[0]][code[1]][code[2]][code[3]]["seq"]
                self.assertNotIn(0x8096, D.dlc_sections["SEQ"].sequences[seq][3:-1])
                self.assertGreater(info["seconds"], 1)
        actions = [tuple(c["action"]) for c in plan["furbies"]["pink"]["clips"].values()]
        self.assertEqual(len(set(actions)), 2)
        # pink's theme picks its mix: clips a and b show demon (animation 1) and bloodshot (2)
        pink = dlc(os.path.join(self.temp_dir, "pink.dlc"))
        for name, theme, word in (("a", "demon", 0x8401), ("b", "bloodshot", 0x8402)):
            info = plan["furbies"]["pink"]["clips"][name]
            self.assertEqual(info["eyes"], theme)
            self.assertEqual(set(spooky_eyes.eye_words(pink, tuple(info["action"]))), {word})
        # The checksum the Furby will report for each DLC
        import zlib
        with open(os.path.join(self.temp_dir, "pink.dlc"), "rb") as f:
            self.assertEqual(plan["furbies"]["pink"]["checksum"], zlib.adler32(f.read()))

    def test_clip_eyes(self):
        """Clips take turns through the eyes list in name order, unless they pick their own"""
        import halloween
        clips = {c: {"path": c} for c in ("d", "a", "c", "b")}
        clips["c"]["eyes"] = "hypno"
        main, eyes = halloween.clip_eyes({"eyes": ["storm", "ghost"]}, clips)
        self.assertEqual(main, "storm")
        self.assertEqual(eyes, {"a": "storm", "b": "ghost", "d": "storm", "c": "hypno"})
        # a theme and no list: that theme's mix, led by the theme
        main, eyes = halloween.clip_eyes({"theme": "demon"}, clips)
        self.assertEqual((main, eyes["a"], eyes["b"]), ("demon", "demon", "bloodshot"))
        # one_eye_animation: every clip shows the main theme
        self.assertEqual(halloween.clip_eyes({"eyes": "storm"}, clips, one=True), ("storm", dict.fromkeys(clips, "storm")))

    def test_one_eye_animation(self):
        """one_eye_animation builds only animation 1, the layout that has run on a Furby"""
        import json

        import halloween
        import spooky_eyes
        clip = "./audio/new_audio/darkside_wav.a18"
        show = {
            "show": {"gap": 0.5, "every": [30, 60], "one_eye_animation": True},
            "furbies": {"pink": {"eyes": ["storm", "demon"], "clips": {"a": clip, "b": {"path": clip, "eyes": "ghost"}}}},
            "scenes": [{"steps": ["pink.a", "pink.b"]}],
        }
        with open(halloween.build_show(show, self.temp_dir)) as f:
            plan = json.load(f)
        D = dlc(os.path.join(self.temp_dir, "pink.dlc"))
        self.assertEqual(len(D.dlc_sections["SPR"].frame_playlists), 16)
        for info in plan["furbies"]["pink"]["clips"].values():
            self.assertEqual(info["eyes"], "storm")
            self.assertEqual(set(spooky_eyes.eye_words(D, tuple(info["action"]))), {0x8401})

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_snippets_and_optional_clips(self):
        """A clip table cuts a snippet; an optional clip that's missing just drops its scenes"""
        import json

        import halloween
        song = {"path": "./audio/new_audio/toccata_in_d_minor_16khz.wav", "start": "0:02", "seconds": 3}
        show = {
            "show": {"gap": 0.5, "every": [30, 60]},
            "furbies": {
                "pink": {"theme": "demon", "clips": {"song": song,
                                                     "extra": {"path": "./no/such.mp3", "optional": True}}},
                "blue": {"theme": "pumpkin", "clips": {"song": song}},
            },
            "scenes": [{"steps": ["pink.song + blue.song"]}, {"steps": ["pink.extra"]}],
        }
        with open(halloween.build_show(show, self.temp_dir)) as f:  # no --skip-missing needed
            plan = json.load(f)
        self.assertEqual(plan["scenes"], [["pink.song + blue.song"]])
        info = plan["furbies"]["pink"]["clips"]["song"]
        self.assertAlmostEqual(info["seconds"], 3, delta=0.1)
        self.assertTrue(info["source"].endswith("song.wav"))  # rehearsals play the snippet, not the whole file
        self.assertTrue(os.path.exists(info["source"]))
        self.assertNotIn("extra", plan["furbies"]["pink"]["clips"])

    def test_duet(self):
        """A "+" step lights and triggers both Furbies before waiting for the longer clip"""
        import asyncio

        import furbyshow
        events = []

        class F(furbyshow.Furby):
            def connected(self):
                return True

            async def _write(self, data):
                events.append((self.name, data[0]))
                if data[0] == 0x13:
                    self.on_response(furbyshow.SEQUENCE_PLAYING)

        async def sleep(seconds):
            events.append(("sleep", seconds))

        plan = {
            "gap": 0.5, "every": [1, 2], "scenes": [],
            "furbies": {
                "pink": {"antenna": [255, 0, 0], "clips": {"a": {"action": [75, 0, 0, 2], "seconds": 3.0}}},
                "blue": {"antenna": [255, 100, 0], "clips": {"a": {"action": [75, 0, 0, 2], "seconds": 5.0}}},
            },
        }
        show = furbyshow.Show(plan, None, sleep=sleep, log=lambda *_: None)
        for name in ("pink", "blue"):
            show.furbies[name] = F(name)
            show.furbies[name].name = name
        asyncio.run(show.play_step("pink.a + blue.a"))
        self.assertEqual(events, [
            ("pink", 0x14), ("blue", 0x14), ("pink", 0x13), ("blue", 0x13),
            ("sleep", 5.0), ("pink", 0x14), ("blue", 0x14), ("sleep", 0.5),
        ])
        self.assertEqual(furbyshow.pick_scene([["pink.a + blue.a"]], {"pink"}), None)
        # A clip's "before" holds a beat ahead of the line, before its antenna lights
        events.clear()
        plan["furbies"]["pink"]["clips"]["a"]["before"] = 1.0
        asyncio.run(show.play_step("pink.a"))
        self.assertEqual(events[:2], [("sleep", 1.0), ("pink", 0x14)])

    def test_play_waits_while_busy(self):
        """A Furby still running its last sequence answers 20:07; play() waits for 20:0e and triggers again"""
        import asyncio

        import furbyshow
        sent = []

        class Busy(furbyshow.Furby):
            def __init__(self, busy_for):
                super().__init__("aa")
                self.busy_for = busy_for  # how many triggers it answers with 20:07

            def connected(self):
                return True

            async def _write(self, data):
                sent.append(bytes(data))
                if data[0] != 0x13:
                    return
                if self.busy_for:
                    self.busy_for -= 1
                    self.on_response(furbyshow.SPEECH_PLAYING)
                    asyncio.get_running_loop().call_later(0.05, self.on_response, furbyshow.SEQUENCE_ENDED)
                else:
                    self.on_response(furbyshow.SEQUENCE_PLAYING)

        self.assertTrue(asyncio.run(Busy(2).play((75, 0, 0, 2))))
        self.assertEqual([d for d in sent if d[0] == 0x13], [bytes([0x13, 0, 75, 0, 0, 2])] * 3)
        # One that never frees up gives up once its patience runs out
        sent.clear()
        self.assertFalse(asyncio.run(Busy(99).play((75, 0, 0, 2), patience_ms=200)))
        self.assertGreater(len(sent), 1)

    def test_greetings_and_cooldown(self):
        """A trigger plays a greeting and the timer the rest; only the sensor waits out a cooldown"""
        import asyncio

        import furbyshow
        sent = []

        class F(furbyshow.Furby):
            def connected(self):
                return True

            async def _write(self, data):
                sent.append(data)
                if data[0] == 0x13:
                    self.on_response(furbyshow.SEQUENCE_PLAYING)

        async def sleep(seconds):
            pass

        plan = {
            "gap": 0, "every": [1, 2], "cooldown": 10,
            "scenes": [["pink.a"], ["pink.b"]], "greetings": [["pink.b"]],
            "furbies": {"pink": {"clips": {"a": {"action": [75, 0, 0, 2], "seconds": 1.0},
                                           "b": {"action": [75, 0, 4, 4], "seconds": 1.0}}}},
        }
        show = furbyshow.Show(plan, None, sleep=sleep, log=lambda *_: None)
        show.furbies["pink"] = F("aa")
        self.assertEqual(show.scenes(), [["pink.a"]])
        self.assertEqual(show.scenes(greeting=True), [["pink.b"]])

        async def press(sensor=False):
            await asyncio.sleep(0.02)
            show.trigger(sensor=sensor)

        async def run():
            await show.run_once()
            self.assertEqual(sent[-1], furbyshow.trigger_command((75, 0, 0, 2)))
            self.assertIsNone(show.greeted)  # a timer scene doesn't start the cooldown
            asyncio.create_task(press(sensor=True))
            self.assertTrue(await show.wait(5))
            await show.run_once(greeting=True)
            self.assertEqual(sent[-1], furbyshow.trigger_command((75, 0, 4, 4)))
            # A greeting just played, so motion is ignored and the wait runs out...
            asyncio.create_task(press(sensor=True))
            self.assertFalse(await show.wait(0.2))
            # ...but a button press always counts
            asyncio.create_task(press())
            self.assertTrue(await show.wait(5))
            # Once the cooldown has passed, motion counts again
            show.greeted -= 10_000
            asyncio.create_task(press(sensor=True))
            self.assertTrue(await show.wait(5))
            # Someone who arrived during a scene is greeted as soon as it ends
            show.trigger()
            self.assertTrue(await show.wait(5))

        asyncio.run(run())
        # With no greetings, a trigger plays any scene
        del plan["greetings"]
        self.assertEqual(show.scenes(greeting=True), plan["scenes"])

    def test_show_parsing(self):
        """furbyshow reads FurBLE's responses and picks playable scenes"""
        import furbyshow
        self.assertEqual(furbyshow.trigger_command((75, 0, 4, 4)), bytes([0x13, 0, 75, 0, 4, 4]))
        # Captured from a Furby with a DLC uploaded to slot 13 and activated
        self.assertEqual(furbyshow.active_slot(bytes.fromhex("720000200000002000")), 13)
        self.assertIsNone(furbyshow.active_slot(bytes.fromhex("720000200000000000")))
        self.assertEqual(furbyshow.slot_name(bytes.fromhex("730d53504f4f4b59444503a236cafd6934")), "SPOOKYDE")
        self.assertEqual(furbyshow.slot_name(b"\x73\x0d____PINK"), "PINK")
        # The same Adler-32 that zlib computes for the uploaded file
        self.assertEqual(furbyshow.slot_checksum(bytes.fromhex("730d53504f4f4b59444503a236cafd6934")), 0xCAFD6934)
        scenes = [["pink.a", "blue.b"], ["pink.c"]]
        self.assertEqual(furbyshow.pick_scene(scenes, {"pink"}), ["pink.c"])
        self.assertIsNone(furbyshow.pick_scene(scenes, set()))
        self.assertEqual(furbyshow.pick_scene(scenes, {"pink"}, last=["pink.c"]), ["pink.c"])

    def test_show_runs_scenes(self):
        """The show connects, identifies Furbies by DLC name, and plays a scene's steps in order"""
        import asyncio

        import furbyshow
        sent = []

        class FakeFurby(furbyshow.Furby):
            def __init__(self, address, dlc):
                super().__init__(address)
                self.dlc = dlc
                self.dropped = False

            def connected(self):
                return not self.dropped

            async def disconnect(self):
                self.dropped = True

            async def _write(self, data):
                sent.append((self.address, data))
                # Answer like a Furby: DLC active in slot 13, named after its file
                if data[0] == 0x13:
                    self.on_response(furbyshow.SEQUENCE_PLAYING)
                elif data == furbyshow.DLC_INFO:
                    self.on_response(bytes.fromhex("720000200000002000"))
                elif data == bytes([0x73, 13]):
                    self.on_response(b"\x73\x0d____" + self.dlc + bytes.fromhex("03a236cafd6934"))

        stray = FakeFurby("cc", b"SPOOKYDE")
        twin = FakeFurby("dd", b"PINK")  # pink.dlc flashed to both Furbies by mistake
        attempts = []

        async def find(known):
            attempts.append(known)
            if len(attempts) == 1:
                raise OSError("scan failed")  # the show should shrug this off and retry
            furbies = [FakeFurby("aa", b"PINK"), FakeFurby("bb", b"BLUE"), stray, twin]
            for f in furbies:
                await f.identify()
            return furbies

        slept = []

        async def sleep(seconds):
            slept.append(seconds)

        plan = {
            "gap": 0.5, "every": [30, 60], "scenes": [["pink.a", "blue.b"]],
            "furbies": {
                "pink": {
                    "checksum": 0x12345678,
                    "antenna": [255, 0, 0],
                    "clips": {"a": {"action": [75, 0, 0, 2], "seconds": 2.0}},
                },
                "blue": {"clips": {"b": {"action": [75, 0, 4, 4], "seconds": 1.5}}},
            },
        }

        logs = []
        waits = []

        async def run():
            show = furbyshow.Show(plan, find, sleep=sleep, log=logs.append)

            async def wait(seconds):
                waits.append(seconds)
                if len(waits) == 2:
                    raise asyncio.CancelledError  # stop after the retry and one scene
            show.wait = wait
            try:
                await show.run()
            except asyncio.CancelledError:
                pass
            for task in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
                task.cancel()
            return show

        show = asyncio.run(run())
        self.assertEqual(waits[0], furbyshow.RETRY_FIND_S)  # the failed scan didn't end the show
        self.assertEqual(sorted(show.furbies), ["blue", "pink"])
        self.assertTrue(stray.dropped)  # a Furby with someone else's DLC is let go
        self.assertTrue(twin.dropped)  # so is a second Furby with the same DLC
        self.assertEqual(show.furbies["pink"].address, "aa")
        self.assertTrue(any("Two Furbies have pink.dlc" in line for line in logs))
        self.assertTrue(any("reflash" in line and "pink" in line for line in logs))
        plays = [(a, d) for a, d in sent if d[0] == 0x13]
        self.assertEqual(plays, [("aa", bytes([0x13, 0, 75, 0, 0, 2])), ("bb", bytes([0x13, 0, 75, 0, 4, 4]))])
        # Pink's antenna glows for its line and goes dark after; blue has no color set
        self.assertEqual([d for a, d in sent if d[0] == 0x14], [bytes([0x14, 255, 0, 0]), bytes([0x14, 0, 0, 0])])
        self.assertEqual(slept, [2.0, 0.5, 1.5, 0.5])
        self.assertTrue(30 <= waits[1] <= 60)

    @unittest.skipUnless(shutil.which("micropython"), "micropython not installed")
    def test_show_runs_on_micropython(self):
        """furbyshow imports and plays a scene under MicroPython, as it will on the board"""
        import subprocess
        script = """
import asyncio, time, furbyshow
sent = []
class F(furbyshow.Furby):
    def connected(self): return True
    async def disconnect(self): pass
    async def _write(self, data):
        sent.append(data)
        if data == furbyshow.DLC_INFO: self.on_response(bytes.fromhex("720000200000002000"))
        elif data == bytes([0x73, 13]): self.on_response(bytes.fromhex("730d5f5f5f5f50494e4b03a236cafd6934"))
async def find(known):
    f = F("aa"); await f.identify(); return [f]
async def sleep(s): pass
plan = {"gap": 0.1, "every": [1, 2], "scenes": [["pink.a"]],
        "furbies": {"pink": {"clips": {"a": {"action": [75, 0, 0, 2], "seconds": 1.0}}}}}
async def main():
    show = furbyshow.Show(plan, find, sleep=sleep, log=lambda *a: None, wake=asyncio.ThreadSafeFlag())
    await show.run_once()
    # The board's idle wait: time out twice, then wake early on the button
    await show.wait(0.05)
    await show.wait(0.05)
    async def press():
        await asyncio.sleep(0.05)
        show.trigger()
    asyncio.create_task(press())
    t = time.ticks_ms()
    await show.wait(5)
    assert time.ticks_diff(time.ticks_ms(), t) < 1000, "button didn't wake the show"
    assert show.furbies["pink"].checksum == 0xCAFD6934
asyncio.run(main())
assert sent[-1] == bytes([0x13, 0, 75, 0, 0, 2]), sent
assert furbyshow.slot_name(b"\\x73\\x0d____PINK") == "PINK"
print("ok")
"""
        result = subprocess.run(["micropython", "-c", script], capture_output=True, text=True, check=False,
                                env=dict(os.environ, MICROPYPATH=".frozen:."))
        self.assertEqual(result.stdout.strip(), "ok", result.stderr)


class TestFlash(unittest.TestCase):
    """flash.py uploads the way FurBLE does, against a stand-in Furby"""

    def test_filename(self):
        import flash
        self.assertEqual(flash.furby_filename("build/halloween/pink.dlc"), "____PINK.DLC")
        self.assertEqual(flash.announce_command(0x0332F6, "____PINK.DLC").hex(),
                         "50000332f6025f5f5f5f50494e4b2e444c430000")  # what FurBLE sent for pink.dlc
        with self.assertRaises(SystemExit):
            flash.furby_filename("toolongname.dlc")

    def test_flash(self):
        import asyncio
        import zlib

        import flash
        import furbyshow
        data = bytes(range(256)) * 5
        checksum = zlib.adler32(data)

        class FakeFurby:
            """Starts with an old DLC active in slot 13; stores and activates the upload in slot 12."""

            def __init__(self):
                self.filled, self.active, self.received, self.writes = {13}, {13}, b"", []
                self.notify = {}

            async def start_notify(self, uuid, cb):
                self.notify[uuid] = cb

            def say(self, data):
                self.notify[furbyshow.GP_LISTEN](None, bytes(data))

            def info(self):
                bits = lambda s: sum(1 << i for i in s)  # noqa: E731
                f, a = bits(self.filled), bits(self.active)
                return bytes([0x72, 0, 0, f >> 8, f & 0xFF, 0, 0, a >> 8, a & 0xFF])

            async def write_gatt_char(self, uuid, data, response=False):
                self.writes.append((uuid, bytes(data)))
                if uuid == flash.FILE_WRITE:
                    self.received += data
                    if len(self.received) == len(data):
                        self.filled.add(12)
                        self.say([0x24, 5])
                    return
                if uuid != furbyshow.GP_WRITE:
                    return
                cmd = data[0]
                if cmd == 0x72:
                    self.say(self.info())
                elif cmd == 0x62:
                    self.active.discard(data[1])
                    self.say([0xDC, data[1], 0])
                elif cmd == 0x74:
                    self.filled.discard(data[1])
                    self.say([0x74, data[1]])
                elif cmd == 0x50:
                    self.say([0x24, 2])
                elif cmd == 0x73:
                    self.say(bytes([0x73, data[1]]) + b"____PINK" + bytes(3) + checksum.to_bytes(4, "big"))
                elif cmd == 0x60:
                    self.loaded = data[1]
                    self.say([0xDC, data[1], 1])
                elif cmd == 0x61:
                    self.active = {self.loaded}
                    self.say([0xDC, self.loaded, 2])

        furby = FakeFurby()
        logs = []
        asyncio.run(flash.Flasher(furby, log=logs.append, packet_delay=0).flash(data, "____PINK.DLC"))
        self.assertEqual(furby.received, data)
        self.assertEqual(furby.active, {12})
        self.assertNotIn(13, furby.filled)  # the old DLC was deleted first, instead of a reset
        self.assertEqual(furby.writes[-1], (furbyshow.GP_WRITE, furbyshow.antenna_command((0, 255, 0))))
        self.assertTrue(any("slot 12" in line for line in logs))


class TestRehearsal(unittest.TestCase):
    """porch.py --rehearse plays each step's source clip, in order, with no Furbies"""

    def test_rehearse_scene(self):
        import argparse
        import asyncio
        from unittest import mock

        import porch

        plan = {
            "gap": 0, "every": [30, 60], "scenes": [["pink.a", "blue.b"]],
            "furbies": {
                "pink": {"antenna": [255, 0, 0], "clips": {"a": {"action": [75, 0, 0, 2], "seconds": 0, "source": "a.wav"}}},
                "blue": {"clips": {"b": {"action": [75, 0, 0, 2], "seconds": 0, "source": "b.wav"}}},
            },
        }
        played = []
        with mock.patch.object(porch, "play_audio", played.append), mock.patch("builtins.print"):
            asyncio.run(porch.rehearse(plan, argparse.Namespace(clip=None, scene=0)))
        # The same action plays each Furby's own clip
        self.assertEqual(played, ["a.wav", "b.wav"])


class TestFirmware(unittest.TestCase):
    """Run firmware/main.py on CPython, against stand-ins for aioble, bluetooth and machine"""

    def setUp(self):
        import asyncio
        import importlib.util
        import sys
        import types

        test = self
        self.pins = {}
        self.irqs = {}  # pin number → the edge its interrupt fires on
        self.feeds = 0
        # DLC name each fake Furby reports; None means no active DLC
        self.furbies = {"aa": b"PINK", "bb": None}
        self.disconnected = []

        class Pin:
            IN, OUT, PULL_UP, IRQ_FALLING, IRQ_RISING = 0, 1, 2, 3, 4

            def __init__(self, number, mode=None, pull=None):
                self.number, self.level = number, test.pins.get(number, 1)

            def value(self, level=None):
                if level is None:
                    return self.level
                self.level = level

            def irq(self, handler, trigger):
                self.handler = handler
                test.irqs[self.number] = trigger

        class WDT:
            def __init__(self, timeout):
                self.timeout = timeout

            def feed(self):
                test.feeds += 1

        class Characteristic:
            def __init__(self, connection):
                self.connection = connection

            async def subscribe(self, notify=True):
                pass

            async def notified(self, timeout_ms=None):
                try:
                    return await asyncio.wait_for(self.connection.inbox.get(), timeout_ms / 1000)
                except asyncio.TimeoutError:
                    raise asyncio.TimeoutError from None

            async def write(self, data, response=None):
                name = test.furbies[self.connection.address]
                if data == b"\x72":
                    self.connection.inbox.put_nowait(bytes.fromhex("72000020000000" + ("2000" if name else "0000")))
                elif data == bytes([0x73, 13]):
                    self.connection.inbox.put_nowait(b"\x73\x0d____" + name + bytes.fromhex("03a236cafd6934"))

        class Service:
            def __init__(self, connection):
                self.connection = connection

            async def characteristic(self, uuid):
                return Characteristic(self.connection)

        class Connection:
            def __init__(self, address):
                self.address, self.open, self.inbox = address, True, asyncio.Queue()

            def is_connected(self):
                return self.open

            async def disconnect(self):
                self.open = False
                test.disconnected.append(self.address)

            async def service(self, uuid):
                return Service(self)

        class Device:
            def __init__(self, address):
                self.address = address

            def addr_hex(self):
                return self.address

            async def connect(self, timeout_ms):
                return Connection(self.address)

        class Result:
            def __init__(self, device, name):
                self.device, self._name = device, name

            def name(self):
                return self._name

        devices = [Device("aa"), Device("bb")]

        class scan:
            def __init__(self, duration_ms, **kwargs):
                # The same Furby shows up repeatedly in a real scan, and so do other devices
                self.results = [Result(devices[0], "Furby"), Result(devices[0], "Furby"),
                                Result(devices[1], "Furby"), Result(Device("cc"), "Headphones")]

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self.results:
                    raise StopAsyncIteration
                return self.results.pop(0)

        fakes = {
            "aioble": types.SimpleNamespace(scan=scan),
            "bluetooth": types.SimpleNamespace(UUID=str),
            "machine": types.SimpleNamespace(Pin=Pin, WDT=WDT),
        }
        self.saved = {name: sys.modules.get(name) for name in fakes}
        sys.modules.update(fakes)
        spec = importlib.util.spec_from_file_location("firmware_main", "./firmware/main.py")
        self.main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main)

    def tearDown(self):
        import sys
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_find(self):
        """Connects each Furby once, identifies it, and lets go of one with no DLC"""
        import asyncio
        furbies = asyncio.run(self.main.find([]))
        self.assertEqual([(f.address, f.name) for f in furbies], [("aa", "pink")])
        self.assertEqual(furbies[0].checksum, 0xCAFD6934)
        self.assertEqual(self.disconnected, ["bb"])
        # Already-connected Furbies are skipped
        self.assertEqual(asyncio.run(self.main.find(["aa"])), [])

    def test_safe_boot(self):
        """Holding the button at power-up skips the show"""
        self.assertFalse(self.main.safe_boot())
        self.pins[self.main.BUTTON_PIN] = 0
        self.assertTrue(self.main.safe_boot())

    def test_motion_sensor(self):
        """The button always triggers the show; a PIR sensor does too once PIR_PIN is set"""
        import asyncio
        import json
        import tempfile
        from unittest import mock

        plan = os.path.join(tempfile.mkdtemp(), "show.json")
        with open(plan, "w") as f:
            json.dump({"gap": 0, "every": [1, 2], "scenes": [], "furbies": {}}, f)

        async def run(show):
            pass

        # CPython has no ThreadSafeFlag; an Event stands in for it
        with mock.patch.object(self.main.furbyshow.Show, "run", run), \
                mock.patch.object(asyncio, "ThreadSafeFlag", asyncio.Event, create=True):
            asyncio.run(self.main.main(plan))
            self.assertEqual(self.irqs, {self.main.BUTTON_PIN: self.main.machine.Pin.IRQ_FALLING})
            self.main.PIR_PIN = 5
            asyncio.run(self.main.main(plan))
            self.assertEqual(self.irqs[5], self.main.machine.Pin.IRQ_RISING)

    def test_watchdog(self):
        """The watchdog is fed while the show makes progress, and starved once it stalls"""
        import asyncio
        from unittest import mock

        class FakeShow:
            stalls = [0, 1000, self.main.STALL_MS]

            def stalled_ms(self):
                return self.stalls.pop(0)

        async def no_sleep(_):
            pass

        with mock.patch.object(self.main.asyncio, "sleep", no_sleep):
            asyncio.run(self.main.watchdog(FakeShow(), self.main.machine.WDT(self.main.WATCHDOG_MS)))
        self.assertEqual(self.feeds, 2)

    @unittest.skipUnless(shutil.which("micropython"), "micropython not installed")
    def test_compiles_for_micropython(self):
        """The board's files compile with MicroPython's own compiler"""
        import subprocess
        for path in ("furbyshow.py", "firmware/main.py"):
            result = subprocess.run(["micropython", "-c", "compile(open(%r).read(), %r, 'exec')" % (path, path)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


class TestEyeCheck(unittest.TestCase):
    """eyecheck composes a DLC's eyes the way the Furby does and fails what won't show as intended"""

    def setUp(self):
        self.stock_path = "./dlc/dlc2/tu003410.dlc"
        if not os.path.exists(self.stock_path):
            self.skipTest("Test DLC file not found")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_stock_composes_its_own_eye(self):
        """Hasbro's animation 1 composes the eye layer under the chilli and flames, as the firmware's files do"""
        import eyecheck
        D = dlc(self.stock_path)
        self.assertEqual(eyecheck.envelope(D), ([], []))
        for rule in eyecheck.RULES:
            frames = eyecheck.compose(D, 0x8401, "right", rule)
            self.assertEqual(len(frames), 38)
            self.assertEqual(frames[0].getpixel((64, 64)), eyecheck.compose(D, 0x8401, "right", "layer")[0].getpixel((64, 64)))

    def test_one_animation_renders_as_drawn(self):
        """spooky_eyes' one-animation DLC composes to its keyframes, frame by frame, under either palette rule"""
        from PIL import Image

        import eyecheck
        import spooky_eyes
        D = dlc(spooky_eyes.build("storm", out_dir=self.temp_dir))
        self.assertEqual(eyecheck.check(D), ([], []))
        palette, pixels = spooky_eyes._palette(spooky_eyes.keyframes("storm"))
        keys = []
        for p in pixels:
            im = Image.new("RGB", (128, 128))
            im.putdata([palette[i][:3] for i in p])
            keys.append(im)
        want = [keys[k] for k in spooky_eyes.timeline("storm")]
        expected = {(0x8401, eye): want for eye in ("right", "left")}
        self.assertEqual(eyecheck.check(D, expected), ([], []))

    def test_several_animations_fail(self):
        """More than one animation (probe.dlc had 32 playlists) is what left the old DLC's cels on screen"""
        import eyecheck
        import spooky_eyes
        slots = spooky_eyes.scene_slots(dlc(self.stock_path))
        clip = "./audio/new_audio/darkside_wav.a18"
        path = spooky_eyes.build("demon", clips={slots[0]: clip}, eyes={slots[0]: "ghost"}, out_dir=self.temp_dir)
        errors, _ = eyecheck.check(dlc(path))
        self.assertTrue(any("24 SPR playlists" in e for e in errors), errors)
        self.assertNotEqual(eyecheck.main([path]), 0)

    def test_long_animation_fails(self):
        """A 76-frame animation's SPR is bigger than any that has shown on a Furby"""
        import eyecheck
        import spooky_eyes
        errors, _ = eyecheck.check(dlc(spooky_eyes.build("storm", out_dir=self.temp_dir, frames=76)))
        self.assertTrue(any("SPR is" in e for e in errors), errors)

    def test_flipped_quarter_fails(self):
        """A quarter with the H-flip bit set doesn't render as drawn, whichever palette rule holds"""
        import eyecheck
        import spooky_eyes
        D = dlc(spooky_eyes.build("demon", out_dir=self.temp_dir))
        S = D.dlc_sections["SPR"]
        f = S.frame_playlists[12]["frame_indices"][0]
        S.frames[f] = S.frames[f][:1] + [S.frames[f][1] | eyecheck.H_FLIP] + S.frames[f][2:]
        errors, _ = eyecheck.check(D)
        self.assertTrue(any("right eye doesn't render" in e for e in errors), errors)

    def test_palette_rule_and_bad_cels(self):
        """Different palettes in slots 4 and 5 depend on the unsettled rule; a missing cel or animation is an error"""
        import eyecheck
        import spooky_eyes
        D = dlc(spooky_eyes.build("demon", out_dir=self.temp_dir))
        P = D.dlc_sections["PAL"].palettes
        P[4] = [P[4][0]] + [(c[0] ^ 0x80, c[1], c[2], c[3]) for c in P[4][1:]]
        errors, warnings = eyecheck.check(D)
        self.assertEqual(errors, [])
        self.assertTrue(any("left eye" in w and "'slot'" in w for w in warnings), warnings)
        S = D.dlc_sections["SPR"]
        f = S.frame_playlists[12]["frame_indices"][0]
        S.frames[f] = [999] + S.frames[f][1:]
        D.trigger_custom_graphics(spooky_eyes.DEMO_ACTIONS[0], 0x8402)
        errors, _ = eyecheck.envelope(D)
        self.assertTrue(any("uses cel 999" in e for e in errors), errors)
        self.assertTrue(any("0x8402" in e for e in errors), errors)

    def test_demo_layout_passes(self):
        """Context's demo layout, which has shown on a Furby, passes; its see-through pixels depend on the rule"""
        import demo
        import eyecheck
        path = os.path.join(self.temp_dir, "demo.dlc")
        demo.make_hacked_inverting(dlc_out=path)
        errors, _ = eyecheck.check(dlc(path))
        self.assertEqual(errors, [])

    def test_stale_cels_and_gifs(self):
        """--gif writes both eyes under each rule; --stale-cel draws another DLC's cels in the new frames"""
        import eyecheck
        import spooky_eyes
        path = spooky_eyes.build("demon", out_dir=self.temp_dir)
        other = spooky_eyes.build("pumpkin", out_dir=self.temp_dir)
        out = os.path.join(self.temp_dir, "gifs")
        self.assertEqual(eyecheck.main([path, "--gif", out, "--stale-cel", other]), 0)
        self.assertEqual(sorted(os.listdir(out)), ["spooky_demon_8401_layer_stale.gif", "spooky_demon_8401_slot_stale.gif"])
        D, stale = dlc(path), dlc(other).dlc_sections["CEL"].cels
        self.assertNotEqual(eyecheck.compose(D, 0x8401, cels=stale)[0].tobytes(), eyecheck.compose(D, 0x8401)[0].tobytes())


class TestAudioUtils(unittest.TestCase):
    """Test the DLL-free audio tools"""

    def setUp(self):
        """Set up test fixtures"""
        if not os.path.exists("./dlc/dlc2/tu003410.dlc"):
            self.skipTest("Test DLC file not found")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_extract_voice(self):
        """Every clip in the stock DLC decodes to a WAV"""
        import sys
        sys.path.insert(0, "./audioutils")
        import extract_voice
        rows = extract_voice.extract(out_dir=self.temp_dir)
        self.assertEqual(len(rows), 146)
        self.assertTrue(all(float(r[2]) > 0 for r in rows))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "index.csv")))


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases"""

    def test_nonexistent_file(self):
        """Test that loading a non-existent file raises an error"""
        with self.assertRaises(FileNotFoundError):
            dlc("nonexistent_file.dlc")

    def test_empty_init(self):
        """Test creating a DLC object without a file"""
        D = dlc()
        self.assertIsNone(D.dlc_header)
        self.assertEqual(D.dlc_sections, {})


if __name__ == '__main__':
    unittest.main()
