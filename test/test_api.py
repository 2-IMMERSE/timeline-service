from __future__ import print_function
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
import unittest
import subprocess
import sys
import time
import os
import requests
import urllib.parse
import _testServer

COVERAGE=False
KEEP_SERVER=not not os.environ.get("TEST_KEEP_SERVER", None)
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
        cmd += ['-m', 'timelineService', '--noKibana', '--logLevel', 'ERROR', '--port', '9042']
        cls.serverProcess = subprocess.Popen(cmd, cwd=homedir, stdout=stdout, stderr=subprocess.STDOUT)
        cls.serverUrl = 'http://localhost:9042/timeline/v1/context'
        cls.helperServer = _testServer.Server(9043)
        cls.helperServer.start()
        cls.helperUrl = 'http://localhost:9043/'
        time.sleep(2)
        
    @classmethod
    def tearDownClass(cls):
        if KEEP_SERVER:
            print('Press return to terminate server -')
            try:
                sys.stdin.readline()
            except KeyboardInterrupt:
                pass
        cls.serverProcess.terminate()
        cls.serverProcess.wait()
        cls.helperServer.stop()
        
    def test_helper(self):
        r = requests.get(self.helperUrl)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text.strip(), "Hello, World!")
        
    def test_helper_nonexistent(self):
        r = requests.get(self.helperUrl + 'nonexistent')
        self.assertEqual(r.status_code, 404)
        
    def test_api(self):
        r = requests.get(self.serverUrl)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(type(r.json()), type([]))

    def test_createEmptyDocument(self):
        layoutServiceUrl=urllib.parse.urljoin(self.helperUrl, '/layout')
        r = requests.post(self.serverUrl, params=dict(contextId='000', layoutServiceUrl=layoutServiceUrl))
        self.assertIn(r.status_code, {200,204})
        r = requests.get(self.serverUrl)
        rv = r.json()
        self.assertEqual(type(rv), type([]))
        self.assertIn('000', rv)
        r = requests.get(self.serverUrl + '/000/dump')
        rv = r.json()
        self.assertIn('layoutServiceUrl', rv)
        self.assertEqual(rv['layoutServiceUrl'], layoutServiceUrl)
        
    def test_createDocument(self):
        self.maxDiff = None
        layoutServiceUrl=urllib.parse.urljoin(self.helperUrl, '/layout')
        timelineDocUrl=urllib.parse.urljoin(self.helperUrl, '/files/test_000_ref.xml')
        r = requests.post(self.serverUrl, params=dict(contextId='001', layoutServiceUrl=layoutServiceUrl))
        self.assertIn(r.status_code, {200,204})
        r = requests.get(self.serverUrl + '/001/loadDMAppTimeline', params=dict(timelineDocUrl=timelineDocUrl, dmappId='d001'))
        self.assertIn(r.status_code, {200,204})
        r = requests.get(self.serverUrl + '/001/dump')
        rv = r.json()
        self.assertIn('layoutServiceUrl', rv)
        self.assertEqual(rv['timelineDocUrl'], timelineDocUrl)
        
if __name__ == '__main__':
    unittest.main()
    
