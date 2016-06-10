import sys
import web
import timeline
import json

urls = (
    '/timelineServer', 'timelineServerServer',
    '/timelineServer/createTimeline', 'timelineServerServer',
    '/timelineServer/(.*)/(.*)', 'timelineServer',
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
        web.header("Content-Type", "application/json")
        return json.dumps(rv)

class timelineServer:
    """Per-timeline service. Need to work out which verbs allow get/put/post and how to encode that."""

    def GET(self, contextId, verb):
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

    def PUT(self, contextId, verb):
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

    def POST(self, contextId, verb):
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

app.run()
