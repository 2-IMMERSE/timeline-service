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
        self.timelineDocBaseUrl = None
        self.layoutServiceUrl = layoutServiceUrl
        self.dmappTimeline = None
        self.dmappId = None
        self.documentHasFinished = False
        self.dmappComponents = {}
        self.clockService = clocks.PausableClock(clocks.SystemClock())
        self.documentClock = clocks.CallbackPausableClock(self.clockService)
        self.documentClock.start()
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
        self.timelineDocBaseUrl = None
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
            currentDocumentTime=self.documentClock.now(),
            waitingEvents=self.documentClock.dumps(),
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
        rv = ProxyDMAppComponent(elt, document, self.timelineDocBaseUrl, clock, self.layoutService)
        self.dmappComponents[rv.componentId] = rv
        return rv

    def updateDelegateFactory(self, elt, document, clock):
        rv = UpdateComponent(elt, document, self.timelineDocBaseUrl, clock, self.layoutService)
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
        self.timelineDocBaseUrl = timelineDocUrl
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
        self.timelineDocBaseUrl = None
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
        MAX_CLOCK_DISCREPANCY = 0.032 # Smaller than a frame duration for both 25fps and 30fps
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
        self.document.clockChanged()
        self.logger.debug("Timeline(%s): after clockChanged clockService=%f, document=%f", self.contextId, self.clockService.now(), self.documentClock.now())
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
        overrideBaseUrl = self.document.root.get(document.NS_2IMMERSE("base"))
        if overrideBaseUrl:
            self.timelineDocBaseUrl = overrideBaseUrl
            self.document.report(logging.INFO, 'DOCUMENT', 'base', self.timelineDocBaseUrl)
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
        params = dict(url=myTimelineUrl, contextID=self.contextId)
        u = urlparse.urljoin(self.timelineDocUrl, 'addcallback')
        r = requests.post(u, params=params)

        self.logger.info("Registering callback using URL %s" % self.timelineServiceUrl)

        if r.status_code == requests.codes.ok:
            self.document.report(logging.INFO, 'DOCUMENT', 'master', u)
            

    def updateDocument(self, generation, operations, wantStateUpdates=False):
        if len(operations):
            self.document.report(logging.INFO, 'DOCUMENT', 'update', 'generation=%d, count=%d, wantUpdates=%s' % (generation, len(operations), wantStateUpdates))
        else:
            self.document.report(logging.DEBUG, 'DOCUMENT', 'update', 'generation=%d, count=%d, wantUpdates=%s' % (generation, len(operations), wantStateUpdates))
        stateUpdateCallback = None
        if wantStateUpdates:
            stateUpdateCallback = self._stateUpdateCallback
        self.document.modifyDocument(generation, operations, stateUpdateCallback)
        self._updateTimeline()
        
    def _stateUpdateCallback(self, documentState):
        t = threading.Thread(target=self._asyncStateUpdate, args=(documentState,))
        t.daemon = True
        t.start()
        
    def _asyncStateUpdate(self, documentState):
        u = urlparse.urljoin(self.timelineDocUrl, 'updatedocstate')
        self.logger.debug("_asyncStateUpdate: send %d elements to %s" % (len(documentState), u))
        try:
            requestStartTime = time.time() # Debugging: sometimes requests take a very long time
            r = requests.put(u, json=documentState)
        except requests.exceptions.RequestException:
            self.logger.warning("_asyncStateUpdate: PUT failed for %s" % u)
            raise
        else:
            requestDuration = time.time() - requestStartTime
            if requestDuration > 2:
                self.logger.warning("_asyncStateUpdate: PUT took %d seconds for %s" % (requestDuration, u))
        
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
        self.logger.info("ProxyLayoutService: contextId %s URL %s" % (self.contextId, self.contactInfo))

    def getContactInfo(self):
        return self.contactInfo + '/context/' + self.contextId + '/dmapp/' + self.dmappId

    def scheduleAction(self, timestamp, componentId, verb, config=None, parameters=None, constraintId=None):
        componentData = dict(componentId=componentId)
        if constraintId:
            componentData['constraintId'] = constraintId
        action = dict(action=verb, components=[componentData])
        if config:
            action["config"] = config
        if parameters:
            action["parameters"] = parameters
        currentActionTimestamp = self.actionsTimestamp
        if currentActionTimestamp and abs(currentActionTimestamp - timestamp) >= 0.1:
            # Timestamp differs by >= 100ms, output the old ones first. Note this
            # looks thread-unsafe but isn't, because at worst forwardActions will be
            # called for nothing.
            self.forwardActions()
        with self.actionsLock:
            if not self.actionsTimestamp:
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
        try:
            r = requests.post(entryPoint, json=body)
        except requests.exceptions.RequestException as e:
            self.logger.error("Failed to forward actions to layout service")
            self.logger.info("Failure URL: %s" % entryPoint)
            self.logger.info("Failure data: %s" % repr(body))
            self.logger.info("Failure reason: %s" % repr(e))
            raise
        r.raise_for_status()

class ProxyMixin:
    def __init__(self, timelineDocBaseUrl, layoutService, componentId):
        self.componentId = componentId
        self.logger = layoutService.logger
        self.timelineDocBaseUrl = timelineDocBaseUrl
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
        self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), self.componentId, startTime, 'constraintId=%s' % self.elt.get(document.NS_2IMMERSE("constraintId")), *extraLogArgs, extra=self.getLogExtra())
        constraintId = self.elt.get(document.NS_2IMMERSE("constraintId"))
        if not constraintId:
            constraintId = self.componentId
        self.layoutService.scheduleAction(self._getTime(startTime), self.componentId, verb, config=config, parameters=parameters, constraintId=constraintId)

    def _getParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in document.NS_2IMMERSE_COMPONENT:
                localName = document.NS_2IMMERSE_COMPONENT.localTag(k)
                value = self.elt.attrib[k]
                if 'url' in localName.lower() and value:
                    value = urllib.basejoin(self.timelineDocBaseUrl, value)
                rv[localName] = value
            elif k in document.NS_TIMELINE_CHECK:
                localName = document.NS_TIMELINE_CHECK.localTag(k)
                value = self.elt.attrib[k]
                if 'url' in localName.lower() and value:
                    value = urllib.basejoin(self.timelineDocBaseUrl, value)
                rv['debug-2immerse-' + localName] = value
        return rv

class ProxyDMAppComponent(document.TimeElementDelegate, ProxyMixin):
    def __init__(self, elt, doc, timelineDocBaseUrl, clock, layoutService):
        document.TimeElementDelegate.__init__(self, elt, doc, clock)
        ProxyMixin.__init__(self, timelineDocBaseUrl, layoutService, self.getId())
        self.klass = self.elt.get(document.NS_2IMMERSE("class"))
        self.url = self.elt.get(document.NS_2IMMERSE("url"), "")
        # Allow relative URLs by doing a basejoin to the timeline document URL.
        if self.url:
            self.url = urllib.basejoin(self.timelineDocBaseUrl, self.url)
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
        self.assertState('ProxyDMAppComponent.startTimelineElement()', document.State.inited)
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

        #
        # Sanity check for state change report
        #
        if state == document.State.inited:
            if self.state == document.State.initing:
                self.setState(state) # This is the expected transition
            elif self.state in {document.State.inited, document.State.starting, document.State.started, document.State.finished, document.State.stopping}:
                pass # This is a second inited, probably because the layout service decided to place the dmappc on an appeared handheld
            elif self.state == document.State.idle:
                self.logger.error('Unexpected "%s" state update for node %s (in state %s), re-issuing destroy' % (state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                self.scheduleAction('destroy')
            else:
                self.logger.error('Unexpected "%s" state update for node %s (in state %s)' % (state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
        elif state == document.State.started:
            if self.state == document.State.starting:
                self.setState(state) # This is the expected transition
            elif self.state == document.State.finished and duration != 0 and duration != None:
                self.document.report(logging.INFO, 'REVIVE', state, self.document.getXPath(self.elt), extra=self.getLogExtra())
                self.setState(state)
            elif self.state in {document.State.started, document.State.stopping}:
                pass # This is a second started, probably because the layout service decided to place the dmappc on an appeared handheld
            elif self.state == document.State.idle:
                self.logger.error('Unexpected "%s" state update for node %s (in state %s), re-issuing destroy' % (state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                self.scheduleAction('destroy')
            else:
                self.logger.error('Ignoring unexpected "%s" state update for node %s (in state %s)' % ( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
        elif state == document.State.idle:
            self.setState(state) # idle is always allowed
        elif state == "destroyed":
            # destroyed is translated into idle, unless we're in idle already
            if self.state != document.State.idle:
                state = document.State.idle
                self.setState(state)
        else:
            self.logger.error('Unknown "%s" state update for node %s (in state %s), ignoring' %( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())

        # XXXJACK quick stopgap until I implement duration
        if state == document.State.started and (duration != None or fromLayout):
            self._scheduleFinished(duration)

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
        self.targetXPath = self.elt.get(document.NS_2IMMERSE("targetXPath"))
        self.append = not not self.elt.get(document.NS_2IMMERSE("append"))
        self.logger
        if self.targetXPath and self.append:
            self.logger.error('%s uses both tim:targetXPath and tim:append which is not implemented' % self.document.getXPath(self.elt), extra=self.getLogExtra())
        ProxyMixin.__init__(self, timelineDocUrl, layoutService, componentId)

    def startTimelineElement(self):
        self.assertState('UpdateComponent.startTimelineElement()', document.State.inited)
        document.TimelineDelegate.startTimelineElement(self)
        parameters = self._getParameters()
        if self.targetXPath:
            # Find all active elements in the group
            allMatchingElements = self.document.root.findall(self.targetXPath, document.NAMESPACES)
            componentIds = []
            for elt in allMatchingElements:
                if elt.delegate.state in document.State.STOP_NEEDED:
                    componentIds.append(elt.delegate.getId())
            self.scheduleActionMulti("update", componentIds, parameters=parameters)
        else:
            # xxxjack should this recording always be done???
            targetElt = self.document.getElementById(self.componentId)
            if targetElt != None:
                for attrName, attrValue in parameters.items():
                    if self.append:
                        # New value should be appended (comma-separated) to current value
                        # and recorded in the document.
                        origAttrValue = targetElt.get(document.NS_2IMMERSE_COMPONENT(attrName))
                        if origAttrValue:
                            attrValue = origAttrValue + ',' + attrValue
                    targetElt.set(document.NS_2IMMERSE_COMPONENT(attrName), attrValue)
                    parameters[attrName] = attrValue
            else:
                self.logger.error('tim:update: no component with xml:id="%s"' % self.componentId, extra=self.getLogExtra())
            self.scheduleAction("update", parameters=parameters)
        
    def scheduleActionMulti(self, verb, componentIds, config=None, parameters=None):
        extraLogArgs = ()
        if config != None or parameters != None:
            extraLogArgs = (config, parameters)
        startTime = self.getStartTime()
        newConstraintId = self.elt.get(document.NS_2IMMERSE("constraintId"))
        for cid in componentIds:
            if newConstraintId:
                self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), cid, startTime, 'constraintId=%s' % newConstraintId, *extraLogArgs, extra=self.getLogExtra())
                self.layoutService.scheduleAction(self._getTime(startTime), cid, verb, config=config, parameters=parameters, constraintId=newConstraintId)
            else:
                self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), cid, startTime, *extraLogArgs, extra=self.getLogExtra())
                self.layoutService.scheduleAction(self._getTime(startTime), cid, verb, config=config, parameters=parameters)



