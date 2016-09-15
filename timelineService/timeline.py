import requests
import clocks
import document
import logging

DEBUG=True
DEBUG_OUTGOING=False
if DEBUG_OUTGOING:
    import httplib
    import logging
    httplib.HTTPConnection.debuglevel = 1

    # You must initialize logging, otherwise you'll not see debug output.
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

class Timeline:
    ALL_CONTEXTS = {}

    @classmethod
    def createTimeline(cls, contextId, layoutServiceUrl):
        """Factory function: create a new context"""
        assert not contextId in cls.ALL_CONTEXTS
        new = cls(contextId, layoutServiceUrl)
        cls.ALL_CONTEXTS[contextId] = new
        return None

    @classmethod
    def get(cls, contextId):
        """Getter: return context for given ID"""
        if not contextId in cls.ALL_CONTEXTS:
            return None
        return cls.ALL_CONTEXTS[contextId]

    @classmethod
    def getAll(cls):
        return cls.ALL_CONTEXTS.keys()

    def __init__(self, contextId, layoutServiceUrl):
        """Initializer, creates a new context and stores it for global reference"""
        document.logger.setLevel(logging.DEBUG)
        self.contextId = contextId
        self.timelineDocUrl = None
        self.layoutServiceUrl = layoutServiceUrl
        self.dmappTimeline = None
        self.dmappId = None
        self.dmappComponents = {}
        self.clockService = clocks.CallbackPausableClock(clocks.SystemClock())
        self.document = document.Document(self.clockService)
        self.document.setDelegateFactory(self.dmappComponentDelegateFactory)
        # Do other initialization

    def destroyTimeline(self):
        """Destructor, sort-of"""
        if DEBUG: print "Timeline(%s): destroyTimeline()" % self.contextId
        del self.ALL_CONTEXTS[self.contextId]
        self.contextId = None
        self.timelineDocUrl = None
        self.dmappTimeline = None
        self.dmappId = None
        self.layoutService = None
        self.dmappComponents = {}
        self.document = None
        # Do other cleanup
        return None

    def dump(self):
        rv = dict(
            contextId=self.contextId,
            timelineDocUrl=self.timelineDocUrl,
            dmappTimeline=self.dmappTimeline,
            dmappId=self.dmappId,
            layoutService=repr(self.layoutService),
            layoutServiceUrl=self.layoutServiceUrl,
            dmappComponents=self.dmappComponents.keys(),
            document=self.document.dumps(),
            )
        return rv

    def dmappComponentDelegateFactory(self, elt, document, clock):
        rv = ProxyDMAppComponent(elt, document, clock, self.layoutService)
        self.dmappComponents[rv.dmappcId] = rv
        return rv

    def loadDMAppTimeline(self, timelineDocUrl, dmappId):
        if DEBUG: print "Timeline(%s): loadDMAppTimeline(%s)" % (self.contextId, timelineDocUrl)
        pass
        assert self.timelineDocUrl is None
        assert self.dmappTimeline is None
        assert self.dmappId is None
        self.timelineDocUrl = timelineDocUrl
        self.dmappTimeline = "Here will be a document encoding the timeline"
        self.dmappId = dmappId

        self.layoutService = ProxyLayoutService(self.layoutServiceUrl, self.contextId, self.dmappId)
        self._populateTimeline()
        self._updateTimeline()
        return None

    def unloadDMAppTimeline(self, dmappId):
        if DEBUG: print "Timeline(%s): unloadDMAppTimeline(%s)" % (self.contextId, dmappId)
        pass
        assert self.timelineDocUrl
        assert self.dmappTimeline
        assert self.dmappId == dmappId
        self.timelineDocUrl = None
        self.dmappTimeline = None
        self.dmappId = None
        return None

    def dmappcStatus(self, dmappId, componentId, status):
        if DEBUG: print "Timeline(%s): dmappcStatus(%s, %s, %s)" % (self.contextId, dmappId, componentId, status)
        assert dmappId == self.dmappId
        c = self.dmappComponents[componentId]
        c.statusReport(status)
        self._updateTimeline()
        return None

    def timelineEvent(self, eventId):
        if DEBUG: print "Timeline(%s): timelineEvent(%s)" % (self.contextId, eventId)
        pass
        return None

    def clockChanged(self, *args, **kwargs):
        if DEBUG: print "Timeline(%s): clockChanged(%s, %s)" % (self.contextId, args, kwargs)
        self._updateTimeline()
        return None

    def _populateTimeline(self):
        """Create proxy objects, etc, using self.dmappTimeline"""
        #self.document.load(self.timelineDocUrl)
        self.document.load("api/sample-hello.xml")
        self.document.addDelegates()

    def _updateTimeline(self):
        curState = self.document.getDocumentState()
        if curState == document.State.idle:
            # We need to initialize the document
            self.document.runDocumentInit()
        elif curState == document.State.inited:
            # We need to start the document
            #self.document.clock.start()
            self.document.runDocumentStart()
        elif curState == document.State.started and self.document.clock.now() == 0:
            self.document.report(logging.DEBUG, 'RUN', 'startClock')
            self.document.clock.start()
        self.document.runAvailable()

class ProxyLayoutService:
    def __init__(self, contactInfo, contextId, dmappId):
        self.contactInfo = contactInfo
        self.contextId = contextId
        self.dmappId = dmappId

    def getContactInfo(self):
        return self.contactInfo + '/context/' + self.contextId + '/dmapp/' + self.dmappId

class ProxyDMAppComponent(document.TimeElementDelegate):
    def __init__(self, elt, doc, clock, layoutService):
    #def __init__(self, clockService, layoutService, dmappcId, klass, url, startTime, stopTime):
        document.TimeElementDelegate.__init__(self, elt, doc, clock)
        self.layoutService = layoutService
        self.dmappcId = self.elt.get(document.NS_2IMMERSE("dmappcid"))
        self.klass = self.elt.get(document.NS_2IMMERSE("class"))
        self.url = self.elt.get(document.NS_2IMMERSE("url"), "")
        self.parameters = {}
        if self.klass == "mastervideo":
            self.klass = "video"
            self.parameters['syncMode'] = "master"
        if self.klass == "video":
            self.parameters['mediaUrl'] = self.url
            self.url = ''
        assert self.dmappcId
        assert self.klass

    def _getContactInfo(self):
        contactInfo = self.layoutService.getContactInfo()
        contactInfo += '/component/' + self.dmappcId
        return contactInfo

    def _getTime(self, timestamp):
        return timestamp + 0.0

    def initTimelineElement(self):
        self.assertState('ProxyDMAppComponent.initTimelineElement()', document.State.idle)
        self.setState(document.State.initing)
        self.document.report(logging.INFO, '>>>>>', 'INIT', self.document.getXPath(self.elt), self._getParameters())
        entryPoint = self._getContactInfo()
        entryPoint += '/actions/init'
        args = {'class':self.klass, 'url':self.url, 'parameters':self.parameters}
        print "CALL", entryPoint, 'JSON', args
        r = requests.post(entryPoint, json=args)
        r.raise_for_status()
        print "RETURNED"
        self.initSent = True
        self.status = "initRequested"

    def startTimelineElement(self):
        self.assertState('ProxyDMAppComponent.initTimelineElement()', document.State.inited)
        self.setState(document.State.starting)
        self.document.report(logging.INFO, '>>>>>', 'START', self.document.getXPath(self.elt), self._getParameters())
        entryPoint = self._getContactInfo()
        entryPoint += '/actions/start'
        args = dict(startTime=self._getTime(self.clock.now()))
        print "CALL", entryPoint, "ARGS", args
        r = requests.post(entryPoint, params=args)
        r.raise_for_status()
        self.startSent = True
        print "RETURNED"

    def stopTimelineElement(self):
        self.document.report(logging.INFO, '>>>>>', 'STOP', self.document.getXPath(self.elt))
        entryPoint = self._getContactInfo()
        entryPoint += '/actions/stop'
        args = dict(stopTime=self._getTime(self.clock.now()))
        print "CALL", entryPoint, "ARGS", args
        r = requests.post(entryPoint, params=args)
        r.raise_for_status()
        self.stopSent = True
        print "RETURNED"

    def statusReport(self, status):
        self.document.report(logging.INFO, '<<<<<', status, self.document.getXPath(self.elt))
        self.setState(status)

    def _getParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in document.NS_2IMMERSE:
                rv[document.NS_2IMMERSE.localTag(k)] = self.elt.attrib[k]
        return rv
