from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import object
import requests
from . import clocks
from . import document
import logging
import urllib.request, urllib.parse, urllib.error
import os
import threading
import time
import traceback
import sys
from . import socketIOhandler

if sys.version_info[0] < 3:
    def str23compat(item):
        return unicode(str(item))
else:
    def str23compat(item):
        return str(item)

logger = logging.getLogger(__name__)

THREADED=True

class BaseTimeline(object):
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
        return list(cls.ALL_CONTEXTS.keys())

    def __init__(self, contextId, layoutServiceUrl):
        """Initializer, creates a new context and stores it for global reference"""
        self.creationTime = time.time() # Mainly for debugging, so we can tell contexts apart
        self.logger = document.MyLoggerAdapter(logger, dict(contextID=contextId))
        self.contextId = contextId
        self.timelineDocUrl = None
        self.timelineDocBaseUrl = None
        self.layoutService = None
        self.layoutServiceUrl = layoutServiceUrl
        self.dmappTimeline = None
        self.dmappId = None
        self.documentHasFinished = False
        self.asyncHandler = None
        self.documentInitialSeek = None
        self.dmappComponents = {}
        self.clockService = clocks.PausableClock(clocks.SystemClock())
        self.documentClock = clocks.CallbackPausableClock(self.clockService, True)
        self.documentClock.setQueueChangedCallback(self._updateTimeline)
        self.document = document.Document(self.documentClock, idAttribute=document.NS_XML("id"), extraLoggerArgs=dict(contextID=contextId))
        self.document.setDelegateFactory(self.dmappComponentDelegateFactory)
        self.document.setDelegateFactory(self.updateDelegateFactory, tag=document.NS_2IMMERSE("update"))
        self.document.setDelegateFactory(self.overlayDelegateFactory, tag=document.NS_2IMMERSE("overlay"))
        # Initialize clock values used to synchronize concurrent live viewing
        self.masterEpoch = None
        self.ourEpoch = None
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
        if self.asyncHandler:
            self.asyncHandler.close()
        self.asyncHandler = None
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
            dmappComponents=list(self.dmappComponents.keys()),
            document=self.document.dumps(),
            )
        return rv

    def debugHelper(self, **kwargs):
        return self.document.debugHelper(**kwargs)
        
    def dmappComponentDelegateFactory(self, elt, document, clock):
        rv = ProxyDMAppComponent(elt, document, self.timelineDocBaseUrl, clock, self.layoutService)
        self.dmappComponents[rv.componentId] = rv
        return rv

    def updateDelegateFactory(self, elt, document, clock):
        rv = UpdateComponent(elt, document, self.timelineDocBaseUrl, clock, self.layoutService)
        return rv

    def overlayDelegateFactory(self, elt, document, clock):
        rv = OverlayComponent(elt, document, self.timelineDocBaseUrl, clock, self.layoutService)
        return rv

    def loadDMAppTimeline(self, timelineDocUrl, dmappId):
        logger.info("Timeline(%s): loadDMAppTimeline(%s)" % (self.contextId, timelineDocUrl))
        logger.info("Timeline(%s): layoutServiceUrl=%s" % (self.contextId, self.layoutServiceUrl))
        if self.timelineDocUrl:
            logger.error("Timeline(%s): loadDMAppTimeline called but context already has a timeline (%s)", self.contextId, self.timelineDocUrl)
        assert self.timelineDocUrl is None
        assert self.dmappTimeline is None
        assert self.dmappId is None
        self.timelineDocUrl = str23compat(timelineDocUrl)
        self.timelineDocBaseUrl = str23compat(timelineDocUrl)
        self.dmappId = dmappId
        self.logger = document.MyLoggerAdapter(logger, dict(contextID=self.contextId, dmappID=dmappId))
        assert self.document
        self.document.setExtraLoggerArgs(dict(contextID=self.contextId, dmappID=dmappId))

        self.checkForAsyncUpdates()
        
        if not self._waitForLiveEpochs():
            self.prepareDMAppTimeline()
        
    def prepareDMAppTimeline(self):
        if self.documentInitialSeek:
            # Remove any start time from the URL
            if '#t=' in self.timelineDocUrl:
                self.timelineDocUrl = self.timelineDocUrl.split('#t=')[0]
            self.timelineDocUrl += '#t=%f' % self.documentInitialSeek
            self.document.report(logging.INFO, 'DOCUMENT', 'addSeek', self.timelineDocUrl)
        self.layoutService = ProxyLayoutService(self.layoutServiceUrl, self.contextId, self.dmappId, self.logger)
        self._populateTimeline()
        self._startTimeline()
        self._updateTimeline()
        self.startAsyncUpdates() # xxxjack At what point should this be done? Here, or earlier?
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

    def dmappcStatus(self, componentId, status, dmappId=None, fromLayout=False, duration=None, revision=None):
        self.logger.debug("Timeline(%s): dmappcStatus(%s, %s, %s, fromLayout=%s, duration=%s, revision=%s)" % (self.contextId, dmappId, componentId, status, fromLayout, duration, revision))
        assert dmappId == None or dmappId == self.dmappId
        c = self.dmappComponents[componentId]
        c.statusReport(status, duration, fromLayout, revision)
        self._updateTimeline()
        return None

    def multiStatus(self, postData):
        self.logger.debug("Timeline(%s): multiStatus([%d items])" % (self.contextId, len(postData)))
        for statusData in postData:
            self.dmappcStatus(**statusData)
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
        #
        # Stopgap measure for 2immerse live: if the clock appears to be wallclock-ish and
        # we are a preview player we _only_ adjust the underlying clock, not the document clock
        #
        if delta > 360000:
            # More than 100 hours difference with old document time
            if abs(contextClock - time.time()) < 36000:
                # Less than 10 hours difference with wallclock time
                self.document.report(logging.INFO, 'CLOCK', 'timewarp', contextClock, '(underlyingClock=%f)' % self.clockService.now())
                oldDocumentNow = self.documentClock.now()
                self.clockService.set(contextClock)
                self.documentClock.set(oldDocumentNow)
                self.document.report(logging.INFO, 'CLOCK', 'timewarped', contextClock, '(underlyingClock=%f)' % self.clockService.now())
                # No need to call _updateTimeline: the document clock has not changed.
                delta = 0
                if not (self.asyncHandler and self.asyncHandler.wantStatusUpdate()):
                    # We are not the preview player but a normal viewer (slaved to the preview player)
                    self._setOurEpoch(contextClock)
                
        MAX_CLOCK_DISCREPANCY = 0.032 # Smaller than a frame duration for both 25fps and 30fps
        if abs(delta) > MAX_CLOCK_DISCREPANCY:
            self.document.report(logging.INFO, 'CLOCK', 'forward', delta, '(underlyingClock=%f)' % self.clockService.now())
            self.clockService.set(contextClock)
        #
        # Check whether we should move the document clock in the reverse direction
        # (effectively not changing it) because we expected this clock delta due to a seek
        #
        adjustDocClock = self.layoutService.adjustExpectedClockOffset(delta)
        if adjustDocClock:
            self.logger.info('clockChanged: delta=%f adjustDocClock=%f', delta, adjustDocClock)
            self.documentClock.set(self.documentClock.now() - adjustDocClock)
            self.document.report(logging.INFO, 'CLOCK', 'adjusted', adjustDocClock, '(underlyingClock=%f)' % self.clockService.now())
            
        #
        # Adjust clock rate, if needed
        #
        if contextClockRate != self.clockService.getRate():
            if contextClockRate:
                self.document.report(logging.INFO, 'CLOCK', 'start', '(underlyingClock=%f)' % self.clockService.now())
                self.clockService.start()
            else:
                self.document.report(logging.INFO, 'CLOCK', 'stop', '(underlyingClock=%f)' % self.clockService.now())
                self.clockService.stop()
        self.document.clockChanged()
        self.logger.debug("Timeline(%s): after clockChanged clockService=%f, document=%f", self.contextId, self.clockService.now(), self.documentClock.now())
        self._updateTimeline()
        if delta < -MAX_CLOCK_DISCREPANCY:
            self.document.root.delegate.notifyNegativeClockChange(self.documentClock.now())
        return None

    def _populateTimeline(self):
        """Create proxy objects, etc, using self.dmappTimeline"""
        try:
            self.document.loadDocument(self.timelineDocUrl)
        except:
            errorStr = '\n'.join(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
            self.logger.error("Timeline(%s): %s: Error loading document: %s", self.contextId, self.timelineDocUrl, errorStr)
            raise
        self.document.report(logging.INFO, 'DOCUMENT', 'loaded', self.timelineDocUrl)
        overrideBaseUrl = self.document.root.get(document.NS_2IMMERSE("base"))
        if overrideBaseUrl:
            self.timelineDocBaseUrl = str23compat(overrideBaseUrl)
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
        
    def checkForAsyncUpdates(self):
        """Check to see whether we are running under control of an editor backend"""
        backendEndpoint = urllib.parse.urljoin(self.timelineDocUrl, 'getliveinfo')
        self.logger.debug("checkForAsyncUpdates: attempt to contact %s" % backendEndpoint)
        r = requests.get(backendEndpoint, params={'contextID' : self.contextId})
        if r.status_code != requests.codes.ok:
            # Assume any incorrect reply means we are not under control of an editor backend. Probably running a normal document.
            self.logger.debug("checkForAsyncUpdates: error contacting %s: %s" % (backendEndpoint, repr(r.status_code)))
            return
        self.document.report(logging.INFO, 'DOCUMENT', 'master', backendEndpoint)
        previewParameters = r.json()
        if 'currentTime' in previewParameters:
            currentTime = previewParameters.pop('currentTime')
            self.documentInitialSeek = float(currentTime)
        if 'clockEpoch' in previewParameters:
            masterStartTime = float(previewParameters.pop('clockEpoch'))
            self.document.report(logging.INFO, 'DOCUMENT', 'masterEpoch', masterStartTime)
            self._setMasterEpoch(masterStartTime)
            # xxxjack more to be done
        self.asyncHandler = socketIOhandler.SocketIOHandler(self, **previewParameters)
        
    def startAsyncUpdates(self):
        if self.asyncHandler and self.asyncHandler.wantStatusUpdate():
            self.document.setStateUpdateCallback(self._stateUpdateCallback)
        if self.asyncHandler:
            self.asyncHandler.start()
        
    def updateDocument(self, generation, operations):
        self.document.report(logging.INFO, 'DOCUMENT', 'update', 'generation=%d, count=%d' % (generation, len(operations)))
        stateUpdateCallback = None
        self.document.modifyDocument(generation, operations)
        self._updateTimeline()
        
    def _stateUpdateCallback(self, elementStates):
        if not self.asyncHandler:
            self.logger.warning("_stateUpdateCallback without asyncHandler")
            return
        documentState = {'elementStates' : elementStates}
        clockEpoch = self.clockService.now() - self.documentClock.now()
        # If this is a very large number we assume we're a live player. We report our underlying clock start time.
        if clockEpoch > 360000:
            documentState['clockEpoch'] = clockEpoch
        
        self.asyncHandler.sendStatusUpdate(dict(documentState))
        
    def _setMasterEpoch(self, masterEpoch):
        """Called if we get a master epoch: the underlying clock value for t=0 on the master player document timeline"""
        if masterEpoch:
            self.masterEpoch = masterEpoch
        if self.masterEpoch and self.ourEpoch:
            self._fixEpochs()
        
    def _setOurEpoch(self, ourEpoch):
        """Called when we know our epoch: the underlying clock value that corresponds to t=0 on our player document timeline"""
        if ourEpoch:
            self.ourEpoch = ourEpoch
        if self.masterEpoch and self.ourEpoch:
            self._fixEpochs()

    def _waitForLiveEpochs(self):
        """Return True if we have to wait for a second epoch before we can fast-forward the clocks"""
        return not not (self.ourEpoch or self.masterEpoch)
        
    def _fixEpochs(self):
        """Called to fix the epoch of our document if master and our epoch have been set previously"""
        self.logger.info("xxxjack fixEpochs masterEpoch=%s ourEpoch=%s initialSeek=%s" % (self.masterEpoch, self.ourEpoch, self.documentInitialSeek))
        self.document.report(logging.INFO, "CLOCK", "fixEpoch", self.ourEpoch - self.masterEpoch)
        if not self.documentInitialSeek:
            self.documentInitialSeek = 0
        self.documentInitialSeek = self.ourEpoch - self.masterEpoch
        if self.documentInitialSeek < 0:
            self.logger.warning("_fixEpochs: resultant seek time is negative: %f" % self.documentInitialSeek)
        self.prepareDMAppTimeline()
        
class TimelinePollingRunnerMixin(object):
    def __init__(self):
        pass
        
    def _startTimeline(self):
        pass
        
    def _updateTimeline(self):
        self._stepTimeline()
        
class TimelineThreadedRunnerMixin(object):
    def __init__(self):
        self.timelineCondition = threading.Condition()
        self.timelineThread = threading.Thread(target=self._runTimeline)
        self.timelineThread.daemon = True

    def _startTimeline(self):
        self.timelineThread.start()
        
    def _runTimeline(self):
        assert self.document
        assert self.document.getDocumentState()
        assert self.document.documentState
        with self.timelineCondition:
            while self.document and not self.document.isDocumentDone():
                self._stepTimeline()
                maxSleep = self.documentClock.nextEventTime(default=None)
                if not self.document.documentState.nudgeClock():
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
        
        
class ProxyLayoutService(object):
    def __init__(self, contactInfo, contextId, dmappId, logger):
        self.logger = logger
        self.contactInfo = contactInfo
        self.contextId = contextId
        self.dmappId = dmappId
        self.actions = []
        self.pendingTransactions = None
        self.actionsTimestamp = None
        # We need somewhere to record the delta we expect from the clock in the near future (because the
        # way we map document clock to playout clock). The ProxyLayoutService is the object that
        # is available both where we know the delay and where we resync the clock
        self.expectedClockOffset = None
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
        shouldDequeue = False
        with self.actionsLock:
            if not self.actions: return
            if self.pendingTransactions is None:
                self.pendingTransactions = []
                shouldDequeue = True
                # This call instance now "owns" self.pendingTransactions.
                # Any concurrent call instances will queue items onto our self.pendingTransactions, to be dequeued in this instance.
            while len(self.actions) > 0:
                self._filterActions()
            self.actionsTimestamp = None
            self.actions = []
        if shouldDequeue:
            while True:
                with self.actionsLock:
                    if len(self.pendingTransactions) == 0:
                        self.pendingTransactions = None
                        return
                    body = self.pendingTransactions.pop(0)
                self._forwardTransaction(body)

    def _filterActions(self):
        blacklist = set()
        send = []
        keep = []
        for action in self.actions:
            assert(len(action["components"]) == 1)
            componentId = action["components"][0]["componentId"]
            if componentId in blacklist:
                keep.append(action)
            else:
                send.append(action)
                if action["action"] == "destroy":
                    blacklist.add(componentId)
                    # Once a component ID has been destroyed in a transaction, any subsequent re-init/etc. actions must be sent in a seperate transaction.
                    # This is because the layout service executes transaction operations in verb order, nor array order.
        self.logger.info("ProxyLayoutService: forwarding %d actions (t=%f): %s" % (len(send), self.actionsTimestamp, repr(send)))
        self.pendingTransactions.append(dict(time=self.actionsTimestamp, actions=send))
        self.actions = keep

    def _forwardTransaction(self, body):
        entryPoint = self.getContactInfo() + '/transaction'
        try:
            r = requests.post(entryPoint, json=body)
        except requests.exceptions.RequestException as e:
            self.logger.error("Failed to forward actions to layout service")
            self.logger.info("Failure URL: %s" % entryPoint)
            self.logger.info("Failure data: %s" % repr(body))
            self.logger.info("Failure reason: %s" % repr(e))
            raise
        r.raise_for_status()

    def recordExpectedClockOffset(self, offset):
        """Called when we expect a future clock offset (from the player) with this delta-T"""
        if self.expectedClockOffset != None:
            self.logger.warn("Recording expected clock offset %f overrides old value %f" % (offset, self.expectedClockOffset))
        self.expectedClockOffset = offset
        
    def adjustExpectedClockOffset(self, delta):
        """A client clock adjustment of delta has come in. Return the amount we should adjust the document clock the other direction."""
        # Note that all values tend to be negative (because the document clock has been seeked forward)
        if self.expectedClockOffset == None:
            # If we have no expected seek we don't want the document clock to adjust
            return 0
        if delta > 0:
            # If the client clock is moving _forward_ we ignore it
            return 0
        if delta >= self.expectedClockOffset:
            rv = delta
            self.expectedClockOffset -= rv
            if abs(self.expectedClockOffset) < 0.1:
                self.expectedClockOffset = None
        else:
            rv = self.expectedClockOffset
            self.expectedClockOffset = None
        return rv
        
class ProxyMixin(object):
    def __init__(self, timelineDocBaseUrl, layoutService, componentId):
        self.componentId = componentId
        self.logger = layoutService.logger
        self.timelineDocBaseUrl = str23compat(timelineDocBaseUrl)
        self.layoutService = layoutService
        
    def getLogExtra(self):
    	return dict(xpath=self.getXPath(), dmappcID=self.componentId)
    	
    def _getTime(self, timestamp):
        """Convert document time to the time used by the external agents (clients, layout)"""
        return timestamp - self.clock.offsetFromUnderlyingClock()

    def scheduleAction(self, verb, timestamp, config=None, parameters=None):
        extraLogArgs = ()
        if config != None or parameters != None:
            extraLogArgs = (config, parameters)
        constraintId = self._getConstraintId()
        self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), self.componentId, timestamp, 'constraintId=%s' % constraintId, *extraLogArgs, extra=self.getLogExtra())
        self.layoutService.scheduleAction(self._getTime(timestamp), self.componentId, verb, config=config, parameters=parameters, constraintId=constraintId)

    def _getParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in document.NS_2IMMERSE_COMPONENT:
                localName = document.NS_2IMMERSE_COMPONENT.localTag(k)
                value = self.elt.attrib[k]
                value = str23compat(value)
                if 'url' in localName.lower() and value:
                    value = urllib.parse.urljoin(self.timelineDocBaseUrl, value)
                rv[localName] = value
            elif k in document.NS_TIMELINE_CHECK:
                localName = document.NS_TIMELINE_CHECK.localTag(k)
                value = self.elt.attrib[k]
                value = str23compat(value)
                if 'url' in localName.lower() and value:
                    value = urllib.parse.urljoin(self.timelineDocBaseUrl, value)
                rv['debug-2immerse-' + localName] = value
        self._fix2immerseTimeParameters(rv)
        return rv

    def _getConstraintId(self):
        constraintId = self.elt.get(document.NS_2IMMERSE("constraintId"))
        if not constraintId:
            constraintId = self.componentId
        return constraintId

    def _fix2immerseTimeParameters(self, parameters):
        # Special case for communicating timestamps to Chyron Hego Prime graphics.
        # These are converted from document time to contextclock
        if not parameters: return
        if 'startedRefTime' in parameters:
            value = float(parameters['startedRefTime'])
            newValue = self._getTime(value)
            self.logger.info("startedRefTime: converted from %s to %s", value, newValue, extra=self.getLogExtra())
            value = str(newValue)
            parameters['startedRefTime'] = value

    def _addSeekParameter(self, parameters):
        """# Also get the initial seek, for sync masters. Assume the syntax for the attributes is as for the video dmappc.
        If the parameters are updated we expect a CLOCK seek later, we return the expected clock seek value (which we will ignore
        for the document clock"""
        if self.mediaClockSeek != None and self.isCurrentTimingMaster(future=True):
            self.document.report(logging.INFO, 'FFWD', 'seekMaster', self.document.getXPath(self.elt), self.mediaClockSeek)
            #
            # Note that we set both startMediaTime (which you can think of as an initial seek into the media file) and offset
            # (which is the delta-T between the time position in the media file and the time position of the internal clock of the dmappc).
            # Normally, offset defaults to startMediaTime, and because offset is "backward pointing" this means that only setting startMediaTime
            # will still cause the dmappc to start at t=0 (internal clock).
            #
            # Normally that is what you want, but for our case, seeking the media because the whole presentation has been seeked) it is not:
            # we want the clock to behave as if the media seek hadn't happened.
            #
            # Still need to check (as of May 1, 2018) that this is also correct for live feeds.
            #
            parameters['startMediaTime'] = str(-self.mediaClockSeek)
            parameters['offset'] = "0"
            return -self.mediaClockSeek
        return None

class ProxyDMAppComponent(document.TimeElementDelegate, ProxyMixin):
    IS_REF_TYPE=True

    def __init__(self, elt, doc, timelineDocBaseUrl, clock, layoutService):
        document.TimeElementDelegate.__init__(self, elt, doc, clock)
        ProxyMixin.__init__(self, timelineDocBaseUrl, layoutService, self.getId())
        self.revision = -1
        self.klass = self.elt.get(document.NS_2IMMERSE("class"))
        self.url = str23compat(self.elt.get(document.NS_2IMMERSE("url"), ""))
        self.lastReceivedDuration = None
        self.activeOverlays = []
        self.seekParameters = {}
        self.nullParameters = set()
        # Allow relative URLs by doing a basejoin to the timeline document URL.
        if self.url:
            self.url = urllib.parse.urljoin(self.timelineDocBaseUrl, self.url)
        if not self.componentId:
            self.componentId = "unknown%d" % id(self)
            self.logger.error("Element %s: missing xml:id attribute, invented %s", self.document.getXPath(self.elt), self.componentId, extra=self.getLogExtra())
        assert self.componentId
        if not self.klass:
            self.klass = "unknownClass"
            self.logger.error("Element %s: missing tim:class attribute, invented %s", self.document.getXPath(self.elt), self.klass, extra=self.getLogExtra())
        self.expectedDuration = None
        assert self.klass

    def _getParameters(self):
        parameters = ProxyMixin._getParameters(self)
        for key in self.seekParameters:
            parameters[key] = self.seekParameters[key]
        for elt in self.activeOverlays:
            for key in elt.delegate.parameters:
                parameters[key] = elt.delegate.parameters[key]
                self.nullParameters.add(key)
        # This is to handle the case where an overlay previously added a new parameter, and now it needs to be removed in the layout service
        for key in self.nullParameters:
            if not key in parameters: parameters[key] = None
        return parameters

    def _getConstraintId(self):
        constraintId = ProxyMixin._getConstraintId(self)
        for elt in self.activeOverlays:
            newConstraintId = elt.get(document.NS_2IMMERSE("constraintId"))
            if newConstraintId: constraintId = newConstraintId
        return constraintId

    def initTimelineElement(self):
        self.assertState('ProxyDMAppComponent.initTimelineElement()', document.State.idle)
        self.setState(document.State.initing)
        self.revision += 1
        config = {'class':self.klass, 'url':self.url, 'revision':self.revision}
        self.seekParameters.clear()
        self.nullParameters.clear()
        expectedClockOffset = self._addSeekParameter(self.seekParameters)
        if expectedClockOffset:
            self.layoutService.recordExpectedClockOffset(-expectedClockOffset)
        self.scheduleAction("init", self.clock.now(), config=config, parameters=self._getParameters())

    def startTimelineElement(self):
        self.assertState('ProxyDMAppComponent.startTimelineElement()', document.State.inited)
        self.setState(document.State.starting)
        self.scheduleAction("start", self.getStartTime())

    def stopTimelineElement(self):
        self.setState(document.State.stopping)
        self.scheduleAction("stop", self.getStopTime())
            
    def destroyTimelineElement(self):
        self.scheduleAction("destroy", self.getStopTime())

    def statusReport(self, state, duration, fromLayout, revision):
        durargs = ()
        if fromLayout:
            durargs = ('fromLayout',)
        if duration != None:
            durargs = ('duration=%s' % duration,)
            self.lastReceivedDuration = duration
        if revision != None:
            if revision != self.revision:
                self.logger.info('Ignoring stale "%s" (revision %s) state update for node %s (in state %s, revision %s)' % ( state, revision, self.document.getXPath(self.elt), self.state, self.revision), extra=self.getLogExtra())
                return
            durargs += ('revision=%s' % revision,)
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
                self.scheduleAction('destroy', self.getStopTime())
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
                self.logger.info('Unexpected "%s" state update for node %s (in state %s), re-issuing destroy' % (state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
                self.scheduleAction('destroy', self.getStopTime())
            else:
                self.logger.info('Ignoring unexpected "%s" state update for node %s (in state %s)' % ( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())
        elif state == document.State.idle:
            self.setState(state) # idle is always allowed
        elif state == "destroyed":
            # destroyed is translated into idle, unless we're in idle already
            if self.state != document.State.idle:
                state = document.State.idle
                self.setState(state)
        else:
            self.logger.error('Unknown "%s" state update for node %s (in state %s), ignoring' %( state, self.document.getXPath(self.elt), self.state), extra=self.getLogExtra())

        # Note: we used to call _scheduleFinished also when duration==None and fromLayout. But this had the effect that if the layout service
        # decided to send a quick "fromlayout" update we might terminate the document before it got actually started.
        # The current solution, not scheduling a synthesized finished, has the disadvantage that if there are no clients at all and they'll never appear
        # either the whole context will sit waiting infinitely long.
        if state == document.State.started and duration != None and self.startTime != None:
            self._scheduleFinished(duration)

    def _scheduleFinished(self, dur):
        if not dur: 
            dur = 0
        if self.expectedDuration is None or self.expectedDuration > dur:
            self.clock.scheduleAt(self.startTime + dur, self._emitFinished)
        if self.expectedDuration != None and self.expectedDuration != dur:
            self.logger.warning('Expected duration of %s changed from %s to %s' % (self.document.getXPath(self.elt), self.expectedDuration, dur), extra=self.getLogExtra())
            self.expectedDuration = dur 
        
    def _emitFinished(self):
        if self.state in (document.State.started, document.State.starting):
            self.document.report(logging.INFO, 'SYNTH', 'finished', self.document.getXPath(self.elt), extra=self.getLogExtra())
            self.setState(document.State.finished)
        else:
            self.document.report(logging.INFO, 'SYN-IGN', 'finished', self.document.getXPath(self.elt), extra=self.getLogExtra())

    def predictStopTime(self, mode, startTimeOverride = None):
        if mode == "deterministic":
            return None
        if startTimeOverride is not None:
            startTime = startTimeOverride
        elif self.startTime is not None:
            startTime = self.startTime
        else:
            return None
        if self.lastReceivedDuration is not None:
            return startTime + self.lastReceivedDuration
        else:
            return None

    def applyOverlayUpdates(self, timestamp):
        if self.state in document.State.STOP_NEEDED:
            self.scheduleAction("update", timestamp, parameters=self._getParameters())

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
            self.scheduleActionMulti("update", self.getStartTime(), componentIds, parameters=parameters)
        else:
            # xxxjack should this recording always be done???
            targetElt = self.document.getElementById(self.componentId)
            if targetElt != None:
                for attrName, attrValue in list(parameters.items()):
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
            self.scheduleAction("update", self.getStartTime(), parameters=parameters)
        
    def scheduleActionMulti(self, verb, timestamp, componentIds, config=None, parameters=None):
        extraLogArgs = ()
        if config != None or parameters != None:
            extraLogArgs = (config, parameters)
        newConstraintId = self.elt.get(document.NS_2IMMERSE("constraintId"))
        for cid in componentIds:
            if newConstraintId:
                self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), cid, timestamp, 'constraintId=%s' % newConstraintId, *extraLogArgs, extra=self.getLogExtra())
                self.layoutService.scheduleAction(self._getTime(timestamp), cid, verb, config=config, parameters=parameters, constraintId=newConstraintId)
            else:
                self.document.report(logging.INFO, 'QUEUE', verb, self.document.getXPath(self.elt), cid, timestamp, *extraLogArgs, extra=self.getLogExtra())
                self.layoutService.scheduleAction(self._getTime(timestamp), cid, verb, config=config, parameters=parameters)

class OverlayComponent(document.TimelineDelegate, ProxyMixin):
    def __init__(self, elt, doc, timelineDocUrl, clock, layoutService):
        document.TimelineDelegate.__init__(self, elt, doc, clock)
        componentId = self.elt.get(document.NS_2IMMERSE("target"))
        self.targetXPath = self.elt.get(document.NS_2IMMERSE("targetXPath"))
        ProxyMixin.__init__(self, timelineDocUrl, layoutService, componentId)

    def _orderedOverlistInsert(self, overlayList, elt):
        # Sort target's overlay list in ascending start time sorted order
        key = elt.delegate.startTime
        lo, hi = 0, len(overlayList)
        while lo < hi:
            mid = (lo + hi) // 2
            if key < overlayList[mid].delegate.startTime:
                hi = mid
            else:
                lo = mid + 1
        overlayList.insert(lo, elt)

    def _tryApplyToElement(self, elt):
        overlayList = getattr(elt.delegate, 'activeOverlays', None)
        if overlayList is not None:
            self._orderedOverlistInsert(overlayList, self.elt)
            self.appliedTo.append(elt)
            elt.delegate.applyOverlayUpdates(self.getStartTime())

    def startTimelineElement(self):
        self.assertState('OverlayComponent.startTimelineElement()', document.State.inited)
        document.TimelineDelegate.startTimelineElement(self)
        self.parameters = self._getParameters()
        self.appliedTo = []
        if self.targetXPath:
            # Find all active elements in the group
            allMatchingElements = self.document.root.findall(self.targetXPath, document.NAMESPACES)
            for elt in allMatchingElements:
                self._tryApplyToElement(elt)
        else:
            # xxxjack should this recording always be done???
            targetElt = self.document.getElementById(self.componentId)
            if targetElt != None:
                self._tryApplyToElement(targetElt)
            else:
                self.logger.error('tim:overlay: no component with xml:id="%s"' % self.componentId, extra=self.getLogExtra())

    def stopTimelineElement(self):
        if self.state == document.State.finished:
            for elt in self.appliedTo:
                elt.delegate.activeOverlays.remove(self.elt)
                elt.delegate.applyOverlayUpdates(self.getStopTime())
            del self.appliedTo
        document.TimelineDelegate.stopTimelineElement(self)
