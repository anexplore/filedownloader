# -*- coding: utf-8 -*-
"""
测试
"""
import os
import unittest

import src.file_downloader as file_downloader


class TestGlobalFunction(unittest.TestCase):

    def test_read_all_finished_segment_list(self):
        """
        测试 read_all_finished_segment_list()
        """
        fix_data_length = 48
        path = 'segment_list.test.temp'
        try:
            with open(path, 'w') as fd:
                fd.write('%s\n' % fix_data_length)
                fd.write('%s,%s\n' % (0, 24))
                fd.write('%s,%s\n' % (24, 32))
                fd.write('%s,%s\n' % (25, 33))
                fd.write('%s,%s\n' % (26, 30))
                fd.write('%s,%s\n' % (34, 40))
                fd.write('%s,%s\n' % (45, 47))
            data_length, segment_list = file_downloader.read_all_finished_segment_list(path)
            self.assertEquals(data_length, fix_data_length, 'data length must match')
            self.assertEquals(len(segment_list), 2, 'segment merges size')
            self.assertTrue(segment_list[0][0] == 0 and segment_list[0][1] == 40, 'segment start and end')
            self.assertTrue(segment_list[1][0] == 45 and segment_list[1][1] == 47, 'segment start and end')
        finally:
            os.remove(path)

    def test_find_holes(self):
        fix_data_length = 48
        single_segments = [
            (0, 40),
            (45, 47)
        ]
        hole_segments = file_downloader.find_holes(fix_data_length, single_segments)
        self.assertEquals(len(hole_segments), 1, 'hole segment size')
        self.assertTrue(hole_segments[0][0] == 41 and hole_segments[0][1] == 44, 'hole start and end')
        multi_segments = [
            (0, 30),
            (35, 40)
        ]
        hole_segments = file_downloader.find_holes(fix_data_length, multi_segments)
        self.assertEquals(len(hole_segments), 2, 'hole segment size')
        self.assertTrue(hole_segments[1][0] == 41 and hole_segments[1][1] == 47, 'last hole')


class TestSegmentWriter(unittest.TestCase):

    def test_write_data(self):
        path = 'segmentwriter.test.tmp'
        data = b'hello, world'
        try:
            file_downloader.create_empty_fix_size_binary_file(path, 20, overwrite_if_already_exists=True)
            writer = file_downloader.SegmentWriter(path, 0, 20)
            writer.write(data)
            self.assertTrue(writer.total_write_data_length() == len(data), 'write data length')
            self.assertTrue(writer.left_capacity() == 20 - len(data), 'left capacity')
            writer.close()
        finally:
            os.remove(path)