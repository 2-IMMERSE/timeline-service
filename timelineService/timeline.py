import requests
import clocks
import document
import logging
import urllib
import os

logger = logging.getLogger(__name__)

TRANSACTIONS=False

class Timeline:
    ALL_CONTEXTS = {}

    @classmethod
    def createTimeline(cls, contextId, layoutServiceUrl):
        """Factory function: create a new context"""
        if contextId in cls.ALL_CONTEXTS:
            logger.error("Creating timeline for context %s but it already exists" % contextId)
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
        logger.info("Timeline(%s): destroyTimeline()" % self.contextId)
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
        logger.info("Timeline(%s): loadDMAppTimeline(%s)" % (self.contextId, timelineDocUrl))
        if self.timelineDocUrl:
            logger.error("Timeline(%s): loadDMAppTimeline called but context already has a timeline (%s)", self.contextId, self.timelineDocUrl)
        assert self.timelineDocUrl is None
        assert self.dmappTimeline is None
        assert self.dmappId is None
        self.timelineDocUrl = timelineDocUrl
        # XXXJACK for debugging purposes, if the URL is a partial URL get it from the samples directory
        self.timelineDocUrl = urllib.basejoin(os.path.dirname(os.path.abspath(__file__)) + "/../samples/", self.timelineDocUrl)
        self.dmappId = dmappId

        self.layoutService = ProxyLayoutService(self.layoutServiceUrl, self.contextId, self.dmappId)
        self._populateTimeline()
        self._updateTimeline()
        return None

    def unloadDMAppTimeline(self, dmappId):
        logger.info("Timeline(%s): unloadDMAppTimeline(%s)" % (self.contextId, dmappId))
        assert self.timelineDocUrl
        assert self.dmappTimeline
        assert self.dmappId == dmappId
        self.timelineDocUrl = None
        self.dmappTimeline = None
        self.dmappId = None
        return None

    def dmappcStatus(self, dmappId, componentId, status):
        logger.debug("Timeline(%s): dmappcStatus(%s, %s, %s)" % (self.contextId, dmappId, componentId, status))
        assert dmappId == self.dmappId
        c = self.dmappComponents[componentId]
        c.statusReport(status)
        self._updateTimeline()
        return None

    def timelineEvent(self, eventId):
        logger.debug("Timeline(%s): timelineEvent(%s)" % (self.contextId, eventId))
        pass
        return None

    def clockChanged(self, *args, **kwargs):
        logger.debug("Timeline(%s): clockChanged(%s, %s)" % (self.contextId, args, kwargs))
        self._updateTimeline()
        return None

    def _populateTimeline(self):
        """Create proxy objects, etc, using self.dmappTimeline"""
        try:
            self.document.load(self.timelineDocUrl)
        except:
            logger.error("Timeline(%s): %s: Error loading document", self.contextId, self.timelineDocUrl)
            raise
        self.document.addDelegates()

    def _updateTimeline(self):
        curState = self.document.getDocumentState()
        if not curState: return
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
        self.layoutService.forwardActions()

class ProxyLayoutService:
    def __init__(self, contactInfo, contextId, dmappId):
        self.contactInfo = contactInfo
        self.contextId = contextId
        self.dmappId = dmappId
        self.actions = []
        self.actionsTimestamp = None

    def getContactInfo(self):
        return self.contactInfo + '/context/' + self.contextId + '/dmapp/' + self.dmappId

    def scheduleAction(self, timestamp, dmappcId, verb, config=None, parameters=None):
        self.actionsTimestamp = timestamp # XXXJACK Should really check that it is the same as previous ones....
        action = dict(action=verb, componentIds=[dmappcId])
        if config:
            action["config"] = config
        if parameters:
            action["parameters"] = parameters
        self.actions.append(action)

    def forwardActions(self):
        if not self.actions: return
        logger.debug("ProxyLayoutService: forwarding %d actions: %s", len(self.actions), repr(self.actions))
        entryPoint = self.getContactInfo() + '/transaction'
        body = dict(time=self.actionsTimestamp, actions=self.actions)
        r = requests.post(entryPoint, json=body)

        r.raise_for_status()
        self.actions = []
        self.actionsTimestamp = None

class ProxyDMAppComponent(document.TimeElementDelegate):
    def __init__(self, elt, doc, clock, layoutService):
        document.TimeElementDelegate.__init__(self, elt, doc, clock)
        self.layoutService = layoutService
        self.dmappcId = self.elt.get(document.NS_2IMMERSE("dmappcid"))
        self.klass = self.elt.get(document.NS_2IMMERSE("class"))
        self.url = self.elt.get(document.NS_2IMMERSE("url"), "")
        if not self.dmappcId:
            self.dmappcId = "unknown%d" % id(self)
            logger.error("Element %s: missing tim:dmappcId attribute, invented %s", self.document.getXPath(self.elt), self.dmappcId)
        assert self.dmappcId
        if not self.klass:
            self.klass = "unknownClass"
            logger.error("Element %s: missing tim:class attribute, invented %s", self.document.getXPath(self.elt), self.klass)
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
        config = {'class':self.klass, 'url':self.url}
        parameters = self._getParameters()
        if TRANSACTIONS:
            self.scheduleAction("init", config=config, parameters=parameters)
        else:
            # Direct API call has parameters inside config (sigh)
            config['parameters'] = parameters
            self.sendAction("init", body=config)

    def startTimelineElement(self):
        self.assertState('ProxyDMAppComponent.initTimelineElement()', document.State.inited)
        self.setState(document.State.starting)
        if TRANSACTIONS:
            self.scheduleAction("start")
        else:
            self.sendAction("start", queryParams=dict(startTime=self._getTime(self.clock.now())))

    def stopTimelineElement(self):
        self.setState(document.State.stopping)
        if TRANSACTIONS:
            self.scheduleAction("stop")
        else:
            self.sendAction("stop", queryParams=dict(stopTime=self._getTime(self.clock.now())))

    def sendAction(self, verb, queryParams=None, body=None):
        if body:
            self.document.report(logging.INFO, 'SEND', verb, self.document.getXPath(self.elt), self.dmappcId, repr(body))
        else:
            self.document.report(logging.INFO, 'SEND', verb, self.document.getXPath(self.elt), self.dmappcId)
        entryPoint = self._getContactInfo()
        entryPoint += '/actions/' + verb
        if body is None:
            r = requests.post(entryPoint, params=queryParams)
        else:
            r = requests.post(entryPoint, json=body, params=queryParams)

        r.raise_for_status()

    def scheduleAction(self, verb, config=None, parameters=None):
        self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), self.dmappcId, self.clock.now())
        self.layoutService.scheduleAction(self._getTime(self.clock.now()), self.dmappcId, verb, config=config, parameters=parameters)

    def statusReport(self, status):
        self.document.report(logging.INFO, 'RECV', status, self.document.getXPath(self.elt))
        self.setState(status)

    def _getParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in document.NS_2IMMERSE:
                localName = document.NS_2IMMERSE.localTag(k)
                if localName == "class" or localName == "url" or localName == "dmappcid":
                    # These are magic, don't pass them in parameters
                    continue
                rv[localName] = self.elt.attrib[k]
        return rv
