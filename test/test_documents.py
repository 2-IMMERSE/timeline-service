import unittest
import sys
import os
import xmldiff.main

BASEDIR=os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(BASEDIR))

import timelineService.document as document

FIXTURES=os.path.join(BASEDIR, 'fixtures')

class TestDocuments(unittest.TestCase):

    def _runOne(self, documentName):
        input = os.path.join(FIXTURES, 'input', documentName + '.xml')
        inputLayout = os.path.join(FIXTURES, 'input', documentName + '-layout.json')
        outputDocument = os.path.join(FIXTURES, 'output', documentName + '.xml')
        outputTrace = os.path.join(FIXTURES, 'output', documentName + '-trace.txt')
        expectedDocument = os.path.join(FIXTURES, 'expected', documentName + '.xml')
        expectedTrace = os.path.join(FIXTURES, 'expected', documentName + '-trace.txt')
        
        if not os.path.exists(inputLayout):
            inputLayout = None
            
        args = document.MakeArgs(document=input, layout=inputLayout, tracefile=outputTrace, dumpfile=outputDocument, fast=True)
        document.run(args)
        
        outputDocumentData = open(outputDocument).read()
        outputTraceData = open(outputTrace).read()
        
        self.assertTrue(os.path.exists(expectedDocument))
        self.assertTrue(os.path.exists(expectedTrace))

        # Compare XML document output state
        diffs = xmldiff.main.diff_files(expectedDocument, outputDocument)
        self.assertEqual(diffs, [])        

        # Compare emitted events
        outputTraceLines = outputTraceData.splitlines()
        outputTraceRecords = [eval(x) for x in outputTraceLines]
        outputTraceRecords.sort()
        expectedTraceData = open(expectedTrace).read()
        expectedTraceLines = expectedTraceData.splitlines()
        expectedTraceRecords = [eval(x) for x in expectedTraceLines]
        expectedTraceRecords.sort()
        for o, e in zip(outputTraceRecords, expectedTraceRecords):
            self.assertEqual(e, o)
        
        
    def test_000_ref(self):
        self._runOne('test_000_ref')

    def test_100_video(self):
        self._runOne('test_100_video')

    def test_104_images(self):
        self._runOne('test_104_images')

    def test_107_button_video(self):
        self._runOne('test_107_button_video')

    def test_108_video_description_images(self):
        self._runOne('test_108_video_description_images')

    def test_111_update_mp4(self):
        self._runOne('test_111_update_mp4')

    def test_113_pip_multi(self):
        self._runOne('test_113_pip_multi')

    def test_124_update_layout(self):
        self._runOne('test_124_update_layout')

    def test_144_repeat_button(self):
        self._runOne('test_144_repeat_button')

    def test_148_update_append(self):
        self._runOne('test_148_update_append')

    def test_202_2video_mp4(self):
        self._runOne('test_202_2video_mp4')

    def test_203_6video_mp4(self):
        self._runOne('test_203_6video_mp4')

    def test_300_events(self):
        self._runOne('test_300_events')
        
if __name__ == '__main__':
    unittest.main()
    
