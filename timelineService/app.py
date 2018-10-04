from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
from builtins import str
from builtins import object
import traceback
import sys
import json
import os
from gevent.pywsgi import WSGIServer
from flask import Flask, Response, request, abort, jsonify, make_response
from werkzeug.exceptions import HTTPException

from . import timeline

app = Flask(__name__)
# app.config.from_object("flask_config")

#
# Disable CORS problems
#
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    if request.method == 'OPTIONS':
        response.headers['Access-Control-Allow-Methods'] = 'DELETE, GET, POST, PUT'
        headers = request.headers.get('Access-Control-Request-Headers')
        if headers:
            response.headers['Access-Control-Allow-Headers'] = headers
    return response
app.after_request(add_cors_headers)

     
API_ROOT = "/timeline/v1/context"

@app.route(API_ROOT, methods=["GET", "POST"])
def allContexts():
    timelineServiceUrl = "http://example.com"
    if request.method == "POST" or request.args:
        if request.form:
            args = request.form.to_dict(flat=True)
        else:
            args = request.args.to_dict(flat=True)
        rv = timeline.Timeline.createTimeline(timelineServiceUrl=timelineServiceUrl, **args)
        return Response(json.dumps(rv), mimetype="application/json")
    else:
        rv = timeline.Timeline.getAll()
        return Response(json.dumps(rv), mimetype="application/json")
    
@app.route(API_ROOT + "/<string:contextId>/<string:verb>", methods=["GET"])
def getContextVerb(contextId, verb):
    args = request.args.to_dict(flat=True)
    tl = timeline.Timeline.get(contextId)
    if not tl:
        abort(make_response("No such context: %s" % contextId, 404))
    method = getattr(tl, verb, None)
    if not method:
        abort(make_response("No such method: %s" % contextId, 404))
    try:
        rv = method(**args)
    except HTTPException:
        raise
    except:
        status = "500 Internal server error: %s" % ' '.join(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
        traceback.print_exc()
        abort(make_response(status, 500))
    return Response(json.dumps(rv), mimetype="application/json")


@app.route(API_ROOT + "/<string:contextId>/<string:verb>", methods=["PUT"])
def putContextVerb(contextId, verb):
    # Argument passing is convoluted...
    args = {}
    if request.args:
        args.update(request.args.to_dict(flat=True))
    if request.form:
        args.update(request.form.to_dict(flat=True))
    if request.is_json:
        jargs = request.get_json()
        if type(jargs) == type("") or type(jargs) == type(u""):
            # xxxjack Bug workaround, 21-Dec-2016
            jargs = json.loads(jargs)
        # Usually the json is an object/dict, sometimes not.
        if type(jargs) == type({}):
            args.update(jargs)
        else:
            args['postData'] = jargs
    tl = timeline.Timeline.get(contextId)
    if not tl:
        abort(make_response("No such context: %s" % contextId, 404))
    method = getattr(tl, verb, None)
    if not method:
        abort(make_response("No such method: %s" % contextId, 404))
    try:
        rv = method(**args)
    except HTTPException:
        raise
    except:
        status = "500 Internal server error: %s" % ' '.join(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
        traceback.print_exc()
        abort(make_response(status, 500))
    return Response(json.dumps(rv), mimetype="application/json")

@app.route(API_ROOT + "/<string:contextId>/<string:verb>", methods=["POST"])
def postContextVerb(contextId, verb):
    return putContextVerb(contextId, verb)

@app.route(API_ROOT + "/<string:contextId>", methods=["DELETE"])
def deleteContext(contextId):
    tl = timeline.Timeline.get(contextId)
    if tl:
        tl.delete()
    return ''

class Server:
    def __init__(self, port):
        self.port = port if port else 8080
        
        self.server = WSGIServer(("0.0.0.0", self.port), app)
        
    def run(self):
        print("timelineService: running on port %d" % self.port)
        self.server.serve_forever()
        
_singleton = None
def app_singleton(port=None):
    global _singleton
    if _singleton == None:
        _singleton = Server(port)
    return _singleton
    
