from __future__ import print_function
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
import sys
import urllib.request, urllib.parse, urllib.error

#
# Specific for 2immerse, needs to be updated as DMApp Component Classes are added and extended.
#
REQUIRED_TIC_ATTRIBUTES={
    "video" : ["mediaUrl"],
    "audio" : ["mediaUrl"],
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
    "AdobeAnimationDMAppComponent" : ["mediaUrl", "animProp"],
    "PostTimelineEventButtonComponent" : ["text", "eventId"],

    "MotoGpSpooler" : [],
    "MotoGpPictureInPicture" : ["spoolerComponent"],
    "HtmlSnippetDMAppComponent" : ["html"],
    "MotoGpLeaderboard" : ["spoolerComponent"],
    "MotoGpLapsRemaining" : ["spoolerComponent"],
    "MotoGPInfoEndResultDMAppComponent" : ["spoolerComponent"],
    "MotoGPBattleForDMAppComponent" : [],
    "MotoGPBattleForMultiDMAppComponent" : ["spoolerComponent"],
    "MotoGPLeadingGroupDMAppComponent" : ["spoolerComponent"],
    "MotoGPFastestLapDMAppComponent" : ["spoolerComponent", "num"],
    "MotoGPInfoOnboardDMAppComponent" : ["spoolerComponent"],
    "MotoGPInfoRiderDMAppComponent" : ["spoolerComponent"],
    "GoogleAnalyticsDMAppComponent" : [],
    "MotoGpCompanionControlPanel" : ["spoolerComponent"],
    "MotoGpCompanionPanelSwitcher" : [],
    "MotoGpCompanionTopBar" : ["spoolerComponent"],
    "MotoGpCompanionStats" : ["spoolerComponent"],
    }

ALLOWED_TIC_ATTRIBUTES={
    "video" : ["mediaUrl", "auxMediaUrl", "muted", "offset", "startMediaTime", "syncMode", "showControls", "__elementClass", "__writeTimingSignal", "selfDestructOnMediaEnd"],
    "audio" : ["mediaUrl", "auxMediaUrl", "offset", "startMediaTime", "syncMode", "volumeSignal"],
    "scroll-text" : ["scriptUrl", "clipMapUrl", "clipId", "offset"],
    "timed-text" : [],
    "title-card" : ["title", "author", "synopsis", "brandImageUrl", "brand", "posterUrl"],
    "article" : ["mediaUrl", "markdown", "position", "groupStateId"],
    "article-controls" : ["groupStateId"],
    "image" : ["mediaUrl", "objectFit", "caption", "groupStateId"],
    "text-chat" : ["lobby", "groupStateId"],
    "text-chat-controls" : ["lobby", "groupStateId"],
    "video-chat" : ["lobby", "groupStateId"],
    "video-chat-view" : ["groupStateId"],
    "video-chat-controls" : ["groupStateId"],
    "component-switcher" : ["articlegroupid", "imagegroupid", "videogroupid"],
    "FallbackClock" : ["syncMode", "offset", "startMediaTime"],
    "AdobeAnimationDMAppComponent" : ["mediaUrl", "animProp", "reportAnimDuration", "onRunning", "__notRunnableBeforeTime"],
    "PostTimelineEventButtonComponent" : ["text", "eventId"],
    
    "MotoGpSpooler" : ["xmlManifestDir", "dataOffsetMs"],
    "MotoGpPictureInPicture" : ["localConfig", "localModeConfig", "spoolerComponent"],
    "HtmlSnippetDMAppComponent" : ["html", "className"],
    "MotoGpLeaderboard" : ["localModeConfig", "spoolerComponent"],
    "MotoGpLapsRemaining" : ["spoolerComponent"],
    "MotoGPInfoEndResultDMAppComponent" : ["spoolerComponent"],
    "MotoGPBattleForDMAppComponent" : ["number"],
    "MotoGPBattleForMultiDMAppComponent" : ["spoolerComponent", "showTyres", "riders", "pos"],
    "MotoGPLeadingGroupDMAppComponent" : ["spoolerComponent"],
    "MotoGPFastestLapDMAppComponent" : ["spoolerComponent", "num"],
    "MotoGPInfoOnboardDMAppComponent" : ["spoolerComponent", "num"],
    "MotoGPInfoRiderDMAppComponent" : ["spoolerComponent", "num"],
    "GoogleAnalyticsDMAppComponent" : [],
    
    "MotoGpCompanionControlPanel" : ["spoolerComponent", "eventsOffset", "eventsUrl", "localPipConfig", "localTyreConfig", "localTyreConfig"],
    "MotoGpCompanionPanelSwitcher" : [],
    "MotoGpCompanionTopBar" : ["spoolerComponent", "localPipConfig"],
    "MotoGpCompanionStats" : ["spoolerComponent"],
    
    
    }

def checkAttributes(self):
    className = self.elt.get(NS_2IMMERSE("class"))
    if not NS_2IMMERSE("class") in list(self.elt.keys()):
        print("* Warning: element", self.getXPath(), "misses expected tim:class attribute", file=sys.stderr)
    if not NS_XML("id") in list(self.elt.keys()):
        print("* Warning: element", self.getXPath(), "misses expected xml:id attribute", file=sys.stderr)
    if not NS_2IMMERSE("url") in list(self.elt.keys()):
        if className not in ("video", "audio"):   # Video is the only one that doesn't need a tim:url
            print("* Warning: element", self.getXPath(), "misses expected tim:url attribute", file=sys.stderr)
    else:
        url = self.elt.get(NS_2IMMERSE("url"))
        url = urllib.basejoin(self.document.url, url)
        if url[:5] != 'file:':
            try:
                fp = urllib.request.urlopen(url)
                del fp
            except IOError:
                print("* Warning: element", self.getXPath(), "has tim:url", url, "which may not exist", file=sys.stderr)
        
    if not className in REQUIRED_TIC_ATTRIBUTES:
        print("* Warning: element", self.getXPath(), "has unknown tim:class", className, file=sys.stderr)
        return
    requiredAttributes = REQUIRED_TIC_ATTRIBUTES[className]
    allowedAttributes = ALLOWED_TIC_ATTRIBUTES[className]
    for attrName in requiredAttributes:
        if not NS_2IMMERSE_COMPONENT(attrName) in list(self.elt.keys()):
            print("* Warning: element", self.getXPath(), "of tim:class", className, "misses expected attribute tic:"+attrName, file=sys.stderr)
    for attrName in list(self.elt.keys()):
        if attrName in NS_2IMMERSE_COMPONENT:
            if not NS_2IMMERSE_COMPONENT.localTag(attrName) in allowedAttributes:
                print("* Warning: element", self.getXPath(), "of tim:class", className, "has unexpected attribute tic:"+NS_2IMMERSE_COMPONENT.localTag(attrName), file=sys.stderr)
