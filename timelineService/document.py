import sys
import urllib2
import urlparse
import argparse
import time
import xml.etree.ElementTree as ET
import logging
import clocks

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

NS_TIMELINE = NameSpace("tl", "http://jackjansen.nl/timelines")
NS_TIMELINE_INTERNAL = NameSpace("tls", "http://jackjansen.nl/timelines/internal")
NS_TIMELINE_CHECK = NameSpace("tlcheck", "http://jackjansen.nl/timelines/check")
NS_2IMMERSE = NameSpace("tim", "http://jackjansen.nl/2immerse")
NS_2IMMERSE_COMPONENT = NameSpace("tic", "http://jackjansen.nl/2immerse/component")
NAMESPACES = {}
NAMESPACES.update(NS_TIMELINE.ns())
NAMESPACES.update(NS_TIMELINE_INTERNAL.ns())
NAMESPACES.update(NS_TIMELINE_CHECK.ns())
NAMESPACES.update(NS_2IMMERSE.ns())
NAMESPACES.update(NS_2IMMERSE_COMPONENT.ns())
for k, v in NAMESPACES.items():
    ET.register_namespace(k, v)

# For attribute checking for 2immerse documents:
import attributeChecker
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
        
    def __repr__(self):
        return 'Delegate(%s)' % self.getXPath()
        
    def getXPath(self):
        return self.document.getXPath(self.elt)
        
    def getLogExtra(self):
    	return dict(xpath=self.getXPath())
    	
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
        self.state = state
        if self.state == State.started:
            assert self.startTime == None
            self.startTime = self.clock.now()
            print 'xxxjack set startTime for ', self.getXPath(), 'to', self.startTime
        else:
            self.startTime = None
        parentElement = self.document.getParent(self.elt)
        if parentElement is not None:
            parentElement.delegate.reportChildState(self.elt, self.state)
        if self.state == State.idle:
            self.destroyTimelineElement()
           
    def assertState(self, action, *allowedStates):
        """Check that the element is in an expected state."""
        assert self.state in set(allowedStates), "%s: %s: state==%s, expected %s" % (self, action, self.state, set(allowedStates))
        
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

    def moveStateToConform(self, oldDelegate):
        """Fast-forward an element so that it is in the same state as its old delegate was"""
        assert self.state == State.idle
        if oldDelegate.state == State.idle:
            return
        if oldDelegate.state in (State.initing, State.inited):
            self.initTimelineElement(self)
            return
        if oldDelegate.state in (State.starting, State.started):
            assert 0
            return
        if oldDelegate.state in (State.finished, State.stopping, State.skipped):
            # xxxjack unsure here, if I remain in idle will everything just work?
            return
        assert 0
        
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
                del self.elt.attrs[attrName]
                    
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
        if self.state == State.started:
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
        self.emittedStopForChildren = False
        for child in self.elt: 
            self.document.schedule(child.delegate.initTimelineElement)
        
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        for child in self.elt: 
            self.document.schedule(child.delegate.startTimelineElement)
        
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
    allowedDmappcIds = None # May be set by main program to enable checking that all refs have a layout
    
    def checkAttributes(self):
        RefDelegate.checkAttributes(self)
        attributeChecker.checkAttributes(self)
        if self.allowedDmappcIds != None:
            dmappcId = self.elt.get(NS_2IMMERSE("dmappcid"))
            if dmappcId and not dmappcId in self.allowedDmappcIds:
                print >>sys.stderr, "* Warning: element", self.getXPath(), 'has tim:dmappcId="'+dmappcId+'" but this does not exist in the layout document'
        
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
        self.clock.schedule(dur, self._done)
        
    def _done(self):
        if self.state != State.started:
            return
        self.document.report(logging.DEBUG, 'SLEEP1', self.elt.get(NS_TIMELINE("dur")), self.document.getXPath(self.elt), extra=self.getLogExtra())
        self.setState(State.finished)
    
    def parseDuration(self, dur):
        try:
            return float(dur)
        except ValueError:
            pass
        tval = time.strptime(dur, "%H:%M:%S")
        return tval.tm_sec + 60*(tval.tm_min+60*tval.tm_hour)
        
class WaitDelegate(TimelineDelegate):
    """<tl:wait> element. Waits for an incoming event."""
    
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("event")
        }
    DEFAULT_PRIO="high"
            
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.document.report(logging.DEBUG, 'WAIT0', self.elt.get(NS_TIMELINE("event")), self.document.getXPath(self.elt), extra=self.getLogExtra())
        self.setState(State.started)
        self.clock.schedule(0, self._done)
        
    def _done(self):
        if self.state != State.started:
            return
        self.document.report(logging.DEBUG, 'WAIT1', self.elt.get(NS_TIMELINE("event")), self.document.getXPath(self.elt), extra=self.getLogExtra())
        self.setState(State.finished)
    
   
DELEGATE_CLASSES = {
    NS_TIMELINE("document") : DocumentDelegate,
    NS_TIMELINE("par") : ParDelegate,
    NS_TIMELINE("seq") : SeqDelegate,
    NS_TIMELINE("ref") : RefDelegate,
    NS_TIMELINE("conditional") : ConditionalDelegate,
    NS_TIMELINE("sleep") : SleepDelegate,
    NS_TIMELINE("wait") : WaitDelegate,
    }
   
DELEGATE_CLASSES_FASTFORWARD = {
    NS_TIMELINE("document") : DocumentDelegate,
    NS_TIMELINE("par") : ParDelegate,
    NS_TIMELINE("seq") : SeqDelegate,
    NS_TIMELINE("ref") : TimeElementDelegate,
    NS_TIMELINE("conditional") : ConditionalDelegate, # xxxjack should return True depending on tree position?
    NS_TIMELINE("sleep") : SleepDelegate,
    NS_TIMELINE("wait") : DummyDelegate,
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
        print 'xxxjack seekPositionReached has triggered'
        
class Document:
    RECURSIVE = False
        
    def __init__(self, clock, extraLoggerArgs=None, idAttribute=None):
        self.tree = None
        self.root = None
        self.fragment = None
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
        
    def setExtraLoggerArgs(self, extraLoggerArgs):
            self.logger = MyLoggerAdapter(logging.getLogger(__name__), extraLoggerArgs)
    
    def setDelegateFactory(self, klass, tag=NS_TIMELINE("ref")):
        assert not self.root
        self.delegateClasses[tag] = klass
        
    def load(self, url):
        assert not self.root
        self.url = url
        fp = urllib2.urlopen(url)
        self.tree = ET.parse(fp)
        self.root = self.tree.getroot()
        self.parentMap = {c:p for p in self.tree.iter() for c in p}
        up = urlparse.urlparse(url)
        if up.fragment:
            xpathExpression = up.fragment
            if not ('/' in xpathExpression or '.' in xpathExpression or '@' in xpathExpression or '[' in xpathExpression):
                # If it is an identifier search for the element with tim:dmappcid equal to that identifier
                xpathExpression = ".//*[@tim:dmappcid='%s']" % xpathExpression
                print 'xxxjack', xpathExpression
            elements = self.tree.findall(xpathExpression, NAMESPACES)
            if len(elements) == 0:
                self.logger.log(logging.ERROR, "Fragment #%s does not match any element" % up.fragment)
            elif len(elements) > 1:
                self.logger.log(logging.ERROR, "Fragment #%s matches %d elements" % (up.fragment, len(elements)))
            else:
                self.logger.log(logging.INFO, "Will start at element %s" % self.getXPath(elements[0]))
                self.fragment = elements[0]  
        if self.idAttribute:
            self.idMap = {}
            for p in self.tree.iter():
                id = p.get(self.idAttribute)
                if id:
                    if id in self.idMap:
                        raise TimelineParseError("Duplicate id %s in element %s" % (id, self.getXPath(p)))
                    self.idMap[id] = p 
        
    def getParent(self, elt):
        return self.parentMap.get(elt)
        
    def getXPath(self, elt):
        assert self.root is not None
        parent = self.getParent(elt)
        if parent is None:
            return '/'
        index = 0
        for ch in parent:
            if ch is elt:
                break
            if ch.tag == elt.tag:
                index += 1
        rv = self.getXPath(parent)
        if rv != '/':
            rv += '/'
        tagname = NS_TIMELINE.localTag(elt.tag)
        rv += tagname
        if index:
            rv = rv + '[%d]' % (index+1)
        return rv
        
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
    
    def prepareDocument(self):
        if self.fragment is None:
            #
            # No positioning needed. Add the real delegates and run all elegible
            # init methods.
            #
            self._addDelegates()
            self.runDocumentInit()
            if not self.RECURSIVE:
                self.runloop(lambda : self.root.delegate.state == State.inited)
            self.runDocumentStart()
            return
        #
        # Positioning needed. Start with providing all elements with the
        # fastforward delegates.
        #
        self._addDelegates(DELEGATE_CLASSES_FASTFORWARD)
        assert self.fragment.delegate
        #
        # Monitor the target element.
        #
        self.fragment.delegate = SeekToElementAdapter(self.fragment.delegate)
        #
        # Call the init methods
        #
        self.report(logging.DEBUG, 'FFWD', 'goto', self.fragment.delegate.getXPath())
        self.runDocumentInit()
        if not self.RECURSIVE:
            self.runloop(lambda : self.root.delegate.state == State.inited)
        #
        # fastforward the document until we get to the target element.
        #
        assert self.fragment.delegate.seekPositionReached == False
        self.clock.start()
        self.runDocumentStart()
        self.runloop(lambda : self.fragment.delegate.seekPositionReached)
        self.report(logging.DEBUG, 'FFWD', 'reached', self.fragment.delegate.getXPath())
        #
        # Now replace the fastforward delegates with the real ones.
        #
        self.dump(sys.stdout)
        assert 0        
        
    def _addDelegates(self, delegateClasses=None):
        assert self.root is not None
        for elt in self.tree.iter():
            if not hasattr(elt, 'delegate'):
                klass = self._getDelegate(elt.tag)
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
            klass = self._getDelegate(elt.tag, newDelegateClasses)
            elt.delegate = klass(elt, self, self.clock)
            elt.delegate.checkAttributes()
            elt.delegate.checkChildren()
            # Make new delegate go to same state as the old delegate was in
            elt.delegate.moveStateToConform(oldDelegate)
                
    def _getDelegate(self, tag, delegateClasses=None):
        if not tag in NS_TIMELINE:
            return DummyDelegate
        if delegateClasses is None:
            delegateClasses =  self.delegateClasses       
        return delegateClasses.get(tag, ErrorDelegate)
            
    def runDocument(self):
        self.clock.start()
        self.runDocumentStart()
        self.runloop(State.finished)
        self.runDocumentStop()
        
    def runDocumentInit(self):
        self.report(logging.INFO, 'RUN', 'init')
        self.schedule(self.root.delegate.initTimelineElement)
    
    def runDocumentStart(self):
        assert self.root is not None
        self.report(logging.INFO, 'RUN', 'start')
        self.schedule(self.root.delegate.startTimelineElement)

    def runDocumentStop(self):
        self.report(logging.INFO, 'RUN', 'stop')
        self.root.delegate.assertDescendentState("run()", State.finished, State.stopping, State.idle)
#        self.terminating = True
        self.root.delegate.stopTimelineElement()
        self.runloop(State.idle)
        self.root.delegate.assertDescendentState("run()", State.idle)
        self.report(logging.INFO, 'RUN', 'done')
            
    def getDocumentState(self):
        if self.root is None:
            return None
        return self.root.delegate.state
            
    def schedule(self, callback, *args, **kwargs):
        assert self.root is not None
        self.report(logging.DEBUG, 'EMIT', callback.__name__, self.getXPath(callback.im_self.elt), extra=callback.im_self.elt.delegate.getLogExtra())
        if self.RECURSIVE or self.terminating:
            callback(*args, **kwargs)
        else:
            self.toDo.append((callback, args, kwargs))
            
    def runloop(self, stopCondition):
        assert self.root is not None
        while not stopCondition() or len(self.toDo):
            if len(self.toDo):
                callback, args, kwargs = self.toDo.pop(0)
                callback(*args, **kwargs)
            else:
                self.sleepUntilNextEvent()
                self.clock.handleEvents(self)
        assert len(self.toDo) == 0, 'events not handled: %s' % repr(self.toDo)
        assert stopCondition(), 'Document root did not reach expected state'
        
    def sleepUntilNextEvent(self):
        self.clock.sleepUntilNextEvent()
        
    def runAvailable(self):
        assert self.root is not None
        self.clock.handleEvents(self)
        while len(self.toDo):
            callback, args, kwargs = self.toDo.pop(0)
            callback(*args, **kwargs)
            if len(self.toDo) == 0:
                self.clock.handleEvents(self)

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
    parser.add_argument("--layout", metavar="URL", help="Check against 2immerse layout document, make sure that all dmappcid are specified in the layout")
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
        timelineDoc = urllib2.urlopen(args.layout)
        timelineData = json.load(timelineDoc)
        # Get all componentIds mentioned in the constraints
        layoutDmappcIds = map((lambda constraint: constraint['componentId']), timelineData['constraints'])
        # Store a set of these into the ref-checker class
        RefDelegate2Immerse.allowedDmappcIds = set(layoutDmappcIds)
    if not args.realtime:
        clock = clocks.CallbackPausableClock(clocks.FastClock())
    else:
        clock = clocks.CallbackPausableClock(clocks.SystemClock())
    
    d = Document(clock, idAttribute=NS_2IMMERSE("dmappcid"))
    if args.attributes:
        d.setDelegateFactory(RefDelegate2Immerse)
    try:
        url = args.document
        if not ':' in url:
            # Shortcut to allow specifying local files
            url = 'file:' + url
        d.load(url)
        d.prepareDocument()
#         if args.dump:
#             d.dump(sys.stdout)
#             print '--------------------'
        d.runDocument()
    finally:
        if args.dump:
            print '--------------------'
            #d.dump(sys.stdout)
            print d.dumps()
    
if __name__ == '__main__':
    main()
