import sys
import urllib
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
NS_2IMMERSE = NameSpace("tim", "http://jackjansen.nl/2immerse")
NAMESPACES = {}
NAMESPACES.update(NS_TIMELINE.ns())
NAMESPACES.update(NS_2IMMERSE.ns())

class State:
    idle = "idle"
    initing = "initing"
    inited = "inited"
    starting = "starting"
    started = "started"
    stopping = "stopping"
    stopped = "stopped"
    terminating = "terminating"
    
class DummyDelegate:
    def __init__(self, elt, document):
        self.elt = elt
        self.document = document
        self.state = State.idle
        
    def __repr__(self):
        return 'Delegate(%s)' % self.document.getXPath(self.elt)
        
    def checkAttributes(self):
        pass
        
    def checkChildren(self):
        pass
        
    def setState(self, state):
        if DEBUG: print self, ': new state', state
        self.state = state
        parentElement = self.document.getParent(self.elt)
        #print 'xxxjack parent is', parentElement
        if parentElement is not None:
            parentElement.delegate.reportChildState(self.elt, self.state)
            
    def reportChildState(self, child, childState):
        pass
        
    def init(self):
        assert self.state == State.idle
        self.setState(State.initing)
        self.setState(State.inited)
        
    def start(self):
        assert self.state == State.inited
        self.setState(State.starting)
        #self.setState(State.started)
        #self.setState(State.stopping)
        self.setState(State.stopped)
        
    def stop(self):
        assert self.state in {State.inited, State.started}
        self.setState(State.stopping)
        self.setState(State.stopped)
        
    def terminate(self):
        assert self.state == State.stopped
        self.setState(State.terminating)
        self.setState(State.idle)
        
class ErrorDelegate(DummyDelegate):
    def __init__(self, elt):
        DummyDelegate.__init__(self, elt)
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
                    
    def checkChildren(self):
        if not self.EXACT_CHILD_COUNT is None and len(self.elt) != self.EXACT_CHILD_COUNT:
            print >>sys.stderr, "* Error: element", self.elt.tag, "expects", self.EXACT_CHILD_COUNT, "children but has", len(self.elt)
        if not self.ALLOWED_CHILDREN is None:
            for child in self.elt:
                if child.tag in NS_2IMMERSE and not child.tag in self.ALLOWED_CHILDREN:
                    print >>sys.stderr, "* Error: element", self.elt.tag, "cannot have child of type", child.tag
         
class SingleChildDelegate(TimelineDelegate):
    EXACT_CHILD_COUNT=1

    def init(self):
        assert self.state == State.idle
        self.setState(State.initing)
        self.elt[0].delegate.init()
        self.setState(State.inited)
        
    def start(self):
        assert self.state == State.inited
        self.setState(State.starting)
        self.elt[0].delegate.start()
        self.setState(State.started)
        
    def stop(self):
        assert self.state in {State.inited, State.started}
        self.setState(State.stopping)
        self.elt[0].delegate.stop()
        self.setState(State.stopped)
        
    def terminate(self):
        assert self.state == State.stopped
        self.setState(State.terminating)
        self.elt[0].delegate.terminate()
        self.setState(State.idle)

class DocumentDelegate(SingleChildDelegate):
    ALLOWED_CHILDREN={
        NS_TIMELINE("par"),
        NS_TIMELINE("seq"),
        }

class TimeElementDelegate(TimelineDelegate):
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("prio")
        }
        
class ParDelegate(TimeElementDelegate):
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("end"),
        NS_TIMELINE("sync"),
        }
        
    def init(self):
        assert self.state == State.idle
        self.setState(State.initing)
        for child in self.elt: child.delegate.init()
        self.setState(State.inited)
        
    def start(self):
        assert self.state == State.inited
        self.setState(State.starting)
        for child in self.elt: child.delegate.start()
        self.setState(State.started)
        
    def stop(self):
        assert self.state in {State.inited, State.started}
        self.setState(State.stopping)
        for child in self.elt: child.delegate.stop()
        self.setState(State.stopped)
        
    def terminate(self):
        assert self.state == State.stopped
        self.setState(State.terminating)
        for child in self.elt: child.delegate.terminate()
        self.setState(State.idle)

class SeqDelegate(TimeElementDelegate):
    pass
    
class RefDelegate(TimeElementDelegate):
    EXACT_CHILD_COUNT=0
    pass
    
class ConditionalDelegate(SingleChildDelegate):
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("expr")
        }

    def start(self):
        assert self.state == State.inited
        self.setState(State.starting)
        print 'xxxjack assuming expr is True for', self
        self.elt[0].delegate.start()
        self.setState(State.started)
        
class SleepDelegate(TimeElementDelegate):
    ALLOWED_ATTRIBUTES = TimeElementDelegate.ALLOWED_ATTRIBUTES | {
        NS_TIMELINE("dur")
        }
    
class WaitDelegate(TimelineDelegate):
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("event")
        }
    
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
        
    def __init__(self):
        self.tree = None
        self.root = None
        self.parentMap = {}
        
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
        self.tree.write(fp)
        
    def addDelegates(self):
        for elt in self.tree.iter():
            if not hasattr(elt, 'delegate'):
                klass = self._getDelegate(elt.tag)
                elt.delegate = klass(elt, self)
                elt.delegate.checkAttributes()
                elt.delegate.checkChildren()
                
    def _getDelegate(self, tag):
        if not tag in NS_TIMELINE:
                return DummyDelegate
        return DELEGATE_CLASSES.get(tag, ErrorDelegate)
            
    def run(self):
        self.root.delegate.init()
        self.root.delegate.start()
            
        
def main():
    d = Document()
    d.load(sys.argv[1])
    d.addDelegates()
    d.dump(sys.stdout)
    print '--------------------'
    d.run()
    
if __name__ == '__main__':
    main()
