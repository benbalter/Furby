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
import types
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

    def test_theme_cost(self):
        """THEME_BYTES, which the size hints, show.toml and README quote, matches what a second theme adds"""
        import spooky_eyes
        one = spooky_eyes.build("demon", out_dir=self.temp_dir, name="one")
        two = spooky_eyes.build("demon", out_dir=self.temp_dir, name="two", eyes={(75, 0, 4, 4): "storm"})
        self.assertAlmostEqual(os.path.getsize(two) - os.path.getsize(one), spooky_eyes.THEME_BYTES, delta=1000)

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
            # transparent + blank cels, then at most 4 quarters per keyframe for each eye
            cels = len(dlc(output_path).dlc_sections["CEL"].cels)
            self.assertLessEqual(cels, 2 + 8 * len(spooky_eyes.THEMES[theme]["keys"]))
            self.assertTrue(os.path.exists(os.path.join(self.temp_dir, theme, "eyes_%s.gif" % theme)))

    def test_one_animation_keeps_demo_layout(self):
        """One theme lays out animation 1 exactly as demo.install_eyes() does, which has run on a Furby"""
        import eyecheck
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
        # the frames follow the timeline, and both eyes share cels, consecutive within each frame, in a
        # CEL section padded to 16 (shared cels in fewer came out garbled on a Furby)
        right = [S.frames[f][0:8:2] for f in S.frame_playlists[12]["frame_indices"]]
        left = [S.frames[f][0:8:2] for f in S.frame_playlists[13]["frame_indices"]]
        self.assertEqual(right, left)
        self.assertEqual(len({tuple(f) for f in right}), 3)
        self.assertEqual(sorted({c for f in left for c in f}), list(range(2, 14)))
        self.assertEqual(len(D.dlc_sections["CEL"].cels), eyecheck.PROVEN_MIN_CELS)
        self.assertEqual(eyecheck.envelope(D)[0], [])
        self.assertEqual(D.dlc_sections["PAL"].palettes[4], D.dlc_sections["PAL"].palettes[5])
        for code in spooky_eyes.DEMO_ACTIONS:
            self.assertEqual(set(spooky_eyes.eye_words(D, code)), {0x8401})

    def test_several_animations(self):
        """Each theme gets its own animation, a copy of animation 1's layout, and each clip shows its own"""
        import spooky_eyes
        stock = dlc(self.test_dlc_path)
        slots = spooky_eyes.scene_slots(stock)
        clip = "./audio/new_audio/darkside_wav.a18"
        eyes = {slots[0]: "ghost", slots[1]: "demon"}
        path = spooky_eyes.build("demon", clips=dict.fromkeys(slots[:3], clip), eyes=eyes, out_dir=self.temp_dir)
        self.assertLess(os.path.getsize(path), spooky_eyes.MAX_UPLOAD)
        D = dlc(path)
        S = D.dlc_sections["SPR"]
        self.assertEqual(len(S.frame_playlists), 8 + 2 * 8)  # animation 0, then demon, ghost
        stock_layers = [p["layer"] for p in stock.dlc_sections["SPR"].frame_playlists[8:16]]
        for n in range(2):
            group = S.frame_playlists[8 + 8 * n:16 + 8 * n]
            self.assertEqual([p["layer"] for p in group], stock_layers)
            self.assertEqual([p["framecount"] for p in group], [38] * 6 + [1, 1])
        # demon is animation 1 (0x8401), the main theme; the rest follow in name order
        expected = {slots[0]: 0x8402, slots[1]: 0x8401, slots[2]: 0x8401}
        for code, word in expected.items():
            self.assertEqual(set(spooky_eyes.eye_words(D, code)), {word})
        # two different animations, each following its theme's timeline
        rendered = {w: spooky_eyes.render(D, w) for w in (0x8401, 0x8402)}
        self.assertEqual(len({f.tobytes() for frames in rendered.values() for f in frames}), 6)
        for word, theme in ((0x8401, "demon"), (0x8402, "ghost")):
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
        for path, (anims, actions, (how, _)) in zip(paths, spooky_eyes.PROBE.values(), strict=True):
            self.assertLessEqual(len(os.path.basename(path)), 12)  # the Furby keeps 8.3 names
            self.assertLess(os.path.getsize(path), 220000)
            D = dlc(path)
            self.assertEqual(len(D.dlc_sections["SPR"].frame_playlists), 8 + 8 * len(anims))
            if how != "demo":
                self.assertEqual(D.dlc_sections["PAL"].palettes[5][0], (0, 0, 0, 0xFF))
            for code, n in actions.items():
                digits, frames, _ = anims[n]
                self.assertEqual(set(spooky_eyes.eye_words(D, code)), {0x8401 + n})
                rendered = {f.tobytes() for f in spooky_eyes.render(D, 0x8401 + n)}
                self.assertEqual(len(spooky_eyes.render(D, 0x8401 + n)), frames)
                self.assertEqual(len(rendered), len(digits))
            if how == "multi":  # each of eyesa's animations looks unlike the others
                frames = [{f.tobytes() for f in spooky_eyes.render(D, 0x8401 + n)} for n in range(3)]
                self.assertFalse(frames[0] & frames[1] or frames[0] & frames[2] or frames[1] & frames[2])

    def test_probe_layout_matches_demo(self):
        """install_layout() with no changes builds exactly what demo.install_eyes() builds, so each probe changes one thing"""
        from PIL import Image

        import spooky_eyes
        from demo import install_eyes
        keys = [spooky_eyes._digit(d, spooky_eyes.RED).resize((128, 128), Image.LANCZOS) for d in (1, 2)]
        built = []
        for how in ("demo", "layout"):
            D = dlc(self.test_dlc_path)
            work = os.path.join(self.temp_dir, how)
            if how == "demo":
                gifs = spooky_eyes._demo_gifs(keys, work)
                install_eyes(D, gifs, gifs)
            else:
                spooky_eyes.install_layout(D, keys, work)
            D.build(os.path.join(self.temp_dir, how + ".dlc"))
            with open(os.path.join(self.temp_dir, how + ".dlc"), "rb") as f:
                built.append(f.read())
        self.assertEqual(built[0], built[1])
        # quarter dedup gives the "1" frame a repeated cel: (2, 3, 2, 4)
        D = dlc(self.test_dlc_path)
        spooky_eyes.install_layout(D, keys, os.path.join(self.temp_dir, "f"), dedup="quarter")
        first = D.dlc_sections["SPR"].frames[D.dlc_sections["SPR"].frame_playlists[13]["frame_indices"][0]][0:8:2]
        self.assertEqual(first, [2, 3, 2, 4])
        # whole-frame dedup keeps each frame's cels consecutive, like demo.install_eyes()
        self.assertEqual(spooky_eyes._add_cels([], [[[[0]], [[0]], [[0]], [[1]]]] * 2), [[0, 1, 2, 3]] * 2)

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
        # Each clip's antenna plays its eyes' light, with an envelope a digit per 100 ms
        self.assertEqual(plan["light_hz"], 10)
        a = plan["furbies"]["pink"]["clips"]["a"]
        self.assertEqual(a["light"], {"effect": "pulse", "color": [255, 0, 0]})
        self.assertAlmostEqual(len(a["envelope"]), a["seconds"] * 10, delta=1)
        self.assertEqual(plan["furbies"]["pink"]["clips"]["b"]["light"]["effect"], "voice")  # bloodshot
        self.assertEqual(plan["furbies"]["blue"]["clips"]["c"]["light"]["effect"], "candle")  # pumpkin
        self.assertNotIn("idle", plan["furbies"]["pink"])  # idle_glow is off unless asked for
        # The checksum the Furby will report for each DLC
        import zlib
        with open(os.path.join(self.temp_dir, "pink.dlc"), "rb") as f:
            self.assertEqual(plan["furbies"]["pink"]["checksum"], zlib.adler32(f.read()))

    def test_assign_slots_keeps_clips_where_they_were(self):
        """Adding, renaming and removing clips leaves the other clips on their actions"""
        import halloween
        slots = [(75, 0, n, 0) for n in range(6)]
        s = ["75-0-%d-0" % n for n in range(6)]
        log = []

        def assign(entry, defined, present=None):
            return halloween.assign_slots(entry, defined, defined if present is None else present, slots, "pink",
                                          log.append)  # fmt: skip
        # No lock: name order, as halloween.py did before it had one
        codes, entry = assign(None, {"b", "c", "d"})
        self.assertEqual(entry["clips"], {"b": s[0], "c": s[1], "d": s[2]})
        self.assertEqual(codes["b"], (75, 0, 0, 0))
        # A new clip that sorts first takes the first free slot; nothing else moves
        _, entry = assign(entry, {"a", "b", "c", "d"})
        self.assertEqual(entry["clips"], {"a": s[3], "b": s[0], "c": s[1], "d": s[2]})
        # Renaming c: c's slot is retired, and the new name takes a fresh slot rather than it
        _, entry = assign(entry, {"a", "b", "cee", "d"})
        self.assertEqual(entry["clips"], {"a": s[3], "b": s[0], "cee": s[4], "d": s[2]})
        self.assertEqual(entry["retired"], {"c": s[1]})
        # Removing d retires it too; bringing c back returns it to its old slot
        _, entry = assign(entry, {"a", "b", "c", "cee"})
        self.assertEqual(entry["clips"], {"a": s[3], "b": s[0], "c": s[1], "cee": s[4]})
        self.assertEqual(entry["retired"], {"d": s[2]})
        # A clip whose file is missing keeps its slot, so making it later moves nothing
        _, entry = assign(entry, {"a", "b", "c", "cee"}, present={"a", "b"})
        self.assertEqual(entry["clips"], {"a": s[3], "b": s[0], "c": s[1], "cee": s[4]})
        # When only retired slots are left, a new clip takes one and the tombstone goes
        _, entry = assign(entry, {"a", "b", "c", "cee", "e", "f"})
        self.assertEqual(entry["clips"]["e"], s[5])
        self.assertEqual(entry["clips"]["f"], s[2])
        self.assertEqual(entry["retired"], {})
        self.assertEqual(log, [])
        # A slot that's no longer a quick slot moves, and says so
        _, entry = assign({"clips": {"a": "75-0-9-9", "b": s[0]}}, {"a", "b"})
        self.assertEqual(entry["clips"], {"a": s[1], "b": s[0]})
        self.assertIn("75-0-9-9 is no longer a quick slot", log[0])

    def test_changes_message(self):
        """The build says which Furbies to reflash, comparing checksums with the last show.json"""
        import halloween
        old = {"furbies": {"pink": {"checksum": 1}, "blue": {"checksum": 2}}, "scenes": []}
        self.assertIn("First build", halloween.changes_message(None, old))
        self.assertEqual(halloween.changes_message(old, old), "Nothing changed since the last build.")
        new = {"furbies": {"pink": {"checksum": 1}, "blue": {"checksum": 2}}, "scenes": [["pink.a"]]}
        self.assertIn("No DLC changed: just redeploy show.json", halloween.changes_message(old, new))
        new = {"furbies": {"pink": {"checksum": 9}, "blue": {"checksum": 2}}, "scenes": []}
        msg = halloween.changes_message(old, new)
        self.assertTrue(msg.startswith("Only pink.dlc changed: reflash pink and redeploy show.json"), msg)
        self.assertIn("--only pink", msg)
        new = {"furbies": {"pink": {"checksum": 9}, "blue": {"checksum": 8}}, "scenes": []}
        self.assertIn("pink.dlc and blue.dlc changed: reflash both", halloween.changes_message(old, new))

    def test_show_toml_mistakes(self):
        """A typo or a bad value in show.toml fails at once, saying where, rather than quietly doing nothing"""
        import halloween

        def load(furbies, show='gap = 0.5\nevery = [20, 45]'):
            path = os.path.join(self.temp_dir, "show.toml")
            with open(path, "w") as f:
                f.write('[show]\n%s\n%s\n[[scenes]]\nsteps = ["pink.a"]\n' % (show, furbies))
            return halloween.load_show(path)

        good = '[furbies.pink.clips]\na = { path = "a.wav", start = 11, seconds = 2 }\n'
        self.assertEqual(load(good)["furbies"]["pink"]["clips"]["a"]["start"], 11)  # left as written...
        self.assertEqual(halloween.clip_spec({"path": "a.wav", "start": 11})["start"], "11")  # ...and read as text
        for furbies, show, message in (
            ('[furbies.Pink.clips]\na = "a.wav"\n', None, "'Pink' won't work as a DLC name"),
            ('[furbies.pink.clips]\na = { path = "a.wav", secconds = 2 }\n', None, "did you mean 'seconds'"),
            ('[furbies.pink.clips]\na = { path = "a.wav", seconds = -1 }\n', None, "clips.a seconds"),
            ('[furbies.pink.clips]\na = { path = "a.a18", seconds = 2 }\n', None, "an .a18 can't be cut"),
            ('[furbies.pink.clips]\na = { start = "1:00" }\n', None, "clips.a needs a path"),
            ('[furbies.pink]\nlight = { color = [300, 0, 0] }\n[furbies.pink.clips]\na = "a.wav"\n', None, "0-255"),
            ('[furbies.pink]\nlight = { colour = [255, 0, 0] }\n[furbies.pink.clips]\na = "a.wav"\n', None,
             "did you mean 'color'"),
            ('[furbies.pink]\nantenna = [255, 0, 0]\n', None, "needs clips"),
            (good, "gap = 0.5\nevery = [45, 20]", "[shortest, longest]"),
            (good, "gap = 0.5\nevery = [20, 45]\ncooldwn = 5", "did you mean 'cooldown'"),
            (good, "every = [20, 45]", "gap should be a number"),
        ):
            with self.subTest(message=message):
                with self.assertRaises(SystemExit) as e:
                    load(furbies, *([show] if show else []))
                self.assertIn(message, str(e.exception))
        # voices.py reads a show.toml with no [show]; only the build needs it
        path = os.path.join(self.temp_dir, "voices.toml")
        with open(path, "w") as f:
            f.write(good + '[[scenes]]\nsteps = ["pink.a"]\n')
        show = halloween.load_show(path)
        with self.assertRaises(SystemExit) as e:
            halloween.build_show(show, self.temp_dir)
        self.assertIn("needs a [show] table", str(e.exception))

    def test_failed_build_keeps_the_last_good_one(self):
        """If one Furby's DLC fails to build, neither DLC nor show.json changes"""
        import halloween
        clip = "./audio/new_audio/darkside_wav.a18"
        show = {
            "show": {"gap": 0.5, "every": [30, 60]},
            "furbies": {"pink": {"eyes": ["demon"], "clips": {"a": clip}},
                        "blue": {"eyes": ["pumpkin"], "clips": {"b": clip}}},
            "scenes": [{"steps": ["pink.a", "blue.b"]}],
        }
        halloween.build_show(show, self.temp_dir)
        names = ("pink.dlc", "blue.dlc", "show.json")

        def contents():
            out = {}
            for name in names:
                with open(os.path.join(self.temp_dir, name), "rb") as f:
                    out[name] = f.read()
            return out

        before = contents()
        show["furbies"]["pink"]["eyes"] = ["storm"]  # pink's DLC would change...
        show["furbies"]["blue"]["eyes"] = ["no-such-theme"]  # ...but blue's can't build
        with self.assertRaises(SystemExit):
            halloween.build_show(show, self.temp_dir)
        self.assertEqual(contents(), before)
        self.assertEqual([f for f in os.listdir(self.temp_dir) if f.endswith(".tmp")], [])

    def test_build_show_with_lock(self):
        """With a lock, adding a clip to one Furby leaves the other's DLC alone and moves no clip"""
        import contextlib
        import io
        import json

        import halloween
        clip = "./audio/new_audio/darkside_wav.a18"
        show = {
            "show": {"gap": 0.5, "every": [30, 60]},
            "furbies": {
                "pink": {"eyes": ["demon"], "clips": {"b": clip, "c": clip}},
                "blue": {"eyes": ["pumpkin"], "clips": {"x": clip}},
            },
            "scenes": [{"steps": ["pink.b", "blue.x"]}, {"steps": ["pink.c"]}],
        }
        lock = os.path.join(self.temp_dir, "slots.lock.json")

        def build():
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                with open(halloween.build_show(show, self.temp_dir, lock_path=lock)) as f:
                    return json.load(f), out.getvalue()
        first, out = build()
        self.assertIn("First build", out)
        self.assertTrue(os.path.exists(lock))
        show["furbies"]["pink"]["clips"]["a"] = "./audio/new_audio/imperial_march-16000_wav.a18"  # sorts first
        second, out = build()
        for k in ("b", "c"):
            self.assertEqual(second["furbies"]["pink"]["clips"][k]["action"], first["furbies"]["pink"]["clips"][k]["action"])
        self.assertEqual(second["furbies"]["blue"]["checksum"], first["furbies"]["blue"]["checksum"])
        self.assertIn("Only pink.dlc changed: reflash pink and redeploy show.json", out)
        self.assertIn("pink.dlc: ", out)  # the size report
        with open(lock) as f:
            self.assertEqual(set(json.load(f)["furbies"]["pink"]["clips"]), {"a", "b", "c"})
        # --reshuffle puts the clips back in name order
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with open(halloween.build_show(show, self.temp_dir, lock_path=lock, reshuffle=True)) as f:
                third = json.load(f)
        slots = [list(c) for c in halloween.quick_slots(dlc("./dlc/dlc2/tu003410.dlc"))]
        self.assertEqual([third["furbies"]["pink"]["clips"][k]["action"] for k in "abc"], slots[:3])

    def test_dlc_budget(self):
        """The size report's parts add up to the DLC, and it says what to cut when it's too big"""
        import halloween
        import spooky_eyes
        D = dlc("./dlc/dlc2/tu003410.dlc")
        slots = halloween.quick_slots(D)
        codes = {"a": slots[0], "b": slots[1]}
        path = spooky_eyes.build(
            "demon",
            clips={slots[0]: "./audio/new_audio/darkside_wav.a18", slots[1]: "./audio/new_audio/imperial_march-16000_wav.a18"},
            out_dir=self.temp_dir,
            name="pink",
            eyes={slots[1]: "ghost"},
        )
        budget = halloween.dlc_budget(path, codes, ["demon", "ghost"])
        self.assertEqual(budget["total"], os.path.getsize(path))
        self.assertEqual(sum(budget["clips"].values()) + budget["eyes"] + budget["base"], budget["total"])
        built = dlc(path)
        for k, code in codes.items():
            track = spooky_eyes._tracks(built, code)[0]
            self.assertEqual(budget["clips"][k], len(built.dlc_sections["AMF"].tracks[track]))
        self.assertEqual(set(budget["themes"]), {"demon", "ghost"})
        self.assertGreater(budget["themes"]["demon"], 20_000)  # each theme is about 37 KB
        self.assertLess(sum(budget["themes"].values()), budget["eyes"])
        report = halloween.budget_report("pink", budget)
        self.assertIn("pink.dlc: %d of 350 KB" % round(budget["total"] / 1000), report)
        self.assertLessEqual(len(report.splitlines()), 4)
        # Judge the warning against a roomy limit, so it doesn't hang on what two themes cost
        self.assertNotIn("Warning", halloween.budget_report("pink", budget, limit=budget["total"] * 2))
        self.assertIn("Warning", halloween.budget_report("pink", budget, limit=budget["total"] + 1000))
        # Over the limit, it suggests clips not in any scene first, then the largest
        tight = budget["total"] - 1000
        over = halloween.budget_report("pink", budget, unused={"a"}, limit=tight)
        self.assertIn("OVER", over)
        self.assertIn("drop a (in no scene", over)
        biggest = max(budget["clips"], key=budget["clips"].get)
        over = halloween.budget_report("pink", budget, limit=tight)
        self.assertIn("cut %s by 0.5 s" % biggest, over)
        self.assertIn("drop an eye theme", over)

    def test_clip_text_doesnt_change_build(self):
        """A voice line's text is for voices.py: the DLCs and show.json come out the same with or without it"""
        import json

        import halloween
        clip = "./audio/new_audio/darkside_wav.a18"
        self.assertEqual(halloween.clip_spec({"path": clip, "text": "Boo!"})["text"], "Boo!")

        def show(text):
            extra = {"text": "Boo! Kah scare you?"} if text else {}
            return {
                "show": {"gap": 0.5, "every": [30, 60]},
                "furbies": {
                    "pink": {"theme": "demon", "clips": {"a": {"path": clip, **extra}}},
                    "blue": {"theme": "pumpkin", "clips": {"b": {"path": clip, "before": 0.4, **extra}}},
                },
                "scenes": [{"steps": ["pink.a", "blue.b"]}],
            }
        outputs = []
        for text in (False, True):
            out_dir = os.path.join(self.temp_dir, "with" if text else "without")
            with open(halloween.build_show(show(text), out_dir)) as f:
                plan = json.load(f)
            dlcs = []
            for name in ("pink", "blue"):
                with open(os.path.join(out_dir, name + ".dlc"), "rb") as f:
                    dlcs.append(f.read())
                for info in plan["furbies"][name]["clips"].values():
                    self.assertNotIn("text", info)
            outputs.append((dlcs, plan))
        self.assertEqual(outputs[0], outputs[1])

    def test_envelope(self):
        """A clip's envelope is one loudness digit per 100 ms of what the Furby plays"""
        import halloween
        for path in ("./audio/new_audio/darkside_wav.a18", "./audio/new_audio/imperial_march-16000_wav.a18"):
            env = halloween.envelope(path)
            seconds = (os.path.getsize(path) - 6) / halloween.A18_BYTES_PER_SECOND
            self.assertAlmostEqual(len(env), seconds * 10, delta=1)
            self.assertTrue(env.isdigit())
            self.assertIn("9", env)  # its loudest moment
        self.assertTrue(halloween.envelope("./audio/new_audio/darkside_wav.a18").startswith("0000"))  # it opens quietly
        # Something the codec can't read just loses its envelope (the light glows at full volume)
        from unittest import mock
        bad = os.path.join(self.temp_dir, "bad.a18")
        with open(bad, "wb") as f:
            f.write(b"\x00" * 64)
        with mock.patch("builtins.print"):
            self.assertIsNone(halloween.envelope(bad))

    def test_clip_lights(self):
        """A clip's light comes from its eyes, then the Furby's light, then its own"""
        import halloween
        self.assertEqual(halloween.clip_light("pink", {}, "a", "storm", {}), {"effect": "lightning", "color": [60, 80, 255]})
        # A Furby-wide color keeps each Furby recognizable, while the effect still matches the eyes
        furby = {"light": {"color": [0, 255, 0]}, "antenna": [1, 2, 3]}
        self.assertEqual(halloween.clip_light("pink", furby, "a", "pumpkin", {}), {"effect": "candle", "color": [0, 255, 0]})
        # A clip names an effect, an eye theme's light, or a table
        self.assertEqual(halloween.clip_light("pink", {}, "a", "demon", {"light": "voice"})["effect"], "voice")
        self.assertEqual(halloween.clip_light("pink", {}, "a", "demon", {"light": "ghost"}), halloween.THEME_LIGHTS["ghost"])
        self.assertEqual(halloween.clip_light("pink", {}, "a", "demon", {"light": {"color": [9, 9, 9]}}), {"effect": "pulse", "color": [9, 9, 9]})
        self.assertIsNone(halloween.clip_light("pink", {}, "a", "demon", {"light": "off"}))
        # No eye theme light: the antenna color, following the voice; with none, no light
        self.assertEqual(halloween.clip_light("pink", {"antenna": [1, 2, 3]}, "a", None, {}), {"effect": "voice", "color": [1, 2, 3]})
        self.assertIsNone(halloween.clip_light("pink", {}, "a", None, {}))
        with self.assertRaises(SystemExit):
            halloween.clip_light("pink", {}, "a", "demon", {"light": "disco"})
        import spooky_eyes
        self.assertEqual(set(halloween.THEME_LIGHTS), set(spooky_eyes.THEMES))  # every eye theme has a light

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

    def test_light_effects(self):
        """Each antenna effect gives valid colours, follows the sound, and repeats exactly"""
        import furbyshow
        red = [255, 0, 0]
        for effect in furbyshow.EFFECTS + ("from-the-future",):
            for level in (0, 0.5, 1):
                for t in range(0, 3000, 70):
                    rgb = furbyshow.light_rgb({"effect": effect, "color": red}, t, level, seed=3)
                    self.assertEqual(len(rgb), 3)
                    self.assertTrue(all(isinstance(c, int) and 0 <= c <= 255 for c in rgb), (effect, rgb))
                    furbyshow.antenna_command(rgb)  # a byte each, or this raises
        light = lambda effect: {"effect": effect, "color": red}  # noqa: E731
        frames = lambda effect, level, seed=0: [furbyshow.light_rgb(light(effect), t, level, seed) for t in range(0, 10000, 100)]  # noqa: E731
        self.assertEqual(set(frames("steady", 0)), {(255, 0, 0)})
        self.assertEqual(set(frames("off", 1)), {(0, 0, 0)})
        self.assertEqual(set(frames("from-the-future", 0)), {(255, 0, 0)})  # an unknown effect glows steady
        self.assertLess(frames("voice", 0)[0][0], frames("voice", 1)[0][0])  # louder is brighter
        self.assertGreater(len(set(frames("candle", 0.5))), 5)  # it flickers
        self.assertEqual(frames("candle", 0.5), frames("candle", 0.5))  # the same way every time
        self.assertNotEqual(frames("candle", 0.5, seed=1), frames("candle", 0.5, seed=2))  # but not in step with the other Furby
        flashes = lambda level: frames("lightning", level).count((255, 255, 255))  # noqa: E731
        self.assertGreater(flashes(0), 0)
        self.assertGreater(flashes(1), 3 * flashes(0))  # far more flashes in a scream
        self.assertGreater(len(set(frames("cycle", 1))), 20)  # round the wheel
        self.assertEqual(furbyshow.hue_rgb(0), (255, 0, 0))
        self.assertEqual(furbyshow.hue_rgb(1 / 3), (0, 255, 0))
        # Envelopes: a digit per 100 ms; none means full volume, past the end silence
        self.assertEqual(furbyshow.envelope_level(None, 500), 1.0)
        self.assertEqual(furbyshow.envelope_level("09", 50), 0.0)
        self.assertEqual(furbyshow.envelope_level("09", 150), 1.0)
        self.assertEqual(furbyshow.envelope_level("09", 250), 0.0)
        # A show.json from before lights: the antenna color glows steady; "off" means none
        self.assertEqual(furbyshow.clip_light({"antenna": red}, {}), {"effect": "steady", "color": red})
        self.assertIsNone(furbyshow.clip_light({}, {}))
        self.assertIsNone(furbyshow.clip_light({"antenna": red}, {"light": {"effect": "off"}}))

    def test_light_follows_line(self):
        """The antenna animates during each line, at most light_hz, and rests when the line or scene ends"""
        import asyncio
        import time

        import furbyshow
        sent = []  # (name, seconds since start, bytes)

        class F(furbyshow.Furby):
            def connected(self):
                return True

            async def _write(self, data):
                sent.append((self.name, time.monotonic() - start, bytes(data)))
                if data[0] == 0x13:
                    self.on_response(furbyshow.SEQUENCE_PLAYING)

        plan = {
            "gap": 0, "every": [1, 2], "scenes": [], "light_hz": 12.5,  # a fraction is rounded down, not fatal
            "furbies": {
                "pink": {"idle": [20, 0, 0], "clips": {"a": {
                    "action": [75, 0, 0, 2], "seconds": 0.6,
                    "light": {"effect": "voice", "color": [255, 0, 0]}, "envelope": "000999"}}},
                "blue": {"clips": {"a": {
                    "action": [75, 0, 4, 4], "seconds": 1.0,
                    "light": {"effect": "cycle", "color": [255, 0, 255]}, "envelope": "9999999999"}}},
            },
        }
        show = furbyshow.Show(plan, None, log=lambda *_: None)
        for name in ("pink", "blue"):
            show.furbies[name] = F(name)
            show.furbies[name].name = name
        start = time.monotonic()
        asyncio.run(show.play_step("pink.a + blue.a"))
        lights = lambda name: [(t, d[1:]) for n, t, d in sent if n == name and d[0] == 0x14]  # noqa: E731
        # Lit before the triggers, so a duet's two lines start together
        self.assertEqual([d[0] for _, _, d in sent[:4]], [0x14, 0x14, 0x13, 0x13])
        # Pink follows its envelope: dim while quiet, bright while loud, then off at its own
        # clip's end rather than the duet's
        pink = lights("pink")
        self.assertEqual([c for _, c in pink], [bytes(furbyshow.scale([255, 0, 0], 0.15)), bytes([255, 0, 0]), bytes(3)])
        blue = lights("blue")
        self.assertLess(pink[-1][0], blue[-1][0] - 0.2)
        # Blue changes every frame, but never faster than light_hz (12), and ends dark
        self.assertGreater(len(blue), 5)
        gaps = [blue[i + 1][0] - blue[i][0] for i in range(len(blue) - 2)]  # the off at the end comes when it comes
        self.assertGreater(min(gaps), 1 / 12 - 0.015)
        self.assertEqual(blue[-1][1], bytes(3))
        self.assertTrue(all(d[0] != 0x14 for n, t, d in sent if t > blue[-1][0]))  # nothing after
        # In a scene, a Furby with an idle glow rests at it between lines, and goes dark at the end
        sent.clear()
        asyncio.run(show.play_scene(["pink.a", "blue.a"]))
        pink = [c for _, c in lights("pink")]
        self.assertEqual(pink[0], bytes([20, 0, 0]))  # from the start of the scene
        self.assertEqual(pink[-2:], [bytes([20, 0, 0]), bytes(3)])  # through blue's line, then dark
        # An interrupted line still stops its light and turns the antenna off
        sent.clear()

        async def broken(seconds):
            await asyncio.sleep(0.15)
            raise OSError("disconnected")

        show.sleep = broken
        start = time.monotonic()
        with self.assertRaises(OSError):
            asyncio.run(show.play_step("blue.a"))
        blue = lights("blue")
        self.assertEqual(blue[-1][1], bytes(3))
        self.assertLess(blue[-1][0], 0.3)

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

    def test_furby_drops_mid_scene(self):
        """A Furby that drops doesn't end the scene: the other finishes it, and the show looks again soon"""
        import asyncio

        import furbyshow
        sent = []

        class F(furbyshow.Furby):
            def __init__(self, name, up=True, breaks=False):
                super().__init__(name)
                self.name, self.up, self.breaks = name, up, breaks

            def connected(self):
                return self.up

            async def _write(self, data):
                if self.breaks:  # still looks connected, but the write fails
                    raise OSError("disconnected")
                sent.append((self.name, bytes(data)))
                if data[0] == 0x13:
                    self.on_response(furbyshow.SEQUENCE_PLAYING)

        async def sleep(seconds):
            pass

        light = {"effect": "steady", "color": [255, 0, 0]}
        plan = {
            "gap": 0, "every": [30, 60], "scenes": [["pink.a + blue.a", "blue.b", "pink.a"]],
            "furbies": {
                "pink": {"clips": {"a": {"action": [75, 0, 0, 2], "seconds": 1.0}}},
                "blue": {"clips": {"a": {"action": [75, 0, 4, 4], "seconds": 1.0, "light": light},
                                   "b": {"action": [75, 0, 5, 5], "seconds": 1.0}}},
            },
        }
        logs = []
        show = furbyshow.Show(plan, None, sleep=sleep, log=logs.append)
        show.furbies = {"pink": F("pink"), "blue": F("blue", breaks=True)}
        self.assertEqual(asyncio.run(show.run_once()), furbyshow.RETRY_FIND_S)
        self.assertEqual([d for n, d in sent if d[0] == 0x13], [furbyshow.trigger_command((75, 0, 0, 2))] * 2)
        self.assertTrue(any(line.startswith("Skipping blue.a: blue dropped") for line in logs), logs)
        self.assertFalse(any("interrupted" in line for line in logs), logs)
        # One that's known to be gone is skipped without trying it
        sent.clear()
        logs.clear()
        show.furbies["blue"] = F("blue", up=False)
        asyncio.run(show.play_scene(plan["scenes"][0]))
        self.assertEqual([n for n, d in sent if d[0] == 0x13], ["pink", "pink"])
        self.assertEqual(logs[1:], ["Skipping blue.a: blue dropped", "Skipping blue.b: blue dropped"])
        # A scene with nobody missing waits as usual
        show.furbies["blue"] = F("blue")
        self.assertGreaterEqual(asyncio.run(show.run_once()), 30)

    def test_greeting_with_a_furby_missing(self):
        """A greeting plays with whoever's here at once, and starts the cooldown even as a fallback"""
        import asyncio

        import furbyshow

        events = []  # triggers and scans, in order

        class F(furbyshow.Furby):
            def connected(self):
                return True

            async def _write(self, data):
                if data[0] == 0x13:
                    events.append("play")
                    self.on_response(furbyshow.SEQUENCE_PLAYING)

        async def find(known):
            events.append("scan")
            return []

        async def sleep(seconds):
            pass

        clip = {"action": [75, 0, 0, 2], "seconds": 1.0}
        plan = {
            "gap": 0, "every": [30, 60], "cooldown": 10,
            "scenes": [["pink.a"], ["pink.b"]], "greetings": [["pink.b"]],
            "furbies": {"pink": {"clips": {"a": clip, "b": clip}}, "blue": {"clips": {"a": clip}}},
        }
        show = furbyshow.Show(plan, find, sleep=sleep, log=lambda *_: None)
        show.furbies["pink"] = F("aa")
        asyncio.run(show.run_once(greeting=True))
        # Greeted first, then the scan for blue, so a busy porch can't keep it from reconnecting
        self.assertEqual(events, ["play", "scan"])
        self.assertEqual(show.last, ["pink.b"])
        events.clear()
        asyncio.run(show.run_once())
        self.assertEqual(events, ["scan", "play"])  # the timer looks for blue first
        # A greeting that needs blue falls back to another scene, and still starts the cooldown
        plan["greetings"] = [["pink.b", "blue.a"]]
        show.greeted = None
        events.clear()
        asyncio.run(show.run_once(greeting=True))
        self.assertEqual(events, ["scan", "play"])
        self.assertIsNotNone(show.greeted)

    def test_keep_alive(self):
        """A connected Furby gets a keepalive after a few quiet seconds, and a failed one doesn't stop it"""
        import asyncio
        from unittest import mock

        import furbyshow
        clock = [0]
        sent = []

        class F(furbyshow.Furby):
            checks = 0

            def connected(self):
                self.checks += 1
                return self.checks <= 9  # 0 s to 8 s

            async def _write(self, data):
                sent.append((clock[0], bytes(data)))
                if len(sent) == 1:
                    raise OSError("busy")

        async def tick(seconds):
            clock[0] += 1000

        with mock.patch.object(furbyshow, "ticks_ms", lambda: clock[0]), \
                mock.patch.object(furbyshow.asyncio, "sleep", tick), mock.patch("builtins.print"):
            furby = F("aa")
            asyncio.run(furby.keep_alive())
        # Quiet for over 3 s at 4 s, then again 4 s after that ping (the failed one counts as sent)
        self.assertEqual(sent, [(4000, furbyshow.KEEPALIVE), (8000, furbyshow.KEEPALIVE)])

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
        # Played scenes wait their turn, but a missing Furby's scenes don't block the rest
        scenes = [["pink.a"], ["pink.b"], ["blue.c"]]
        self.assertEqual(furbyshow.pick_scene(scenes, {"pink"}, played=[["pink.a"]]), ["pink.b"])
        self.assertEqual(furbyshow.pick_scene(scenes, {"pink"}, ["pink.b"], [["pink.a"], ["pink.b"]]), ["pink.a"])

    def test_show_shuffles_scenes(self):
        """Every scene plays once before any repeats, and a new pass never opens with the last one"""
        import asyncio

        import furbyshow

        plan = {"furbies": {"pink": {"clips": {}}}, "gap": 0, "every": [0, 0], "scenes": [["pink.%d" % i] for i in range(4)]}
        show = furbyshow.Show(plan, find=None, log=lambda line: None)
        show.furbies = {"pink": types.SimpleNamespace(connected=lambda: True)}
        show.reconnect = lambda: asyncio.sleep(0)
        show.play_scene = lambda scene: asyncio.sleep(0)
        order = []
        for _ in range(40):
            asyncio.run(show.run_once())
            order.append(show.last[0])
        for start in range(0, 40, 4):
            self.assertEqual(sorted(order[start : start + 4]), ["pink.%d" % i for i in range(4)])
        self.assertTrue(all(order[i] != order[i + 1] for i in range(len(order) - 1)))

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
# Every effect makes bytes the antenna command takes
for effect in furbyshow.EFFECTS:
    for t in range(0, 2000, 90):
        furbyshow.antenna_command(furbyshow.light_rgb({"effect": effect, "color": [255, 80, 0]}, t, t / 2000, 5))
# A line's light runs in real time alongside it, then goes dark
plan["light_hz"] = 15
plan["furbies"]["pink"]["clips"]["a"].update(seconds=0.3, envelope="294", light={"effect": "candle", "color": [255, 80, 0]})
async def lit():
    show = furbyshow.Show(plan, find, log=lambda *a: None)
    await show.connect_missing()
    sent.clear()
    await show.play_step("pink.a")
asyncio.run(lit())
lights = [d for d in sent if d[0] == 0x14]
assert len(lights) > 2, sent
assert lights[-1] == bytes([0x14, 0, 0, 0]), lights
assert furbyshow.slot_name(b"\\x73\\x0d____PINK") == "PINK"
# MicroPython's dicts forget show.json's order, so the board takes it from the text
import json
text = '{"scenes": [], "furbies": {"pink": {"clips": {}}, "blue": {"clips": {}}}}'
assert furbyshow.plan_order(text, json.loads(text)["furbies"]) == ["pink", "blue"]
show = furbyshow.Show({"furbies": {"blue": {}, "pink": {}}}, find, order=["pink", "blue"])
assert show.waiting_for() == "pink" and show.waiting_index() == 0, show.waiting_for()
assert "only the pink Furby" in show.guidance(), show.guidance()
print("ok")
"""
        result = subprocess.run(["micropython", "-c", script], capture_output=True, text=True, check=False,
                                env=dict(os.environ, MICROPYPATH=".frozen:."))
        self.assertEqual(result.stdout.strip(), "ok", result.stderr)


class TestPowerUp(unittest.TestCase):
    """The show asks for Furbies one at a time, since two woken together sing and can't be found"""

    def test_plan_order(self):
        """The board reads who's first from show.json's text, which MicroPython's dicts forget"""
        import json

        import furbyshow
        text = json.dumps({"scenes": [["blue.a"]], "furbies": {
            "pink": {"clips": {"blue": {}}},  # a clip that shares a later Furby's name
            "blue": {"clips": {}}, "green": {}}})
        self.assertEqual(furbyshow.plan_order(text, {"green": 1, "blue": 1, "pink": 1}), ["pink", "blue", "green"])
        self.assertEqual(furbyshow.plan_order(text, ["zed", "pink"]), ["pink", "zed"])  # unknown names go last
        show = furbyshow.Show({"order": ["blue", "pink"], "furbies": {"pink": {}, "blue": {}}}, None)
        self.assertEqual(show.waiting_for(), "blue")  # an explicit order in show.json wins

    def test_guided_power_up(self):
        """porch.py says who to power up next, once per change, including after a drop"""
        import asyncio
        import sys
        from unittest import mock

        import furbyshow
        import porch
        clip = {"action": [75, 0, 0, 1], "seconds": 0.0}
        plan = {"gap": 0, "every": [30, 60], "scenes": [["pink.a", "blue.a"]], "furbies": {
            "pink": {"clips": {"a": clip}}, "blue": {"clips": {"a": clip}}}}
        pink, blue = FakeBleFurby("aa", "pink"), FakeBleFurby("bb", "blue")
        # One scan per run_once while someone's missing; the last repeats
        scans = [[], [pink], [], [blue], []]
        log = []

        async def sleep(_):
            pass

        async def run():
            show = furbyshow.Show(plan, porch.find, sleep=sleep, log=log.append)
            for n in range(9):
                if n == 5:
                    blue.is_connected = False  # blue drops mid-show
                if n == 8:
                    pink.is_connected = False  # then pink: both gone, and neither advertising
                await show.run_once()
            for task in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
                task.cancel()

        with mock.patch.dict(sys.modules, {"bleak": fake_bleak(scans)}), mock.patch("builtins.print"):
            asyncio.run(run())
        # Each said once, when it changed, though the show scanned nine times
        said = [line for line in log if not line.startswith(("Connected", "Scene"))]
        self.assertEqual(said, [
            "Put batteries in (or wake) only the pink Furby. Wake the others once it connects.",
            "Pink is connected. Now power up blue.",
            "All Furbies connected: pink, blue.",
            "Blue dropped. Pink is still connected; wake blue again.",
            "Still no blue. Take its batteries out and put them back to wake it.",  # after 3 empty scans
            "If they're singing together, take the batteries out of one and power them up one at a time.",
        ])
        self.assertEqual(len(blue.triggers), 2)  # the scene played while both were connected


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
        size = len(data)

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
                    if len(self.received) == size:  # the whole file, not this 20-byte packet
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
                    self.received = b""
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

        # A fresh upload that reports the previous DLC's checksum is read again, then re-uploaded once
        for stale_reads, uploads in ((2, 1), (flash.CHECKSUM_READS, 2)):
            furby = FakeFurby()
            furby.stale = stale_reads
            say = furby.say

            def stale_say(data, furby=furby, say=say):
                if data[:1] == bytes([0x73]) and furby.stale:
                    furby.stale -= 1
                    data = bytes(data[:13]) + (checksum ^ 1).to_bytes(4, "big")
                say(data)

            furby.say = stale_say
            flasher = flash.Flasher(furby, log=logs.append, packet_delay=0)
            flasher.recheck_s = 0
            asyncio.run(flasher.flash(data, "____PINK.DLC"))
            self.assertEqual(len([w for w in furby.writes if w == (furbyshow.GP_WRITE, w[1]) and w[1][:1] == b"\x50"]), uploads)
            self.assertEqual(furby.active, {12})


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
        # A scene or clip that isn't in the built show lists what is, rather than a traceback
        porch.check_choice(plan, argparse.Namespace(clip="pink.a + blue.b", scene=0))
        with self.assertRaises(SystemExit) as e:
            porch.check_choice(plan, argparse.Namespace(clip=None, scene=1))
        self.assertIn("no scene 1. The built show has 1:\n  0  pink.a -> blue.b", str(e.exception))
        with self.assertRaises(SystemExit) as e:
            porch.check_choice(plan, argparse.Namespace(clip="pink.b", scene=None))
        self.assertIn("It has: blue.b, pink.a", str(e.exception))

    def test_rehearse_draws_antennas(self):
        """In a terminal, every lit antenna is a coloured block on one line, redrawn in place"""
        import io
        from unittest import mock

        import porch

        out = io.StringIO()
        out.isatty = lambda: True
        with mock.patch("sys.stdout", out):
            porch.show_antenna("pink", (255, 0, 0))
            porch.show_antenna("blue", (0, 0, 255))
            self.assertIn("\033[48;2;255;0;0m", out.getvalue().split("\r")[-1])
            self.assertIn("\033[48;2;0;0;255m", out.getvalue().split("\r")[-1])
            porch.show_antenna("pink", (0, 0, 0))
            porch.show_antenna("blue", (0, 0, 0))
        self.assertEqual(out.getvalue().split("\r")[-1], "\033[K  ")  # all dark: the line is cleared
        # Piped output gets no per-frame flood
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            porch.show_antenna("pink", (255, 0, 0))
        self.assertEqual(out.getvalue(), "")
        porch.show_antenna("pink", (0, 0, 0))


class TestFirmware(unittest.TestCase):
    """Run firmware/main.py on CPython, against stand-ins for aioble, bluetooth and machine"""

    def setUp(self):
        import asyncio
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
            IN, OUT, PULL_UP, PULL_DOWN, IRQ_FALLING, IRQ_RISING = 0, 1, 2, 5, 3, 4

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

        class Reset(Exception):
            pass

        def reset():
            raise Reset

        self.Reset = Reset
        self.fakes = {
            "aioble": types.SimpleNamespace(scan=scan),
            "bluetooth": types.SimpleNamespace(UUID=str),
            "machine": types.SimpleNamespace(Pin=Pin, WDT=WDT, reset=reset),
        }
        self.saved = {name: sys.modules.get(name) for name in self.fakes}
        sys.modules.update(self.fakes)
        self.main = self.load()

    def load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("firmware_main", "./firmware/main.py")
        main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main)
        return main

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

    def test_startup_crash(self):
        """If the show can't even load, the board says why, blinks three long blinks, and restarts"""
        import io
        import sys
        from contextlib import redirect_stdout
        from unittest import mock

        sys.modules["aioble"] = None  # as if deploy.sh never installed it
        levels = []
        out = io.StringIO()
        with mock.patch("time.sleep", lambda _: levels.append(self.pins.get("led"))), redirect_stdout(out):
            with mock.patch.object(self.fakes["machine"].Pin, "value",
                                   lambda pin, level=None: self.pins.__setitem__("led", level)):
                with self.assertRaises(self.Reset):
                    self.load()
        self.assertIn("aioble", out.getvalue())
        self.assertEqual(len(levels), 300)  # 30 s of 100 ms steps
        self.assertEqual(levels[:5], [1, 1, 1, 1, 0])
        # Holding the button still gets you to the REPL to fix the files, rather than a reset loop
        self.pins[47] = 0  # BUTTON_PIN; the module that would say so didn't load
        with redirect_stdout(io.StringIO()) as out, self.assertRaises(ImportError):
            self.load()
        self.assertIn("safe boot", out.getvalue())

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
                mock.patch.object(asyncio, "ThreadSafeFlag", asyncio.Event, create=True), \
                mock.patch.object(self.main, "PIR_PIN", None):
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

    def test_status_light(self):
        """The LED blinks once for the first Furby to power up, twice for the second, and so on"""
        import asyncio
        from unittest import mock

        class FakeShow:
            playing, index, is_stuck = False, 0, False

            def waiting_index(self):
                return self.index

            def stuck(self):
                return self.is_stuck

        show = FakeShow()
        pattern = self.main.led_pattern
        self.assertEqual(pattern(show), (1, 1, 0, 0) + (0,) * 8)  # 1 blink: power up the first
        show.index = 1
        self.assertEqual(pattern(show), (1, 1, 0, 0, 1, 1, 0, 0) + (0,) * 8)  # 2 blinks: the second
        show.is_stuck = True
        self.assertEqual(pattern(show), (1, 0))  # flicker: they may be singing together
        show.playing = True
        self.assertEqual(pattern(show), (1,))  # solid during a scene, as before
        show.playing, show.index = False, None
        self.assertEqual(pattern(show), (0,))  # off once everyone's connected

        # status_light steps through the pattern, and starts a new one from its first blink
        led = self.main.machine.Pin(self.main.LED_PIN, self.main.machine.Pin.OUT)
        levels = []
        show.index, show.is_stuck = 1, False

        async def sleep(_):
            levels.append(led.value())
            if len(levels) == 3:
                show.index = 0  # the first Furby dropped: blink once
            if len(levels) == 17:
                raise asyncio.CancelledError

        with mock.patch.object(self.main.asyncio, "sleep", sleep):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(self.main.status_light(show, led))
        self.assertEqual(levels, [1, 1, 0] + [1, 1, 0, 0] + [0] * 8 + [1, 1])

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

    def test_shared_eye_cels_fail(self):
        """Eyes sharing cels over blanked layers in under 16 cels is what eyesb, eyese and eyesh showed garbled"""
        from PIL import Image

        import eyecheck
        import spooky_eyes
        keys = [spooky_eyes._digit(d, spooky_eyes.RED).resize((128, 128), Image.LANCZOS) for d in (1, 2)]
        # eyese failed; eyesl (separate cels, 10) and eyesk (eyese padded to 18) passed
        for share, pad, fails in ((True, 0, True), (False, 0, False), (True, 8, False)):
            D = dlc(self.stock_path)
            spooky_eyes.install_animations(D, [(keys, [i * 2 // 38 for i in range(38)])], share=share, min_cels=0)
            CEL = D.dlc_sections["CEL"]
            CEL.cels.extend([row[:] for row in CEL.cels[0]] for _ in range(pad))
            D.trigger_custom_graphics((75, 0, 4, 4))
            errors = eyecheck.envelope(D)[0]
            self.assertEqual(any("share cels" in e for e in errors), fails, (share, pad, errors))

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


class TestEmulator(unittest.TestCase):
    """emulate.py's virtual Furby answers like the hardware, on a virtual clock"""

    def setUp(self):
        if not os.path.exists("./dlc/dlc2/tu003410.dlc"):
            self.skipTest("Test DLC file not found")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def build(self, name, n=2, **kw):
        """A small DLC with n clips on quick slots; returns (path, actions)."""
        import halloween
        import spooky_eyes

        slots = halloween.quick_slots(dlc("./dlc/dlc2/tu003410.dlc"))[:n]
        clip = "./audio/new_audio/darkside_wav.a18"
        path = spooky_eyes.build("demon", clips=dict.fromkeys(slots, clip), out_dir=self.temp_dir, name=name, **kw)
        return path, slots

    def test_virtual_time(self):
        """A long wait takes no real time"""
        import asyncio
        import time

        import emulate

        start = time.monotonic()
        _, seconds = emulate.run(asyncio.sleep(600))
        self.assertAlmostEqual(seconds, 600, places=3)
        self.assertLess(time.monotonic() - start, 1)

    def test_trigger_replies(self):
        """20:0c when idle, 20:07 while the last sequence runs, 20:0e when it ends; DLC info names it"""
        import zlib

        import emulate
        import furbyshow

        path, (action, _) = self.build("pink")
        D = dlc(path)
        busy, audio = emulate.sequence_seconds(D, action)
        self.assertGreater(audio, 1)
        self.assertGreaterEqual(busy, audio)
        furby = emulate.furby_class()("virtual", path, "____PINK.DLC")

        async def go():
            name = await furby.identify()
            first = await furby.command(furbyshow.trigger_command(action), expect=(b"\x20\x0c", b"\x20\x07"))
            again = await furby.command(furbyshow.trigger_command(action), expect=(b"\x20\x0c", b"\x20\x07"))
            ended = await furby.command(None, expect=furbyshow.SEQUENCE_ENDED, timeout=busy + 1)
            played = await furby.play(action)
            await furby.command(furbyshow.KEEPALIVE)
            await furby.set_antenna((255, 0, 0))
            return name, first, again, ended, played

        (name, first, again, ended, played), seconds = emulate.run(go())
        self.assertEqual((name, first, again, ended, played), ("pink", b"\x20\x0c", b"\x20\x07", b"\x20\x0e", True))
        with open(path, "rb") as f:
            self.assertEqual(furby.checksum, zlib.adler32(f.read()))
        events = [e for _, e, _ in furby.model.log]
        self.assertEqual(events.count("played"), 2)
        self.assertEqual(events.count("silent"), 1)
        self.assertIn("keepalive", events)
        self.assertEqual(furby.model.antenna, (255, 0, 0))
        self.assertLess(seconds, busy + 2)

    def plan(self, pink, blue):
        """Two Furbies; scene 0 has pink say both its lines back to back, the way that went silent."""
        path_p, (a, b) = pink
        path_b, (c, _) = blue
        clip = lambda action: {"action": list(action), "seconds": 0.5}  # noqa: E731
        return {
            "gap": 0.2,
            "every": [30, 60],
            "furbies": {
                "pink": {"clips": {"a": clip(a), "b": clip(b)}},
                "blue": {"clips": {"c": clip(c)}},
            },
            "scenes": [["pink.a", "pink.b"], ["pink.a + blue.c"]],
            "greetings": [],
        }

    def test_show_catches_silent_clips(self):
        """The old fire-and-forget play() leaves a line silent; today's waits for the Furby instead"""
        import types

        import emulate
        import furbyshow

        pink, blue = self.build("pink"), self.build("blue")
        plan = self.plan(pink, blue)
        dlcs = {"pink": pink[0], "blue": blue[0]}
        report = emulate.simulate(plan, dlcs)
        self.assertEqual([r["silent"] for r in report], [[], []])
        self.assertEqual([r["skipped"] for r in report], [[], []])
        self.assertGreater(report[0]["seconds"], report[0]["planned"] + 0.5)  # it waited for pink

        # furbyshow before 925f386: play() sent the trigger and moved on
        old = types.ModuleType("furbyshow_old")
        old.__dict__.update(furbyshow.__dict__)

        class Furby(furbyshow.Furby):
            async def play(self, action, patience_ms=0):
                await self.command(furbyshow.trigger_command(action))
                return True

        old.Furby = Furby
        report = emulate.simulate(plan, dlcs, engine=old)
        self.assertEqual(report[0]["silent"], ["pink 75-%d-%d-%d" % tuple(pink[1][1][1:])])
        self.assertEqual(report[1]["silent"], [])
        with __import__("unittest").mock.patch("builtins.print"):
            self.assertTrue(emulate.print_report(report))

    def test_emulate_cli(self):
        """emulate.py reads show.json and the DLCs beside it"""
        import json
        from unittest import mock

        import emulate

        pink, blue = self.build("pink"), self.build("blue")
        path = os.path.join(self.temp_dir, "show.json")
        with open(path, "w") as f:
            json.dump(self.plan(pink, blue), f)
        with mock.patch("builtins.print"):
            self.assertEqual(emulate.main([path, "--scene", "1"]), 0)
            self.assertEqual(emulate.main([path, "--worst"]), 0)
        with self.assertRaises(SystemExit):
            emulate.main([os.path.join(self.temp_dir, "nope.json")])
        elsewhere = os.path.join(self.temp_dir, "pink", "show.json")  # no DLCs beside it
        shutil.copy(path, elsewhere)
        with self.assertRaises(SystemExit):
            emulate.main([elsewhere])

    def test_flash(self):
        """flash.py's whole upload against the virtual Furby; eyes outside the envelope keep the old cels"""
        import emulate
        import flash
        import spooky_eyes

        good, _ = self.build("pink", n=1)
        multi = spooky_eyes.build(
            "demon",
            clips={spooky_eyes.DEMO_ACTIONS[0]: "./audio/new_audio/darkside_wav.a18"},
            eyes={spooky_eyes.DEMO_ACTIONS[0]: "ghost"},
            out_dir=self.temp_dir,
            name="probe",
        )
        client = emulate.VirtualClient()

        async def go(path):
            with open(path, "rb") as f:
                data = f.read()
            await flash.Flasher(client, log=lambda _: None, packet_delay=0).flash(data, flash.furby_filename(path))

        emulate.run(go(good))
        model = client.model
        with open(good, "rb") as f:
            self.assertEqual(model.slots[model.active]["data"], f.read())
        self.assertEqual(model.antenna, (0, 255, 0))
        cels = model.cels
        emulate.run(go(multi))
        self.assertEqual(len(model.slots), 1)  # flash.py deleted the old one first
        self.assertIs(model.cels, cels)
        self.assertTrue(any(e == "eyes keep the previous DLC's cels" for _, e, _ in model.log))
        stale = model.eyes(0x8401)[0].tobytes()
        self.assertNotEqual(stale, __import__("eyecheck").compose(model.dlc(), 0x8401)[0].tobytes())

        big = os.path.join(self.temp_dir, "big.dlc")
        with open(big, "wb") as f:
            f.write(bytes(emulate.MAX_UPLOAD + 100))
        with self.assertRaises(RuntimeError):
            emulate.run(go(big))
        self.assertEqual(model.antenna, (255, 0, 0))


class TestPreview(unittest.TestCase):
    """preview.py's virtual porch replays emulate's timeline, with the DLCs' own sound and eyes"""

    def setUp(self):
        if not os.path.exists("./dlc/dlc2/tu003410.dlc"):
            self.skipTest("Test DLC file not found")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_preview(self):
        import json
        import wave
        from unittest import mock

        import emulate
        import preview

        pink, blue = TestEmulator.build(self, "pink"), TestEmulator.build(self, "blue")
        plan = TestEmulator.plan(self, pink, blue)
        plan["furbies"]["pink"]["antenna"] = [255, 0, 0]  # a steady glow while pink speaks
        plan["greetings"] = [plan["scenes"][1]]
        path = os.path.join(self.temp_dir, "show.json")
        with open(path, "w") as f:
            json.dump(plan, f)
        out = os.path.join(self.temp_dir, "preview")
        with mock.patch("builtins.print"):
            self.assertEqual(preview.main(["--show", path, "--out", out]), 0)
        with open(os.path.join(out, "index.html")) as f:
            self.assertIn('<script src="data.js">', f.read())
        with open(os.path.join(out, "data.js")) as f:
            data = json.loads(f.read().split("window.PREVIEW = ", 1)[1].rstrip().rstrip(";"))
        self.assertEqual((data["timer"], data["greetings"]), ([0], [1]))

        # Sound and eyes from the DLCs
        clip = data["furbies"]["pink"]["clips"]["a"]
        with wave.open(os.path.join(out, clip["audio"])) as w:
            busy, audio = emulate.sequence_seconds(dlc(pink[0]), pink[1][0])
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), audio, delta=0.1)
        words = [s["eyes"] for s in clip["eyes"] if "eyes" in s]
        self.assertTrue(words)
        sprite = data["furbies"]["pink"]["sprites"][words[0]]
        self.assertGreater(sprite["frames"], 1)
        self.assertTrue(os.path.exists(os.path.join(out, sprite["src"])))
        self.assertIn("motor 0x", clip["motor"])

        # The timeline is emulate's, scene by scene, in both timings
        dlcs = {"pink": pink[0], "blue": blue[0]}
        for mode, worst in (("typical", False), ("worst", True)):
            report = emulate.simulate(plan, dlcs, durations=emulate.load_durations(worst=worst))
            scenes = data["timelines"][mode]
            self.assertEqual([s["seconds"] for s in scenes], [r["seconds"] for r in report])
            self.assertEqual(
                [sum(e["kind"] == "play" for e in s["events"]) for s in scenes], [r["played"] for r in report]
            )
            for s in scenes:
                plays = [e for e in s["events"] if e["kind"] == "play"]
                self.assertEqual(plays[0]["t"], 0)  # a scene's first line plays the moment it starts
                self.assertGreaterEqual(s["end"], max(e["t"] + e["busy"] for e in plays))
        # pink says both its lines back to back in scene 0, so it waits once, and glows while speaking
        events = data["timelines"]["typical"][0]["events"]
        self.assertEqual([e["clip"] for e in events if e["kind"] == "busy"], ["b"])
        self.assertIn([255, 0, 0], [e["rgb"] for e in events if e["kind"] == "antenna"])


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



class FakeTimedFurby:
    """Builds a stand-in Furby that runs each action for a set time and answers 20:07 while busy"""

    @staticmethod
    def make(durations, busy_for=0.0):
        import asyncio

        import furbyshow

        class Fake(furbyshow.Furby):
            def __init__(self):
                super().__init__("fake")
                self.name, self.busy_until, self.triggers = "slots", None, []

            def connected(self):
                return True

            async def disconnect(self):
                pass

            async def _write(self, data):
                if data[0] != 0x13:
                    return
                loop = asyncio.get_running_loop()
                self.triggers.append(tuple(data[2:6]))
                if self.busy_until is None:  # something was already playing when we connected
                    self.busy_until = loop.time() + busy_for
                    if busy_for:
                        loop.call_at(self.busy_until, self.on_response, b"\x20\x0e")
                if loop.time() < self.busy_until:
                    self.on_response(b"\x20\x07")
                    return
                seconds = durations[tuple(data[2:6])]
                self.busy_until = loop.time() + seconds
                self.on_response(b"\x20\x0c")
                loop.call_later(seconds, self.on_response, b"\x20\x0e")

        return Fake()


class TestProbe(unittest.TestCase):
    """probe.py builds numbered test DLCs and times each slot against a stand-in Furby"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_names_and_motors(self):
        import probe
        self.assertEqual(probe.parse_motors("e000-e002, 0xe010"), [0xE000, 0xE001, 0xE002, 0xE010])
        self.assertEqual(len(probe.parse_motors("e000-e028")), 41)
        for bad in ("e0zz", "e005-e001", ""):
            with self.assertRaises(SystemExit):
                probe.parse_motors(bad)
        self.assertEqual(probe.check_name("motions2"), "motions2")
        for bad in ("toolongname", "Slots", "my_dlc"):  # the Furby uppercases it and pads with _
            with self.assertRaises(SystemExit):
                probe.check_name(bad)

    def say(self, text, path):
        """Stands in for macOS say: a short silent clip, so the test needs no TTS or ffmpeg"""
        import struct

        import a1800_codec
        frames = bytes(a1800_codec.encode(bytes(3200), 16000))[6:]
        with open(path + ".a18", "wb") as f:
            f.write(struct.pack("<IH", len(frames) + 2, 16000) + frames)
        self.said.append(text)
        return path + ".a18"

    def test_build_motions(self):
        """Each slot says "move N" and its sequence becomes just its motor word and one eye animation"""
        import json
        from unittest import mock

        import probe
        import spooky_eyes
        if not os.path.exists(probe.STOCK_DLC):
            self.skipTest("Test DLC file not found")
        self.said = []
        with mock.patch("builtins.print"):
            path = probe.build("motions", [0xE000, 0xE005, 0xE028], out_dir=self.temp_dir, say=self.say)
        self.assertEqual(self.said, ["move 1", "move 2", "move 3"])
        self.assertTrue(path.endswith("motions.dlc"))
        with open(os.path.join(self.temp_dir, "motions.json")) as f:
            plan = json.load(f)
        D = dlc(path)
        slots = spooky_eyes.scene_slots(dlc(probe.STOCK_DLC))
        for entry, code, motor in zip(plan["slots"], slots[:3], (0xE000, 0xE005, 0xE028), strict=True):
            self.assertEqual(tuple(entry["action"]), code)
            self.assertEqual(D.dlc_sections["SEQ"].sequences[spooky_eyes._seq(D, code)][2:], [motor, 0x8401, 0])
            self.assertEqual(entry["motor"], "0x%04x" % motor)
        self.assertEqual(plan["kind"], "motions")
        with self.assertRaises(SystemExit):  # more motor words than slots: split them
            probe.build("toomany", list(range(0xE000, 0xE029)), out_dir=self.temp_dir, say=self.say)

    def test_sweep_times_each_slot(self):
        """run waits out 20:07, then times 20:0c to 20:0e for every slot, every run"""
        import asyncio

        import probe
        slots = [{"n": 1, "action": [75, 0, 0, 2], "say": "1"}, {"n": 2, "action": [75, 0, 0, 3], "say": "2"}]
        furby = FakeTimedFurby.make({(75, 0, 0, 2): 0.1, (75, 0, 0, 3): 0.3}, busy_for=0.2)
        logs = []
        runs = asyncio.run(probe.sweep(furby, slots, times=2, reverse=True, gap=0, settle=0, log=logs.append))
        self.assertEqual(furby.triggers[:2], [(75, 0, 0, 3)] * 2)  # reversed, and retried once while busy
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0][2]["retries"], 1)
        self.assertEqual(runs[1][2]["retries"], 0)
        for run in runs:
            self.assertAlmostEqual(run[1]["seconds"], 0.1, delta=0.08)
            self.assertAlmostEqual(run[2]["seconds"], 0.3, delta=0.08)
        rows = probe.summarize(slots, runs)
        self.assertEqual([r["n"] for r in rows], [1, 2])
        self.assertEqual(rows[1]["retries"], 1)
        self.assertLessEqual(rows[1]["min"], rows[1]["max"])
        self.assertIn("slot", probe.table(rows))
        self.assertTrue(any("busy retries" in line for line in logs))

    def test_slots_from_show(self):
        """With no probe map, run plays a show DLC's clips, so it can time pink and blue too"""
        import json

        import probe
        show = os.path.join(self.temp_dir, "show.json")
        with open(show, "w") as f:
            json.dump({"furbies": {"pink": {"clips": {"boo": {"action": [75, 0, 0, 2]}, "a": {"action": [75, 0, 0, 3]}}}}}, f)
        slots = probe.load_slots("pink", out_dir=self.temp_dir, show_json=show)
        self.assertEqual([(s["n"], s["say"], s["action"]) for s in slots], [(1, "a", [75, 0, 0, 3]), (2, "boo", [75, 0, 0, 2])])


class TestDoctor(unittest.TestCase):
    """doctor.py explains what's missing, with a fix for each problem"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.lines = []

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def report(self):
        import doctor
        return doctor.Report(self.lines.append)

    def write_show(self):
        sfx = os.path.join(self.temp_dir, "build", "sfx")
        os.makedirs(sfx)
        here = os.path.join(sfx, "boo-0.wav")
        open(here, "wb").close()
        toml = os.path.join(self.temp_dir, "show.toml")
        with open(toml, "w") as f:
            f.write(
                '[show]\ngap = 0.5\nevery = [20, 45]\n'
                '[furbies.pink.clips]\nboo = "%s"\ncackle = "%s/witch-cackle-0.wav"\n'
                'song = { path = "%s/song.mp3", optional = true }\n'
                '[furbies.blue.clips]\nhi = "%s"\n'
                '[[scenes]]\nsteps = ["pink.boo", "pink.cackle", "blue.hi"]\n' % (here, sfx, sfx, here)
            )
        return toml

    def test_clips(self):
        """A missing clip fails with how to get it; a missing optional one only warns"""
        import doctor
        r = self.report()
        show = doctor.check_show(r, self.write_show())
        self.assertEqual(sorted(show["furbies"]), ["blue", "pink"])
        self.assertEqual(r.failures, 1)
        text = "\n".join(self.lines)
        self.assertIn("pink.cackle", text)
        self.assertIn('freesound_fetch.py "witch cackle"', text)
        self.assertIn("optional", text)
        self.assertIn("blue: all 1 clips are there", text)

    def test_bad_show(self):
        import doctor
        toml = os.path.join(self.temp_dir, "show.toml")
        with open(toml, "w") as f:
            f.write('[show]\n[furbies.pink.clips]\n[[scenes]]\nsteps = ["pink.nope"]\n')
        r = self.report()
        self.assertIsNone(doctor.check_show(r, toml))
        self.assertEqual(r.failures, 1)

    def test_built_dlcs(self):
        """Each DLC must exist, fit in an upload, and match show.json's checksum"""
        import json
        import zlib
        from unittest import mock

        import doctor
        out = os.path.join(self.temp_dir, "halloween")
        os.makedirs(out)
        r = self.report()
        self.assertIsNone(doctor.check_build(r, None, out, "show.toml"))
        self.assertIn("uv run halloween.py", self.lines[-1])
        pink, blue = b"pink" * 100, b"blue" * 100
        for name, data in (("pink", pink), ("blue", b"stale")):
            with open(os.path.join(out, name + ".dlc"), "wb") as f:
                f.write(data)
        plan = {"furbies": {"pink": {"checksum": zlib.adler32(pink)}, "blue": {"checksum": zlib.adler32(blue)},
                            "cyan": {"checksum": 1}}}
        with open(os.path.join(out, "show.json"), "w") as f:
            json.dump(plan, f)
        self.lines.clear()
        r = self.report()
        self.assertEqual(doctor.check_build(r, None, out, "show.toml"), plan)
        self.assertEqual(r.failures, 2)  # blue doesn't match, cyan isn't built
        self.assertTrue(any(line.startswith("✅ pink.dlc") for line in self.lines))
        with mock.patch("spooky_eyes.MAX_UPLOAD", 100):
            r = self.report()
            doctor.check_build(r, None, out, "show.toml")
            self.assertIn("uploads time out", "\n".join(self.lines))

    def test_bluetooth(self):
        """A failed or hung scan on macOS points at the Bluetooth permission for the terminal app"""
        import subprocess
        from unittest import mock

        import doctor

        def runs(returncode=0, stdout="", stderr="", hang=False):
            def run(cmd, **kw):
                if hang:
                    raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
                return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
            return run

        with mock.patch.object(doctor, "MAC", True):
            r = self.report()
            doctor.check_bluetooth(r, runs(stdout="12 2\n"))
            self.assertEqual(r.failures, 0)
            self.assertIn("12 devices", self.lines[-1])
            for run in (runs(1, stderr="BleakError: BLE is not authorized"), runs(hang=True), runs(-6)):
                r = self.report()
                doctor.check_bluetooth(r, run)
                self.assertEqual(r.failures, 1)
                self.assertIn("Privacy & Security", self.lines[-1])
            r = self.report()
            doctor.check_bluetooth(r, runs(1, stderr="BleakError: Bluetooth device is turned off"))
            self.assertIn("Turn Bluetooth on", self.lines[-1])

    def test_furbies(self):
        """Each Furby in the show must be in range with its own, current DLC"""
        import asyncio

        import doctor

        class Found:
            def __init__(self, name, checksum):
                self.name, self.checksum, self.address, self.disconnected = name, checksum, "placeholder", False

            async def disconnect(self):
                self.disconnected = True

        found = [Found("pink", 1), Found("probe", 5)]

        async def find(known):
            return found

        plan = {"furbies": {"pink": {"checksum": 1}, "blue": {"checksum": 2}}}
        r = self.report()
        asyncio.run(doctor.check_furbies(r, plan, find))
        self.assertEqual(r.failures, 1)  # probe.dlc isn't in the show
        self.assertTrue(all(f.disconnected for f in found))
        text = "\n".join(self.lines)
        self.assertIn("✅ pink", text)
        self.assertIn("Didn't see blue", text)  # checked one at a time, so only a note
        self.assertIn("wake only blue", text)
        # With nobody awake, that's a failure
        found.clear()
        r = self.report()
        asyncio.run(doctor.check_furbies(r, plan, find))
        self.assertEqual(r.failures, 1)
        self.assertIn("Wake only one", "\n".join(self.lines))

    def test_missing_packages(self):
        import doctor
        r = self.report()
        self.assertFalse(doctor.check_packages(r, lambda mod: None if mod == "bleak" else object()))
        self.assertIn("uv run doctor.py", self.lines[-1])

class FakeBleFurby:
    """A Furby as bleak sees it, standing in for both the BLEDevice and the BleakClient.

    It answers DLC info (0x72/0x73), takes uploads the way TestFlash's fake
    does, and replies to triggers as scripted in actions: {action: (kind,
    seconds)}, kind "play" (20:0c, then 20:0e after seconds), "busy" (20:07)
    or "silent" (nothing). Like CoreBluetooth, it refuses a second start_notify.
    """

    def __init__(self, address, dlc_name=None, checksum=0, actions=None):
        self.address, self.name = address, "Furby"
        self.slots = {13: (dlc_name.upper().rjust(8, "_"), checksum)} if dlc_name else {}
        self.active = set(self.slots)
        self.actions = actions or {}
        self.is_connected, self.notify, self.antenna, self.triggers = False, {}, [], []
        self.upload, self.received = None, b""

    async def connect(self, timeout=None):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False
        self.notify.clear()

    async def start_notify(self, uuid, cb):
        if uuid in self.notify:
            raise ValueError("Characteristic notifications already started")
        self.notify[uuid] = cb

    async def stop_notify(self, uuid):
        del self.notify[uuid]

    def say(self, data):
        import furbyshow
        if furbyshow.GP_LISTEN in self.notify:
            self.notify[furbyshow.GP_LISTEN](None, bytes(data))

    def dlc(self):
        """(name, checksum) of the active DLC, or None."""
        return self.slots[min(self.active)] if self.active else None

    async def write_gatt_char(self, uuid, data, response=False):
        import asyncio
        import zlib

        import flash
        import furbyshow
        data = bytes(data)
        if uuid == flash.FILE_WRITE:
            self.received += data
            if len(self.received) == self.upload[1]:
                self.slots[12] = (self.upload[0], zlib.adler32(self.received))
                self.say([0x24, 5])
            return
        if uuid != furbyshow.GP_WRITE:
            return
        cmd = data[0]
        bits = lambda s: sum(1 << i for i in s)  # noqa: E731
        if cmd == 0x72:
            f, a = bits(self.slots), bits(self.active)
            self.say([0x72, 0, 0, f >> 8, f & 0xFF, 0, 0, a >> 8, a & 0xFF])
        elif cmd == 0x73:
            name, checksum = self.slots[data[1]]
            self.say(bytes([0x73, data[1]]) + name.encode() + bytes(3) + checksum.to_bytes(4, "big"))
        elif cmd == 0x62:
            self.active.discard(data[1])
            self.say([0xDC, data[1], 0])
        elif cmd == 0x74:
            del self.slots[data[1]]
            self.say([0x74, data[1]])
        elif cmd == 0x50:
            self.upload, self.received = (data[6:14].decode(), int.from_bytes(data[2:5], "big")), b""
            self.say([0x24, 2])
        elif cmd == 0x60:
            self.loaded = data[1]
            self.say([0xDC, data[1], 1])
        elif cmd == 0x61:
            self.active = {self.loaded}
            self.say([0xDC, self.loaded, 2])
        elif cmd == 0x14:
            self.antenna.append(tuple(data[1:4]))
        elif cmd == 0x13:
            action = tuple(data[2:6])
            self.triggers.append(action)
            kind, seconds = self.actions.get(action, ("play", 0.02))
            if kind == "play":
                self.say(furbyshow.SEQUENCE_PLAYING)
                asyncio.get_running_loop().call_later(seconds, self.say, furbyshow.SEQUENCE_ENDED)
            elif kind == "busy":
                self.say(furbyshow.SPEECH_PLAYING)
                asyncio.get_running_loop().call_later(0.01, self.say, furbyshow.SEQUENCE_ENDED)


def fake_bleak(scans):
    """A stand-in bleak module: BleakClient(device) is the FakeBleFurby itself, and each
    BleakScanner.discover() returns the next list in scans (the last one repeats)."""
    import types
    bleak = types.ModuleType("bleak")
    bleak.BleakClient = lambda device, disconnected_callback=None, timeout=None: device

    class BleakScanner:
        @staticmethod
        async def discover(timeout=None):
            return scans.pop(0) if len(scans) > 1 else scans[0]

    bleak.BleakScanner = BleakScanner
    return bleak


class TestDeploy(unittest.TestCase):
    """deploy.py walks someone through flashing both Furbies, one at a time"""

    def setUp(self):
        import json
        import zlib
        self.temp_dir = tempfile.mkdtemp()
        self.plan = {"gap": 0, "every": [30, 60], "scenes": [], "furbies": {}}
        for name, color in (("pink", [255, 0, 120]), ("blue", [0, 0, 255])):
            data = bytes([len(name)]) * 300 + name.encode()
            with open(os.path.join(self.temp_dir, name + ".dlc"), "wb") as f:
                f.write(data)
            self.plan["furbies"][name] = {"checksum": zlib.adler32(data), "antenna": color, "clips": {}}
        self.show = os.path.join(self.temp_dir, "show.json")
        with open(self.show, "w") as f:
            json.dump(self.plan, f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def deploy(self, argv, scans, answers=None, run=None):
        """Run deploy.main with a fake bleak; returns (results or the DeployError, prompts, log)."""
        import sys
        from unittest import mock

        import deploy
        prompts, log = [], []

        def ask(prompt):
            prompts.append(prompt)
            if answers is None:
                raise AssertionError("asked %r with --yes" % prompt)
            return answers.pop(0)

        args = deploy.parse_args(["--no-build", "--show", self.show] + argv)
        with mock.patch.dict(sys.modules, {"bleak": fake_bleak(scans)}), mock.patch.object(deploy, "BLINK_S", 0):
            try:
                result = deploy.main(args, ask=ask, log=log.append, run=run)
            except deploy.DeployError as e:
                result = e
        return result, prompts, log

    def test_guided_deploy(self):
        """Two awake Furbies get a retry; each one is blinked, confirmed and flashed with its own DLC"""
        pink = FakeBleFurby("aa", "TU003410", 1)  # the stock DLC
        blue = FakeBleFurby("bb")  # nothing on it yet
        result, prompts, log = self.deploy([], [[pink, blue], [pink], [blue]], ["", "", "y", "", "y"])
        self.assertEqual(set(result), {"pink", "blue"}, log)
        self.assertEqual(pink.dlc(), ("____PINK", self.plan["furbies"]["pink"]["checksum"]))
        self.assertEqual(blue.dlc(), ("____BLUE", self.plan["furbies"]["blue"]["checksum"]))
        self.assertTrue(any("Found 2 Furbies" in line for line in log))
        self.assertTrue(any("tu003410.dlc active" in line for line in log))
        self.assertTrue(any("no DLC active" in line for line in log))
        self.assertIn("Put the pink Furby to sleep", prompts[3])
        self.assertIn((255, 0, 120), pink.antenna)  # blinked in its show colour
        self.assertEqual(pink.antenna[-1], (0, 255, 0))  # then green when flashed
        self.assertFalse(pink.is_connected or blue.is_connected)
        self.assertIn("porch.py --check", log[-1])

    def test_wrong_one_asks_again(self):
        pink = FakeBleFurby("aa")
        result, prompts, _ = self.deploy(["--only", "pink"], [[pink]], ["", "n", "", "y"])
        self.assertEqual(list(result), ["pink"])
        self.assertEqual(len(prompts), 4)

    def test_same_furby_twice(self):
        """The Furby just flashed pink is refused for blue"""
        import deploy
        pink = FakeBleFurby("aa")
        result, _, _ = self.deploy([], [[pink]], ["", "y", ""])
        self.assertIsInstance(result, deploy.DeployError)
        self.assertIn("just flashed as pink", str(result))
        self.assertEqual(pink.dlc()[0], "____PINK")

    def test_yes(self):
        """--yes never asks: it flashes, skips one already up to date, and stops rather than retrying"""
        import deploy
        furby = FakeBleFurby("aa")
        result, _, _ = self.deploy(["--yes", "--only", "blue"], [[furby]])
        self.assertEqual(furby.dlc()[0], "____BLUE")
        self.assertIn("flashed", result["blue"])
        result, _, _ = self.deploy(["--yes", "--only", "blue"], [[furby]])
        self.assertEqual(result["blue"], "already up to date")
        # A Furby with this show's blue.dlc isn't overwritten with pink's unless someone says so
        result, _, _ = self.deploy(["--yes", "--only", "pink"], [[furby]])
        self.assertIsInstance(result, deploy.DeployError)
        self.assertIn("blue.dlc", str(result))
        self.assertEqual(furby.dlc()[0], "____BLUE")
        result, _, _ = self.deploy(["--yes"], [[FakeBleFurby("aa"), FakeBleFurby("bb")]])
        self.assertIn("Found 2 Furbies", str(result))
        result, _, _ = self.deploy(["--yes"], [[]])
        self.assertIn("No Furby found", str(result))
        result, _, _ = self.deploy(["--yes", "--only", "green"], [[]])
        self.assertIn("no green Furby", str(result))

    def test_stale_dlc_and_esp32(self):
        from unittest import mock

        import deploy
        ran = []

        def run(cmd):
            ran.append(cmd)
            return mock.Mock(returncode=0)

        result, _, _ = self.deploy(["--yes", "--only", "pink", "--esp32"], [[FakeBleFurby("aa")]], run=run)
        self.assertEqual(result["esp32"], "show copied")
        self.assertTrue(ran[0][0].endswith(os.path.join("firmware", "deploy.sh")))
        with open(os.path.join(self.temp_dir, "pink.dlc"), "ab") as f:
            f.write(b"changed")
        result, _, _ = self.deploy(["--yes", "--only", "pink"], [[FakeBleFurby("aa")]])
        self.assertIsInstance(result, deploy.DeployError)
        self.assertIn("doesn't match show.json", str(result))


class TestCheck(unittest.TestCase):
    """porch.py --check plays each clip once and reads the Furby's replies to say what happened"""

    def test_check(self):
        import asyncio
        import json
        import sys
        from unittest import mock

        import porch
        clip = lambda n: {"action": [75, 0, 0, n], "seconds": 0.0, "source": "x.wav"}  # noqa: E731
        plan = {"gap": 0, "every": [30, 60], "scenes": [], "furbies": {
            "pink": {"checksum": 1, "clips": {"a": clip(1), "b": clip(2), "c": clip(3), "d": clip(4)}},
            "blue": {"checksum": 2, "clips": {"a": clip(1)}},
            "green": {"checksum": 3, "clips": {"a": clip(1)}},
        }}
        pink = FakeBleFurby("aa", "pink", 1, actions={
            (75, 0, 0, 1): ("play", 0.05), (75, 0, 0, 2): ("busy", 0), (75, 0, 0, 3): ("silent", 0),
            (75, 0, 0, 4): ("play", 0.4),
        })
        blue = FakeBleFurby("bb", "blue", 99)  # flashed from an older build
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)
        timings = os.path.join(temp_dir, "timings.json")
        log = []
        with mock.patch.dict(sys.modules, {"bleak": fake_bleak([[pink], [blue]])}), mock.patch("builtins.print"):
            failures = asyncio.run(porch.check(plan, porch.find, log=log.append, timings_path=timings,
                                               patience_s=1, long_tail_s=0.3, settle_s=0.05, pause_s=0))
        self.assertEqual(failures, [
            "pink.b: skipped", "pink.c: no reply",
            "blue: its DLC doesn't match show.json; reflash it with: uv run deploy.py --only blue",
            "green: not connected. Is it awake, nearby and free of FurBLE?",
        ])
        self.assertEqual(pink.triggers.count((75, 0, 0, 2)), 2)  # tried again once the busy sequence ended
        with open(timings) as f:
            measured = json.load(f)
        self.assertTrue(0 < measured["pink"]["a"]["sequence_seconds"] < 0.3)
        self.assertTrue(any("Waiting for blue, green" in line for line in log))  # blue turned up on a later scan
        self.assertEqual(measured["pink"]["b"]["result"], "skipped")
        self.assertIsNone(measured["pink"]["c"]["sequence_seconds"])
        self.assertTrue(any(line.lstrip().startswith("d ") and "past its audio" in line for line in log), log)
        self.assertFalse(any(line.lstrip().startswith("a ") and "past its audio" in line for line in log))
        self.assertFalse(pink.is_connected)


class TestPorchAction(unittest.TestCase):
    """porch.py --action triggers one action on any DLC, so probes don't need FurBLE"""

    def test_parse_action(self):
        import argparse

        import porch
        for text in ("75,0,4,4", "75 0 4 4", "75-0-4-4"):
            self.assertEqual(porch.parse_action(text), (75, 0, 4, 4))
        for text in ("75,0,4", "75,0,4,256", "a,b,c,d", ""):
            with self.assertRaises(argparse.ArgumentTypeError):
                porch.parse_action(text)


class TestPorchStop(unittest.TestCase):
    """Ctrl-C turns the antennas off and disconnects, even from a Furby that won't answer"""

    def test_let_go(self):
        import asyncio
        import types

        import porch

        class F:
            def __init__(self, fails=False):
                self.is_connected, self.fails, self.antenna = True, fails, None

            def connected(self):
                return self.is_connected

            async def set_antenna(self, rgb):
                if self.fails:
                    raise OSError("gone")
                self.antenna = rgb

            async def disconnect(self):
                self.is_connected = False

        good, gone, asleep = F(), F(fails=True), F()
        asleep.is_connected = False
        show = types.SimpleNamespace(furbies={"pink": gone, "blue": good, "green": asleep})
        asyncio.run(porch.let_go(show))
        self.assertEqual(good.antenna, (0, 0, 0))
        self.assertFalse(good.is_connected)
        self.assertIsNone(asleep.antenna)


class TestRealShow(unittest.TestCase):
    """halloween/show.toml, built with placeholder clips, plays every line on virtual Furbies"""

    def test_every_line_plays(self):
        """No scene is dropped, and no line goes silent or is skipped, with typical or worst-case movements"""
        import json
        import sys
        from unittest import mock

        import emulate
        import halloween
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
        import ci_show
        if not os.path.exists("./dlc/dlc2/tu003410.dlc"):
            self.skipTest("Test DLC file not found")
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)
        with mock.patch("builtins.print"):
            scenes = halloween.load_show()["scenes"]
            with open(ci_show.main(["-o", temp_dir])) as f:
                plan = json.load(f)
        self.assertEqual(len(plan["scenes"]), len(scenes))  # optional clips get placeholders too
        dlcs = {name: os.path.join(temp_dir, name + ".dlc") for name in plan["furbies"]}
        for worst in (False, True):
            report = emulate.simulate(plan, dlcs, durations=emulate.load_durations(None, worst))
            problems = [(i, r["silent"], r["skipped"]) for i, r in enumerate(report) if r["silent"] or r["skipped"]]
            self.assertEqual(problems, [], "worst-case movements" if worst else "typical movements")


class TestScripts(unittest.TestCase):
    """Every command-line script at least starts, including ones no test imports"""

    def test_help(self):
        """--help exits 0 for each script with an argparse CLI"""
        import glob
        import subprocess
        import sys

        root = os.path.dirname(os.path.abspath(__file__))
        scripts = []
        # Just the repo's script folders, so local untracked files elsewhere don't change the result
        for path in sorted(p for d in ("", "audioutils", "tools") for p in glob.glob(os.path.join(root, d, "*.py"))):
            with open(path, encoding="utf-8") as f:
                source = f.read()
            # Scripts without argparse (demo.py, firmware/main.py...) do real work when run, so skip them
            if "argparse" in source and "__main__" in source and not path.endswith("test_furby.py"):
                scripts.append(path)
        self.assertGreater(len(scripts), 10, scripts)
        runs = {p: subprocess.Popen([sys.executable, p, "--help"], cwd=root, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True) for p in scripts}
        for path, proc in runs.items():
            out, err = proc.communicate(timeout=60)
            with self.subTest(script=os.path.relpath(path, root)):
                self.assertEqual(proc.returncode, 0, err)
                self.assertIn("usage:", out)

class FakeEngine:
    """A text-to-speech engine that writes the words and voice instead of audio"""

    name, suffix, command = "say", ".aiff", "fake-say"

    def __init__(self, voices=("Albert", "Junior", "Whisper")):
        self.voices = voices

    def has_voice(self, voice):
        return voice in self.voices

    def speak(self, text, voice, out):
        with open(out, "w") as f:
            f.write("%s|%s" % (voice, text))


def copy_audio(src, out):
    shutil.copy(src, out)


class TestVoices(unittest.TestCase):
    """voices.py speaks each voice line's text into the file show.toml names"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.path = lambda name: os.path.join(self.temp_dir, "cloned", name + ".wav")
        self.show = {
            "furbies": {
                "pink": {"clips": {
                    "boo": {"path": self.path("pink_boo"), "text": "Boo!"},
                    "trick": {"path": self.path("pink_trick"), "before": 0.4, "text": "Trick."},
                    "scream": os.path.join(self.temp_dir, "sfx", "scream.wav"),  # no text: not a voice line
                }},
                "blue": {"voice": "Whisper", "clips": {"hi": {"path": self.path("blue_hi"), "text": "Hi!"}}},
            },
            "scenes": [{"steps": ["pink.boo", "pink.trick", "pink.scream", "blue.hi"]}],
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def read(self, name):
        with open(self.path(name)) as f:
            return f.read()

    def test_makes_missing_lines_only(self):
        """Each missing line gets its Furby's voice; existing files stay unless forced"""
        import voices
        os.makedirs(os.path.dirname(self.path("pink_trick")))
        with open(self.path("pink_trick"), "w") as f:
            f.write("my own recording")
        log = []
        made, kept = voices.make_voices(self.show, FakeEngine(), convert=copy_audio, log=log.append)
        self.assertEqual(made, ["pink.boo", "blue.hi"])
        self.assertEqual(kept, ["pink.trick"])
        self.assertEqual(self.read("pink_boo"), "Albert|Boo!")  # pink's default
        self.assertEqual(self.read("blue_hi"), "Whisper|Hi!")  # blue's voice from show.toml
        self.assertEqual(self.read("pink_trick"), "my own recording")
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "sfx")))
        # --force remakes it; --furby and --voice narrow and override
        made, _ = voices.make_voices(self.show, FakeEngine(), only=["pink"], voice="Junior", force=True,
                                     convert=copy_audio, log=log.append)
        self.assertEqual(made, ["pink.boo", "pink.trick"])
        self.assertEqual(self.read("pink_trick"), "Junior|Trick.")
        self.assertEqual(self.read("blue_hi"), "Whisper|Hi!")

    def test_voices(self):
        """An unknown chosen voice stops with a hint; a missing default falls back to the system voice"""
        import voices
        with self.assertRaises(SystemExit) as e:
            voices.make_voices(self.show, FakeEngine(), voice="Nobody", convert=copy_audio, log=lambda m: None)
        self.assertIn("say -v '?'", str(e.exception))
        log = []
        voices.make_voices(self.show, FakeEngine(voices=("Whisper",)), convert=copy_audio, log=log.append)
        self.assertEqual(self.read("pink_boo"), "None|Boo!")
        self.assertIn("pink: no Albert voice here, so using the system voice.", log)
        self.assertEqual(voices.find_engine(lambda c: "/usr/bin/" + c if c == "espeak" else None).name, "espeak")
        self.assertIsNone(voices.find_engine(lambda c: None))
        # A synthesizer that fails says which line and how to see the voices, not a traceback
        import subprocess

        def fail(src, out):
            raise subprocess.CalledProcessError(1, ["/usr/bin/ffmpeg"])
        with self.assertRaises(SystemExit) as e:
            voices.make_voices(self.show, FakeEngine(), force=True, convert=fail, log=log.append)
        self.assertIn("pink.boo: couldn't make", str(e.exception))
        self.assertIn("ffmpeg stopped", str(e.exception))

    def test_main(self):
        """The command line lists lines, makes them, and says what to run next"""
        import voices
        toml = os.path.join(self.temp_dir, "show.toml")
        with open(toml, "w") as f:
            f.write('[furbies.pink.clips]\nboo = { path = "%s", text = "Boo!" }\nscream = "%s"\n'
                    '[[scenes]]\nsteps = ["pink.boo", "pink.scream"]\n'
                    % (self.path("pink_boo"), os.path.join(self.temp_dir, "scream.wav")))
        log = []
        voices.main(["--show", toml, "--list"], log=log.append)
        self.assertEqual(len(log), 1)
        self.assertTrue(log[0].startswith("missing  pink.boo"))
        self.assertIn('"Boo!"', log[0])
        log = []
        voices.main(["--show", toml], engine=FakeEngine(), convert=copy_audio, log=log.append)
        self.assertEqual(self.read("pink_boo"), "Albert|Boo!")
        self.assertIn("Next, build the show: uv run halloween.py --skip-missing", log)  # the scream's still missing
        with self.assertRaises(SystemExit):
            voices.main(["--show", toml, "--furby", "green"], engine=FakeEngine(), convert=copy_audio, log=log.append)
        with self.assertRaises(SystemExit) as e:
            voices.main(["--show", toml, "--force"], which=lambda c: None, log=log.append)
        self.assertIn("espeak-ng", str(e.exception))

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_to_wav_trims_and_resamples(self):
        """The audio comes out 16 kHz mono 16-bit, without the silence at each end"""
        import math
        import struct
        import wave

        import voices
        src, out = os.path.join(self.temp_dir, "raw.wav"), os.path.join(self.temp_dir, "out.wav")
        rate = 22050
        tone = [int(8000 * math.sin(2 * math.pi * 440 * n / rate)) for n in range(rate // 2)]
        with wave.open(src, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(rate)
            samples = [0] * rate + tone + [0] * rate  # 1 s of silence, 0.5 s of tone, 1 s of silence
            w.writeframes(b"".join(struct.pack("<hh", s, s) for s in samples))
        voices.to_wav(src, out)
        with wave.open(out) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 16000))
            self.assertAlmostEqual(w.getnframes() / 16000, 0.5, delta=0.1)


class TestPackage(unittest.TestCase):
    """package.py zips a built show for a friend to flash without building"""

    def setUp(self):
        import json
        import zlib
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.temp_dir)  # clip sources in show.json are relative to the repo root
        os.makedirs("build/halloween/pink")
        os.makedirs("build/cloned")
        self.plan = {"furbies": {}, "scenes": []}
        for name in ("pink", "blue"):
            data = name.encode() * 100
            with open("build/halloween/%s.dlc" % name, "wb") as f:
                f.write(data)
            self.plan["furbies"][name] = {"checksum": zlib.adler32(data), "clips": {}}
        for path in ("build/cloned/pink_boo.wav", "build/halloween/pink/toccata.wav"):
            with open(path, "w") as f:
                f.write("audio")
        self.plan["furbies"]["pink"]["clips"] = {
            "boo": {"source": "build/cloned/pink_boo.wav"},
            "toccata": {"source": "build/halloween/pink/toccata.wav"},  # a cut clip's snippet
            "march": {"source": "audio/new_audio/imperial_march-16000_wav.a18"},  # comes with the repo
            "gone": {"source": "build/cloned/pink_gone.wav"},
        }
        with open("build/halloween/show.json", "w") as f:
            json.dump(self.plan, f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_package(self):
        """The zip has what deploy.py --no-build and porch.py need, where they look for it"""
        import zipfile

        import package
        log = []
        package.main([], log=log.append)
        with zipfile.ZipFile("build/furby-show.zip") as z:
            self.assertEqual(sorted(z.namelist()), ["README_FIRST.txt", "build/halloween/blue.dlc",
                                                    "build/halloween/pink.dlc", "build/halloween/show.json"])
            readme = z.read("README_FIRST.txt").decode()
        self.assertIn("uv run deploy.py --no-build", readme)
        self.assertIn("unzip -o ~/Downloads/furby-show.zip", readme)
        self.assertNotIn("--rehearse", readme)
        self.assertTrue(any("PRIVATE" in line and "Hasbro" in line for line in log))
        # --rehearsal adds the audio porch.py --rehearse plays, but not what the repository has
        log = []
        package.main(["--rehearsal", "--out", "build/rehearse.zip"], log=log.append)
        with zipfile.ZipFile("build/rehearse.zip") as z:
            names = z.namelist()
            self.assertIn("--rehearse", z.read("README_FIRST.txt").decode())
        self.assertIn("build/cloned/pink_boo.wav", names)
        self.assertIn("build/halloween/pink/toccata.wav", names)
        self.assertFalse(any(n.startswith("audio/") for n in names))
        self.assertIn("pink.gone: no build/cloned/pink_gone.wav, so it's left out of the rehearsal.", log)
        # A commit GitHub has pins the friend's code to the version that built the show
        from types import SimpleNamespace
        package.main([], log=log.append, run=lambda cmd, **kw: SimpleNamespace(stdout="abc1234\n"))
        with zipfile.ZipFile("build/furby-show.zip") as z:
            readme = z.read("README_FIRST.txt").decode()
        self.assertIn("git checkout abc1234", readme)
        self.assertIn("archive/abc1234.zip", readme)
        self.assertEqual(package.published_commit(lambda cmd, **kw: SimpleNamespace(stdout="")), None)

    def test_refuses_stale_dlc(self):
        """A DLC that doesn't match show.json's checksum stops the zip"""
        import package
        with open("build/halloween/blue.dlc", "ab") as f:
            f.write(b"changed")
        with self.assertRaises(SystemExit) as e:
            package.main([], log=lambda m: None)
        self.assertIn("doesn't match show.json", str(e.exception))
        self.assertFalse(os.path.exists("build/furby-show.zip"))
        os.remove("build/halloween/show.json")
        with self.assertRaises(SystemExit):
            package.main([], log=lambda m: None)


if __name__ == '__main__':
    unittest.main()
