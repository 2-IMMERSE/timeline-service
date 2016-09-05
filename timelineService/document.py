import sys
import urllib
import argparse
import time
import Queue
import xml.etree.ElementTree as ET

DEBUG=True

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
NS_2IMMERSE = NameSpace("tim", "http://jackjansen.nl/2immerse")
NAMESPACES = {}
NAMESPACES.update(NS_TIMELINE.ns())
NAMESPACES.update(NS_2IMMERSE.ns())
NAMESPACES.update(NS_TIMELINE_INTERNAL.ns())
for k, v in NAMESPACES.items():
    ET.register_namespace(k, v)

PRIO_TO_INT = dict(low=0, normal=50, high=100)

class State:
    idle = "idle"
    initing = "initing"
    inited = "inited"
    starting = "starting"
    started = "started"
    stopping = "stopping"
    stopped = "stopped"
#    terminating = "terminating"
    
#    DONE = {stopping, stopped, terminating}
    DONE = {stopped}
    READY = {inited}
    
class DummyDelegate:
    def __init__(self, elt, document, clock):
        self.elt = elt
        self.document = document
        self.state = State.idle
        self.clock = clock
        
    def __repr__(self):
        return 'Delegate(%s)' % self.document.getXPath(self.elt)
        
    def checkAttributes(self):
        pass
        
    def checkChildren(self):
        pass
        
    def storeStateForSave(self):
        if self.state != State.idle:
            self.elt.set(NS_TIMELINE_INTERNAL("state"), self.state)
            
    def setState(self, state):
        self.document.report('STATE', state, self.document.getXPath(self.elt))
        if self.state == state:
            print 'xxxjack superfluous state change: %-8s %-8s %s' % ('STATE', state, self.document.getXPath(self.elt))
            if DEBUG:
                import pdb
                pdb.set_trace()
            return
        self.state = state
        parentElement = self.document.getParent(self.elt)
        if parentElement is not None:
            parentElement.delegate.reportChildState(self.elt, self.state)
           
    def assertState(self, action, *allowedStates):
        assert self.state in set(allowedStates), "%s: %s: state==%s, expected %s" % (self, action, self.state, set(allowedStates))
        
    def assertDescendentState(self, action, *allowedStates):
        for desc in self.elt.iter():
            assert desc.delegate.state in set(allowedStates), "%s: %s: descendent %s: state==%s, expected %s" % (self, action, desc.delegate, desc.delegate.state, set(allowedStates))
         
    def reportChildState(self, child, childState):
        pass
        
    def initTimelineElement(self):
        self.assertState('initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        self.setState(State.initing)
        self.setState(State.inited)
        
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited, State.stopped)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        #self.setState(State.started)
        #self.setState(State.stopping)
        self.setState(State.stopped)
        
    def stopTimelineElement(self):
        self.assertState('stopTimelineElement()', State.inited, State.started)
        self.setState(State.stopping)
        self.setState(State.stopped)
        
    def getCurrentPriority(self):
        return PRIO_TO_INT["low"]
        
#     def terminate(self):
#         self.assertState('terminate()', State.stopped)
#         self.setState(State.terminating)
#         self.setState(State.idle)
        
class ErrorDelegate(DummyDelegate):
    def __init__(self, elt, document, clock):
        DummyDelegate.__init__(self, elt, document, clock)
        print >>sys.stderr, "* Error: unknown tag", elt.tag

class TimelineDelegate(DummyDelegate):
    ALLOWED_ATTRIBUTES = set()
    ALLOWED_CHILDREN = None
    EXACT_CHILD_COUNT = None
    
    def checkAttributes(self):
        for attrName in self.elt.keys():
            if attrName in NS_TIMELINE:
                if not attrName in self.ALLOWED_ATTRIBUTES:
                    print >>sys.stderr, "* Error: element", self.elt.tag, "has unknown attribute", attrName
            # Remove state attributes
            if attrName in NS_TIMELINE_INTERNAL:
                del self.elt.attrs[attrName]
                    
    def checkChildren(self):
        if not self.EXACT_CHILD_COUNT is None and len(self.elt) != self.EXACT_CHILD_COUNT:
            print >>sys.stderr, "* Error: element", self.elt.tag, "expects", self.EXACT_CHILD_COUNT, "children but has", len(self.elt)
        if not self.ALLOWED_CHILDREN is None:
            for child in self.elt:
                if child.tag in NS_2IMMERSE and not child.tag in self.ALLOWED_CHILDREN:
                    print >>sys.stderr, "* Error: element", self.elt.tag, "cannot have child of type", child.tag
         
class SingleChildDelegate(TimelineDelegate):
    EXACT_CHILD_COUNT=1

    def reportChildState(self, child, childState):
        if childState == State.inited:
            self.assertState('reportChildState(inited)', State.initing)
            self.setState(State.inited)
        elif childState == State.started:
            self.assertState('reportChildState(started)', State.starting)
            self.setState(State.started)
        elif childState == State.stopped:
            self.assertState('reportChildState(stopped)', State.stopping, State.started)
            self.setState(State.stopped)
            self.assertDescendentState('reportChildState(stopped)', State.stopped)

    def initTimelineElement(self):
        self.assertState('initTimelineElement()', State.idle)
        self.assertDescendentState('initTimelineElement()', State.idle)
        self.setState(State.initing)
        self.document.schedule(self.elt[0].delegate.initTimelineElement)
        
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.document.schedule(self.elt[0].delegate.startTimelineElement)
        
    def stopTimelineElement(self):
        self.assertState('stopTimelineElement()', State.inited, State.started)
        self.setState(State.stopping)
        self.document.schedule(self.elt[0].delegate.stopTimelineElement)
        
#     def terminate(self):
#         self.assertState('terminate()', State.stopped)
#         self.setState(State.terminating)
#         self.document.schedule(self.elt[0].delegate.terminate)
#         self.setState(State.idle)

class DocumentDelegate(SingleChildDelegate):
    ALLOWED_CHILDREN={
        NS_TIMELINE("par"),
        NS_TIMELINE("seq"),
        }

class TimeElementDelegate(TimelineDelegate):
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("prio")
        }
        
    def getCurrentPriority(self):
        if self.state == State.started:
            val = self.elt.get(NS_TIMELINE("prio"), "normal")
        else:
            val = "low"
        val = PRIO_TO_INT.get(val, val)
        val = int(val)
        return val
        
class ParDelegate(TimeElementDelegate):
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("end"),
        NS_TIMELINE("sync"),
        }
        
    def reportChildState(self, child, childState):
        if self.state == State.initing:
            for ch in self.elt:
                if ch.delegate.state != State.inited:
                    return
            self.setState(State.inited)
        elif self.state == State.starting:
            for ch in self.elt:
                if ch.delegate.state not in {State.started, State.stopped}:
                    return
            self.setState(State.started)
        elif self.state == State.started:
            relevantChildren = self._getRelevantChildren()
            for ch in relevantChildren:
                if ch.delegate.state != State.stopped:
                    return
            self.setState(State.stopping)
            needToWait = False
            for ch in self.elt:
                if ch.delegate.state == State.stopping:
                    needToWait = True
                elif ch.delegate.state != State.stopped:
                    self.document.schedule(ch.delegate.stopTimelineElement)
                    needToWait = True
                else:
                    pass
            if not needToWait:
                self.setState(State.stopped)
        elif self.state == State.stopping:
            for ch in self.elt:
                if ch.delegate.state != State.stopped:
                    return
            self.setState(State.stopped)
            self.assertDescendentState('reportChildState[self.state==stopped]', State.stopped)
    
    def _getRelevantChildren(self):
        # Stopgap
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
        for child in self.elt: 
            self.document.schedule(child.delegate.initTimelineElement)
        
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited, State.stopped)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        for child in self.elt: 
            self.document.schedule(child.delegate.startTimelineElement)
        
    def stopTimelineElement(self):
        self.assertState('stopTimelineElement()', State.inited, State.started)
        self.setState(State.stopping)
        for child in self.elt: 
            self.document.schedule(child.delegate.stopTimelineElement)
        
#     def terminate(self):
#         self.assertState('terminate()', State.stopped)
#         self.setState(State.terminating)
#         for child in self.elt: 
#             self.document.schedule(child.delegate.terminate)
#         self.setState(State.idle)

class SeqDelegate(TimeElementDelegate):

    def reportChildState(self, child, childState):
        assert len(self.elt)
        if self.state == State.initing:
            if self.elt[0].delegate.state != State.inited:
                return
            self.setState(State.inited)
        elif self.state == State.starting:
            if self.elt[0].delegate.state not in {State.started, State.stopped}:
                return
            self.setState(State.started)
        elif self.state == State.started:
            if self._currentChild.delegate.state not in State.DONE:
                return
            nextChild = self._nextChild()
            if nextChild is None:
                self.setState(State.stopped)
                self.assertDescendentState('reportChildState[self.state==stopped]', State.stopped)
            elif nextChild.delegate.state in State.READY:
                self._currentChild = nextChild
                self.document.schedule(self._currentChild.delegate.startTimelineElement)
                nextChild = self._nextChild()
                if nextChild is not None:
                    self.document.schedule(nextChild.delegate.initTimelineElement)
            else:
                pass # Wait for inited callback from nextChild
        elif self.state == State.stopping:
            for ch in self.elt:
                if ch.delegate.state != State.stopped:
                    return
            self.setState(State.stopped)
            
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
        self.assertState('startTimelineElement()', State.inited, State.stopped)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        if not len(self.elt):
            self.setState(State.stopped)
            return
        self._currentChild = self.elt[0]
        self.document.schedule(self._currentChild.delegate.startTimelineElement)
        nextChild = self._nextChild()
        if nextChild is not None:
            self.document.schedule(nextChild.delegate.initTimelineElement)
                    
    def stopTimelineElement(self):
        self.assertState('stopTimelineElement()', State.inited, State.started)
        self.setState(State.stopping)
        if self._currentChild is not None:
            self.document.schedule(self._currentChild.delegate.stopTimelineElement)
        
#     def terminate(self):
#         self.assertState('terminate()', State.stopped)
#         self.setState(State.terminating)
#         if self._currentChild is not None:
#             self.document.schedule(self._currentChild.delegate.terminate)
#         # xxxjack: do anything about nextChild?
#         self.setState(State.idle)

    def _nextChild(self):
        foundCurrent = False
        for ch in self.elt:
            if foundCurrent: return ch
            foundCurrent = (ch == self._currentChild)
        return None
    
class RefDelegate(TimeElementDelegate):
    EXACT_CHILD_COUNT=0

    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited, State.stopped)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.setState(State.started)
        self.document.report('>', 'START', self.document.getXPath(self.elt), self._getParameters())
        # XXXJACK test code. Assume text/image nodes finish straight away, masterVideo takes forever and others take 42 seconds
        cl = self.elt.get(NS_2IMMERSE("class"), "unknown")
        if cl == "masterVideo":
            return
        dur = 42
        if cl == "text" or cl == "image": 
            dur = 0
        self.clock.schedule(dur, self._done)
               
    def _done(self):
        self.document.report('<', 'stopped', self.document.getXPath(self.elt))
        self.setState(State.stopped)

    def stopTimelineElement(self):
        self.document.report('>', 'STOP', self.document.getXPath(self.elt), self._getParameters())
        TimeElementDelegate.stopTimelineElement(self)
        
    def _getParameters(self):
        rv = {}
        for k in self.elt.attrib:
            if k in NS_2IMMERSE:
                rv[NS_2IMMERSE.localTag(k)] = self.elt.attrib[k]
        return rv
        
class ConditionalDelegate(SingleChildDelegate):
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("expr")
        }

    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited, State.stopped)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.document.report('COND', True, self.document.getXPath(self.elt))
        self.document.schedule(self.elt[0].delegate.startTimelineElement)
        
class SleepDelegate(TimeElementDelegate):
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("dur")
        }

    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited, State.stopped)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.setState(State.started)
        self.document.report('SLEEP0', self.elt.get(NS_TIMELINE("dur")), self.document.getXPath(self.elt))
        dur = self.parseDuration(self.elt.get(NS_TIMELINE("dur")))
        self.clock.schedule(dur, self._done)
        
    def _done(self):
        self.document.report('SLEEP1', self.elt.get(NS_TIMELINE("dur")), self.document.getXPath(self.elt))
        self.setState(State.stopped)
    
    def parseDuration(self, dur):
        try:
            return float(dur)
        except ValueError:
            pass
        tval = time.strptime(dur, "%H:%M:%S")
        return tval.tm_sec + 60*(tval.tm_min+60*tval.tm_hour)
        
class WaitDelegate(TimelineDelegate):
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("event")
        }
        
    def startTimelineElement(self):
        self.assertState('startTimelineElement()', State.inited, State.stopped)
        self.assertDescendentState('startTimelineElement()', State.idle, State.inited)
        self.setState(State.starting)
        self.document.report('WAIT0', self.elt.get(NS_TIMELINE("event")), self.document.getXPath(self.elt))
        self.setState(State.started)
        self.document.report('WAIT1', self.elt.get(NS_TIMELINE("event")), self.document.getXPath(self.elt))
        self.setState(State.stopped)
    
    
DELEGATE_CLASSES = {
    NS_TIMELINE("document") : DocumentDelegate,
    NS_TIMELINE("par") : ParDelegate,
    NS_TIMELINE("seq") : SeqDelegate,
    NS_TIMELINE("ref") : RefDelegate,
    NS_TIMELINE("conditional") : ConditionalDelegate,
    NS_TIMELINE("sleep") : SleepDelegate,
    NS_TIMELINE("wait") : WaitDelegate,
    }
    
class Document:
    RECURSIVE = False
        
    def __init__(self, clock):
        self.tree = None
        self.root = None
        self.clock = clock
        self.parentMap = {}
        self.toDo = []
        self.delegateClasses = {}
        self.delegateClasses.update(DELEGATE_CLASSES)
        
    def setDelegateFactory(self, klass, tag=NS_TIMELINE("ref")):
        self.delegateClasses[tag] = klass
        
    def load(self, url):
        fp = urllib.urlopen(url)
        self.tree = ET.parse(fp)
        self.root = self.tree.getroot()
        self.parentMap = {c:p for p in self.tree.iter() for c in p}        
        
    def getParent(self, elt):
        return self.parentMap.get(elt)
        
    def getXPath(self, elt):
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
        for elt in self.tree.iter():
            elt.delegate.storeStateForSave()
        self.tree.write(fp)
        fp.write('\n')
        
    def addDelegates(self):
        for elt in self.tree.iter():
            if not hasattr(elt, 'delegate'):
                klass = self._getDelegate(elt.tag)
                elt.delegate = klass(elt, self, self.clock)
                elt.delegate.checkAttributes()
                elt.delegate.checkChildren()
                
    def _getDelegate(self, tag):
        if not tag in NS_TIMELINE:
                return DummyDelegate
        return self.delegateClasses.get(tag, ErrorDelegate)
            
    def run(self):
        self.schedule(self.root.delegate.initTimelineElement)
        if not self.RECURSIVE:
            self.runloop(State.inited)
        self.clock.start()
        self.schedule(self.root.delegate.startTimelineElement)
        if not self.RECURSIVE:
            self.runloop(State.stopped)       
            
    def schedule(self, callback, *args, **kwargs):
        self.report('EMIT', callback.__name__, self.getXPath(callback.im_self.elt))
        if self.RECURSIVE:
            callback(*args, **kwargs)
        else:
            self.toDo.append((callback, args, kwargs))
            
    def runloop(self, stopstate):
        assert not self.RECURSIVE
        while not self.root.delegate.state == stopstate:
            if len(self.toDo):
                callback, args, kwargs = self.toDo.pop(0)
                callback(*args, **kwargs)
            else:
                self.clock.sleepUntilNextEvent()
                self.clock.handleEvents(self)
        assert len(self.toDo) == 0, 'events not handled: %s' % repr(self.toDo)

    def report(self, event, verb, *args):
        args = reduce((lambda h, t: str(h) + ' ' + str(t)), args)
        if DEBUG: print '%8.3f %-8s %-22s %s' % (self.clock.now(), event, verb, args)
    
class ProxyClockService:
    def __init__(self, sysclock=time):
        self.epoch = 0
        self.running = False
        self.queue = Queue.PriorityQueue()
        self.sysclock = sysclock

    def now(self):
        if not self.running:
            return self.epoch
        return self.sysclock.time() - self.epoch

    def start(self):
        if not self.running:
            self.epoch = self.sysclock.time() - self.epoch
            self.running = True

    def stop(self):
        if self.running:
            self.epoch = self.sysclock.time() - self.epoch
            self.running = False
            
    def wait(self):
        pass

    def sleepUntilNextEvent(self):
        try:
            peek = self.queue.get(False)
        except Queue.Empty:
            assert 0, "No events are forthcoming"
        assert peek, "No events are forthcoming"
        self.queue.put(peek)
        t, callback, args, kwargs = peek
        delta = t-self.now()
        if delta > 0:
            self.sysclock.sleep(delta)
        
    def schedule(self, delay, callback, *args, **kwargs):
        assert not self.queue.full()
        self.queue.put((self.now()+delay, callback, args, kwargs))
        
    def handleEvents(self, handler):
        while True:
            try:
                peek = self.queue.get(False)
            except Queue.Empty:
                return
            if not peek: return
            t, callback, args, kwargs = peek
            if self.now() >= t:
                handler.schedule(callback, *args, **kwargs)
            else:
                assert not self.queue.full()
                self.queue.put(peek)
                return
       
class FastClock:
    def __init__(self):
        self.now = 0
        
    def time(self):
        return self.now
        
    def sleep(self, duration):
        self.now += duration
             
def main():
    global DEBUG
    parser = argparse.ArgumentParser(description="Test runner for timeline documents")
    parser.add_argument("document", help="The XML timeline document to parse and run")
    parser.add_argument("--debug", action="store_true", help="Print detailed state machine progression output")
    parser.add_argument("--dump", action="store_true", help="Dump document to stdout on exceptions and succesful termination")
    parser.add_argument("--fast", action="store_true", help="Use fast-forward clock in stead of realtime clock")
    args = parser.parse_args()
    DEBUG = args.debug
    
    if args.fast:
        clock = ProxyClockService(FastClock())
    else:
        clock = ProxyClockService()
    
    d = Document(clock)
    try:
        d.load(args.document)
        d.addDelegates()
#         if args.dump:
#             d.dump(sys.stdout)
#             print '--------------------'
        d.run()
    finally:
        if args.dump:
            print '--------------------'
            d.dump(sys.stdout)
    
if __name__ == '__main__':
    main()
