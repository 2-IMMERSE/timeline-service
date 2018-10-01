from __future__ import print_function
from __future__ import absolute_import
import sys
import web
import time
import datetime
from . import timeline
import json
import argparse
import logging
import traceback
import os

# Make stdout unbuffered
class Unbuffered(object):
   def __init__(self, stream):
       self.stream = stream
   def write(self, data):
       self.stream.write(data)
       self.stream.flush()
   def __getattr__(self, attr):
       return getattr(self.stream, attr)

class StreamToLogger(object):
   def __init__(self, logger, log_level=logging.INFO):
      self.logger = logger
      self.log_level = log_level
      self.linebuf = ''

   def write(self, buf):
      for line in buf.rstrip().splitlines():
         self.logger.log(self.log_level, line.rstrip())

logging.basicConfig()


# Default logging configuration: INFO for document and timeline (useful to app developers), WARNING for everything else.
DEFAULT_LOG_CONFIG="document:INFO,timeline:INFO,INFO"

class MyFormatter(logging.Formatter):

    def format(self, record):
        contextID = None
        dmappID = None
        if hasattr(record, 'contextID'):
            contextID = record.contextID
        if hasattr(record, 'dmappID'):
            dmappID = record.dmappID
        source = "TimelineService"
        level = record.levelname
        subSource = record.module
        message = logging.Formatter.format(self, record)
        logmessage = repr('"' + message)
        if logmessage[0] == 'u':
            logmessage = logmessage[1:]
        logmessage = "'" + logmessage[2:]
        
        rvList = ['2-Immerse']
        if source:
            rvList.append('source:%s' % source)
        if subSource:
            rvList.append('subSource:%s' % subSource)
        if level:
            rvList.append('level:%s' % level)
        if contextID:
            rvList.append('contextID:%s' % contextID)
        if dmappID:
            rvList.append('dmappID:%s' % dmappID)
        if hasattr(record, 'xpath'):
            rvList.append('xpath:%s ' % repr(record.xpath))
        if hasattr(record, 'dmappcID'):
            rvList.append('dmappcID:%s ' % repr(record.dmappcID))
        rvList.append('sourcetime:%s' % datetime.datetime.fromtimestamp(time.time()).isoformat())
        rvList.append('logmessage:%s' % logmessage)
        return ' '.join(rvList)
        
urls = (
    '/timeline/v1/context', 'timelineServerServer',
    '/timeline/v1/context/(.*)/(.*)', 'timelineServer',
    '/timeline/v1/context/(.*)', 'timelineServer',
)

app = web.application(urls, globals())

def appendCorsHeaders():
    web.ctx.headers.append(('Allow', 'GET,PUT,POST,DELETE'))
    web.ctx.headers.append(('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE'))
    web.ctx.headers.append(('Access-Control-Allow-Origin', '*'))

class timelineServerServer:
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

class timelineServer:
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

def main():
    parser = argparse.ArgumentParser(description='Run 2immerse Timeline Service')
    parser.add_argument('--layoutService', metavar="URL", help="Override URL for contacting layout service")
    parser.add_argument('--port', type=int, help="Set port to listen on")
    parser.add_argument('--logLevel', metavar='SPEC', help="Set log levels (comma-separated list of [loggername:]LOGLEVEL)", default=DEFAULT_LOG_CONFIG)
    parser.add_argument('--noKibana', action='store_true', help="Use human-readable log formatting in stead of Kibana-style formatting")
    args = parser.parse_args()
    if args.noKibana:
        global MyFormatter
        MyFormatter = logging.Formatter
        sys.stdout = Unbuffered(sys.stdout)
    else:
        sys.stdout = StreamToLogger(logging.getLogger('stdout'), logging.INFO)
        sys.stderr = StreamToLogger(logging.getLogger('stderr'), logging.INFO)
    if args.logLevel:
        for ll in args.logLevel.split(','):
            if ':' in ll:
                loggerToModify = logging.getLogger(ll.split(':')[0])
                newLevel = getattr(logging, ll.split(':')[1])
            else:
                loggerToModify = logging.getLogger()
                newLevel = getattr(logging, ll)
            loggerToModify.setLevel(newLevel)
    
    rootLogger = logging.getLogger()
    rootLogger.handlers[0].setFormatter(MyFormatter())

    rootLogger.log(logging.INFO, "Timeline service INFO log line")
    print("Timeline service stdout print")
    print("Timeline service stderr print", file=sys.stderr)
    if True:
        # Temporary measure: the origin server certificate is untrusted on our docker containers.
        rootLogger.log(logging.WARN, "https verification disabled for now (Nov 2016)")
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
    if args.layoutService:
        timeline.LAYOUTSERVICE = args.layoutService
    del sys.argv[1:]
    if args.port:
        sys.argv.append(str(args.port))
    app.run()

main()
