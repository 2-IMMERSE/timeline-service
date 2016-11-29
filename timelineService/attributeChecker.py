import sys

#
# Specific for 2immerse, needs to be updated as DMApp Component Classes are added and extended.
#
REQUIRED_TIC_ATTRIBUTES={
    "video" : ["mediaUrl"],
    "scroll-text" : [],
    "timed-text" : [],
    "title-card" : [],
    "article" : [],
    "article-controls" : [],
    "image" : ["mediaUrl"],
    "text-chat" : [],
    "text-chat-controls" : [],
    "video-chat" : [],
    "video-chat-view" : [],
    "video-chat-controls" : [],
    "component-switcher" : [],
    "FallbackClock" : [],
    }

ALLOWED_TIC_ATTRIBUTES={
    "video" : ["mediaUrl", "offset", "startMediaTime", "syncMode", "showControls"],
    "scroll-text" : ["scriptUrl", "clipMapUrl", "clipId", "offset"],
    "timed-text" : [],
    "title-card" : ["title", "author", "synopsis", "brandImageUrl", "brand", "posterUrl"],
    "article" : ["mediaUrl", "markdown", "position", "groupStateId"],
    "article-controls" : ["groupStateId"],
    "image" : ["mediaUrl", "objectFit"],
    "text-chat" : ["lobby"],
    "text-chat-controls" : ["lobby"],
    "video-chat" : ["lobby", "groupStateId"],
    "video-chat-view" : ["groupStateId"],
    "video-chat-controls" : ["groupStateId"],
    "component-switcher" : ["groupStateId"],
    "FallbackClock" : ["syncMode", "offset", "startMediaTime"],
    }

def checkAttributes(self):
    if not NS_2IMMERSE("class") in self.elt.keys():
        print >>sys.stderr, "* Warning: element", self.getXPath(), "misses expected tim:class attribute"
    if not NS_2IMMERSE("dmappcid") in self.elt.keys():
        print >>sys.stderr, "* Warning: element", self.getXPath(), "misses expected tim:dmappcid attribute"
    className = self.elt.get(NS_2IMMERSE("class"))
    if not className in REQUIRED_TIC_ATTRIBUTES:
        print >>sys.stderr, "* Warning: element", self.getXPath(), "has unknown tim:class", className
        return
    requiredAttributes = REQUIRED_TIC_ATTRIBUTES[className]
    allowedAttributes = ALLOWED_TIC_ATTRIBUTES[className]
    for attrName in requiredAttributes:
        if not NS_2IMMERSE_COMPONENT(attrName) in self.elt.keys():
            print >>sys.stderr, "* Warning: element", self.getXPath(), "of tim:class", className, "misses expected attribute tic:"+attrName
    for attrName in self.elt.keys():
        if attrName in NS_2IMMERSE_COMPONENT:
            if not NS_2IMMERSE_COMPONENT.localTag(attrName) in allowedAttributes:
                print >>sys.stderr, "* Warning: element", self.getXPath(), "of tim:class", className, "has unexpected attribute tic:"+NS_2IMMERSE_COMPONENT.localTag(attrName)
