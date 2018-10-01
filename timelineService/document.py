from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import map
from builtins import str
from builtins import object
import sys
import urllib.request, urllib.error, urllib.parse
import urllib.parse
import argparse
import time
import xml.etree.ElementTree as ET
import logging
from . import clocks
import json
from functools import reduce

logging.basicConfig()

class MyLoggerAdapter(logging.LoggerAdapter):

	def process(self, msg, kwargs):
		if 'extra' in kwargs:
			kwargs['extra'].update(self.extra)
		else:
			kwargs['extra'] = self.extra
		return msg, kwargs
		
DEBUG=True

class TimelineParseError(ValueError):
    pass
    
class NameSpace(object):
    def __init__(self, namespace, url):
        self.namespace = namespace
        self.url = url
        
    def ns(self):
        return { self.namespace : self.url }
        
    def __call__(self, str):
        return "{%s}%s" % (self.url, str)
        
    def __contains__(self, str):
        return str.startswith('{'+self.url+'}')
        
    def localTag(self, str):
        if str in self:
            return str[len(self.url)+2:]
        return str


COMPAT_V1=True # Set to True to allow tim:dmappcid to be used in lieu of xml:id

NS_TIMELINE = NameSpace("tl", "http://jackjansen.nl/timelines")
NS_TIMELINE_INTERNAL = NameSpace("tls", "http://jackjansen.nl/timelines/internal")
NS_TIMELINE_CHECK = NameSpace("tlcheck", "http://jackjansen.nl/timelines/check")
NS_TIMELINE_DEFAULTS = NameSpace("tldefaults", "http://jackjansen.nl/timelines/defaults")
NS_2IMMERSE = NameSpace("tim", "http://jackjansen.nl/2immerse")
NS_2IMMERSE_COMPONENT = NameSpace("tic", "http://jackjansen.nl/2immerse/component")
NS_XML = NameSpace("xml", "http://www.w3.org/XML/1998/namespace")
NS_TRIGGER = NameSpace("tt", "http://jackjansen.nl/2immerse/livetrigger")
NS_AUTH = NameSpace("au", "http://jackjansen.nl/2immerse/authoring")
NAMESPACES = {}
NAMESPACES.update(NS_XML.ns())
NAMESPACES.update(NS_TIMELINE.ns())
NAMESPACES.update(NS_TIMELINE_INTERNAL.ns())
NAMESPACES.update(NS_TIMELINE_CHECK.ns())
NAMESPACES.update(NS_2IMMERSE.ns())
NAMESPACES.update(NS_2IMMERSE_COMPONENT.ns())
NAMESPACES.update(NS_TRIGGER.ns())
NAMESPACES.update(NS_AUTH.ns())
for k, v in list(NAMESPACES.items()):
    ET.register_namespace(k, v)

# For attribute checking for 2immerse documents:
from . import attributeChecker
attributeChecker.NS_XML = NS_XML
attributeChecker.NS_TIMELINE = NS_TIMELINE
attributeChecker.NS_TIMELINE_CHECK = NS_TIMELINE_CHECK
attributeChecker.NS_2IMMERSE = NS_2IMMERSE
attributeChecker.NS_2IMMERSE_COMPONENT = NS_2IMMERSE_COMPONENT

PRIO_TO_INT = dict(low=0, normal=50, high=100)

class State(object):
    idle = "idle"
    initing = "initing"
    inited = "inited"
    starting = "starting"
    started = "started"
    finished = "finished"
    stopping = "stopping"
#    stopped = "stopped"
#    terminating = "terminating"
    
    NOT_DONE = {initing, inited, starting, started}
    STOP_NEEDED = {initing, inited, starting, started, finished}
    MOVE_ALLOWED_TARGET_STATES = {idle, inited, started, finished}
    MOVE_ALLOWED_START_STATES = {inited, starting, started, finished, stopping}
    TRIGGER_IMPORTANT_STATES = {idle, started, finished}
    TRIGGER_PROGRESS_IMPORTANT_STATES = {started, finished}
    
class DummyDelegate(object):
    """Baseclass for delegates, also used for non-timeline elements."""
    DEFAULT_PRIO="low"
    IS_REF_TYPE=False
    
    def __init__(self, elt, document, clock):
        self.elt = elt
        self.document = document
        self.logger = self.document.logger
        self.state = State.idle
        self.clock = clock
        self.startTime = None
        self.startTimeFixed = False
        self.conformTargetDelegate = None
        self.mediaClockSeek = None # If set this is how far the media clock should be seeked ahead.
        
    def __repr__(self):
        return 'Delegate(%s)' % self.getXPath()
        
    def getId(self):
        uniqId = self.elt.get(self.document.idAttribute)
        if COMPAT_V1:
            if not uniqId:
                uniqId = self.elt.get(NS_2IMMERSE("dmappcid"))
        return uniqId

    def getXPath(self):
        return self.document.getXPath(self.elt)
        
    def getLogExtra(self):
    	rv = dict(xpath=self.getXPath())
    	uid = self.getId()
    	if uid:
    		rv['dmappcID'] = uid
    	elif hasattr(self, 'componentId'):
    		rv['dmappcID'] = self.componentId
    	return rv
    	
    def checkAttributes(self):
        """Check XML attributes for validity"""
        pass
        
    def checkChildren(self):
        """Check XML children for validity"""
        pass
        
    def isCurrentTimingMaster(self, future=False):
        """Return True if this element currently has control over its own clock"""
        return False
        
    def storeStateForSave(self):
        """Store internal state in XML, prior to serialisation"""
        if self.state != State.idle:
            self.elt.set(NS_TIMELINE_INTERNAL("state"), self.state)
        if self.startTime != None:
            if self.isCurrentTimingMaster():
                self.elt.set(NS_TIMELINE_INTERNAL("progress"), str(self.clock.now()-self.startTime))
            else:
                self.elt.set(NS_TIMELINE_INTERNAL("slavedProgress"), str(self.clock.now()-self.startTime))
            
    def setState(self, state):
        """Advance element state to a new one. Subclasses will add side effects (such as actually playing media)"""
        self.document.report(logging.DEBUG, 'STATE', state, self.document.getXPath(self.elt), extra=self.getLogExtra())
        if self.state == state:
            self.logger.info('superfluous state change: %-8s %-8s %s' % ('STATE', state, self.document.getXPath(self.elt)), extra=self.getLogExtra())
            if state == State.idle:
                # Defensive programming: destroy it again...
                self.logger.info('Re-issuing destroy for %s' % self.document.getXPath(self.elt), extra=self.getLogExtra())
                self.destroyTimelineElement()
            return
        oldState = self.state
        self.state = state
        
        if self.state == State.started:
            # Remember the time this element actually started. A bit convoluted
            # because of reviving of elements in 2immerse
            if oldState not in {State.started, State.finished}:
                # Unfortunately we also come here when we re-start the pars after seeking.
                pass # assert self.startTime == None
            if self.startTime == None:
                self.startTime = self.clock.now()
        elif self.state == State.finished:
            # Similar to for state=started, but only f started didn't set it.
            if self.startTime == None:
                self.startTime = self.clock.now()
        else:
            if not self.startTimeFixed:
                # The element is no longer running, so forget the start time.
                self.startTime = None
            
        parentElement = self.document.getParent(self.elt)
        if parentElement is not None:
#            self.logger.info('xxxjack report statechange for %s to %s' % (self.getXPath(), parentElement.delegate.getXPath()))
            parentElement.delegate.reportChildState(self.elt, self.state)
        else:
            if self.elt != self.document.root:
                self.logger.error("setState for element %s which has no parent" % self.getXPath(), extra=self.getLogExtra())
            
        if self.state == State.idle:
            self.destroyTimelineElement()
            
        self.forwardStateChangeToTriggerTool()
        
    def forwardStateChangeToTriggerTool(self):
        """If a trigger tool is attached to this session and it is interested in this element tell it about the state change"""
        if not self.state in State.TRIGGER_IMPORTANT_STATES:
            return
        if not self.elt.get(NS_TRIGGER("wantstatus")):
            return
        self.document.forwardElementStateChangeToTriggerTool(self.elt)
        
    def getStateForTriggerTool(self):
        """Return relevant state information (for the trigger tool) for this element"""
        if self.state in State.TRIGGER_PROGRESS_IMPORTANT_STATES:
            progressVal = str(self.clock.now()-self.startTime)
        else:
            progressVal = None
        rv = {NS_TIMELINE_INTERNAL("state"): self.state, NS_TIMELINE_INTERNAL("progress"): progressVal}
        if self.clock.getRate() > 0:
            rv[NS_TIMELINE_INTERNAL("clockRunning")] = "true"
        return rv
        
           
    def assertState(self, action, *allowedStates):
        """Check that the element is in an expected state."""
        if len(allowedStates) == 1 and type(allowedStates[0]) == set:
            allowedStates = allowedStates[0]
        else:
            allowedStates = set(allowedStates)
        if not self.state in allowedStates:
            self.logger.error("Assertion failure: %s: %s: state==%s, expected %s" % (self, action, self.state, allowedStates), extra=self.getLogExtra())
        assert self.state in allowedStates, "%s: %s: state==%s, expected %s" % (self, action, self.state, allowedStates)
        
    def assertDescendentState(self, action, *allowedStates):
        """Check that all descendents of the element are in an expected state"""
        for desc in self.elt.iter():
            if not desc.delegate.state in set(allowedStates):
                self.logger.error("Assertion failure: %s: %s: descendent %s: state==%s, expected %s" % (self, action, desc.delegate, desc.delegate.state, set(allowedStates)), extra=self.getLogExtra())
            assert desc.delegate.state in set(allowedStates), "%s: %s: descendent %s: state==%s, expected %s" % (self, action, desc.delegate, desc.delegate.state, set(allowedStates))
         
    def reportChildState(self, child, childState):
        """Called by direct children when they change their state"""
        pass
        
    def initTimelineElement(self):
        """Called by parent or outer control to initialize the element"""
        self.assertState('initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        #self.setState(State.initing)
        self.setState(State.inited)
        
    def initTimelineElementIfNotInited(self):
        """Called by parent or outer control to initialize the element. This variant is to handle the case where the init may be asynchronously queued more than once."""
        if self.state == State.idle:
            self.initTimelineElement()

    def startTimelineElement(self):
        """Called by parent or outer control to start the element"""
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        #self.setState(State.starting)
        #self.setState(State.started)
        #self.setState(State.stopping)
        self.setState(State.finished)
        
    def stopTimelineElement(self):
        """Called by parent or outer control to stop the element"""
        if self.state == State.idle:
            return
        self.setState(State.idle)
        
    def destroyTimelineElement(self):
        pass
        
    def getCurrentPriority(self):
        """Return current priority of this element for clock arbitration"""
        val = self.elt.get(NS_TIMELINE("prio"), self.DEFAULT_PRIO)
#         if self.state == State.started:
#             val = self.elt.get(NS_TIMELINE("prio"), "normal")
#         else:
#             val = "low"
        val = PRIO_TO_INT.get(val, val)
        val = int(val)
        return val

    def prepareMoveStateToConform(self, conformTargetDelegate):
        """Prepare for fast-forward an element so that it is in the same state 
        as its old delegate was."""
        assert self.state == State.idle
        if  self.state == conformTargetDelegate.state:
            # This delegate is already in its target state. Nothing to do.
            self.conformTargetDelegate = None
            return
        self.conformTargetDelegate = conformTargetDelegate
        assert self.conformTargetDelegate.state in State.MOVE_ALLOWED_TARGET_STATES, "%s: prepareMoveStateToConform: state==%s, target=%s, expected %s" % (self, self.state, self.conformTargetDelegate.state, State.MOVE_ALLOWED_TARGET_STATES)

    def stepMoveStateToConform(self, startAllowed):
        """Execute a next step."""
        if self.conformTargetDelegate is None or self.state == self.conformTargetDelegate.state:
            # Apparently we are done.
            self.conformTargetDelegate = None
            return
        # xxxjack we really need a matrix here....
        if self.conformTargetDelegate.state == State.idle:
            if self.state in State.STOP_NEEDED:
                self.stopTimelineElement()
                return
        needInit = self.conformTargetDelegate.state in {State.inited, State.started, State.finished}
        if needInit and self.state == State.idle:
            self.initTimelineElement()
            self.assertState("stepMoveStateToConform:init", State.MOVE_ALLOWED_START_STATES|{State.initing})
            return
        if not startAllowed:
            return
        if self.conformTargetDelegate.state in {State.started, State.finished}:
            self.startTimelineElement()
            # Note that any initial seek is recorded later.
        self.assertState("stepMoveStateToConform:start", State.MOVE_ALLOWED_START_STATES)
        
    def hasFinishedMoveStateToConform(self):
        """Returns False is there is more work to be done on this element before
        it is in the state conforming to the state of its old delegate"""
        if self.conformTargetDelegate is None or self.state == self.conformTargetDelegate.state:
            # Apparently we are done.
            self.conformTargetDelegate = None
        return self.conformTargetDelegate is None
        
    def readyToStartMoveStateToConform(self):
        """Returns False if this element is still waiting for inited callback."""
        return self.hasFinishedMoveStateToConform() or self.state in State.MOVE_ALLOWED_START_STATES
        
    def updateMediaSeekForDocumentSeek(self, adjustment):
        """We may need to seek the media for this element, record that."""
        if self.conformTargetDelegate != None:
            if self.conformTargetDelegate.state in {State.started, State.finished}:
                self.mediaClockSeek = adjustment
                
    def getStartTime(self):
        """Return the time at which this element should have started, or now."""
        # xxxjack this does not yet handle seeking during playback, for elements which only
        # need to be repositioned (because they were running before the seek and are still running
        # after the seek)
        if self.startTimeFixed:
            return self.startTime
        if self.conformTargetDelegate != None:
            if self.conformTargetDelegate.state in {State.started, State.finished}:
                assert self.conformTargetDelegate.startTime != None
                self.logger.debug("Element %s should have started at t=%f", self.document.getXPath(self.elt), self.conformTargetDelegate.startTime)
                return self.conformTargetDelegate.startTime
        return self.clock.now()

    def predictStopTime(self, mode, startTimeOverride = None):
        """Return the predicted stop time of this element using the given prediction mode, or None if no valid prediction can be made."""
        if startTimeOverride is not None:
            return startTimeOverride
        if self.startTimeFixed or mode != "deterministic":
            return self.startTime
        else:
            return None

    def getStopTime(self):
        """Return the time at which this element should stop, or now."""
        stopTime = self.clock.now()
        parentElement = self.document.getParent(self.elt)
        if parentElement is not None:
            stopTime = parentElement.delegate.clipStopTime(stopTime)
        return stopTime

    def clipStopTime(self, stopTime):
        """Clip stop time to be within the bounds of the parent, as necessary"""
        parentElement = self.document.getParent(self.elt)
        if parentElement is not None:
            stopTime = parentElement.delegate.clipStopTime(stopTime)
        return stopTime
        
    def attributesChanged(self, attrs):
        """Called after an edit operation has changed attributes on this element."""
        self.logger.debug("%s: Unexpected call to attributesChanged(%s)" % (self.getXPath(), repr(attrs)))
        
    def childAdded(self, child):
        """Called after an edit operation when a new child has been added."""
        self.logger.debug("%s: Unexpected call to childAdded(%s)" % (self.getXPath(), self.document.getXPath(child)))
        
    def setMediaClockSeek(self, mediaClockSeek):
        """Tell item to seek this amount when started (negative number for forward in the media). Returns how much of this it will _not_ use."""
        return mediaClockSeek
        
    def notifyNegativeClockChange(self, newTime):
        """Notify element that clock has made a step change in the negative direction."""
        pass

class ErrorDelegate(DummyDelegate):
    """<tl:...> element of unknown type. Prints an error and handles the rest as a non-tl: element."""
    
    def __init__(self, elt, document, clock):
        DummyDelegate.__init__(self, elt, document, clock)
        print("* Error: unknown tag", elt.tag, file=sys.stderr)

class TimelineDelegate(DummyDelegate):
    """Baseclass for all <tl:...> elements."""
    
    ALLOWED_ATTRIBUTES = set()
    ALLOWED_CHILDREN = None
    EXACT_CHILD_COUNT = None
    
    def checkAttributes(self):
        for attrName in list(self.elt.keys()):
            if attrName in NS_TIMELINE:
                if not attrName in self.ALLOWED_ATTRIBUTES:
                    print("* Error: element", self.getXPath(), "has unknown attribute", attrName, file=sys.stderr)
            # Remove state attributes
            if attrName in NS_TIMELINE_INTERNAL:
                del self.elt.attrib[attrName]
                    
    def checkChildren(self):
        if not self.EXACT_CHILD_COUNT is None and len(self.elt) != self.EXACT_CHILD_COUNT:
            print("* Error: element", self.getXPath(), "expects", self.EXACT_CHILD_COUNT, "children but has", len(self.elt), file=sys.stderr)
        if not self.ALLOWED_CHILDREN is None:
            for child in self.elt:
                if child.tag in NS_2IMMERSE and not child.tag in self.ALLOWED_CHILDREN:
                    print("* Error: element", self.getXPath(), "cannot have child of type", child.tag, file=sys.stderr)
         
    def setMediaClockSeek(self, mediaClockSeek):
        """Tell item to seek this amount when started (negative number for forward in the media). Returns how much of this it will _not_ use."""
        self.mediaClockSeek = mediaClockSeek
        return 0
        
class SingleChildDelegate(TimelineDelegate):
    """Baseclass for elements that have exactly one child."""
    
    EXACT_CHILD_COUNT=1

    def __init__(self, elt, document, clock):
        self.timingModel = "floating"
        TimelineDelegate.__init__(self, elt, document, clock)

    def reportChildState(self, child, childState):
        assert child == self.elt[0]
        if self.state == State.idle:
            return
        if self.state == State.initing:
            if childState in {State.inited}:
                self.setState(State.inited)
                return
            assert childState == State.initing
            return
        if self.state == State.starting:
            if childState == State.started:
                self.setState(State.started)
                return
            elif childState == State.finished:
                self.setState(State.finished)
                return
            else:
                assert childState == State.starting
                return
        if self.state in {State.started, State.finished}:
            if child.delegate.state in State.NOT_DONE:
                return
            self.setState(State.finished)
            return
        if self.state == State.stopping:
            if childState == State.idle:
                self.setState(State.idle)
                return
            assert childState == State.stopping
            return

    def initTimelineElement(self):
        self.assertState('SingleChildDelegate.initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        self.setState(State.initing)
        if self.timingModel == "deterministic" and self.startTime is not None:
            self.elt[0].delegate.startTime = self.startTime
            self.elt[0].delegate.startTimeFixed = True
        self.document.schedule(self.elt[0].delegate.initTimelineElement)
        
    def startTimelineElement(self):
        self.assertState('SingleChildDelegate.startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.inited, State.idle)
        self.setState(State.starting)
        if self.timingModel == "deterministic" and self.startTime is not None:
            self.elt[0].delegate.startTime = self.startTime
            self.elt[0].delegate.startTimeFixed = True
        self.document.schedule(self.elt[0].delegate.startTimelineElement)
        
    def stopTimelineElement(self):
        if self.state == State.idle:
            return
        self.setState(State.stopping)
        waitNeeded = False
        if self.elt[0].delegate.state in State.STOP_NEEDED:
            self.document.schedule(self.elt[0].delegate.stopTimelineElement)
            waitNeeded = True
        if self.elt[0].delegate.state == State.stopping:
            waitNeeded = True
        if not waitNeeded:
            self.setState(State.idle)

    def predictStopTime(self, mode, startTimeOverride = None):
        return self.elt[0].delegate.predictStopTime(mode, startTimeOverride)

    def notifyNegativeClockChange(self, newTime):
        self.elt[0].delegate.notifyNegativeClockChange(newTime)

class DocumentDelegate(SingleChildDelegate):
    """<tl:document> element."""
    ALLOWED_CHILDREN={
        NS_TIMELINE("par"),
        NS_TIMELINE("seq"),
        }

    def __init__(self, elt, document, clock):
        document.defaultTimingModel = elt.get(NS_TIMELINE_DEFAULTS("timingModel"), document.defaultTimingModel)
        SingleChildDelegate.__init__(self, elt, document, clock)
        self.startTime = 0
        self.startTimeFixed = True
        self.timingModel = "deterministic"

    def initTimelineElement(self):
        self.startTime = -self.document.startTime # handle document seek at init
        SingleChildDelegate.initTimelineElement(self)

class TimeElementDelegate(TimelineDelegate):
    """Baseclass for elements that have a clock, and therefore a prio attribute."""
    
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("prio"),
        NS_TIMELINE("timingModel"),
        }

    def __init__(self, elt, document, clock):
        TimelineDelegate.__init__(self, elt, document, clock)
        self.timingModel = self.elt.get(NS_TIMELINE("timingModel"), document.defaultTimingModel)
        assert self.timingModel in {"floating", "deterministic"}, "%s: unknown timing model name: '%s'" % (self, self.timingModel)

    def getCurrentPriority(self):
        val = self.elt.get(NS_TIMELINE("prio"), "normal")
#         if self.state == State.started:
#             val = self.elt.get(NS_TIMELINE("prio"), "normal")
#         else:
#             val = "low"
        val = PRIO_TO_INT.get(val, val)
        val = int(val)
        return val

    def isCurrentTimingMaster(self, future=False):
        # xxxjack only correct for 2immerse....
        if not future and self.state != State.started:
            return False
        if self.state not in {State.initing, State.inited, State.starting, State.started}:
            return False
        syncMode = self.elt.get(NS_2IMMERSE_COMPONENT("syncMode"), "unspecified")
        if syncMode != "master":
            return False
        return True
        
class FFWDTimeElementDelegate(TimeElementDelegate):
    """Timed element (ref) fast-forward handling. All items finish directly, except timing masters"""
    
    def startTimelineElement(self):
        """Called by parent or outer control to start the element"""
        expectedDuration = float(self.elt.get(NS_TIMELINE_CHECK("dur"), 0))
        if not self.isCurrentTimingMaster(future=True):
            return TimeElementDelegate.startTimelineElement(self)
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.started)
        # Quick hack: tim:update elements don't finish (because they have a side effect)
        # For other media see if we can determine their expected duration

        if expectedDuration == 0:
            self.logger.warning("%s: syncMode=master element without tlcheck:dur. Guessing at 10 hours." % self.getXPath())
            expectedDuration = 36000
        self.clock.schedule(expectedDuration, self._done)
               
    def _done(self):
        if self.state == State.started:
            # Do nothing if we aren't in the started state anymore (probably because we've been stopped)
            self.document.report(logging.INFO, '<', 'finished', self.document.getXPath(self.elt), extra=self.getLogExtra())
            self.setState(State.finished)

    def predictStopTime(self, mode, startTimeOverride = None):
        if startTimeOverride is None:
            startTimeOverride = self.startTime
        if mode == "deterministic":
            return None
        else:
            return startTimeOverride + float(self.elt.get(NS_TIMELINE_CHECK("dur"), 0))

class FFWDSideEffectTimeElementDelegate(TimeElementDelegate):
    """Timed element with side effect (tim:update) fast-forward handling."""
    
    def startTimelineElement(self):
        """Called by parent or outer control to start the element"""
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.started)
        # Never finishes...

class ParDelegate(TimeElementDelegate):
    """<tl:par> element. Runs all its children in parallel."""
    
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("end"),
        NS_TIMELINE("sync"),
        }
        
    def reportChildState(self, child, childState):
#        self.logger.info('xxxjack par %s state %s child %s state %s' % (self.getXPath(), self.state, self.document.getXPath(child), childState))
        if self.state == State.idle:
            # If the <par> is idle we do not care about children changing state.
            return
        if self.state == State.initing:
            # We're initializing. Go to initialized once all our children have.
            for ch in self.elt:
                if ch.delegate.state not in {State.inited}:
                    return
            self.setState(State.inited)
            return
        #
        # See if this child should be auto-started (because it was inserted during runtime)
        #
        if child in self.childrenToAutoStart and childState == State.inited:
            self.logger.debug("%s: autostarting child %s" % (self.getXPath(), self.document.getXPath(child)))
            if self.timingModel == "deterministic" and self.startTime is not None:
                child.delegate.startTime = self.startTime
                child.delegate.startTimeFixed = True
            self.document.schedule(child.delegate.startTimelineElement)
        if self.state == State.inited and childState in {State.initing, State.inited}:
            # This can happen after fast-forward. Ignore.
            return
        if self.state == State.starting:
            # We're starting. Wait for all our children to have started (or started-and-finished).
            for ch in self.elt:
                if ch.delegate.state not in {State.started, State.finished}:
#                    self.logger.info('xxxjack starting %s waitforchild %s in state %s' % (self.getXPath(), ch.delegate.getXPath(), ch.delegate.state))
#                    if ch.delegate.state == State.inited:
#                        # xxxjack I am not sure why these "straddlers" exist, sometime, after seeking. Push it along.
#                        self.logger.debug("%s: autostarting child %s" % (self.getXPath(), self.document.getXPath(ch)))
#                        self.document.schedule(ch.delegate.startTimelineElement)
                    return
            self.setState(State.started)
            # Note that we fall through into the next if straight away
        if self.state == State.started:
            #
            # First check whether any of the children that are relevant to our lifetime are still not finished.
            # 
            relevantChildren = self._getRelevantChildren()
            for ch in relevantChildren:
                if ch.delegate.state in State.NOT_DONE:
                    return
            #
            # All timing-relevant children are done, we should terminate.
            # Terminate all our children.
            #
            # NOTE: there are some semantic issues with this. It means that
            # the children of this <par> will disappear instantly. It may be nicer to
            # have them linger on until this <par> gets a stopTimelineElement.
            # But that would mean that this <par> has no timeline anymore but
            # some of its children may still have one.
            #
            # The ultimate answer may be to add a freezeTimelineElement call
            # so we can get SMIL-like semantics.
            #
            if not self.emittedStopForChildren:
                for ch in self.elt:
                    if ch.delegate.state in State.STOP_NEEDED:
                        self.document.schedule(ch.delegate.stopTimelineElement)
                self.emittedStopForChildren = True
            # If all terminate calls and such have been emitted we are finished
            for ch in self.elt:
                if ch.delegate.state in State.NOT_DONE:
                    return
            self.setState(State.finished)
            return
        if self.state == State.stopping:
            # We're stopping. When all our children have stopped so have we.
            for ch in self.elt:
                if ch.delegate.state != State.idle:
                    return
            self.setState(State.idle)
            return
        if self.state == State.finished:
            # We're fine with finished reports from children
            if not childState in State.NOT_DONE:
                return
        # If we get here we got an unexpected state change from a child. Report.
        self.logger.warning('par[%s].reportChildState(%s,%s) but self is %s' % (self.document.getXPath(self.elt), self.document.getXPath(child), childState, self.state), extra=self.getLogExtra())

    def _getEndMode(self):
        childSelector = self.elt.get(NS_TIMELINE("end"))
        if childSelector:
            return childSelector
        elif self.timingModel == "deterministic":
            return "allNonRef"
        else:
            return "all"

    def _getRelevantChildren(self):
        if len(self.elt) == 0: return []
        childSelector = self._getEndMode()
        if childSelector == "all":
            return list(self.elt)
        elif childSelector == "allNonRef":
            return [ch for ch in self.elt if not ch.delegate.IS_REF_TYPE]
        elif childSelector == "master":
            child = self._getMasterChild()
            return [child]
        elif childSelector == "first":
            # If any child is finished we return an empty list
            for ch in self.elt:
                if ch.delegate.state in State.NOT_DONE:
                    return list(self.elt)
            return []
        self.logger.error('par[%s]: unknown value in end=%s' % (self.document.getXPath(self.elt), childSelector), extra=self.getLogExtra())
        return list(self.elt)

    def predictStopTime(self, mode, startTimeOverride = None):
        if len(self.elt) == 0:
            return TimeElementDelegate.predictStopTime(self, mode, startTimeOverride)

        if mode == "deterministic" and self.timingModel != "deterministic": return None
        if mode != "deterministic": startTimeOverride = None
        childSelector = self._getEndMode()
        stopTime = None
        if childSelector == "all" or childSelector == "allNonRef":
            for ch in self.elt:
                if ch.delegate.IS_REF_TYPE and childSelector == "allNonRef":
                    continue
                chStopTime = ch.delegate.predictStopTime(mode, startTimeOverride)
                if chStopTime is not None and (stopTime is None or chStopTime > stopTime):
                    stopTime = chStopTime
                elif chStopTime is None and mode in ["deterministic", "complete"]:
                    return None
        elif childSelector == "master":
            child = self._getMasterChild()
            if child is not None:
                stopTime = child.delegate.predictStopTime(mode, startTimeOverride)
        elif childSelector == "first":
            for ch in self.elt:
                chStopTime = ch.delegate.predictStopTime(mode, startTimeOverride)
                if chStopTime is not None and (stopTime is None or chStopTime < stopTime):
                    stopTime = chStopTime
                elif chStopTime is None and mode in ["deterministic", "complete"]:
                    return None
        else:
            self.logger.error('par[%s]: unknown value in end=%s' % (self.document.getXPath(self.elt), childSelector), extra=self.getLogExtra())
            return None
        return stopTime

    def clipStopTime(self, stopTime):
        clipTime = self.predictStopTime("complete")
        if clipTime is not None and stopTime > clipTime:
            stopTime = clipTime
        return TimeElementDelegate.clipStopTime(self, stopTime)

    def _getMasterChild(self):
        prioritiesAndChildren = []
        for ch in self.elt:
            prio = ch.delegate.getCurrentPriority()
            prioritiesAndChildren.append((prio, ch))
        prioritiesAndChildren.sort()
        return prioritiesAndChildren[-1][1]
        
        
    def initTimelineElement(self):
        self.assertState('ParDelegate.initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        self.setState(State.initing)
        self.emittedStopForChildren = False # Set to True if we have already emitted the stop clls to the children
        self.childrenToAutoStart = [] # Children that we start on inited (have been added during runtime with childAdded)
        if self.timingModel != "deterministic" and self.mediaClockSeek != None:
            self.logger.debug("ParDelegate(%s): forwarding mediaClockSeek %s" % (self.document.getXPath(self.elt), self.mediaClockSeek), extra=self.getLogExtra())
        for child in self.elt:
            if self.timingModel == "deterministic" and self.startTime is not None:
                child.delegate.startTime = self.startTime
                child.delegate.startTimeFixed = True
            if self.timingModel != "deterministic" and self.mediaClockSeek:
                child.delegate.setMediaClockSeek(self.mediaClockSeek)
            self.document.schedule(child.delegate.initTimelineElement)
        self.mediaClockSeek = None
        # xxxjack: should we go to inited if we have no children?
        
    def startTimelineElement(self):
        self.assertState('ParDelegate.startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        for child in self.elt:
            if self.timingModel == "deterministic" and self.startTime is not None:
                child.delegate.startTime = self.startTime
                child.delegate.startTimeFixed = True
            self.document.schedule(child.delegate.startTimelineElement)
        # xxxjack: should we go to finished if we have no children?
        
    def stopTimelineElement(self):
        if self.state == State.idle:
            return
        self.setState(State.stopping)
        waitNeeded = False
        for child in self.elt:
            if child.delegate.state in State.STOP_NEEDED:
                self.document.schedule(child.delegate.stopTimelineElement)
                waitNeeded = True
            if child.delegate.state == State.stopping:
                waitNeeded = True
        if not waitNeeded:
            self.setState(State.idle)

    def childAdded(self, child):
        """Called after an edit operation when a new child has been added."""
        self.logger.debug("%s: call to ParDelegate.childAdded(%s)" % (self.getXPath(), self.document.getXPath(child)))
        if self.state == State.idle:
            # New child is in idle and can stay so
            child.delegate.assertState('parent.childAdded()', State.idle)
        elif self.state == State.initing:
            self.logger.debug("%s: call to ParDelegate.childAdded(%s): self.state==initing, init child" % (self.getXPath(), self.document.getXPath(child)))
            self.document.schedule(child.delegate.initTimelineElement)
        elif self.state == State.inited:
            # xxxjack not sure this is safe. Will see.
            self.logger.warning("%s: childAdded() while state=inited, reverting to initing." % self.getXPath())
            self.logger.debug("%s: call to ParDelegate.childAdded(%s): self.state==inited, revert to initing, init child" % (self.getXPath(), self.document.getXPath(child)))
            self.setState(State.initing)
            self.document.schedule(child.delegate.initTimelineElement)
        elif self.state == State.starting:
            self.logger.debug("%s: call to ParDelegate.childAdded(%s): self.state==starting, init+start child" % (self.getXPath(), self.document.getXPath(child)))
            self.document.schedule(child.delegate.initTimelineElement)
            self.childrenToAutoStart.append(child)
        elif self.state == State.started:
            if self.emittedStopForChildren:
                # We are started, but already cleaning up. Sorry, but the new element is too late
                self.logger.debug("%s: call to ParDelegate.childAdded(%s): self.state==starting but already stopping." % (self.getXPath(), self.document.getXPath(child)))
                pass
            else:
                self.logger.debug("%s: call to ParDelegate.childAdded(%s): self.state==started, init+start child" % (self.getXPath(), self.document.getXPath(child)))
                tooLate = self.startTime - self.clock.now() # This is a negative number
                child.delegate.setMediaClockSeek(tooLate)
                self.logger.debug("%s: child seek %s seconds (tooLate %s, we started %s now %s)" % (self.getXPath(), child.delegate.mediaClockSeek, tooLate, self.startTime, self.clock.now()))
                self.document.schedule(child.delegate.initTimelineElement)
            self.childrenToAutoStart.append(child)
        elif self.state == State.stopping:
            # Too late.
            self.logger.debug("%s: call to ParDelegate.childAdded(%s): self.state==stopping, too late." % (self.getXPath(), self.document.getXPath(child)))
            pass
        elif self.state == State.finished:
            # xxxjack not sure this is safe....
            self.logger.debug("%s: call to ParDelegate.childAdded(%s): self.state==finished, revert to started, init+start child." % (self.getXPath(), self.document.getXPath(child)))
            self.setState(State.started)
            self.emittedStopForChildren = False
            tooLate = self.startTime - self.clock.now() # This is a negative number
            child.delegate.setMediaClockSeek(tooLate)
            self.logger.debug("%s: child seek %s seconds (tooLate %s, we started %s now %s)" % (self.getXPath(), child.delegate.mediaClockSeek, tooLate, self.startTime, self.clock.now()))
            self.document.schedule(child.delegate.initTimelineElement)
            self.childrenToAutoStart.append(child)
        else:
            assert 0

    def notifyNegativeClockChange(self, newTime):
        if self.timingModel == "deterministic" and self.state != State.idle:
            for ch in self.elt:
                ch.delegate.notifyNegativeClockChange(newTime)


class SeqDelegate(TimeElementDelegate):
    """<tl:seq> element. Runs its children in succession."""

    def _checkSkipChildren(self, nextChild):
        if self.timingModel == "deterministic":
            childEndTime = self.startTime
            useNext = False
            for ch in self.elt:
                if useNext:
                    nextChild = ch
                    useNext = False
                prevStopTime = childEndTime
                childEndTime = ch.delegate.predictStopTime("deterministic", childEndTime)
                if childEndTime is None:
                    return nextChild, None, False
                if ch == nextChild:
                    # found the current child, check if it should be skipped entirely
                    if self.clock.now() >= childEndTime:
                        # skip it
                        if nextChild.delegate.state in State.STOP_NEEDED:
                            # skipped child needs to be stopped
                            self._currentChild = nextChild
                            self.document.schedule(nextChild.delegate.stopTimelineElement)
                            return None, None, True
                        else:
                            # try the next one
                            useNext = True
                    else:
                        return nextChild, prevStopTime, False
            # component not found
            return None, None, False
        else:
            return nextChild, None, False

    def reportChildState(self, child, childState):
        self._advanceState()

    def _preInitNextChild(self):
        nextChild = self._nextChild()
        if nextChild is not None and nextChild.delegate.state == State.idle:
            if self.timingModel != "deterministic" and self.mediaClockSeek != None:
                self.logger.debug("SeqDelegate(%s): forward mediaClockSeek %s to next child" % (self.document.getXPath(self.elt), self.mediaClockSeek), extra=self.getLogExtra())
                self.mediaClockSeek = nextChild.delegate.setMediaClockSeek(self.mediaClockSeek)
                self.logger.debug("SeqDelegate(%s): leftover mediaClockSeek %s from next child" % (self.document.getXPath(self.elt), self.mediaClockSeek), extra=self.getLogExtra())
                if self.mediaClockSeek >= 0:
                    self.mediaClockSeek = None
            self.document.schedule(nextChild.delegate.initTimelineElementIfNotInited)

    def _advanceState(self):
        assert len(self.elt)
        if self.state == State.idle:
            # We're idle. We don't care about children state changes.
            return
        if self.state == State.initing:
            # Initializing. We're initialized when our first (useful) child is.
            nextChild, prevStopTime, tryAgainLater = self._checkSkipChildren(self.elt[0])
            if tryAgainLater: return
            if nextChild is not None:
                if nextChild.delegate.state in {State.idle}:
                    self.document.schedule(nextChild.delegate.initTimelineElementIfNotInited)
                    return
                elif nextChild.delegate.state not in {State.inited}:
                    return
            self.setState(State.inited)
            return
        if self.state == State.starting:
            # We're starting. Once our first (useful) child has started (or started and stopped) so have we.
            nextChild, prevStopTime, tryAgainLater = self._checkSkipChildren(self.elt[0])
            if tryAgainLater: return
            if nextChild is None:
                self.setState(State.finished)
                return
            if nextChild.delegate.state in {State.idle}:
                self.document.schedule(nextChild.delegate.initTimelineElementIfNotInited)
                return
            elif nextChild.delegate.state in {State.inited}:
                self._currentChild = nextChild
                if self.timingModel == "deterministic":
                    if prevStopTime is not None:
                        nextChild.delegate.startTime = prevStopTime
                        nextChild.delegate.startTimeFixed = True
                self.document.schedule(nextChild.delegate.startTimelineElement)
                self._preInitNextChild()
                return
            elif nextChild.delegate.state not in {State.started, State.finished}:
                return
            else:
                self._currentChild = nextChild
                self.setState(State.started)
            # Note that we fall through into the next "if" straight away.
        if self.state == State.started:
            if self.reselectChild:
                # Wait for all children to be idle
                for ch in self.elt:
                    if ch.delegate.state != State.idle:
                        return
                # Pick a new child
                nextChild, prevStopTime, tryAgainLater = self._checkSkipChildren(self.elt[0])
                if tryAgainLater: return
                self.reselectChild = False
                if nextChild is not None:
                    self.logger.debug("SeqDelegate(%s): selecting child %s after negative clock step change" % (self.document.getXPath(self.elt), self.document.getXPath(nextChild)), extra=self.getLogExtra())
            elif self._currentChild is None:
                # No currently running child, pick a new one
                # This is generally the one inited previously by the reselectChild block
                nextChild, prevStopTime, tryAgainLater = self._checkSkipChildren(self.elt[0])
                if tryAgainLater: return
            else:
                # Started. Check whether our current child is still active.
                if self._currentChild.delegate.state in State.NOT_DONE:
                    return
                # Our current child is no longer active, advance to the next (if any)
                prevChild = self._currentChild
                if prevChild is not None and prevChild.delegate.state in State.STOP_NEEDED:
                    self.document.schedule(prevChild.delegate.stopTimelineElement)
                nextChild, prevStopTime, tryAgainLater = self._checkSkipChildren(self._nextChild())
                if tryAgainLater: return

            if nextChild is None:
                 #That was the last child. We are done.
                self.setState(State.finished)
                # We cannot assert descendent states here. One of our chidren could be a finished par, and it could have
                # scheduled stop calls for its descendents, but that doesn't mean those have been run yet.
                #
                #self.assertDescendentState('reportChildState[self.state==finished]', State.finished, State.stopping, State.idle)
            elif nextChild.delegate.state in {State.inited}:
                # Next child is ready to run. Start it, and initialize the one after that, then stop old one.
                self._currentChild = nextChild
                if self.timingModel == "deterministic":
                    if prevStopTime is not None:
                        self._currentChild.delegate.startTime = prevStopTime
                        self._currentChild.delegate.startTimeFixed = True
                self.document.schedule(self._currentChild.delegate.startTimelineElement)
                self._preInitNextChild()
            elif nextChild.delegate.state == State.idle:
                # Normally the init for the next child has already been issued, but
                # if the current child had a DummyDelegate it can happen that it hasn't.
                # Issue it now.
                self.document.schedule(nextChild.delegate.initTimelineElementIfNotInited)
            else:
                # Next child not yet ready to run.
                nextChild.delegate.assertState('seq-parent-reportChildState()', State.initing)
                pass # Wait for inited callback from nextChild
        if self.state == State.stopping:
            for ch in self.elt:
                if ch.delegate.state != State.idle:
                    return
            self.setState(State.idle)
            
    def initTimelineElement(self):
        self.assertState('SeqDelegate.initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        self.reselectChild = False
        self.setState(State.initing)
        if not len(self.elt):
            self.setState(State.inited)
            return
        if self.timingModel != "deterministic" and self.mediaClockSeek != None:
            self.logger.debug("SeqDelegate(%s): forward mediaClockSeek %s to first child" % (self.document.getXPath(self.elt), self.mediaClockSeek), extra=self.getLogExtra())
            # xxxjack the following code is incorrect. It will only really work for initial seq children
            # that do nothing.
            self.mediaClockSeek = self.elt[0].delegate.setMediaClockSeek(self.mediaClockSeek)
            self.logger.debug("SeqDelegate(%s): leftover mediaClockSeek %s from first child" % (self.document.getXPath(self.elt), self.mediaClockSeek), extra=self.getLogExtra())
            if self.mediaClockSeek >= 0:
                self.mediaClockSeek = None
        self._advanceState()

    def startTimelineElement(self):
        self.assertState('SeqDelegate.startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        if not len(self.elt):
            self.setState(State.finished)
            return
        self._advanceState()

    def stopTimelineElement(self):
        self.setState(State.stopping)
        waitNeeded = False
        for ch in self.elt:
            if ch.delegate.state in State.STOP_NEEDED:
                self.document.schedule(ch.delegate.stopTimelineElement)
                waitNeeded = True
            if ch.delegate.state == State.stopping:
                waitNeeded = True
        if not waitNeeded:
            self.setState(State.idle)

    def _nextChild(self):
        foundCurrent = False
        for ch in self.elt:
            if foundCurrent: return ch
            foundCurrent = (ch == self._currentChild)
        return None

    def predictStopTime(self, mode, startTimeOverride = None):
        if len(self.elt) == 0:
            return TimeElementDelegate.predictStopTime(self, mode, startTimeOverride)

        if mode == "deterministic":
            if self.timingModel != "deterministic": return None
            if startTimeOverride is not None:
                endTime = startTimeOverride
            elif self.startTimeFixed:
                endTime = self.startTime
            else:
                return None
            for ch in self.elt:
                endTime = ch.delegate.predictStopTime(mode, endTime)
                if endTime is None:
                    return None
            return endTime
        elif mode == "complete":
            return self.elt[-1].delegate.predictStopTime(mode)
        else:
            return None

    def _reselectChild(self, newTime):
        self.reselectChild = True
        self._currentChild = None
        self.logger.debug("SeqDelegate(%s): reselecting child due to negative clock step change: %d" % (self.document.getXPath(self.elt), newTime), extra=self.getLogExtra())
        if self.state == State.finished:
            self.setState(State.started)
        self._advanceState()

    def notifyNegativeClockChange(self, newTime):
        if self.timingModel == "deterministic" and self.state != State.idle:
            endTime = self.startTime
            elements = iter(self.elt)
            for ch in elements:
                if endTime is None:
                    return
                startTime = endTime
                endTime = ch.delegate.predictStopTime("deterministic", startTime)
                if ch.delegate.state != State.idle:
                    # first non-idle child
                    if newTime < startTime:
                        # We have seeked to before the start point of the first non-idle child.
                        # Stop it and select a new child.
                        # Stop all subsequent children.
                        if ch.delegate.state in State.STOP_NEEDED:
                            self.document.schedule(ch.delegate.stopTimelineElement)
                        for afterch in elements:
                            if afterch.delegate.state in State.STOP_NEEDED:
                                self.document.schedule(afterch.delegate.stopTimelineElement)
                        self._reselectChild(newTime)
                    elif endTime is None or newTime < endTime:
                        # seek is within this child, forward it the message if it's not idle
                        if ch.delegate.state != State.idle:
                            ch.delegate.notifyNegativeClockChange(newTime)
                    return
            # All children are idle
            self._reselectChild(newTime)

class RepeatDelegate(SingleChildDelegate):
    """<tl:repeat> element. Runs it child if the condition is true."""
    
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("count")
        }

    def reportChildState(self, child, childState):
        #
        # We only need to handle special cases while we are started.
        #
        if self.state != State.started:
            SingleChildDelegate.reportChildState(self, child, childState)
            return
        if childState == State.initing:
            return
        if childState == State.inited:
            # Another run of the child. Start it.
            self.document.schedule(self.elt[0].delegate.startTimelineElement)
            return
        if childState == State.starting:
            return
        if childState == State.started:
            return
        if childState == State.finished:
            # Child has finished its normal run. Stop it.
            self.document.schedule(child.delegate.stopTimelineElement)
            return
        if childState == State.stopping:
            return
        if childState == State.idle:
            # Child stop has completed.
            # See whether we need another run:
            remainingCount = self.elt.get(NS_TIMELINE("count"), "indefinite")
            if remainingCount != "indefinite":
                remainingCount = str(int(remainingCount)-1)
                self.elt.set(NS_TIMELINE("count"), remainingCount)
            if remainingCount == "indefinite" or int(remainingCount) > 0:
                # More repeats to do. Restart child.
                self.document.schedule(self.elt[0].delegate.initTimelineElement)
            else:
                self.setState(State.finished)
            return
        assert 0
                    
    def startTimelineElement(self):
        remainingCount = self.elt.get(NS_TIMELINE("count"), "indefinite")
        if remainingCount == "indefinite" or int(remainingCount) > 0:
            SingleChildDelegate.startTimelineElement(self)
        else:
            self.setState(State.finished)

    def predictStopTime(self, mode, startTimeOverride = None):
        return None
            
class RefDelegate(TimeElementDelegate):
    """<tl:ref> element. Handles actual media playback. Usually subclassed to actually do something."""
    
    EXACT_CHILD_COUNT=0
    IS_REF_TYPE=True
    
    def initTimelineElement(self):
        TimeElementDelegate.initTimelineElement(self)

    def startTimelineElement(self):
        self.assertState('RefDelegate.startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.setState(State.started)
        self.document.report(logging.INFO, '>', 'START', self.document.getXPath(self.elt), self._getParameters(), self._getDmappcParameters(), extra=self.getLogExtra())
        # XXXJACK test code. Assume text/image nodes finish straight away, masterVideo takes forever and others take 42 seconds
        cl = self.elt.get(NS_2IMMERSE("class"), "unknown")
        if cl == "mastervideo":
            return
        # While checking document we use the tlcheck:dur attribute for the duration, or 42.345 as default
        if cl == "text" or cl == "image": 
            dft_dur = 0
        else:
            dft_dur = 42.345
        dur = float(self.elt.get(NS_TIMELINE_CHECK("dur"), dft_dur))
        if not self.startTimeFixed and self.mediaClockSeek != None:
            dur += self.mediaClockSeek
        self.clock.scheduleAt(self.startTime + dur, self._done)
               
    def _done(self):
        if self.state == State.started:
            # Do nothing if we aren't in the started state anymore (probably because we've been stopped)
            self.document.report(logging.INFO, '<', 'finished', self.document.getXPath(self.elt), extra=self.getLogExtra())
            self.setState(State.finished)

    def stopTimelineElement(self):
        self.document.report(logging.INFO, '>', 'STOP', self.document.getXPath(self.elt), extra=self.getLogExtra())
        TimeElementDelegate.stopTimelineElement(self)
        
    def _getParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in NS_2IMMERSE:
                rv[NS_2IMMERSE.localTag(k)] = self.elt.attrib[k]
        return rv
        
    def _getDmappcParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in NS_2IMMERSE_COMPONENT:
                rv[NS_2IMMERSE_COMPONENT.localTag(k)] = self.elt.attrib[k]
        return rv

    def predictStopTime(self, mode, startTimeOverride = None):
        return None

class RefDelegate2Immerse(RefDelegate):
    """2-Immerse specific RefDelegate that checks the attributes"""
    allowedConstraints = None # May be set by main program to enable checking that all refs have a layout
    
    def checkAttributes(self):
        RefDelegate.checkAttributes(self)
        attributeChecker.checkAttributes(self)
        if self.allowedConstraints != None:
            constraintId = self.elt.get(document.NS_2IMMERSE("constraintId"))
            if not constraintId:
                constraintId = self.getId()
            if constraintId and constraintId not in self.allowedConstraints:
                print("* Warning: element", self.getXPath(), 'has tim:constraintId (or xml:id)="'+constraintId+'" but this does not exist in the layout document', file=sys.stderr)
        
class UpdateDelegate2Immerse(TimelineDelegate):
    """2-Immerse specific delegate for tim:update that checks the attributes and reports actions"""
    
    def __init__(self, elt, document, clock):
        TimelineDelegate.__init__(self, elt, document, clock)
        
    def checkAttributes(self):
        TimelineDelegate.checkAttributes(self)
        #attributeChecker.checkAttributes(self)
        uniqId = self.elt.get(NS_2IMMERSE("target"))
        if not uniqId:
            if not self.elt.get(NS_2IMMERSE("targetXPath")):
                print("* element", self.getXPath(), 'misses required tim:target attribute', file=sys.stderr)
        if uniqId and not uniqId in self.document.idMap:
            print("* Warning: element", self.getXPath(), 'has tim:target="'+uniqId+'" but this xml:id does not exist in the document', file=sys.stderr)
                
    def startTimelineElement(self):
        uniqId = self.elt.get(NS_2IMMERSE("target"))
        self.document.report(logging.INFO, '>', 'UPDATE', self.document.getXPath(self.elt), uniqId, self._getDmappcParameters(), extra=self.getLogExtra())
        TimelineDelegate.startTimelineElement(self)

    def _getDmappcParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in NS_2IMMERSE_COMPONENT:
                rv[NS_2IMMERSE_COMPONENT.localTag(k)] = self.elt.attrib[k]
        return rv    
        
class ConditionalDelegate(SingleChildDelegate):
    """<tl:condition> element. Runs it child if the condition is true."""
    
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("expr")
        }

    def startTimelineElement(self):
        self.assertState('ConditionalDelegate.startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.document.report(logging.DEBUG, 'COND', True, self.document.getXPath(self.elt), extra=self.getLogExtra())
        self.document.schedule(self.elt[0].delegate.startTimelineElement)
        
class SleepDelegate(TimeElementDelegate):
    """<tl:sleep> element. Waits for a specified duration (on the elements clock)"""
    
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("dur")
        }
    DEFAULT_PRIO="high"
    
    def startTimelineElement(self):
        self.assertState('SleepDelegate.startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.setState(State.started)
        self.document.report(logging.DEBUG, 'SLEEP0', self.elt.get(NS_TIMELINE("dur")), self.document.getXPath(self.elt), extra=self.getLogExtra())
        dur = self.parseDuration(self.elt.get(NS_TIMELINE("dur")))
        assert self.startTime != None
        if not self.startTimeFixed and self.mediaClockSeek != None:
            self.document.logger.debug("SleepDelegate(%s): adjusted mediaClockSeek %s" % (self.document.getXPath(self.elt), self.mediaClockSeek), extra=self.getLogExtra())
            dur += self.mediaClockSeek
            self.mediaClockSeek = None
        self.sleepEndTime = self.startTime + dur
        if self.sleepEndTime != float('inf'):
            self.clock.scheduleAt(self.sleepEndTime, self._done, self.sleepEndTime)
        
    def _done(self, expectedSleepEndTime):
        if self.sleepEndTime != expectedSleepEndTime:
            # Sleep end time was changed after _done was scheduled.
            # This call to _done is therefore invalid and no action should be taken.
            return
        if self.state != State.started:
            self.document.logger.debug("SleepDelegate(%s): spurious _done callback" % self.document.getXPath(self.elt), extra=self.getLogExtra())
            return
        if self.clock.now() < self.sleepEndTime:
            self.document.logger.warning("SleepDelegate(%s): early _done callback (%.3f expected %.3f), ending anyway" % (self.document.getXPath(self.elt), self.clock.now(), self.sleepEndTime), extra=self.getLogExtra())
        self.document.report(logging.DEBUG, 'SLEEP1', self.elt.get(NS_TIMELINE("dur")), self.document.getXPath(self.elt), extra=self.getLogExtra())
        self.setState(State.finished)
    
    def parseDuration(self, dur):
        try:
            return float(dur)
        except ValueError:
            pass
        tval = time.strptime(dur, "%H:%M:%S")
        return tval.tm_sec + 60*(tval.tm_min+60*tval.tm_hour)
        
    def attributesChanged(self, attrsChanged):
        for k in attrsChanged:
            if k == NS_TIMELINE("dur"):
                dur = self.parseDuration(self.elt.get(NS_TIMELINE("dur")))
                if self.startTime == None or self.state != State.started:
                    self.document.logger.debug("SleepDelegate(%s): dur %.3f ignored, self.state=%s self.startTime=%s" % (self.document.getXPath(self.elt), dur, self.state, self.startTime), extra=self.getLogExtra())
                    continue
                newSleepEndTime = self.startTime + dur
                self.document.logger.debug("SleepDelegate(%s): sleepEndTime changed from %.3f to %.3f" % (self.document.getXPath(self.elt), self.sleepEndTime, newSleepEndTime), extra=self.getLogExtra())
                self.sleepEndTime = newSleepEndTime
                if self.sleepEndTime != float('inf'):
                    self.clock.scheduleAt(self.sleepEndTime, self._done, self.sleepEndTime)
            else:
                self.document.logger.warning("SleepDelegate(%s): unexpected attribute changed: %s" % (self.document.getXPath(self.elt), k), extra=self.getLogExtra())
        
    def setMediaClockSeek(self, mediaClockSeek):
        self.mediaClockSeek = mediaClockSeek
        dur = self.parseDuration(self.elt.get(NS_TIMELINE("dur")))
        dur += mediaClockSeek
        if dur < 0:
            return dur
        return 0

    def predictStopTime(self, mode, startTimeOverride = None):
        startTime = TimeElementDelegate.predictStopTime(self, mode, startTimeOverride)
        if startTime is not None:
            return startTime + self.parseDuration(self.elt.get(NS_TIMELINE("dur")))
        else:
            return None

class WaitDelegate(TimeElementDelegate):
    """<tl:wait> element. Waits for an incoming event."""
    
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("event")
        }
    DEFAULT_PRIO="high"
            
    def startTimelineElement(self):
        self.assertState('WaitDelegate.startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        eventId = self.elt.get(NS_TIMELINE("event"))
        self.document.report(logging.DEBUG, 'WAIT0', eventId, self.document.getXPath(self.elt), extra=self.getLogExtra())
        self.setState(State.started)
        self.document.registerEvent(eventId, self._done)
        
    def _done(self):
        if self.state != State.started:
            return
        eventId = self.elt.get(NS_TIMELINE("event"))
        self.document.report(logging.DEBUG, 'WAIT1', eventId, self.document.getXPath(self.elt), extra=self.getLogExtra())
        self.setState(State.finished)
    
    def stopTimelineElement(self):
    	eventId = self.elt.get(NS_TIMELINE("event"))
    	self.document.unregisterEvent(eventId, self._done)
        TimelineDelegate.stopTimelineElement(self)

    def predictStopTime(self, mode, startTimeOverride = None):
        if self.elt.get(NS_TIMELINE("event")) is None:
            # this wait will never end as there is no event ID, so return infinity
            return float("inf")
        else:
            return None

DELEGATE_CLASSES = {
    NS_TIMELINE("document") : DocumentDelegate,
    NS_TIMELINE("par") : ParDelegate,
    NS_TIMELINE("seq") : SeqDelegate,
    NS_TIMELINE("repeat") : RepeatDelegate,
    NS_TIMELINE("ref") : RefDelegate,
    NS_TIMELINE("conditional") : ConditionalDelegate,
    NS_TIMELINE("sleep") : SleepDelegate,
    NS_TIMELINE("wait") : WaitDelegate,
    }
   
DELEGATE_CLASSES_FASTFORWARD = {
    NS_TIMELINE("document") : DocumentDelegate,
    NS_TIMELINE("par") : ParDelegate,
    NS_TIMELINE("seq") : SeqDelegate,
    NS_TIMELINE("repeat") : RepeatDelegate,
    NS_TIMELINE("ref") : FFWDTimeElementDelegate,
    NS_2IMMERSE("update") : FFWDSideEffectTimeElementDelegate,
    NS_TIMELINE("conditional") : ConditionalDelegate, # xxxjack should return True depending on tree position?
    NS_TIMELINE("sleep") : SleepDelegate,
    NS_TIMELINE("wait") : DummyDelegate, # xxxjack This makes all events appear to happen instantaneous...
    }
    
#
# Adapters
#

class DelegateAdapter(object):
    """Baseclass for delegate adapters, transparent."""
    
    def __init__(self, delegate):
        self._adapter_delegate = delegate
        
    def __getattr__(self, attrname):
        return getattr(self._adapter_delegate, attrname)

class SeekToElementAdapter(DelegateAdapter):
    def __init__(self, delegate):
        DelegateAdapter.__init__(self, delegate)
        self.seekPositionReached = False
        
    def startTimelineElement(self):
        self._adapter_delegate.startTimelineElement()
        self.seekPositionReached = True
        
class DocumentState(object):
    def __init__(self, document):
        self.document = document
        document.report(logging.DEBUG, 'DOCSTATE', self.__class__.__name__)
        
    def nudgeClock(self):
    	return False
    	
    def stateFinished(self):
        return True
        
    def documentFinished(self):
        return False
        
    def nextState(self):
        return DocumentStateInit(self.document)
        
class DocumentStateInit(DocumentState):
    def __init__(self, document):
        DocumentState.__init__(self, document)
        self.hasSeekToElement = document.startElement is not None
        self.hasSeekToTime = document.startTime > 0
        
        if self.hasSeekToElement:
            initialDelegateClasses = DELEGATE_CLASSES_FASTFORWARD
        elif self.hasSeekToTime:
            initialDelegateClasses = DELEGATE_CLASSES_FASTFORWARD
        else:
            initialDelegateClasses = None # Use normal delegates, possibly overridden
            
        #
        # Populate the initial delegates
        #
        document._addDelegates(initialDelegateClasses)
        
        if self.hasSeekToElement:
            assert document.startElement.delegate
            # Monitor the target element.
            document.startElement.delegate = SeekToElementAdapter(document.startElement.delegate)
            document.report(logging.INFO, 'FFWD', 'goto', document.startElement.delegate.getXPath())
        elif self.hasSeekToTime:
            # Monitoring is done by checking the clock
            document.report(logging.INFO, 'FFWD', 'goto', '#t=%f' % document.startTime, '(underlyingClock=%f)' % self.document.clock.underlyingClock.now())
        else:
            pass

        #
        # Execute all init calls
        #
        assert document.root is not None
        assert document.root.delegate
        document.root.delegate.assertState("runDocumentInit()", State.idle)
        document.report(logging.INFO, 'RUN', 'init')
        document.schedule(document.root.delegate.initTimelineElement)
        
    def stateFinished(self):
        return self.document.root.delegate.state == State.inited
        
    def nextState(self):
        if self.hasSeekToElement:
            return DocumentStateSeekElementStart(self.document, self.document.startElement)
        elif self.hasSeekToTime:
            return DocumentStateSeekTimeStart(self.document, self.document.startTime)
        else:
            return DocumentStateStart(self.document)

class DocumentStateStart(DocumentState):
    def __init__(self, document):
        DocumentState.__init__(self, document)
        assert document.root is not None
        assert document.root.delegate
        document.root.delegate.assertState("scheduleDocumentStart()", State.inited)
        document.report(logging.INFO, 'RUN', 'start')
        document.schedule(document.root.delegate.startTimelineElement)
        
    def stateFinished(self):
        return True
        
    def nextState(self):
        return DocumentStateRunDocument(self.document)
              
class DocumentStateSeekElementStart(DocumentStateStart):
    def __init__(self, document, startElement):
        DocumentStateStart.__init__(self, document)
        self.startElement = startElement
        if document.clock.nextEventTime(None) != None:
        	self.document.logger.warning("Events pending while starting seek. Could lead to problems later.")
        document.clock.replaceUnderlyingClock(clocks.FastClock())
        document.clock.start()
        
    def nudgeClock(self):
    	return self.document.clock.sleepUntilNextEvent()
    	
    def stateFinished(self):
        if self.document.root.delegate.state == State.finished:
            self.document.report(logging.ERROR, 'FFWD', 'end-of-document', '#t=%f' % self.document.clock.now(), '(underlyingClock=%f)' % self.document.clock.underlyingClock.now())
            return True
        return self.startElement.delegate.seekPositionReached
        
    def nextState(self):
        if self.document.root.delegate.state == State.finished:
            return DocumentStateStopDocument(self.document)
        self.document.report(logging.INFO, 'FFWD', 'reached', self.startElement.delegate.getXPath())
        return DocumentStateSeekFinish(self.document)

class DocumentStateSeekTimeStart(DocumentStateStart):
    def __init__(self, document, startTime):
        DocumentStateStart.__init__(self, document)
        self.document = document
        self.startTime = startTime
        if document.clock.nextEventTime(None) != None:
        	self.document.logger.warning("Events pending while starting seek. Could lead to problems later.")
        document.clock.replaceUnderlyingClock(clocks.FastClock())
        document.clock.start()
        
    def nudgeClock(self):
    	return self.document.clock.sleepUntilNextEvent()
    	
    def stateFinished(self):
        if self.document.root.delegate.state == State.finished:
            self.document.report(logging.ERROR, 'FFWD', 'end-of-document', '#t=%f' % self.document.clock.now())
            return True
        deltaT = self.document.clock.nextEventTime(None)
        if deltaT is None: 
            return False 
        nextEventTime = self.document.clock.now() + deltaT
        return nextEventTime >= self.startTime
            

    def nextState(self):
        if self.document.root.delegate.state == State.finished:
            return DocumentStateStopDocument(self.document)
        self.document.report(logging.INFO, 'FFWD', 'reached', '#t=%f' % self.document.clock.now(), '(underlyingClock=%f)' % self.document.clock.underlyingClock.now())
        if self.document.clock.now() != self.startTime:
            self.document.clock.set(self.startTime)            
            self.document.report(logging.INFO, 'FFWD', 'nudge', '#t=%f' % self.document.clock.now(), '(underlyingClock=%f)' % self.document.clock.underlyingClock.now())
        return DocumentStateSeekFinish(self.document)

class DocumentStateSeekFinish(DocumentState):
    def __init__(self, document):
        DocumentState.__init__(self, document)
        #
        # Put the normal delegates in place
        #
        document.replaceDelegates(None)
        #
        # Bug fix: any par element that is started is moved back to starting
        # xxxjack this is a hack, to forestall pars ending early because all the
        # children are idle.
        #
        for elt in document.tree.iter():
            if elt.delegate.__class__ == ParDelegate and elt.delegate.state == State.started:
                elt.delegate.state = State.starting
                #elt.delegate.startTime = None
        #
        # Now do the set-position on the clock of the current master timing element.
        #
        adjustment = self.document.clock.restoreUnderlyingClock(False)
        for elt in self.document.tree.iter():
            elt.delegate.updateMediaSeekForDocumentSeek(adjustment)
        self.document.report(logging.INFO, 'FFWD', 'reposition', 'delta-t=%f' % adjustment, '(underlyingClock=%f)' % self.document.clock.underlyingClock.now())
        #
        # Now re-execute all external inits and destroys.
        #
        for elt in document.tree.iter():
            elt.delegate.stepMoveStateToConform(startAllowed=False)

    def stateFinished(self):
        for elt in self.document.tree.iter():
            if not elt.delegate.readyToStartMoveStateToConform():
                return False
        return True
        
    def nextState(self):
        #
        # Now use the real clock again
        #
        if False and self.document.clock.nextEventTime(None) != None:
            # xxxjack code temporarily disabled. Some of the events we have to flush
            # (specifically _done events for real media items), so we have to keep
            # (done events for sleeps). Have to work out whether to restart the
            # sleeps and put in the flushEvents or sort through the events
            # to see which ones are needed.
        	count = self.document.clock.flushEvents()
        	self.document.logger.info("Flushed %d pending events while ending seek." % count)
#        self.document.dump(open('seekend1.xml', 'w')) # xxxjack
        #
        # Now (re)issue the start calls
        #
        for elt in self.document.tree.iter():
            elt.delegate.stepMoveStateToConform(startAllowed=True)
        self.document.report(logging.INFO, 'FFWD', 'done', '(underlyingClock=%f)' % self.document.clock.underlyingClock.now())
#        self.document.dump(open('seekend2.xml', 'w')) #xxxjack
        return DocumentStateRunDocument(self.document)
        
class DocumentStateRunDocument(DocumentState):
    def __init__(self, document):
        DocumentState.__init__(self, document)
        assert document.root is not None
        assert document.root.delegate
        document.root.delegate.assertState("runDocumentBody()", State.inited, State.starting, State.started)
        document.clock.start()
        
    def stateFinished(self):
        return self.document.root.delegate.state == State.finished
        
    def nextState(self):
        return DocumentStateStopDocument(self.document)
        
class DocumentStateStopDocument(DocumentState):
    def __init__(self, document):
        DocumentState.__init__(self, document)
        document.report(logging.INFO, 'RUN', 'stop')
        document.root.delegate.assertDescendentState("run()", State.finished, State.stopping, State.idle)
#        document.terminating = True
        document.root.delegate.stopTimelineElement()
        
    def stateFinished(self):
        return self.document.root.delegate.state == State.idle
        
    def nextState(self):
        self.document.root.delegate.assertDescendentState("run()", State.idle)
        self.document.report(logging.INFO, 'RUN', 'done')
        return None

class DocumentModificationMixin(object):

    def __init__(self):
        self.stateUpdateCallback = None
        
    def setStateUpdateCallback(self, stateUpdateCallback):
        self.stateUpdateCallback = stateUpdateCallback
        
    def modifyDocument(self, generation, commands):
        """Modify the running document from the given command list"""
        # First check generation
        myGeneration = self.root.get(NS_AUTH("generation"), "0")
        if int(generation) != int(myGeneration)+1:
            self.logger.warning("modifyDocument: current generation=%s new generation=%s" % (myGeneration, generation))
        self.root.attrib[NS_AUTH("generation")] = str(generation)
        
        updateCallbacks = []
        for command in commands:
            cmd = command['verb']
            del command['verb']
            if cmd == 'add':
                path = command['path']
                where = command['where']
                dataXml = command['data']
                newElement = ET.fromstring(dataXml)
                ucb = self._paste(path, where, newElement)
                if ucb:
                    updateCallbacks.append(ucb)
            elif cmd == 'delete':
                path = command['path']
                self.xml().cut(path=path)
            elif cmd == 'change':
                path = command['path']
                attrsJson = command['attrs']
                attrs = json.loads(attrsJson)
                ucb = self._modifyAttributes(path, attrs)
                if ucb:
                    updateCallbacks.append(ucb)
            else:
                assert 0, 'Unknown forward() verb: %s' % cmd
        for cb, arg in updateCallbacks:
            cb(arg)
            
    def _paste(self, path, where, newElement):
        anchorElement = self.getElement(path)
        assert anchorElement != None
        parentElement = None
        #
        # Put the new element in the tree, in the right location
        #
        if where == 'begin':
            parentElement = anchorElement
            anchorElement.insert(0, newElement)
        elif where == 'end':
            parentElement = anchorElement
            anchorElement.append(newElement)
        elif where == 'before':
            parentElement = self.getParent(anchorElement)
            assert parentElement
            pos = list(parentElement).index(anchorElement)
            parentElement.insert(pos, newElement)
        elif where == 'after':
            parentElement = self.getParent(anchorElement)
            assert parentElement != None
            pos = list(parentElement).index(anchorElement)
            parentElement.insert(pos+1, newElement)
        #
        # Add the new elements to the parentMap.
        # 
        self.parentMap[newElement] = parentElement
        for p in newElement.iter():
            for c in p:
                self.parentMap[c] = p
            id = p.get(self.idAttribute)
            if id:
                self.idMap[id] = p

        #
        # Add the default delegates to the new elements
        #
        self._addDelegates(None, root=newElement)
        #
        # Make the new parent handle the rest
        #
        return (parentElement.delegate.childAdded, newElement)
        
    def _modifyAttributes(self, path, attrs):
        self.logger.debug("modifyAttributes(%s, %s)" % (path, repr(attrs)))
        element = self.getElement(path)
        assert element is not None
        #
        # Replace/delete attributes, and remember the keys
        #
        attrsChanged = set()
        for k, v in list(attrs.items()):
            if v == None:
                if k in element.attrib:
                    attrsChanged.add(k)
                    element.attrib.pop(k)
            else:
                if element.attrib.get(k) != v:
                    element.attrib[k] = v
                    attrsChanged.add(k)
        #
        # Make the element itself handle the rest of the implementation
        #
        return (element.delegate.attributesChanged, attrsChanged)

    def clockChanged(self):
        """Called by the timeline to inform us that our clock has changed"""
        self.forwardElementStateChangeToTriggerTool(None)
    
    def forwardElementStateChangeToTriggerTool(self, element):
        """An element state has changed and we should inform the trigger tool"""
        if not self.stateUpdateCallback:
            return
        if element == None:
            self.logger.debug("forwardElementStateChangeToTriggerTool: clock changed")
        else:
            self.logger.debug("forwardElementStateChangeToTriggerTool: %s changed state to %s" % (self.getXPath(element), element.delegate.state))
        documentState = self.collectStateForTriggerTool()
        self.stateUpdateCallback(documentState)
        
    def collectStateForTriggerTool(self):
        rv = {}
        interestingElements = self.tree.getroot().findall(".//*[@tt:wantstatus]", NAMESPACES)
        self.logger.debug("collectStateForTriggerTool: %d interesting elements" % len(interestingElements))
        for elt in interestingElements:
            id = elt.get(self.idAttribute)
            if not id:
                self.logger.warning("collectStateForTriggerTool: %s has no ID-attribute" % self.getXPath(elt))
                continue
            value = elt.delegate.getStateForTriggerTool()
            rv[id] = value
        return rv
            
class Document(DocumentModificationMixin):
    RECURSIVE = False
        
    def __init__(self, clock, extraLoggerArgs=None, idAttribute=None):
        DocumentModificationMixin.__init__(self)
        self.tree = None
        self.root = None
        self.documentElement = None # Nasty trick to work around elementtree XPath incompleteness
        self.startElement = None    # If set, this is the element at which playback should start
        self.startTime = 0          # If set, this is the time at which playback should start
        self.documentState = None   # State machine for progressing (and seeking) document
        self.url = None
        self.clock = clock
        self.parentMap = {}
        self.idAttribute = idAttribute
        self.idMap = {}
        self.toDo = []
        self.delegateClasses = {}
        self.delegateClasses.update(DELEGATE_CLASSES)
        self.terminating = False
        self.logger = logging.getLogger(__name__)
        self.defaultTimingModel = "floating"
        if extraLoggerArgs:
            self.logger = MyLoggerAdapter(self.logger, extraLoggerArgs)
        self.events = []
        self.tracefile = None
        
    def setExtraLoggerArgs(self, extraLoggerArgs):
            self.logger = MyLoggerAdapter(logging.getLogger(__name__), extraLoggerArgs)
    
    def setDelegateFactory(self, klass, tag=NS_TIMELINE("ref")):
        assert not self.root
        self.delegateClasses[tag] = klass
        
    def registerEvent(self, eventId, callback):
    	self.events.append((eventId, callback))
    	
    def unregisterEvent(self, eventId, callback):
    	try:
			self.events.remove((eventId, callback))
    	except ValueError:
    		pass
    		
    def triggerEvent(self, eventId):
    	anyDone = False
    	for eid, callback in self.events:
    		if eid == eventId:
    			callback()
    			anyDone = True
    	if not anyDone:
    		self.logger.warning("Event %s did not trigger anything" % eventId)
    			
    def loadDocument(self, url):
        assert not self.root
        self.url = url
        #
        # Open and load the document
        #
        fp = urllib.request.urlopen(url)
        self.tree = ET.parse(fp)
        #
        # Remember the root, and the parent of each node
        #
        self.root = self.tree.getroot()
        self.parentMap = {c:p for p in self.tree.iter() for c in p}
        #
        # Invent a document-element for easier xpath implementation
        #
        self.documentElement = ET.Element('')
        self.documentElement.append(self.tree.getroot())

        #
        # Create the mapping to find elements by ID (tim:dmappcid or xml:id, probably)
        #
        if self.idAttribute:
            self.idMap = {}
            for p in self.tree.iter():
                id = p.get(self.idAttribute)
                if COMPAT_V1:
                    # Temporary: check for fallback tim:dmappcid attribute
                    altId = p.get(NS_2IMMERSE("dmappcid"))
                    if id and altId:
                        raise TimelineParseError("Element %s had xml:id and tim:dmappcid" % self.getXPath(p))
                    elif not id:
                        id = altId
                if id:
                    if id in self.idMap:
                        raise TimelineParseError("Duplicate id %s in element %s" % (id, self.getXPath(p)))
                    self.idMap[id] = p 
        #
        # Check to see whether we have a #dmappcid or #t=time
        #
        up = urllib.parse.urlparse(url)
        if up.fragment and up.fragment[:2] == 't=':
            self.startTime = float(up.fragment[2:])
        elif up.fragment:
            # Not a Media Fragment time specifier, so it is a node ID
            if not up.fragment in self.idMap:
                self.logger.log(logging.ERROR, "Fragment #%s does not match any element" % up.fragment)
            else:
                self.startElement = self.idMap[up.fragment]

    def prepareDocument(self):
        """Prepare for running the document"""
        assert self.documentState is None
        self.documentState = DocumentStateInit(self)
        
    def runDocument(self):
        """Run the whole document."""
        assert self.documentState is not None
        while not self.isDocumentDone():
            self.runloop()
            assert self.documentState.stateFinished()
            self.advanceDocument()

    def isDocumentDone(self):
        """Return true if the document is not active"""
        return self.documentState is None
        
    def advanceDocument(self):
        """Advance the document state to the next state, if applicable"""
        while self.documentState and self.documentState.stateFinished():
            self.documentState = self.documentState.nextState()

    def getParent(self, elt):
        return self.parentMap.get(elt)
        
    def getXPath(self, elt, strict=False):
        assert self.root is not None
        # Our "own" tl: tags are non-namespaced
        if elt.tag in NS_TIMELINE:
            tagname = NS_TIMELINE.localTag(elt.tag)
        else:
            tagname = elt.tag
        parent = self.getParent(elt)
        if parent is None:
            return '/' + tagname
        index = 0
        for ch in parent:
            if ch is elt:
                break
            if ch.tag == elt.tag:
                index += 1
        rv = self.getXPath(parent) + '/'
        rv += tagname
        if strict or index:
            rv = rv + '[%d]' % (index+1)
        return rv

    def getElement(self, path):
        if path == '/':
            # Findall implements bare / paths incorrectly
            positions = []
        elif path[:1] == '/':
            positions = self.documentElement.findall('.'+path, NAMESPACES)
        else:
            positions = self.tree.getroot().findall(path, NAMESPACES)
        if not positions:
            assert False,  'No tree element matches XPath %s' % path
        if len(positions) > 1:
            assert False, 'Multiple tree elements match XPath %s' % path
        element = positions[0]
        return element
        
    def getElementById(self, id):
        return self.idMap.get(id)
        
    def dump(self, fp):
        if self.root is None:
            return
        for elt in self.tree.iter():
            elt.delegate.storeStateForSave()
        self.tree.write(fp)
        fp.write('\n')
        self.logger.info("created XML document dump")
        
    def dumps(self):
        if self.root is None:
            return ''
        for elt in self.tree.iter():
            elt.delegate.storeStateForSave()
        xmlstr = ET.tostring(self.root, encoding='utf8', method='xml')
        self.logger.info("created XML document dump")
        return xmlstr
    
    def _addDelegates(self, delegateClasses, root=None):
        if root == None: root = self.root
        assert root is not None
        for elt in root.iter():
            if not hasattr(elt, 'delegate'):
                klass = self._getDelegateFactory(elt.tag, delegateClasses)
                elt.delegate = klass(elt, self, self.clock)
                elt.delegate.checkAttributes()
                elt.delegate.checkChildren()
                
    def replaceDelegates(self, newDelegateClasses):
        assert self.root is not None
        for elt in self.tree.iter():
            assert hasattr(elt, 'delegate')
            # Remember old delegate
            oldDelegate = elt.delegate
            # Create new delegate
            klass = self._getDelegateFactory(elt.tag, newDelegateClasses)
            if oldDelegate.__class__ == klass:
                # Nothing to do for this element.
                continue
            elt.delegate = klass(elt, self, self.clock)
            elt.delegate.checkAttributes()
            elt.delegate.checkChildren()
            # Make new delegate go to same state as the old delegate was in
            elt.delegate.prepareMoveStateToConform(oldDelegate)
                
    def _getDelegateFactory(self, tag, delegateClasses=None):
        if delegateClasses is None:
            delegateClasses = self.delegateClasses       
        rv = delegateClasses.get(tag)
        if rv is None:
            if not tag in NS_TIMELINE:
                rv = DummyDelegate
            else:
                rv = ErrorDelegate
        return rv
            
    def getDocumentState(self):
        if self.root is None or not hasattr(self.root, 'delegate') or not self.root.delegate:
            return None
        return self.root.delegate.state
            
    def schedule(self, callback, *args, **kwargs):
        assert self.root is not None
        self.report(logging.DEBUG, 'EMIT', callback.__name__, self.getXPath(callback.__self__.elt), extra=callback.__self__.elt.delegate.getLogExtra())
        if self.RECURSIVE or self.terminating:
            callback(*args, **kwargs)
        else:
            self.toDo.append((callback, args, kwargs))
            
    def runloop(self):
        """Process events until end of current DocumentState, or deadlock."""
        assert self.documentState
        assert self.root is not None
        #
        # We run the loop until we have reached the expected condition, or until nothing can happen anymore
        #
        while not self.documentState.stateFinished() or self.toDo:
            self.runAvailable()
            #
            # If we are not at the expected end condition check whether the clock has any events forthcoming.
            #
            if not self.documentState.stateFinished():
                self.sleepUntilNextEvent()
        #
        # End condition reached, or deadlocked.
        #
        assert len(self.toDo) == 0, 'events not handled: %s' % repr(self.toDo)
        assert self.documentState.stateFinished(), 'Document root did not reach expected state'
        
    def sleepUntilNextEvent(self):
        """Relinquish control if and until a new event happens"""
        self.clock.sleepUntilNextEvent()
        
    def runAvailable(self):
        """Execute any events that can be run without relinquishing control"""
        assert self.root is not None
        assert self.documentState
        self.clock.handleEvents(self)
        while not self.documentState.stateFinished() or self.toDo:
            if self.toDo:
                # Handle an event, and repeat the loop
                callback, args, kwargs = self.toDo.pop(0)
                callback(*args, **kwargs)
            else:
                # No events to handle. See if the clock has any more imminent events.
                # If we are fastforwarding we nudge the clock so it is at the next event time.
                if self.documentState.nudgeClock():
                    # If the clock actually moved forward we return to the outer loop
                    return
                self.clock.handleEvents(self)
                if not self.toDo: break

	def nextEventTime(self, *args, **kwargs):
		return self.clock.nextEventTime(*args, **kwargs)
		
    def report(self, level, event, verb, *args, **kwargs):
        if args:
            args = reduce((lambda h, t: str(h) + ' ' + str(t)), args)
        else:
            args = ''
        self.logger.log(level, '%8.3f %-8s %-22s %s', self.clock.now(), event, verb, args, **kwargs)
        if self.tracefile and level >= logging.INFO:
            record = dict(timestamp=self.clock.now(), event=event, verb=verb, args=args)
            self.tracefile.write(repr(record)+'\n')
            
             
    def setTracefile(self, filename):
        if self.tracefile:
            self.tracefile.close()
        self.tracefile = None
        if filename:
            self.tracefile = open(filename, 'w')
        
def main():
    global DEBUG
    parser = argparse.ArgumentParser(description="Test runner for timeline documents")
    parser.add_argument("document", help="The XML timeline document to parse and run")
    parser.add_argument("--debug", action="store_true", help="Print detailed state machine progression output")
    parser.add_argument("--trace", action="store_true", help="Print less detailed externally visible progression output")
    parser.add_argument("--tracefile", metavar="FILE", help="Write less detailed externally visible progression output to a parseable FILE")
    parser.add_argument("--dump", action="store_true", help="Dump document to stdout on exceptions and succesful termination")
    parser.add_argument("--dumpfile", metavar="FILE", help="Dump document to FILE on exceptions and succesful termination")
    parser.add_argument("--realtime", action="store_true", help="Use realtime clock in stead of fast-forward clock")
    parser.add_argument("--recursive", action="store_true", help="Debugging: use recursion for callbacks, not queueing")
    parser.add_argument("--attributes", action="store_true", help="Check 2immerse tim: and tic: atributes")
    parser.add_argument("--layout", metavar="URL", help="Check against 2immerse layout document, make sure that all xml:id are specified in the layout")
    args = parser.parse_args()
    logger = logging.getLogger(__name__)
    DEBUG = args.debug
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    elif args.trace:
        logger.setLevel(logging.INFO)
    if args.recursive: Document.RECURSIVE=True
    run(args)
    
class MakeArgs(object):
    def __init__(self, **kwargs):
        args = dict(debug=False, trace=False, tracefile=False, dump=False, dumpfile=None, realtime=False, recursive=False, attributes=False, layout=None)
        args.update(kwargs)
        self.__dict__.update(args)
        
def run(args):
    if args.layout:
        import json
        args.attributes = True
        # Open the document, read the JSON
        layout = args.layout
        if not ':' in layout:
            layout = 'file:' + layout
        timelineDoc = urllib.request.urlopen(layout)
        timelineData = json.load(timelineDoc)
        # Get all componentIds mentioned in the constraints
        layoutComponentIds = list(map((lambda constraint: constraint['constraintId']), timelineData['constraints']))
        # Store a set of these into the ref-checker class
        RefDelegate2Immerse.constraintIds = set(layoutComponentIds)
    if not args.realtime:
        clock = clocks.CallbackPausableClock(clocks.FastClock())
    else:
        clock = clocks.CallbackPausableClock(clocks.SystemClock())
    
    d = Document(clock, idAttribute=NS_XML("id"))
    if args.tracefile:
        d.setTracefile(args.tracefile)
    if args.attributes:
        d.setDelegateFactory(RefDelegate2Immerse)
    d.setDelegateFactory(UpdateDelegate2Immerse, tag=NS_2IMMERSE("update"))
    try:
        url = args.document
        if not ':' in url:
            # Shortcut to allow specifying local files
            url = 'file:' + url
        d.loadDocument(url)
        d.prepareDocument()
        d.runDocument()
        assert d.isDocumentDone()
    finally:
        if args.dump:
            print('--------------------')
            #d.dump(sys.stdout)
            print(d.dumps())
        if args.dumpfile:
            fp = open(args.dumpfile, 'w')
            fp.write(d.dumps())
            fp.close()
        d.setTracefile(None)
    
if __name__ == '__main__':
    main()
