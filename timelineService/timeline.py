import requests
import clocks
import document
import logging
import urllib
import urlparse
import os
import threading
import time
import traceback
import sys

logger = logging.getLogger(__name__)

THREADED=True

class BaseTimeline:
    ALL_CONTEXTS = {}
    timelineServiceUrl = None

    @classmethod
    def createTimeline(cls, contextId, layoutServiceUrl, timelineServiceUrl=None):
        """Factory function: create a new context"""
        if timelineServiceUrl:
            cls.timelineServiceUrl = timelineServiceUrl
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
        self.documentHasFinished = False
        self.dmappComponents = {}
        self.clockService = clocks.PausableClock(clocks.SystemClock())
        self.documentClock = clocks.CallbackPausableClock(self.clockService)
        self.documentClock.setQueueChangedCallback(self._updateTimeline)
        self.document = document.Document(self.documentClock, idAttribute=document.NS_XML("id"), extraLoggerArgs=dict(contextID=contextId))
        self.document.setDelegateFactory(self.dmappComponentDelegateFactory)
        self.document.setDelegateFactory(self.updateDelegateFactory, tag=document.NS_2IMMERSE("update"))
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
        self.dmappComponents[rv.componentId] = rv
        return rv

    def updateDelegateFactory(self, elt, document, clock):
        rv = UpdateComponent(elt, document, self.timelineDocUrl, clock, self.layoutService)
        return rv

    def loadDMAppTimeline(self, timelineDocUrl, dmappId):
        logger.info("Timeline(%s): loadDMAppTimeline(%s)" % (self.contextId, timelineDocUrl))
        logger.info("Timeline(%s): layoutServiceUrl=%s" % (self.contextId, self.layoutServiceUrl))
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
        self._registerForChanges() # xxxjack At what point should this be done? Here, or earlier?
        return None

    def unloadDMAppTimeline(self, dmappId):
        self.logger.info("Timeline(%s): unloadDMAppTimeline(%s)" % (self.contextId, dmappId))
        assert self.timelineDocUrl
        assert self.dmappTimeline
        assert self.dmappId == dmappId
        self.timelineDocUrl = None
        self.dmappTimeline = None
        self.dmappId = None
        self.documentHasFinished = False
        return None

    def dmappcStatus(self, dmappId, componentId, status, fromLayout=False, duration=None):
        self.logger.debug("Timeline(%s): dmappcStatus(%s, %s, %s, fromLayout=%s, duration=%s)" % (self.contextId, dmappId, componentId, status, fromLayout, duration))
        assert dmappId == self.dmappId
        c = self.dmappComponents[componentId]
        c.statusReport(status, duration, fromLayout)
        self._updateTimeline()
        return None

    def timelineEvent(self, eventId):
        self.document.report(logging.INFO, 'EVENT', 'event', eventId)
        if '(' in eventId:
            self.logger.warn("Timeline(%s): parameterized events not yet implemented", self.contextId)
        else:
            self.document.triggerEvent(eventId)
            self._updateTimeline()
        return None

    def clockChanged(self, contextClock, contextClockRate, wallClock):
        self.logger.debug("Timeline(%s): clockChanged(contextClock=%s, contextClockRate=%f, wallClock=%s)", self.contextId, contextClock, contextClockRate, wallClock)
        # self.clockService.setxxxxx(contextClock, wallClock)

        #
        # Adjust clock position, if needed
        #
        delta = contextClock - self.clockService.now()
        MAX_CLOCK_DISCREPANCY = 0.1 # xxxjack pretty random number, 100ms....
        if abs(delta) > MAX_CLOCK_DISCREPANCY:
            self.document.report(logging.INFO, 'CLOCK', 'forward', delta)
            self.clockService.set(contextClock)
            
        #
        # Adjust clock rate, if needed
        #
        if contextClockRate != self.clockService.getRate():
            if contextClockRate:
                self.document.report(logging.INFO, 'CLOCK', 'start', self.clockService.now())
                self.clockService.start()
            else:
                self.document.report(logging.INFO, 'CLOCK', 'stop', self.clockService.now())
                self.clockService.stop()

        self._updateTimeline()
        return None

    def _populateTimeline(self):
        """Create proxy objects, etc, using self.dmappTimeline"""
        try:
            self.document.loadDocument(self.timelineDocUrl)
        except:
            errorStr = '\n'.join(traceback.format_exception_only(sys.exc_type, sys.exc_value))
            self.logger.error("Timeline(%s): %s: Error loading document: %s", self.contextId, self.timelineDocUrl, errorStr)
            raise
        self.document.report(logging.INFO, 'DOCUMENT', 'loaded', self.timelineDocUrl)
        self.document.prepareDocument()

    def _stepTimeline(self):
        self.logger.debug("Timeline(%s): stepTimeline at %f(speed=%f) docClock %f(speed=%f)", self.contextId, self.clockService.now(), self.clockService.getRate(), self.documentClock.now(), self.documentClock.getRate())
        if self.document.isDocumentDone():
            if not self.documentHasFinished:
                self.documentHasFinished = True
                self.document.report(logging.INFO, 'DOCUMENT', 'done', self.timelineDocUrl)
            return
        self.document.advanceDocument()
        self.document.runAvailable()
        self.layoutService.forwardActions()
        
    def _registerForChanges(self):
        if not self.timelineServiceUrl:
            return
        myTimelineUrl = self.timelineServiceUrl + '/timeline/v1/context/' + self.contextId + '/updateDocument'
        params = dict(url=myTimelineUrl)
        u = urlparse.urljoin(self.timelineDocUrl, 'addcallback')
        r = requests.post(u, params=params)
        if r.status_code == requests.codes.ok:
            self.document.report(logging.INFO, 'DOCUMENT', 'master', u)
            

    def updateDocument(self, generation, operations, wantStateUpdates=False):
        self.document.report(logging.INFO, 'DOCUMENT', 'update', 'generation=%d, count=%d, wantUpdates=%s' % (generation, len(operations), wantStateUpdates))
        stateUpdateCallback = None
        if wantStateUpdates:
            stateUpdateCallback = self._stateUpdateCallback
        self.document.modifyDocument(generation, operations, stateUpdateCallback)
        self._updateTimeline()
        
    def _stateUpdateCallback(self, documentState):
        u = urlparse.urljoin(self.timelineDocUrl, 'updatedocstate')
        self.logger.debug("_stateUpdateCallback: send %d elements to %s" % (len(documentState), u))
        r = requests.put(u, json=documentState)
    
        
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
            while self.document and not self.document.isDocumentDone():
                self._stepTimeline()
                maxSleep = self.documentClock.nextEventTime(default=None)
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
        self.actionsLock = threading.Lock()
        self._isV4 = ('/v4/' in self.contactInfo)
        self.logger.info("ProxyLayoutService: URL=%s V4=%s" % (self.contactInfo, repr(self._isV4)))

    def getContactInfo(self):
        return self.contactInfo + '/context/' + self.contextId + '/dmapp/' + self.dmappId

    def scheduleAction(self, timestamp, componentId, verb, config=None, parameters=None, constraintId=None):
        if self._isV4:
            if not constraintId:
                constraintId = componentId
            componentData = dict(componentId=componentId, constraintId=constraintId)
        else:
            componentData = componentId
        action = dict(action=verb, componentIds=[componentData])
        if config:
            action["config"] = config
        if parameters:
            action["parameters"] = parameters
        if self.actionsTimestamp and self.actionsTimestamp != timestamp:
            # Different timestamp, output the old ones first. Note this
            # looks thread-unsafe but isn't, because at worst forwardActions will be
            # called for nothing.
            self.forwardActions()
        with self.actionsLock:
            self.actionsTimestamp = timestamp
            self.actions.append(action)

    def forwardActions(self):
        with self.actionsLock:
            if not self.actions: return
            actions = self.actions
            actionsTimestamp = self.actionsTimestamp
            self.actionsTimestamp = None
            self.actions = []
        self.logger.info("ProxyLayoutService: forwarding %d actions (t=%f): %s" % (len(actions), actionsTimestamp, repr(actions)))
        entryPoint = self.getContactInfo() + '/transaction'
        body = dict(time=actionsTimestamp, actions=actions)
        r = requests.post(entryPoint, json=body)
        self.logger.info("ProxyLayoutService: request returned status code: %s" % repr(r.status_code))
        r.raise_for_status()

class ProxyMixin:
    def __init__(self, timelineDocUrl, layoutService, componentId):
        self.componentId = componentId
        self.logger = layoutService.logger
        self.timelineDocUrl = timelineDocUrl
        self.layoutService = layoutService
        
    def getLogExtra(self):
    	return dict(xpath=self.getXPath(), dmappcID=self.componentId)
    	
    def _getTime(self, timestamp):
        return timestamp + 0.0

    def scheduleAction(self, verb, config=None, parameters=None):
        extraLogArgs = ()
        if config != None or parameters != None:
            extraLogArgs = (config, parameters)
        startTime = self.getStartTime()
        self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), self.componentId, startTime, *extraLogArgs, extra=self.getLogExtra())
        self.layoutService.scheduleAction(self._getTime(startTime), self.componentId, verb, config=config, parameters=parameters, constraintId=self.elt.get(document.NS_2IMMERSE("constraintId")))

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

class ProxyDMAppComponent(document.TimeElementDelegate, ProxyMixin):
    def __init__(self, elt, doc, timelineDocUrl, clock, layoutService):
        document.TimeElementDelegate.__init__(self, elt, doc, clock)
        ProxyMixin.__init__(self, timelineDocUrl, layoutService, self.getId())
        self.klass = self.elt.get(document.NS_2IMMERSE("class"))
        self.url = self.elt.get(document.NS_2IMMERSE("url"), "")
        # Allow relative URLs by doing a basejoin to the timeline document URL.
        if self.url:
            self.url = urllib.basejoin(self.timelineDocUrl, self.url)
        if not self.componentId:
            self.componentId = "unknown%d" % id(self)
            self.logger.error("Element %s: missing xml:id attribute, invented %s", self.document.getXPath(self.elt), self.componentId, extra=self.getLogExtra())
        assert self.componentId
        if not self.klass:
            self.klass = "unknownClass"
            self.logger.error("Element %s: missing tim:class attribute, invented %s", self.document.getXPath(self.elt), self.klass, extra=self.getLogExtra())
        self.expectedDuration = None
        assert self.klass

    def initTimelineElement(self):
        self.assertState('ProxyDMAppComponent.initTimelineElement()', document.State.idle)
        self.setState(document.State.initing)
        config = {'class':self.klass, 'url':self.url}
        parameters = self._getParameters()
        self.scheduleAction("init", config=config, parameters=parameters)

    def startTimelineElement(self):
        self.assertState('ProxyDMAppComponent.initTimelineElement()', document.State.inited)
        self.setState(document.State.starting)
        self.scheduleAction("start")

    def stopTimelineElement(self):
        self.setState(document.State.stopping)
        self.scheduleAction("stop")
            
    def destroyTimelineElement(self):
        self.scheduleAction("destroy")

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
            if self.state == document.State.initing:
                pass # This is the expected transition
            elif self.state in {document.State.inited, document.State.starting, document.State.started, document.State.finished, document.State.stopping}:
                return # This is a second inited, probably because the layout service decided to place the dmappc on an appeared handheld
            elif self.state == document.State.idle:
                self.logger.error('Unexpected "%s" state update for node %s (in state %s), re-issuing destroy' % (state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                self.scheduleAction('destroy')
                return
            else:
                self.logger.error('Unexpected "%s" state update for node %s (in state %s)' % (state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                return
        elif state == document.State.started:
            if self.state == document.State.starting:
                pass # This is the expected transition
            elif self.state == document.State.finished:
                self.document.report(logging.INFO, 'REVIVE', state, self.document.getXPath(self.elt), extra=self.getLogExtra())
                self.setState(state)
                return
            elif self.state in {document.State.started, document.State.stopping}:
                return # This is a second started, probably because the layout service decided to place the dmappc on an appeared handheld
            elif self.state == document.State.idle:
                self.logger.error('Unexpected "%s" state update for node %s (in state %s), re-issuing destroy' % (state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                self.scheduleAction('destroy')
                return
            else:
                self.logger.error('Ignoring unexpected "%s" state update for node %s (in state %s)' % ( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                return
        elif state == document.State.idle:
            pass # idle is always allowed
        elif state == "destroyed":
            # destroyed is translated into idle, unless we're in idle already
            if self.state == document.State.idle:
                return
            state = document.State.idle
        else:
            self.logger.error('Unknown "%s" state update for node %s (in state %s), issuing destroy' %( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
            self.scheduleAction('destroy')
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
        if self.state in (document.State.started, document.State.starting):
            self.document.report(logging.INFO, 'SYNTH', 'finished', self.document.getXPath(self.elt), extra=self.getLogExtra())
            self.setState(document.State.finished)
        else:
            self.document.report(logging.INFO, 'SYN-IGN', 'finished', self.document.getXPath(self.elt), extra=self.getLogExtra())

class UpdateComponent(document.TimelineDelegate, ProxyMixin):
    def __init__(self, elt, doc, timelineDocUrl, clock, layoutService):
        document.TimelineDelegate.__init__(self, elt, doc, clock)
        componentId = self.elt.get(document.NS_2IMMERSE("target"))
        ProxyMixin.__init__(self, timelineDocUrl, layoutService, componentId)

    def startTimelineElement(self):
        self.assertState('UpdateComponent.initTimelineElement()', document.State.inited)
        document.TimelineDelegate.startTimelineElement(self)
        parameters = self._getParameters()
        self.scheduleAction("update", parameters=parameters)
        
