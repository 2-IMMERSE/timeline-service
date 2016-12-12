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

def genDocument():
    root = ET.Element(NS_TIMELINE("document"))
    tree = ET.ElementTree(root)
    topPar = ET.Element(NS_TIMELINE("par"))
    root.append(topPar)
    
    return tree, topPar
    
