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
        
        if os.path.exists(expectedDocument):
#            expectedDocumentData = open(expectedDocument).read()
#            self.assertEqual(outputDocumentData, expectedDocumentData)
            diffs = xmldiff.main.diff_files(expectedDocument, outputDocument)
            self.assertEqual(diffs, [])
        
        if os.path.exists(expectedTrace):
            outputTraceLines = outputTraceData.splitlines()
            outputTraceRecords = [eval(x) for x in outputTraceLines]
            expectedTraceData = open(expectedTrace).read()
            expectedTraceLines = expectedTraceData.splitlines()
            expectedTraceRecords = [eval(x) for x in expectedTraceLines]
            for o, e in zip(outputTraceRecords, expectedTraceRecords):
                self.assertEqual(e, o)
        
        
    def test_000(self):
        self._runOne('test_000_ref')
        
if __name__ == '__main__':
    unittest.main()
    
