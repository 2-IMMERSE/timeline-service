DEBUG=True

class Timeline:
    ALL_CONTEXTS = {}

    @classmethod
    def createTimeline(cls, contextId):
        """Factory function: create a new context"""
        assert not contextId in cls.ALL_CONTEXTS
        new = cls(contextId)
        cls.ALL_CONTEXTS[contextId] = new
        return contextId
        
    @classmethod
    def get(cls, contextId):
        """Getter: return context for given ID"""
        return cls.ALL_CONTEXTS[contextId]
        
    @classmethod
    def getAll(cls):
        return cls.ALL_CONTEXTS.keys()
        
    def __init__(self, contextId):
        """Initializer, creates a new context and stores it for global reference"""
        if DEBUG: print "Timeline(%s): created with object %s" % (contextId, self)
        self.contextId = contextId
        self.dmappSpec = None
        self.dmappTimeline = None
        self.dmappId = None
        # Do other initialization
        
    def destroyTimeline(self):
        """Destructor, sort-of"""
        if DEBUG: print "Timeline(%s): destroyTimeline()" % self.contextId
        del self.ALL_CONTEXTS[self.contextId]
        self.contextId = None
        self.dmappSpec = None
        self.dmappTimeline = None
        self.dmappId = None
        # Do other cleanup
        
    def dump(self):
        return dict(contextId=self.contextId, dmappSpec=self.dmappSpec, dmappTimeline=self.dmappTimeline, dmappId=self.dmappId)
        
    def loadDMAppTimeline(self, dmappSpec):
        if DEBUG: print "Timeline(%s): loadDMAppTimeline(%s)" % (self.contextId, dmappSpec)
        pass
        assert self.dmappSpec is None
        assert self.dmappTimeline is None
        assert self.dmappId is None
        self.dmappSpec = dmappSpec
        self.dmappTimeline = "Here will be a document encoding the timeline"
        self.dmappId = "dmappid-42"
        return {'dmappId':self.dmappId}
        
    def unloadDMAppTimeline(self, dmappId):
        if DEBUG: print "Timeline(%s): unloadDMAppTimeline(%s)" % (self.contextId, dmappId)
        pass
        assert self.dmappSpec
        assert self.dmappTimeline
        assert self.dmappId == dmappId
        self.dmappSpec = None
        self.dmappTimeline = None
        self.dmappId = None
        
    def dmappcStatus(self, dmappId, componentId, status):
        if DEBUG: print "Timeline(%s): dmappcStatus(%s, %s, %s)" % (self.contextId, dmappId, componentId, status)
        pass
        
    def timelineEvent(self, eventId):
        if DEBUG: print "Timeline(%s): timelineEvent(%s)" % (self.contextId, eventId)
        pass
        
    def clockChanged(self, *args, **kwargs):
        if DEBUG: print "Timeline(%s): clockChanged(%s, %s)" % (self.contextId, args, kwargs)
        pass
        
