import sys
import urllib2
import urlparse
import argparse
import time
import xml.etree.ElementTree as ET
import logging
import clocks
import json

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
    
class NameSpace:
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
for k, v in NAMESPACES.items():
    ET.register_namespace(k, v)

# For attribute checking for 2immerse documents:
import attributeChecker
attributeChecker.NS_XML = NS_XML
attributeChecker.NS_TIMELINE = NS_TIMELINE
attributeChecker.NS_TIMELINE_CHECK = NS_TIMELINE_CHECK
attributeChecker.NS_2IMMERSE = NS_2IMMERSE
attributeChecker.NS_2IMMERSE_COMPONENT = NS_2IMMERSE_COMPONENT

PRIO_TO_INT = dict(low=0, normal=50, high=100)

class State:
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
    
class DummyDelegate:
    """Baseclass for delegates, also used for non-timeline elements."""
    DEFAULT_PRIO="low"
    
    def __init__(self, elt, document, clock):
        self.elt = elt
        self.document = document
        self.logger = self.document.logger
        self.state = State.idle
        self.clock = clock
        self.startTime = None
        self.conformTargetDelegate = None
        
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
        
    def isCurrentTimingMaster(self):
        """Return True if this element currently has control over its own clock"""
        return False
        
    def storeStateForSave(self):
        """Store internal state in XML, prior to serialisation"""
        if self.state != State.idle:
            self.elt.set(NS_TIMELINE_INTERNAL("state"), self.state)
        if self.isCurrentTimingMaster() and self.startTime != None:
            self.elt.set(NS_TIMELINE_INTERNAL("progress"), str(self.clock.now()-self.startTime))
            
    def setState(self, state):
        """Advance element state to a new one. Subclasses will add side effects (such as actually playing media)"""
        self.document.report(logging.DEBUG, 'STATE', state, self.document.getXPath(self.elt), extra=self.getLogExtra())
        if self.state == state:
            self.logger.warning('superfluous state change: %-8s %-8s %s' % ('STATE', state, self.document.getXPath(self.elt)), extra=self.getLogExtra())
            if state == State.idle:
                # Defensive programming: destroy it again...
                self.logger.warning('Re-issuing destroy for %s' % self.document.getXPath(self.elt), extra=self.getLogExtra())
                self.destroyTimelineElement()
            return
        oldState = self.state
        self.state = state
        
        if self.state == State.started:
            # Remember the time this element actually started. A bit convoluted
            # because of reviving of elements in 2immerse
            if oldState not in {State.started, State.finished}:
                assert self.startTime == None
            if self.startTime == None:
                self.startTime = self.clock.now()
        elif self.state == State.finished:
            # Similar to for state=started, but only f started didn't set it.
            if self.startTime == None:
                self.startTime = self.clock.now()
        else:
            # The element is no longer running, so forget the start time.
            self.startTime = None
            
        parentElement = self.document.getParent(self.elt)
        if parentElement is not None:
            parentElement.delegate.reportChildState(self.elt, self.state)
            
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
        assert self.state in allowedStates, "%s: %s: state==%s, expected %s" % (self, action, self.state, allowedStates)
        
    def assertDescendentState(self, action, *allowedStates):
        """Check that all descendents of the element are in an expected state"""
        for desc in self.elt.iter():
            assert desc.delegate.state in set(allowedStates), "%s: %s: descendent %s: state==%s, expected %s" % (self, action, desc.delegate, desc.delegate.state, set(allowedStates))
            #if not desc.delegate.state in set(allowedStates):
            #    print "WARNING XXXJACK: %s: %s: descendent %s: state==%s, expected %s" % (self, action, desc.delegate, desc.delegate.state, set(allowedStates))
         
    def reportChildState(self, child, childState):
        """Called by direct children when they change their state"""
        pass
        
    def initTimelineElement(self):
        """Called by parent or outer control to initialize the element"""
        self.assertState('initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        #self.setState(State.initing)
        self.setState(State.inited)
        
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
        # print 'xxxjack stepMoveStateToConform(%s): move from %s to %s' % (self, self.state, self.conformTargetDelegate.state)
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
            self.startTimelineElement() # xxxjack need to pass time offset from conformTargetElement.startTime
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
        
    def adjustStartTimeRecordedDuringSeek(self, adjustment):
        """Start times recorded during seek should be converted to the runtime document clock."""
        if self.conformTargetDelegate != None:
            if self.conformTargetDelegate.state in {State.started, State.finished}:
                assert self.conformTargetDelegate.startTime != None
                self.conformTargetDelegate.startTime += adjustment
        
    def getStartTime(self):
        """Return the time at which this element should have started, or now."""
        # xxxjack this does not yet handle seeking during playback, for elements which only
        # need to be repositioned (because they were running before the seek and are still running
        # after the seek)
        if self.conformTargetDelegate != None:
            if self.conformTargetDelegate.state in {State.started, State.finished}:
                assert self.conformTargetDelegate.startTime != None
                self.logger.debug("Element %s should have started at t=%f", self.document.getXPath(self.elt), self.conformTargetDelegate.startTime)
                return self.conformTargetDelegate.startTime
        return self.clock.now()
        
    def attributesChanged(self, attrs):
        """Called after an edit operation has changed attributes on this element."""
        self.logger.warning("%s: Unexpected call to attributesChanged(%s)" % (self.getXPath(), repr(attrs)))
        
    def childAdded(self, child):
        """Called after an edit operation when a new child has been added."""
        self.logger.warning("%s: Unexpected call to childAdded(%s)" % (self.getXPath(), self.document.getXPath(child)))
        
class ErrorDelegate(DummyDelegate):
    """<tl:...> element of unknown type. Prints an error and handles the rest as a non-tl: element."""
    
    def __init__(self, elt, document, clock):
        DummyDelegate.__init__(self, elt, document, clock)
        print >>sys.stderr, "* Error: unknown tag", elt.tag

class TimelineDelegate(DummyDelegate):
    """Baseclass for all <tl:...> elements."""
    
    ALLOWED_ATTRIBUTES = set()
    ALLOWED_CHILDREN = None
    EXACT_CHILD_COUNT = None
    
    def checkAttributes(self):
        for attrName in self.elt.keys():
            if attrName in NS_TIMELINE:
                if not attrName in self.ALLOWED_ATTRIBUTES:
                    print >>sys.stderr, "* Error: element", self.getXPath(), "has unknown attribute", attrName
            # Remove state attributes
            if attrName in NS_TIMELINE_INTERNAL:
                del self.elt.attrib[attrName]
                    
    def checkChildren(self):
        if not self.EXACT_CHILD_COUNT is None and len(self.elt) != self.EXACT_CHILD_COUNT:
            print >>sys.stderr, "* Error: element", self.getXPath(), "expects", self.EXACT_CHILD_COUNT, "children but has", len(self.elt)
        if not self.ALLOWED_CHILDREN is None:
            for child in self.elt:
                if child.tag in NS_2IMMERSE and not child.tag in self.ALLOWED_CHILDREN:
                    print >>sys.stderr, "* Error: element", self.getXPath(), "cannot have child of type", child.tag
         
class SingleChildDelegate(TimelineDelegate):
    """Baseclass for elements that have exactly one child."""
    
    EXACT_CHILD_COUNT=1

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
        #import pdb ; pdb.set_trace()
        #self.assertState('reportChildState()', 'no-state-would-be-correct')

    def initTimelineElement(self):
        self.assertState('initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        self.setState(State.initing)
        self.document.schedule(self.elt[0].delegate.initTimelineElement)
        
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.inited, State.idle)
        self.setState(State.starting)
        self.document.schedule(self.elt[0].delegate.startTimelineElement)
        
    def stopTimelineElement(self):
        if self.state == State.idle:
            return
        self.setState(State.stopping)
        waitNeeded = False
        if self.elt[0].delegate.state in State.STOP_NEEDED:
            self.document.schedule(self.elt[0].delegate.stopTimelineElement)
            waitNeeded = True
        if not waitNeeded:
            self.setState(State.idle)

class DocumentDelegate(SingleChildDelegate):
    """<tl:document> element."""
    ALLOWED_CHILDREN={
        NS_TIMELINE("par"),
        NS_TIMELINE("seq"),
        }

class TimeElementDelegate(TimelineDelegate):
    """Baseclass for elements that have a clock, and therefore a prio attribute."""
    
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("prio")
        }
        
    def getCurrentPriority(self):
        val = self.elt.get(NS_TIMELINE("prio"), "normal")
#         if self.state == State.started:
#             val = self.elt.get(NS_TIMELINE("prio"), "normal")
#         else:
#             val = "low"
        val = PRIO_TO_INT.get(val, val)
        val = int(val)
        return val

    def isCurrentTimingMaster(self):
        # xxxjack only correct for 2immerse....
        if self.state != State.started:
            return False
        syncMode = self.elt.get(NS_2IMMERSE_COMPONENT("syncMode"), "unspecified")
        if syncMode != "master":
            return False
        return True
        
class ParDelegate(TimeElementDelegate):
    """<tl:par> element. Runs all its children in parallel."""
    
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("end"),
        NS_TIMELINE("sync"),
        }
        
    def reportChildState(self, child, childState):
        if self.state == State.idle:
            # If the <par> is idle we do not care about children changing state.
            return
        if self.state == State.initing:
            # We're initializing. Go to initialized once all our children have.
            for ch in self.elt:
                if ch.delegate.state not in {State.inited}:
#                    print 'xxxjack par initing', self.document.getXPath(self.elt), 'waitforchild', self.document.getXPath(ch)
                    return
            self.setState(State.inited)
#            print 'xxxjack par inited'
            return
        #
        # See if this child should be auto-started (because it was inserted during runtime)
        #
        if child in self.childrenToAutoStart and childState == State.inited:
            self.logger.debug("%s: autostarting child %s" % (self.getXPath(), self.document.getXPath(child)))
            self.document.schedule(child.delegate.startTimelineElement)
        if self.state == State.starting:
            # We're starting. Wait for all our children to have started (or started-and-finished).
            for ch in self.elt:
                if ch.delegate.state not in {State.started, State.finished}:
                    return
            self.setState(State.started)
            # Note that we fall through into the next if straight away
        if self.state == State.started:
            #
            # First check whether any of the children that are relevant to our lifetime are still not finished.
            # 
            relevantChildren = self._getRelevantChildren()
#            print 'xxxjack par relevant children', relevantChildren
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
#            self.setState(State.stopping)
#             needToWait = False
#             for ch in self.elt:
#                 if ch.delegate.state == State.stopping:
# #                    print 'xxxjack par stopping, need to wait for', ch.delegate
#                     needToWait = True
#                 elif ch.delegate.state != State.stopped:
# #                    print 'xxxjack par stopping, need to stop', ch.delegate
#                     self.document.schedule(ch.delegate.stopTimelineElement)
#                     needToWait = True
#                 else:
# #                    print 'xxxjack par stopping, already stopped', ch.delegate
#                     pass
#             if not needToWait:
#                 self.setState(State.stopped)
#         elif self.state == State.stopping:
#             for ch in self.elt:
#                 if ch.delegate.state != State.stopped:
#                     return
#             self.setState(State.stopped)
#             self.assertDescendentState('reportChildState[self.state==stopped]', State.stopped, State.idle)
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
    
    def _getRelevantChildren(self):
        if len(self.elt) == 0: return []
        childSelector = self.elt.get(NS_TIMELINE("end"), "all")
        if childSelector == "all":
            return list(self.elt)
        elif childSelector == "master":
            child = self._getMasterChild()
            return [child]
        assert 0, "Only all and master are implemented"
        return [self.elt[0]]
        
    def _getMasterChild(self):
        prioritiesAndChildren = []
        for ch in self.elt:
            prio = ch.delegate.getCurrentPriority()
            prioritiesAndChildren.append((prio, ch))
        prioritiesAndChildren.sort()
        return prioritiesAndChildren[-1][1]
        
        
    def initTimelineElement(self):
        self.assertState('initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        self.setState(State.initing)
        self.emittedStopForChildren = False # Set to True if we have already emitted the stop clls to the children
        self.childrenToAutoStart = [] # Children that we start on inited (have been added during runtime with childAdded)
        for child in self.elt: 
            self.document.schedule(child.delegate.initTimelineElement)
        # xxxjack: should we go to inited if we have no children?
        
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        for child in self.elt: 
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
            self.document.schedule(child.delegate.initTimelineElement)
            self.childrenToAutoStart.append(child)
        else:
            assert 0
        

class SeqDelegate(TimeElementDelegate):
    """<tl:seq> element. Runs its children in succession."""

    def reportChildState(self, child, childState):
        assert len(self.elt)
        if self.state == State.idle:
            # We're idle. We don't care about children state changes.
            return
        if self.state == State.initing:
            # Initializing. We're initialized when our first child is.
            if self.elt[0].delegate.state not in {State.inited}:
                return
            self.setState(State.inited)
            return
        if self.state == State.starting:
            # We're starting. Once our first child has started (or started and stopped) so have we.
            if self.elt[0].delegate.state not in {State.started, State.finished}:
                return
            self.setState(State.started)
            # Note that we fall through into the next "if" straight away.
        if self.state == State.started:
            # Started. Check whether our current child is still active.
            if self._currentChild.delegate.state in State.NOT_DONE:
                return
            # Our current child is no longer active, advance to the next (if any)
            prevChild = self._currentChild            
            nextChild = self._nextChild()
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
                self.document.schedule(self._currentChild.delegate.startTimelineElement)
                nextChild = self._nextChild()
                if nextChild is not None:
                    self.document.schedule(nextChild.delegate.initTimelineElement)
            elif nextChild.delegate.state == State.idle:
                # Normally the init for the next child has already been issued, but
                # if the current child had a DummyDelegate it can happen that it hasn't.
                # Issue it now.
                pass # self.document.schedule(nextChild.delegate.initTimelineElement)
            else:
                # Next child not yet ready to run.
                nextChild.delegate.assertState('seq-parent-reportChildState()', State.initing)
                pass # Wait for inited callback from nextChild
            if prevChild is not None and prevChild.delegate.state in State.STOP_NEEDED:
                self.document.schedule(prevChild.delegate.stopTimelineElement)
        if self.state == State.stopping:
            for ch in self.elt:
                if ch.delegate.state != State.idle:
                    return
            self.setState(State.idle)
            
    def initTimelineElement(self):
        self.assertState('initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        self.setState(State.initing)
        if not len(self.elt):
            self.setState(State.inited)
            return
        self._currentChild = None
        self.document.schedule(self.elt[0].delegate.initTimelineElement)
        
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        if not len(self.elt):
            self.setState(State.finished)
            return
        self._currentChild = self.elt[0]
        self.document.schedule(self._currentChild.delegate.startTimelineElement)
        nextChild = self._nextChild()
        if nextChild is not None:
            self.document.schedule(nextChild.delegate.initTimelineElement)
                    
    def stopTimelineElement(self):
        self.setState(State.stopping)
        waitNeeded = False
        for ch in self.elt:
            if ch.delegate.state in State.STOP_NEEDED:
                self.document.schedule(ch.delegate.stopTimelineElement)
                waitNeeded = True
        if not waitNeeded:
            self.setState(State.idle)

    def _nextChild(self):
        foundCurrent = False
        for ch in self.elt:
            if foundCurrent: return ch
            foundCurrent = (ch == self._currentChild)
        return None
    
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
                self.elt.set(NS_TIMELINE("count"), str(rcInt))
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
            self.setState(State.starting)
            SingleChildDelegate.startTimelineElement(self)
        else:
            self.setState(State.finished)
            
class RefDelegate(TimeElementDelegate):
    """<tl:ref> element. Handles actual media playback. Usually subclassed to actually do something."""
    
    EXACT_CHILD_COUNT=0
    
    def initTimelineElement(self):
        TimeElementDelegate.initTimelineElement(self)

    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited)
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
        self.clock.schedule(dur, self._done)
               
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
        
class RefDelegate2Immerse(RefDelegate):
    """2-Immerse specific RefDelegate that checks the attributes"""
    allowedIds = None # May be set by main program to enable checking that all refs have a layout
    
    def checkAttributes(self):
        RefDelegate.checkAttributes(self)
        attributeChecker.checkAttributes(self)
        if self.allowedIds != None:
            uniqId = self.getId()
            if uniqId and not uniqId in self.allowedIds:
                print >>sys.stderr, "* Warning: element", self.getXPath(), 'has xml:id="'+uniqId+'" but this does not exist in the layout document'
        
class UpdateDelegate2Immerse(TimelineDelegate):
    """2-Immerse specific delegate for tim:update that checks the attributes and reports actions"""
    allowedIds = None # May be set by main program to enable checking that all refs have a layout
    
    def __init__(self, elt, document, clock):
        TimelineDelegate.__init__(self, elt, document, clock)
        
    def checkAttributes(self):
        TimelineDelegate.checkAttributes(self)
        #attributeChecker.checkAttributes(self)
        uniqId = self.elt.get(NS_2IMMERSE("target"))
        if not uniqId:
            print >> sys.stderr, "* element", self.getXPath(), 'misses required tim:target attribute'
        if uniqId and not uniqId in self.document.idMap:
            print >>sys.stderr, "* Warning: element", self.getXPath(), 'has tim:target="'+uniqId+'" but this xml:id does not exist in the document'
                
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
        self.assertState('startTimelineElement()', State.inited)
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
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.setState(State.started)
        self.document.report(logging.DEBUG, 'SLEEP0', self.elt.get(NS_TIMELINE("dur")), self.document.getXPath(self.elt), extra=self.getLogExtra())
        dur = self.parseDuration(self.elt.get(NS_TIMELINE("dur")))
        assert self.startTime != None
        self.sleepEndTime = self.startTime + dur
        self.clock.scheduleAt(self.sleepEndTime, self._done)
        
    def _done(self):
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
                assert self.startTime
                newSleepEndTime = self.startTime + dur
                self.document.logger.debug("SleepDelegate(%s): sleepEndTime changed from %.3f to %.3f" % (self.document.getXPath(self.elt), self.sleepEndTime, newSleepEndTime), extra=self.getLogExtra())
                self.sleepEndTime = newSleepEndTime
                self.clock.scheduleAt(self.sleepEndTime, self._done)
            else:
                self.document.logger.warning("SleepDelegate(%s): unexpected attribute changed: %s" % (self.document.getXPath(self.elt), k), extra=self.getLogExtra())
        
class WaitDelegate(TimeElementDelegate):
    """<tl:wait> element. Waits for an incoming event."""
    
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("event")
        }
    DEFAULT_PRIO="high"
            
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited)
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
    NS_TIMELINE("ref") : TimeElementDelegate,
    NS_TIMELINE("conditional") : ConditionalDelegate, # xxxjack should return True depending on tree position?
    NS_TIMELINE("sleep") : SleepDelegate,
    NS_TIMELINE("wait") : DummyDelegate, # xxxjack This makes all events appear to happen instantaneous...
    }
    
#
# Adapters
#

class DelegateAdapter:
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
        # print 'xxxjack seekPositionReached has triggered'
        
class DocumentState:
    def __init__(self, document):
        self.document = document
        document.report(logging.DEBUG, 'DOCSTATE', self.__class__.__name__)
        
    def nudgeClock(self):
    	pass
    	
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
            document.report(logging.INFO, 'FFWD', 'goto', '#t=%f' % document.startTime)
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
    	self.document.clock.sleepUntilNextEvent()
    	
    def stateFinished(self):
         return self.startElement.delegate.seekPositionReached
        
    def nextState(self):
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
    	self.document.clock.sleepUntilNextEvent()
    	
    def stateFinished(self):
        return self.document.clock.now() >= self.startTime

    def nextState(self):
        self.document.report(logging.INFO, 'FFWD', 'reached', '#t=%f' % self.document.clock.now())
        return DocumentStateSeekFinish(self.document)

class DocumentStateSeekFinish(DocumentState):
    def __init__(self, document):
        DocumentState.__init__(self, document)
        document.replaceDelegates(None)
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
        adjustment = self.document.clock.restoreUnderlyingClock(True)
        #
        # Now do the set-position on the clock of the current master timing element.
        #
        for elt in self.document.tree.iter():
            elt.delegate.adjustStartTimeRecordedDuringSeek(adjustment)
#        	if not elt.delegate.startTime is None:
#        		elt.delegate.startTime += adjustment
        		
        self.document.report(logging.INFO, 'FFWD', 'reposition', 'delta-t=%f' % adjustment)
        #
        # Now (re)issue the start calls
        #
        for elt in self.document.tree.iter():
            elt.delegate.stepMoveStateToConform(startAllowed=True)
        self.document.report(logging.INFO, 'FFWD', 'done')
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

class DocumentModificationMixin:

    def __init__(self):
        self.stateUpdateCallback = None
        
    def modifyDocument(self, generation, commands, stateUpdateCallback=None):
        """Modify the running document from the given command list"""
        updateCallbacks = []
        self.stateUpdateCallback = stateUpdateCallback
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
        for k, v in attrs.items():
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
        if extraLoggerArgs:
            self.logger = MyLoggerAdapter(self.logger, extraLoggerArgs)
        self.events = []
        
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
        fp = urllib2.urlopen(url)
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
        up = urlparse.urlparse(url)
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
        
    def dump(self, fp):
        if self.root is None:
            return
        for elt in self.tree.iter():
            elt.delegate.storeStateForSave()
        self.tree.write(fp)
        fp.write('\n')
        
    def dumps(self):
        if self.root is None:
            return ''
        for elt in self.tree.iter():
            elt.delegate.storeStateForSave()
        xmlstr = ET.tostring(self.root, encoding='utf8', method='xml')
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
        self.report(logging.DEBUG, 'EMIT', callback.__name__, self.getXPath(callback.im_self.elt), extra=callback.im_self.elt.delegate.getLogExtra())
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
                self.documentState.nudgeClock()
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
             
def main():
    global DEBUG
    parser = argparse.ArgumentParser(description="Test runner for timeline documents")
    parser.add_argument("document", help="The XML timeline document to parse and run")
    parser.add_argument("--debug", action="store_true", help="Print detailed state machine progression output")
    parser.add_argument("--trace", action="store_true", help="Print less detailed externally visible progression output")
    parser.add_argument("--dump", action="store_true", help="Dump document to stdout on exceptions and succesful termination")
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
    
    if args.layout:
        import json
        args.attributes = True
        # Open the document, read the JSON
        layout = args.layout
        if not ':' in layout:
            layout = 'file:' + layout
        timelineDoc = urllib2.urlopen(layout)
        timelineData = json.load(timelineDoc)
        # Get all componentIds mentioned in the constraints
        layoutComponentIds = map((lambda constraint: constraint['componentId']), timelineData['constraints'])
        # Store a set of these into the ref-checker class
        RefDelegate2Immerse.allowedIds = set(layoutComponentIds)
        UpdateDelegate2Immerse.allowedIds = set(layoutComponentIds)
    if not args.realtime:
        clock = clocks.CallbackPausableClock(clocks.FastClock())
    else:
        clock = clocks.CallbackPausableClock(clocks.SystemClock())
    
    d = Document(clock, idAttribute=NS_XML("id"))
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
            print '--------------------'
            #d.dump(sys.stdout)
            print d.dumps()
    
if __name__ == '__main__':
    main()
