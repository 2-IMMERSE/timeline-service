from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
from builtins import str
from builtins import object
import traceback
import sys
import json
import os
import web
from . import timeline

        
urls = (
    '/timeline/v1/context', 'timelineServerServer',
    '/timeline/v1/context/(.*)/(.*)', 'timelineServer',
    '/timeline/v1/context/(.*)', 'timelineServer',
)

app = web.application(urls, globals())

def appendCorsHeaders():
    if sys.version_info[0] < 3:
        def A(x): return x.encode('ascii')
    else:
        def A(x): return x
    web.ctx.headers.append((A('Allow'), A('GET,PUT,POST,DELETE')))
    web.ctx.headers.append((A('Access-Control-Allow-Methods'), A('GET,PUT,POST,DELETE')))
    web.ctx.headers.append((A('Access-Control-Allow-Origin'), A('*')))

class timelineServerServer(object):
    """Toplevel REST interface: create new timeline servers and get the identity of existing ones"""
    # Note this is hack-y: post/get work with both /timelineServer and /timelineServer/createTimeline
    # and do the same. To be fixed.

    def GET(self):
        rv = timeline.Timeline.getAll()
        # HACK WARNING: GET with arguments is treated as POST
        if web.input():
            return self.POST()
        appendCorsHeaders()
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

    def POST(self):
        appendCorsHeaders()
        args = web.input()

        # XXX Ugly hack because I don't know what else to do
        timelineServiceUrl = os.getenv("TIMELINE_SERVICE_URL")

        if timelineServiceUrl is None:
            timelineServiceUrl = web.ctx.env.get("wsgi.url_scheme", "http") + "://" + web.ctx.env.get("HTTP_HOST")

        rv = timeline.Timeline.createTimeline(timelineServiceUrl=timelineServiceUrl, **args)

        if rv == None or rv == '':
            web.ctx.status = '204 No Content'
            return ''
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

class timelineServer(object):
    """Per-timeline service. Need to work out which verbs allow get/put/post and how to encode that."""

    def OPTIONS(self, *args):
        appendCorsHeaders()
        return ''

    def GET(self, contextId, verb=None):
        appendCorsHeaders()
        if not verb:
            return web.badrequest()
        args = web.input()
        tl = timeline.Timeline.get(contextId)
        if not tl:
            return web.notfound("404 No such context: %s" % contextId)
        method = getattr(tl, verb, None)
        if not method:
            return web.notfound("404 No such verb: %s" % verb)
        try:
            rv = method(**args)
        except web.HTTPError:
            raise
        except:
            web.ctx.status = "500 Internal server error: %s" % ' '.join(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
            traceback.print_exc()
            return ''
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

    def PUT(self, contextId, verb=None):
        appendCorsHeaders()
        if not verb:
            return web.badrequest()
        args = dict(web.input())
        # PUT gets some data as a JSON body, sometimes...
        data = web.data()
        if data:
            args2 = json.loads(data)
            if type(args2) == type('') or type(args2) == type(u''):
                # xxxjack Bug workaround, 21-Dec-2016
                args2 = json.loads(args2)
            args.update(args2)
        tl = timeline.Timeline.get(contextId)
        if not tl:
            return web.notfound("404 No such context: %s" % contextId)
        method = getattr(tl, verb, None)
        if not method:
            return web.notfound("404 No such verb: %s" % verb)
        try:
            rv = method(**args)
        except web.HTTPError:
            raise
        except:
            web.ctx.status = "500 Internal server error: %s" % ' '.join(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
            traceback.print_exc()
            return ''
        if rv == None or rv == '':
            web.ctx.status = '204 No Content'
            return ''
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

    def POST(self, contextId, verb=None):
        appendCorsHeaders()
        if not verb:
            return web.badrequest()
        args = web.input()
        data = web.data()
        if data:
            args2 = json.loads(data)
            if type(args2) == type('') or type(args2) == type(u''):
                # xxxjack Bug workaround, 21-Dec-2016
                args2 = json.loads(args2)
            # Sometimes it is an object, sometimes it is something else (like an array)
            if type(args2) != type({}):
                args2 = {'postData' : args2}
            args.update(args2)
        tl = timeline.Timeline.get(contextId)
        if not tl:
            return web.notfound("404 No such context: %s" % contextId)
        method = getattr(tl, verb, None)
        if not method:
            return web.notfound("404 No such verb: %s" % verb)
        try:
            rv = method(**args)
        except web.HTTPError:
            raise
        except:
            web.ctx.status = "500 Internal server error: %s" % ' '.join(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
            traceback.print_exc()
            return ''
        if rv == None or rv == '':
            web.ctx.status = '204 No Content'
            return ''
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

    def DELETE(self, contextId, verb=None):
        appendCorsHeaders()
        args = web.input()
        if verb != None or args:
            return web.badrequest()
        tl = timeline.Timeline.get(contextId)
        if not tl:
            return web.notfound("404 No such context: %s" % contextId)
        tl.delete()
        web.ctx.status = '204 No Content'
        return ''
        
def app_singleton(port=None):
    del sys.argv[1:]
    if port:
        sys.argv.append(str(args.port))
    return app
