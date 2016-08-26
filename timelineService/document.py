import sys
import urllib
import xml.etree.ElementTree as ET

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

NS_TIMELINE = NameSpace("tl", "http://jackjansen.nl/timelines")
NS_2IMMERSE = NameSpace("tim", "http://jackjansen.nl/2immerse")
NAMESPACES = {}
NAMESPACES.update(NS_TIMELINE.ns())
NAMESPACES.update(NS_2IMMERSE.ns())

class DummyDelegate:
    def __init__(self, elt):
        self.elt = elt
        self.state = "idle"
        
    def checkAttributes(self):
        pass
        
    def checkChildren(self):
        pass
        
    def setState(self, state):
        self.state = state
        
    def init(self):
        assert self.state == "idle"
        self.setState("inited")
        
    def start(self):
        assert self.state == "inited"
        self.setState("started")
        
    def stop(self):
        assert self.state in {"inited", "started"}
        self.setState("stopped")
        
    def terminate(self):
        assert self.state == "stopped"
        self.setState("idle")
        
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
            
class DocumentDelegate(TimelineDelegate):
    EXACT_CHILD_COUNT=1
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
        
class SeqDelegate(TimeElementDelegate):
    pass
    
class RefDelegate(TimeElementDelegate):
    EXACT_CHILD_COUNT=0
    pass
    
class ConditionalDelegate(TimelineDelegate):
    EXACT_CHILD_COUNT=1
    ALLOWED_ATTRIBUTES = {
        NS_TIMELINE("expr")
        }
        
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
        
    def load(self, url):
        fp = urllib.urlopen(url)
        self.tree = ET.parse(fp)
        self.root = self.tree.getroot()
        
    def dump(self, fp):
        self.tree.write(fp)
        
    def addDelegates(self):
        for elt in self.tree.iter():
            if not hasattr(elt, 'delegate'):
                klass = self._getDelegate(elt.tag)
                elt.delegate = klass(elt)
                elt.delegate.checkAttributes()
                elt.delegate.checkChildren()
                
    def _getDelegate(self, tag):
        if not tag in NS_TIMELINE:
                return DummyDelegate
        return DELEGATE_CLASSES.get(tag, ErrorDelegate)
            
            
        
def main():
    d = Document()
    d.load(sys.argv[1])
    d.addDelegates()
    d.dump(sys.stdout)
    
if __name__ == '__main__':
    main()
