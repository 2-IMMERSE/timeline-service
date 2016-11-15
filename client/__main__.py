import sys
import os
import argparse
import application
import webbrowser
import urlparse

DEFAULT_LAYOUT="https://layout-service.2immerse.advdev.tv/layout/v2"
DEFAULT_TIMELINE="https://timeline-service.2immerse.advdev.tv/timeline/v1"

KIBANA_URL="https://2immerse.advdev.tv/kibana/app/kibana#/discover/All-2-Immerse-prefixed-logs-without-Websocket-Service?_g=(refreshInterval:(display:'10%%20seconds',pause:!f,section:1,value:10000),time:(from:now-15m,mode:quick,to:now))&_a=(columns:!(sourcetime,source,subSource,verb,logmessage,contextID,message),filters:!(),index:'logstash-*',interval:auto,query:(query_string:(analyze_wildcard:!t,query:'rawmessage:%%22%%2F%%5E2-Immerse%%2F%%22%%20AND%%20NOT%%20source:%%22WebsocketService%%22%%20AND%%20contextID:%%22%s%%22')),sort:!(sourcetime,desc))"

LAYOUTRENDERER_URL='file://%s#contextID=%%s' % os.path.realpath(os.path.join(os.path.dirname(__file__), '../../layout-service/renderer/render.html'))

def context_for_tv(layoutServiceURL):
    caps = dict(
        displayWidth=1920, 
        displayHeight=1080,
        audioChannels=1,
        concurrentVideo=1,
        touchInteraction=False,
        communalDevice=True,
        orientations=["landscape"],
        deviceType="TV",
        )
    context = application.Context("TV", caps)

    context.create(layoutServiceURL)
    return context

def dmapp_for_tv(context, layoutServiceURL, timelineServiceURL, tsserver, timelineDocUrl, layoutDocUrl):
    appSettings = dict(
        timelineDocUrl=timelineDocUrl,
        timelineServiceUrl=timelineServiceURL,
        extLayoutServiceUrl=layoutServiceURL,  # For now: the layout service cannot determine this itself....
        layoutReqsUrl=layoutDocUrl
        )
    dmapp = context.createDMApp(appSettings)
    if tsserver:
        dmapp.selectClock(dict(contentId='dvb://233a.1004.1044;363a~20130218T0915Z--PT00H45M', timelineSelector='urn:dvb:css:timeline:pts', host=tsserver, port=7681))
    else:
        dmapp.selectClock({})
    return dmapp
    
def dmapp_for_handheld(layoutServiceContextURL, tsclient):
    caps = dict(
        displayWidth=720, 
        displayHeight=1280,
        audioChannels=2,
        concurrentVideo=2,
        touchInteraction=True,
        communalDevice=False,
        orientations=['landscape', 'portrait'],
        deviceType="handheld",
        )
    context = application.Context("handheld", caps)
    context.join(layoutServiceContextURL)
    dmapp = context.getDMApp()
    if tsclient:
        dmapp.selectClock(dict(tsUrl=tsclient, contentIDStem="dvb:", timelineSelector='urn:dvb:css:timeline:pts'))
    else:
        dmapp.selectClock({})
    return dmapp
    
def main():
    parser = argparse.ArgumentParser(description="Run 2immerse test client app, as tv or handheld")
    parser.add_argument('--tsserver', metavar="HOST", help="Run DVB TSS server on IP-address HOST, port 7681 (usually tv only)")
    parser.add_argument('--tsclient', metavar="URL", help="Contact DVB TSS server on URL, for example ws://127.0.0.1:7681/ts (usually handheld only)")
    parser.add_argument('--layoutServer', metavar="URL", help="Create context and app at layout server endpoint URL (default: %s)" % DEFAULT_LAYOUT, default=DEFAULT_LAYOUT)
    parser.add_argument('--layoutDoc', metavar="URL", help="Layout document")
    parser.add_argument('--timelineServer', metavar="URL", help="Tell layout server about timeline server endpoint URL (default: %s)" % DEFAULT_TIMELINE, default=DEFAULT_TIMELINE)
    parser.add_argument('--timelineDoc', metavar="URL", help="Timeline document")
    parser.add_argument('--context', metavar="URL", help="Connect to layout context at URL (usually handheld only)")
    parser.add_argument('--kibana', action="store_true", help="Open a browser window with the Kibana log for this run (tv only)")
    parser.add_argument('--layoutRenderer', action="store_true", help="Open a browser window that renders the layout for this run (tv only)")
    
    args = parser.parse_args()
    if args.context:
        # Client mode.
        if args.layoutServer or args.timelineServer:
            print "Specify either --context (handheld) or both --layoutServer and --timelineServer (tv)"
            sys.exit(1)
        dmapp = dmapp_for_handheld(args.context, args.tsclient)
    else:
        if not args.layoutServer or not args.timelineServer:
            print "Specify either --context (handheld) or both --layoutServer and --timelineServer (tv)"
            sys.exit(1)
            
        if not args.layoutDoc:
            print "Must specify --layoutDoc"
            sys.exit(1)
        # Sanity check that all URLs are correct
        up = urlparse.urlparse(args.layoutServer)
        if not up.scheme in {'http', 'https'}:
            print 'Only absolute http/https URL allowed:', args.layoutServer
            sys.exit(1)
        up = urlparse.urlparse(args.timelineServer)
        if not up.scheme in {'http', 'https'}:
            print 'Only absolute http/https URL allowed:', args.timelineServer
            sys.exit(1)
        up = urlparse.urlparse(args.layoutDoc)
        if not up.scheme in {'http', 'https'}:
            print 'Only absolute http/https URL allowed:', args.layoutDoc
            sys.exit(1)
        if args.timelineDoc:
            up = urlparse.urlparse(args.timelineDoc)
            if not up.scheme in {'http', 'https'}:
                print 'Only absolute http/https URL allowed:', args.timelineDoc
                sys.exit(1)
        context = context_for_tv(args.layoutServer)

        if args.kibana:
            kibana_url = KIBANA_URL % context.contextId
            webbrowser.open(kibana_url)
        
        if args.layoutRenderer:
            renderer_url = LAYOUTRENDERER_URL % context.contextId
            print 'xxxjack', renderer_url
            webbrowser.open(renderer_url)
            
        tsargsforclient = ""
        if args.tsserver:
            tsargsforclient = "--tsclient ws://%s:7681/ts" % args.tsserver
        print 'For handheld(s) run: %s %s --context %s' % (sys.argv[0], tsargsforclient, context.layoutServiceContextURL)
        print
        print 'Press return when done -',
        _ = sys.stdin.readline()
        
        dmapp = dmapp_for_tv(context, args.layoutServer, args.timelineServer, args.tsserver, args.timelineDoc, args.layoutDoc)
            
    dmapp.start()
    dmapp.wait()

main()
