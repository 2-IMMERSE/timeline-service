from __future__ import print_function
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from flask import Flask, Response, abort, request
from gevent.pywsgi import WSGIServer
import sys
import os
import threading

DEBUG=False

staticdir = os.path.join(os.path.dirname(__file__), 'fixtures', 'input')

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello, World!'
    
@app.route('/files/<path:path>')
def get_file(path):
    filename = os.path.join(staticdir, path)
    if not os.path.exists(filename):
        abort(404)
    data = open(filename).read()
    return Response(data, mimetype='application/xml')
    
@app.route('/layout/context/<string:contextId>/dmapp/<string:dmappId>/<string:verb>', methods=['GET', 'PUT', 'POST'])
def get_layout(contextId, dmappId, verb):
    print('Layout: context %s dmapp %s verb %s args %s' % (contextId, dmappId, verb, request.get_json()))
    return ''
    
class Server(threading.Thread):
    def __init__(self, port):
        threading.Thread.__init__(self)
        self.port = port if port else 9090
        
    def run(self):
        if DEBUG: print("_testServer: running on port %d" % self.port)
        self.server = WSGIServer(("0.0.0.0", self.port), app)
        self.server.serve_forever()

    def stop(self):
        self.server.stop()
        
if __name__ == '__main__':
    s = Server(9090)
    s.start()
    try:
        while True:
            print('Type stop to stop -')
            if sys.stdin.readline().strip() == 'stop':
                break
    except KeyboardInterrupt:
        pass
    s.stop()
