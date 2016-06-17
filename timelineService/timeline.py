import requests

DEBUG=True

class Timeline:
    ALL_CONTEXTS = {}

    @classmethod
    def createTimeline(cls, contextId):
        """Factory function: create a new context"""
        assert not contextId in cls.ALL_CONTEXTS
        new = cls(contextId)
        cls.ALL_CONTEXTS[contextId] = new
        return dict(contextId=contextId)
        
    @classmethod
    def get(cls, contextId):
        """Getter: return context for given ID"""
        if not contextId in cls.ALL_CONTEXTS:
        	return cls.createTimeline(contextId)
        return cls.ALL_CONTEXTS[contextId]
        
    @classmethod
    def getAll(cls):
        return cls.ALL_CONTEXTS.keys()
        
    def __init__(self, contextId):
        """Initializer, creates a new context and stores it for global reference"""
        self.contextId = contextId
        self.timelineUrl = None
        self.layoutServiceId = None
        self.dmappTimeline = None
        self.dmappId = None
        # Do other initialization
        
    def destroyTimeline(self):
        """Destructor, sort-of"""
        if DEBUG: print "Timeline(%s): destroyTimeline()" % self.contextId
        del self.ALL_CONTEXTS[self.contextId]
        self.contextId = None
        self.timelineUrl = None
        self.dmappTimeline = None
        self.dmappId = None
        self.layoutService = None
        self.dmappComponents = {}
        # Do other cleanup
        
    def dump(self):
        return dict(
            contextId=self.contextId, 
            timelineUrl=self.timelineUrl, 
            dmappTimeline=self.dmappTimeline, 
            dmappId=self.dmappId,
            layoutService=repr(self.layoutService),
            dmappComponents=self.dmappComponents.keys(),
            )
        
    def loadDMAppTimeline(self, timelineUrl, layoutServiceId=None):
        if DEBUG: print "Timeline(%s): loadDMAppTimeline(%s)" % (self.contextId, timelineUrl)
        pass
        assert self.timelineUrl is None
        assert self.dmappTimeline is None
        assert self.dmappId is None
        self.timelineUrl = timelineUrl
        self.layoutService = layoutServiceId
        self.dmappTimeline = "Here will be a document encoding the timeline"
        self.dmappId = "dmappid-42"
            
        self.layoutService = ProxyLayoutService(self.layoutService, self.contextId, self.dmappId)
        self.clockService = ProxyClockService()
        self._populateTimeline()
        self._updateTimeline()
        return {'dmappId':self.dmappId}
        
    def unloadDMAppTimeline(self, dmappId):
        if DEBUG: print "Timeline(%s): unloadDMAppTimeline(%s)" % (self.contextId, dmappId)
        pass
        assert self.timelineUrl
        assert self.dmappTimeline
        assert self.dmappId == dmappId
        self.timelineUrl = None
        self.dmappTimeline = None
        self.dmappId = None
        
    def dmappcStatus(self, dmappId, componentId, status):
        if DEBUG: print "Timeline(%s): dmappcStatus(%s, %s, %s)" % (self.contextId, dmappId, componentId, status)
        assert dmappId == self.dmappId
        c = self.dmappComponents[componentId]
        c.statusReport(status)
        self._updateTimeline()
                
    def timelineEvent(self, eventId):
        if DEBUG: print "Timeline(%s): timelineEvent(%s)" % (self.contextId, eventId)
        pass
        
    def clockChanged(self, *args, **kwargs):
        if DEBUG: print "Timeline(%s): clockChanged(%s, %s)" % (self.contextId, args, kwargs)
        pass
        
    def _populateTimeline(self):
        """Create proxy objects, etc, using self.dmappTimeline"""
        self.dmappComponents = dict(
            masterVideo = ProxyDMAppComponent(self.clockService, self.layoutService, "masterVideo", "video", "http://example.com/masterVideo.mp4", 0, None),
            hello = ProxyDMAppComponent(self.clockService, self.layoutService, "hello", "text", None, 0, 10),
            world = ProxyDMAppComponent(self.clockService, self.layoutService, "world", "text", None, 0, None),
            goodbye = ProxyDMAppComponent(self.clockService, self.layoutService, "goodbye", "text", None, 10, None),
            )
     
    def _updateTimeline(self):
        # Initialize any components that can be initialized
        for c in self.dmappComponents.values():
            if c.shouldInitialize():
                c.initComponent()
        # Check whether all components that should have been initialized are so
        for c in self.dmappComponents.values():
            if c.shouldStart():
                c.startComponent(c.startTime)
        for c in self.dmappComponents.values():
            if c.shouldStop():
                c.stopComponent(c.stopTime)
    
class ProxyClockService:
    def __init__(self):
        self.epoch = 0
        self.running = False
        
    def now(self):
        if not self.running:
            return self.epoch
        return time.time() - self.epoch
        
    def start(self):
        if not self.running:
            self.epoch = time.time() - self.epoch
            self.running = True
            
    def stop(self):
        if self.running:
            self.epoch = time.time() - self.epoch
            self.running = False
            
class ProxyLayoutService:
    def __init__(self, contactInfo, contextId, dmappId):
        self.contactInfo = contactInfo
        self.contextId = contextId
        self.dmappId = dmappId
        
    def getContactInfo(self):
        return self.contactInfo + '/context/' + self.contextId + '/dmapp/' + self.dmappId
        
class ProxyDMAppComponent:
    def __init__(self, clockService, layoutService, dmappcId, klass, url, startTime, stopTime):
        self.clockService = clockService
        self.layoutService = layoutService
        self.dmappcId = dmappcId
        self.klass = klass
        if not url: url = ""
        self.url = url
        self.startTime = startTime
        self.stopTime = stopTime
        self.status = None

    def _getContactInfo(self):
        contactInfo = self.layoutService.getContactInfo()
        contactInfo += '/component/' + self.dmappcId
        return contactInfo
        
    def initComponent(self):
        entryPoint = self._getContactInfo()
        entryPoint += '/actions/init'
        print "CALL", entryPoint
        r = requests.post(entryPoint, json={'class':self.klass, 'url':self.url})
        r.raise_for_status()
        print "RETURNED"
        self.status = "initRequested"
        
    def startComponent(self, timeSpec):
        assert self.status == "initialized"
        entryPoint = self._getContactInfo()
        entryPoint += '/actions/start'
        print "CALL", entryPoint
        r = requests.post(entryPoint)
        r.raise_for_status()
        print "RETURNED"
        
    def stopComponent(self, timeSpec):
        entryPoint = self._getContactInfo()
        entryPoint += '/actions/stop'
        print "CALL", entryPoint
        r = requests.post(entryPoint)
        r.raise_for_status()
        print "RETURNED"
       
    def statusReport(self, status):
        self.status = status
        
    def shouldInitialize(self):
        return self.status == None
        
    def shouldStart(self):
        return self.status == "initialized" and self.startTime >= self.clockService.now()
        
    def shouldStop(self):
        return self.status == "running" and self.stopTime is not None and self.stopTime >= self.clockService.now()
        
        
