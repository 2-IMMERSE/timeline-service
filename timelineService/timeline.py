import requests
import clocks
import document
import logging
import urllib
import os
import threading
import time
import traceback
import sys

logger = logging.getLogger(__name__)

TRANSACTIONS=True
THREADED=True

class BaseTimeline:
    ALL_CONTEXTS = {}

    @classmethod
    def createTimeline(cls, contextId, layoutServiceUrl):
        """Factory function: create a new context"""
        if contextId in cls.ALL_CONTEXTS:
            la = document.MyLoggerAdapter(logger, extra=dict(contextID=contextId))
            la.error("Creating timeline for context %s but it already exists" % contextId)
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
        self.creationTime = time.time() # Mainly for debugging, so we can tell contexts apart
        self.logger = document.MyLoggerAdapter(logger, dict(contextID=contextId))
        self.contextId = contextId
        self.timelineDocUrl = None
        self.layoutServiceUrl = layoutServiceUrl
        self.dmappTimeline = None
        self.dmappId = None
        self.documentHasRun = False
        self.dmappComponents = {}
        self.clockService = clocks.CallbackPausableClock(clocks.SystemClock())
        self.document = document.Document(self.clockService, idAttribute=document.NS_2IMMERSE("dmappcid"), extraLoggerArgs=dict(contextID=contextId))
        self.document.setDelegateFactory(self.dmappComponentDelegateFactory)
        # Do other initialization

    def delete(self):
        """Destructor, sort-of"""
        self.logger.info("Timeline(%s): delete()" % self.contextId)
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
            creationTime=self.creationTime,
            currentPresentationTime=self.clockService.now(),
            waitingEvents=self.clockService.dumps(),
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
        rv = ProxyDMAppComponent(elt, document, self.timelineDocUrl, clock, self.layoutService)
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
        self.dmappId = dmappId
        self.logger = document.MyLoggerAdapter(logger, dict(contextID=self.contextId, dmappID=dmappId))
        assert self.document
        self.document.setExtraLoggerArgs(dict(contextID=self.contextId, dmappID=dmappId))

        self.layoutService = ProxyLayoutService(self.layoutServiceUrl, self.contextId, self.dmappId, self.logger)
        self._populateTimeline()
        self._startTimeline()
        self._updateTimeline()
        return None

    def unloadDMAppTimeline(self, dmappId):
        self.logger.info("Timeline(%s): unloadDMAppTimeline(%s)" % (self.contextId, dmappId))
        assert self.timelineDocUrl
        assert self.dmappTimeline
        assert self.dmappId == dmappId
        self.timelineDocUrl = None
        self.dmappTimeline = None
        self.dmappId = None
        self.documentHasRun = False
        return None

    def dmappcStatus(self, dmappId, componentId, status, fromLayout=False, duration=None):
        self.logger.debug("Timeline(%s): dmappcStatus(%s, %s, %s, fromLayout=%s, duration=%s)" % (self.contextId, dmappId, componentId, status, fromLayout, duration))
        assert dmappId == self.dmappId
        c = self.dmappComponents[componentId]
        c.statusReport(status, duration, fromLayout)
        self._updateTimeline()
        return None

    def timelineEvent(self, eventId):
        self.logger.debug("Timeline(%s): timelineEvent(%s)" % (self.contextId, eventId))
        pass
        return None

    def clockChanged(self, contextClock, contextClockRate, wallClock):
        self.logger.debug("Timeline(%s): clockChanged(contextClock=%s, contextClockRate=%f, wallClock=%s)", self.contextId, contextClock, contextClockRate, wallClock)
        # self.document.clock.setxxxxx(contextClock, wallClock)

        #
        # Adjust clock position, if needed
        #
        delta = contextClock - self.document.clock.now()
        MAX_CLOCK_DISCREPANCY = 0.1 # xxxjack pretty random number, 100ms....
        if abs(delta) > MAX_CLOCK_DISCREPANCY:
            self.document.report(logging.INFO, 'CLOCK', 'forward', delta)
            self.document.clock.set(contextClock)
            
        #
        # Adjust clock rate, if needed
        #
        if contextClockRate != self.document.clock.getRate():
            if contextClockRate:
                self.document.report(logging.INFO, 'CLOCK', 'start', self.document.clock.now())
                self.document.clock.start()
            else:
                self.document.report(logging.INFO, 'CLOCK', 'stop', self.document.clock.now())
                self.document.clock.stop()

        self._updateTimeline()
        return None

    def _populateTimeline(self):
        """Create proxy objects, etc, using self.dmappTimeline"""
        try:
            self.document.load(self.timelineDocUrl)
        except:
            errorStr = '\n'.join(traceback.format_exception_only(sys.exc_type, sys.exc_value))
            self.logger.error("Timeline(%s): %s: Error loading document: %s", self.contextId, self.timelineDocUrl, errorStr)
            raise
        self.document.addDelegates()

    def _stepTimeline(self):
        self.logger.debug("Timeline(%s): stepTimeline at %f", self.contextId, self.document.clock.now())
        curState = self.document.getDocumentState()
        if not curState: return
        if curState == document.State.idle:
            # We need to initialize the document
            if self.documentHasRun:
                logger.info("Timeline(%s): Finished with %s" % (self.contextId, timelineDocUrl))
            else:
                self.document.runDocumentInit()
        elif curState == document.State.inited:
            # We need to start the document
            self.documentHasRun = True
            self.document.runDocumentStart()
        elif curState == document.State.finished:
            self.document.report(logging.DEBUG, 'RUN', 'done')
        self.document.runAvailable()
        self.layoutService.forwardActions()

class TimelinePollingRunnerMixin:
    def __init__(self):
        pass
        
    def _startTimeline(self):
        pass
        
    def _updateTimeline(self):
        self._stepTimeline()
        
class TimelineThreadedRunnerMixin:
    def __init__(self):
        self.timelineCondition = threading.Condition()
        self.timelineThread = threading.Thread(target=self._runTimeline)
        self.timelineThread.daemon = True

    def _startTimeline(self):
        self.timelineThread.start()
        
    def _runTimeline(self):
        assert self.document
        assert self.document.getDocumentState()
        with self.timelineCondition:
            while self.document and self.document.getDocumentState():
                self._stepTimeline()
                maxSleep = self.document.clock.nextEventTime(default=None)
                self.timelineCondition.wait(maxSleep)
            
    def _updateTimeline(self):
        with self.timelineCondition:
            self.timelineCondition.notify()

if THREADED:
    class Timeline(BaseTimeline, TimelineThreadedRunnerMixin):
        def __init__(self, *args, **kwargs):
            BaseTimeline.__init__(self, *args, **kwargs)
            TimelineThreadedRunnerMixin.__init__(self)
else:
    class Timeline(BaseTimeline, TimelinePollingRunnerMixin):
        def __init__(self, *args, **kwargs):
            BaseTimeline.__init__(self, *args, **kwargs)
            TimelinePollingRunnerMixin.__init__(self)
        
        
class ProxyLayoutService:
    def __init__(self, contactInfo, contextId, dmappId, logger):
        self.logger = logger
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
        self.logger.debug("ProxyLayoutService: forwarding %d actions: %s", len(self.actions), repr(self.actions))
        entryPoint = self.getContactInfo() + '/transaction'
        body = dict(time=self.actionsTimestamp, actions=self.actions)
        r = requests.post(entryPoint, json=body)

        r.raise_for_status()
        self.actions = []
        self.actionsTimestamp = None

class ProxyDMAppComponent(document.TimeElementDelegate):
    def __init__(self, elt, doc, timelineDocUrl, clock, layoutService):
        document.TimeElementDelegate.__init__(self, elt, doc, clock)
        self.logger = layoutService.logger
        self.timelineDocUrl = timelineDocUrl
        self.layoutService = layoutService
        self.dmappcId = self.elt.get(document.NS_2IMMERSE("dmappcid"))
        self.klass = self.elt.get(document.NS_2IMMERSE("class"))
        self.url = self.elt.get(document.NS_2IMMERSE("url"), "")
        # Allow relative URLs by doing a basejoin to the timeline document URL.
        if self.url:
            self.url = urllib.basejoin(self.timelineDocUrl, self.url)
        if not self.dmappcId:
            self.dmappcId = "unknown%d" % id(self)
            self.logger.error("Element %s: missing tim:dmappcid attribute, invented %s", self.document.getXPath(self.elt), self.dmappcId, extra=self.getLogExtra())
        assert self.dmappcId
        if not self.klass:
            self.klass = "unknownClass"
            self.logger.error("Element %s: missing tim:class attribute, invented %s", self.document.getXPath(self.elt), self.klass, extra=self.getLogExtra())
        self.expectedDuration = None
        assert self.klass

    def getLogExtra(self):
    	return dict(xpath=self.getXPath(), dmappcID=self.dmappcId)
    	
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
            
    def destroyTimelineElement(self):
        if TRANSACTIONS:
            self.scheduleAction("destroy")
        else:
            self.sendAction("destroy")

    def sendAction(self, verb, queryParams=None, body=None):
        if body:
            self.document.report(logging.INFO, 'SEND', verb, self.document.getXPath(self.elt), self.dmappcId, repr(body), extra=self.getLogExtra())
        else:
            self.document.report(logging.INFO, 'SEND', verb, self.document.getXPath(self.elt), self.dmappcId, extra=self.getLogExtra())
        entryPoint = self._getContactInfo()
        entryPoint += '/actions/' + verb
        if body is None:
            r = requests.post(entryPoint, params=queryParams)
        else:
            r = requests.post(entryPoint, json=body, params=queryParams)

        r.raise_for_status()

    def scheduleAction(self, verb, config=None, parameters=None):
        extraLogArgs = ()
        if config != None or parameters != None:
            extraLogArgs = (config, parameters)
        self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), self.dmappcId, self.clock.now(), *extraLogArgs, extra=self.getLogExtra())
        self.layoutService.scheduleAction(self._getTime(self.clock.now()), self.dmappcId, verb, config=config, parameters=parameters)

    def statusReport(self, state, duration, fromLayout):
        durargs = ()
        if fromLayout:
            durargs = ('fromLayout',)
        if duration != None:
            durargs = ('duration=%s' % duration,)
            
        self.document.report(logging.INFO, 'RECV', state, self.document.getXPath(self.elt), duration, *durargs, extra=self.getLogExtra())
        # XXXJACK quick stopgap until I implement duration
        if state == document.State.started and (duration != None or fromLayout):
            self._scheduleFinished(duration)
        #
        # Sanity check for state change report
        #
        if state == document.State.inited:
            if self.state != document.State.initing:
                if self.state != document.State.inited:
                    self.logger.warning('Unexpected "%s" state update for node %s (in state %s)' % (state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                return
        elif state == document.State.started:
            if self.state != document.State.starting:
                if self.state == document.State.finished:
                    # A companion has appeared.
                    self.document.report(logging.INFO, 'REVIVE', state, self.document.getXPath(self.elt), extra=self.getLogExtra())
                    self.setState(state)
                elif self.state != document.State.started:
                    self.logger.error('Unexpected "%s" state update for node %s (in state %s)' % ( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                return
        elif state == document.State.finished:
            if self.state not in {document.State.starting, document.State.started}:
                if self.state not in (document.State.finished, document.State.stopping, document.State.stopped):
                    self.logger.warning('Unexpected "%s" state update for node %s (in state %s)' % ( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                return
        elif state == document.State.idle:
            pass
        else:
            self.logger.error('Unknown "%s" state update for node %s (in state %s)' %( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
            return
        self.setState(state)

    def _scheduleFinished(self, dur):
        if not dur: 
            dur = 0
        if self.expectedDuration is None or self.expectedDuration > dur:
            self.clock.schedule(dur, self._emitFinished)
        if self.expectedDuration != None and self.expectedDuration != dur:
            self.logger.warning('Expected duration of %s changed from %s to %s' % (self.document.getXPath(self.elt), self.expectedDuration, dur), extra=self.getLogExtra())
            self.expectedDuration = dur 
        
    def _emitFinished(self):
        self.document.report(logging.INFO, 'SYNTH', 'finished', self.document.getXPath(self.elt), extra=self.getLogExtra())
        if self.state in (document.State.started, document.State.starting):
            self.setState(document.State.finished)
            
    def _getParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in document.NS_2IMMERSE_COMPONENT:
                localName = document.NS_2IMMERSE_COMPONENT.localTag(k)
                value = self.elt.attrib[k]
                if 'url' in localName.lower() and value:
                    value = urllib.basejoin(self.timelineDocUrl, value)
                rv[localName] = value
            elif k in document.NS_TIMELINE_CHECK:
                localName = document.NS_TIMELINE_CHECK.localTag(k)
                value = self.elt.attrib[k]
                if 'url' in localName.lower() and value:
                    value = urllib.basejoin(self.timelineDocUrl, value)
                rv['debug-2immerse-' + localName] = value
        return rv
