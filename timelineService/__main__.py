import sys
import web
import time
import datetime
import timeline
import json
import argparse
import logging

# Make stdout unbuffered
class Unbuffered(object):
   def __init__(self, stream):
       self.stream = stream
   def write(self, data):
       self.stream.write(data)
       self.stream.flush()
   def __getattr__(self, attr):
       return getattr(self.stream, attr)

import sys
sys.stdout = Unbuffered(sys.stdout)

logging.basicConfig()

# Default logging configuration: INFO for document and timeline (useful to app developers), WARNING for everything else.
DEFAULT_LOG_CONFIG="document:INFO,timeline:INFO,WARNING"

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
        rvList.append('sourcetime:%s' % datetime.datetime.fromtimestamp(time.time()).isoformat())
        rvList.append('logmessage:%s' % logmessage)
        return ' '.join(rvList)
        
urls = (
    '/timeline/v1/context', 'timelineServerServer',
    '/timeline/v1/context/(.*)/(.*)', 'timelineServer',
    '/timeline/v1/context/(.*)', 'timelineServer',
)

app = web.application(urls, globals())

class timelineServerServer:
    """Toplevel REST interface: create new timeline servers and get the identity of existing ones"""
    # Note this is hack-y: post/get work with both /timelineServer and /timelineServer/createTimeline
    # and do the same. To be fixed.

    def GET(self):
        rv = timeline.Timeline.getAll()
        # HACK WARNING: GET with arguments is treated as POST
        if web.input():
            return self.POST()
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

    def POST(self):
        args = web.input()
        rv = timeline.Timeline.createTimeline(**args)
        if rv == None or rv == '':
            web.ctx.status = '204 No Content'
            return ''
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

class timelineServer:
    """Per-timeline service. Need to work out which verbs allow get/put/post and how to encode that."""

    def GET(self, contextId, verb=None):
        if not verb:
            return web.badrequest()
        args = web.input()
        tl = timeline.Timeline.get(contextId)
        if not tl:
            return web.notfound("404 No such context: %s" % contextId)
        method = getattr(tl, verb, None)
        if not method:
            return web.notfound("404 No such verb: %s" % verb)
        rv = method(**args)
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

    def PUT(self, contextId, verb=None):
        if not verb:
            return web.badrequest()
        args = dict(web.input())
        # PUT gets data as a JSON body, sometimes?
        if not args:
            data = web.data()
            if data:
                args = json.loads(data)
        tl = timeline.Timeline.get(contextId)
        if not tl:
            return web.notfound("404 No such context: %s" % contextId)
        method = getattr(tl, verb, None)
        if not method:
            return web.notfound("404 No such verb: %s" % verb)
        rv = method(**args)
        if rv == None or rv == '':
            web.ctx.status = '204 No Content'
            return ''
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

    def POST(self, contextId, verb=None):
        if not verb:
            return web.badrequest()
        args = web.input()
        tl = timeline.Timeline.get(contextId)
        if not tl:
            return web.notfound("404 No such context: %s" % contextId)
        method = getattr(tl, verb, None)
        if not method:
            return web.notfound("404 No such verb: %s" % verb)
        rv = method(**args)
        if rv == None or rv == '':
            web.ctx.status = '204 No Content'
            return ''
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

    def DELETE(self, contextId, verb=None):
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
    parser.add_argument('--noTransactions', action='store_true', help="Don't transaction interface to layout service for dmappc updates (default: simple calls)")
    parser.add_argument('--port', type=int, help="Set port to listen on")
    parser.add_argument('--logLevel', metavar='SPEC', help="Set log levels (comma-separated list of [loggername:]LOGLEVEL)", default=DEFAULT_LOG_CONFIG)
    args = parser.parse_args()
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

    if True:
        # Temporary measure: the origin server certificate is untrusted on our docker containers.
        rootLogger.log(logging.WARN, "https verification disabled for now (Nov 2016)")
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
    if args.noTransactions:
        timeline.TRANSACTIONS = False
    if args.layoutService:
        timeline.LAYOUTSERVICE = args.layoutService
    del sys.argv[1:]
    if args.port:
        sys.argv.append(str(args.port))
    app.run()

main()
