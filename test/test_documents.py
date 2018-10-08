from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import zip
import unittest
import sys
import os
import urllib.request, urllib.parse, urllib.error
import xmldiff.main

BASEDIR=os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(BASEDIR))

import timelineService.document as document

FIXTURES=os.path.join(BASEDIR, 'fixtures')

class TestDocuments(unittest.TestCase):

    def _runOne(self, documentName, urlsuffix='', filesuffix=''):
        input = os.path.join(FIXTURES, 'input', documentName + '.xml')
        inputLayout = os.path.join(FIXTURES, 'input', documentName + '-layout.json')
        outputDocument = os.path.join(FIXTURES, 'output', documentName + filesuffix + '.xml')
        outputTrace = os.path.join(FIXTURES, 'output', documentName + filesuffix + '-trace.txt')
        expectedDocument = os.path.join(FIXTURES, 'expected', documentName + filesuffix + '.xml')
        expectedTrace = os.path.join(FIXTURES, 'expected', documentName + filesuffix + '-trace.txt')
        
        if not os.path.exists(inputLayout):
            inputLayout = None
            
        inputUrl = urllib.request.pathname2url(input)
        
        args = document.MakeArgs(document=inputUrl + urlsuffix, layout=inputLayout, tracefile=outputTrace, dumpfile=outputDocument, fast=True)
        document.run(args)
        
        fp = open(outputDocument)
        outputDocumentData = fp.read()
        fp.close()
        fp = open(outputTrace)
        outputTraceData = fp.read()
        fp.close()
        
        self.assertTrue(os.path.exists(expectedDocument))
        self.assertTrue(os.path.exists(expectedTrace))

        # Compare XML document output state
        diffs = xmldiff.main.diff_files(expectedDocument, outputDocument)
        self.assertEqual(diffs, [])        

        # Compare emitted events
        outputTraceLines = outputTraceData.splitlines()
        outputTraceRecords = [eval(x) for x in outputTraceLines]
        outputTraceRecords.sort(key=lambda x:(x['timestamp'], x['event'], x['verb'], x['args']))
        fp = open(expectedTrace)
        expectedTraceData = fp.read()
        fp.close()
        expectedTraceLines = expectedTraceData.splitlines()
        expectedTraceRecords = [eval(x) for x in expectedTraceLines]
        expectedTraceRecords.sort(key=lambda x:(x['timestamp'], x['event'], x['verb'], x['args']))
        for o, e in zip(outputTraceRecords, expectedTraceRecords):
            self.assertEqual(e, o)
        
        
    def test_000_ref(self):
        self._runOne('test_000_ref')

    def test_000_ref_seek(self):
        self._runOne('test_000_ref', '#t=60', '-seek60')

    def test_001_editable(self):
        self._runOne('test_001_editable')

    def test_100_video(self):
        self._runOne('test_100_video')

    def test_100_video_seek(self):
        self._runOne('test_100_video', '#t=60', '-seek60')

    def test_104_images(self):
        self._runOne('test_104_images')

    def test_104_images_seek(self):
        self._runOne('test_104_images', '#t=60', '-seek60')

    def test_107_button_video(self):
        self._runOne('test_107_button_video')

    def test_107_button_video_seek(self):
        self._runOne('test_107_button_video', '#t=60', '-seek60')

    def test_108_video_description_images(self):
        self._runOne('test_108_video_description_images')

    def test_108_video_description_images_seek(self):
        self._runOne('test_108_video_description_images', '#t=60', '-seek60')

    def test_111_update_mp4(self):
        self._runOne('test_111_update_mp4')

    def test_111_update_mp4_seek(self):
        self._runOne('test_111_update_mp4', '#t=60', '-seek60')

    def test_113_pip_multi(self):
        self._runOne('test_113_pip_multi')

    def test_113_pip_multi_seek(self):
        self._runOne('test_113_pip_multi', '#t=60', '-seek60')

    def test_124_update_layout(self):
        self._runOne('test_124_update_layout')

    def test_124_update_layout_seek(self):
        self._runOne('test_124_update_layout', '#t=60', '-seek60')

    def test_144_repeat_button(self):
        self._runOne('test_144_repeat_button')

    def test_144_repeat_button_seek(self):
        self._runOne('test_144_repeat_button', '#t=60', '-seek60')

    def test_148_update_append(self):
        self._runOne('test_148_update_append')

    def test_148_update_append_seek(self):
        self._runOne('test_148_update_append', '#t=60', '-seek60')

    def test_202_2video_mp4(self):
        self._runOne('test_202_2video_mp4')

    def test_202_2video_mp4_seek(self):
        self._runOne('test_202_2video_mp4', '#t=60', '-seek60')

    def test_203_6video_mp4(self):
        self._runOne('test_203_6video_mp4')

    def test_203_6video_mp4_seek(self):
        self._runOne('test_203_6video_mp4', '#t=60', '-seek60')

    def test_300_events(self):
        self._runOne('test_300_events')
        
    def test_300_events_seek(self):
        self._runOne('test_300_events', '#t=60', '-seek60')
        
if __name__ == '__main__':
    unittest.main()
    
