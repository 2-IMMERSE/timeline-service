from __future__ import print_function
from __future__ import unicode_literals
import unittest
import subprocess
import sys
import time
import os
import requests

COVERAGE=False
KEEP_SERVER=False
BASEDIR=os.path.dirname(os.path.abspath(__file__))
FIXTURES=os.path.join(BASEDIR, 'fixtures')

class TestAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        homedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stdout = open(os.path.join(FIXTURES, 'output', 'server-output.txt'), 'w')
        cmd = [sys.executable]
        if COVERAGE:
            # untested
            cmd += ['-m', 'coverage', 'run', '--parallel-mode']
        cmd += ['-m', 'timelineService', '--noKibana', '--logLevel', 'ERROR']
        cls.serverProcess = subprocess.Popen(cmd, cwd=homedir, stdout=stdout, stderr=subprocess.STDOUT)
        cls.serverUrl = 'http://localhost:8080/timeline/v1/context'
        time.sleep(2)
        
    @classmethod
    def tearDownClass(cls):
        if KEEP_SERVER:
            print('Press control-c to terminate server -')
            try:
                time.sleep(99999)
            except KeyboardInterrupt:
                pass
        cls.serverProcess.terminate()
        cls.serverProcess.wait()
        
    def test_api(self):
        r = requests.get(self.serverUrl)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(type(r.json()), type([]))

    def test_createDocument(self):
        r = requests.post(self.serverUrl, params=dict(contextId='000', layoutServiceUrl='http://localhost:9999/'))
        self.assertIn(r.status_code, {200,204})
        r = requests.get(self.serverUrl)
        rv = r.json()
        self.assertEqual(type(rv), type([]))
        self.assertIn('000', rv)
        
if __name__ == '__main__':
    unittest.main()
    