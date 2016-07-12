import time
import sys
import dvbcss
import dvbcss.clock
import dvbcss.protocol.client.ts
import dvbcss.protocol.server.ts
import cherrypy

class DvbClientClock:
    def __init__(self, tsUrl, contentIDStem, timelineSelector):
        timelineFreq = 1000 # Ticks-per-second we want for the clock we expose.
        #
        # First we need a monotonic clock. For the time being we use SysClock, will
        # use TunableClock or something later.
        #
        self.wallClock = dvbcss.clock.SysClock()
        #
        # Based on that we create a second clock, that will run along with that clock,
        # but possibly updated by the clock master.
        #
        self.timelineClock = dvbcss.clock.CorrelatedClock(self.wallClock, timelineFreq)
        #
        # Now we can create the controller, that will update our timelineClock
        # when messages form the master come in
        #
        self.startClient(tsUrl, contentIDStem, timelineSelector)
        
    def startClient(self, tsUrl, contentIDStem, timelineSelector):
        self.controller = dvbcss.protocol.client.ts.TSClientClockController(
            tsUrl,
            contentIDStem,
            timelineSelector,
            self.timelineClock,
            correlationChangeThresholdSecs=0.001
            )
        #
        # Connect callbacks (xxxjack should use subclassing here) and start it
        # running
        #
        self.controller.onConnected = self.onConnected
        self.controller.onDisconnected = self.onDisconnected
        self.controller.onTimelineAvailable = self.onTimelineAvailable
        self.controller.onTimelineUnavailable = self.onTimelineUnavailable
        self.controller.onTimingChange = self.onTimingChange
        
    def connect(self):
        self.controller.connect()
            
    def onConnected(self, *args, **kwargs):
        print 'xxxjack: DvbClientClock.onConnected args=%s kwargs=%s' % (args, kwargs)
        
    def onDisconnected(self, *args, **kwargs):
        print 'xxxjack: DvbClientClock.onDisconnected args=%s kwargs=%s' % (args, kwargs)
        
    def onTimelineAvailable(self, *args, **kwargs):
        print 'xxxjack: DvbClientClock.onTimelineAvailable args=%s kwargs=%s' % (args, kwargs)
        
    def onTimelineUnavailable(self, *args, **kwargs):
        print 'xxxjack: DvbClientClock.onTimelineUnavailable args=%s kwargs=%s' % (args, kwargs)
        
    def onTimingChange(self, *args, **kwargs):
        print 'xxxjack: DvbClientClock.onTimingChange args=%s kwargs=%s' % (args, kwargs)
        
    def now(self):
        return self.timelineClock.ticks/1000.0
        
class DvbServerClock:
    def __init__(self, contentId, timelineSelector, host='127.0.0.1', port=7681):
        timelineFreq = 1000 # Ticks-per-second we want for the clock we expose.
        #
        # First we need a monotonic clock. For the time being we use SysClock, will
        # use TunableClock or something later.
        #
        self.wallClock = dvbcss.clock.SysClock()
        #
        # Based on that we create a second clock, that will run along with that clock,
        # but possibly updated by the clock master.
        #
        self.timelineClock = dvbcss.clock.CorrelatedClock(self.wallClock, timelineFreq)
        #
        # Now we can create the controller, that will update our timelineClock
        # when messages form the master come in
        #
        self.startServer(contentId, timelineSelector, host, port)
        
    def startServer(self, contentId, timelineSelector, host, port):
        #
        # Create clock server
        #
        self.tsServer = dvbcss.protocol.server.ts.TSServer(
            contentId=contentId,
            wallClock = self.wallClock,
            maxConnectionsAllowed=3,
            )
            
        self.timelineTimeline = dvbcss.protocol.server.ts.SimpleClockTimelineSource(
            timelineSelector=timelineSelector,
            wallClock=self.wallClock,
            clock=self.timelineClock,
            )
        self.tsServer.attachTimelineSource(self.timelineTimeline)
        
        #
        # Boilerplate picked up from pydvbcss/examples/TSServer.py, no clue how it works
        #
        cherrypy.config.update({
            'server.socket_host' : host,
            'server.socket_port' : port,
            'engine.autoreload.on' : False,
            })

        class Root(object):
            @cherrypy.expose
            def ts(self):
                pass
                
        cherrypy.tree.mount(Root(), '/', config={
            "/ts" : {
                "tools.dvb_ts.on" : True,
                "tools.dvb_ts.handler_cls" : self.tsServer.handler
                }
            })
            
        cherrypy.engine.start()
        
                
    def now(self):
        return self.timelineClock.ticks/1000.0
        
        
if __name__ == '__main__':
    if sys.argv[1] == 'client':
        c = DvbClientClock('ws://127.0.0.1:7681/ts', 'dvb:', 'urn:dvb:css:timeline:pts')
        c.connect()
        while True:
            time.sleep(1)
            print
            print 'C', time.time(), c.now(),
            sys.stdout.flush()
    elif sys.argv[1] == 'server':
        s = DvbServerClock('dvb:', 'urn:dvb:css:timeline:pts', '127.0.0.1', 7681)
        while True:
            time.sleep(1)
            print
            print 'S', time.time(), s.now(),
            sys.stdout.flush()

