#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for Furby Connect DLC tools

This test suite validates the Python 3 migration and core functionality
of the Furby Connect DLC file parser and builder.
"""

import unittest
import os
import tempfile
import shutil
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
