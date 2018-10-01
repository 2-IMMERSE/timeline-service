from __future__ import print_function
import sys
import os
import argparse
import application
import webbrowser
import urlparse
import logging
import subprocess

DEFAULT_LAYOUT="https://layout-service.2immerse.advdev.tv/layout/v3"
DEFAULT_TIMELINE="https://timeline-service.2immerse.advdev.tv/timeline/v1"
LOCAL_LAYOUT="http://%s:8000/layout/v3"
LOCAL_TIMELINE="http://%s:8080/timeline/v1"

KIBANA_URL="https://2immerse.advdev.tv/kibana/app/kibana#/discover/All-2-Immerse-prefixed-logs-without-Websocket-Service?_g=(refreshInterval:(display:'10%%20seconds',pause:!f,section:1,value:10000),time:(from:now-15m,mode:quick,to:now))&_a=(columns:!(sourcetime,source,subSource,verb,logmessage,contextID,message),filters:!(),index:'logstash-*',interval:auto,query:(query_string:(analyze_wildcard:!t,query:'rawmessage:%%22%%2F%%5E2-Immerse%%2F%%22%%20AND%%20NOT%%20source:%%22WebsocketService%%22%%20AND%%20contextID:%%22%s%%22')),sort:!(sourcetime,desc))"

LAYOUTRENDERER_URL="http://origin.2immerse.advdev.tv/test/layout-renderer/render.html?contextId=%s&layoutUrl=%s"

def context_for_tv(layoutServiceURL, deviceType=None, width=None, height=None):
    if width == None: width = 1920
    if height == None: height = 1080
    if deviceType == None:
        deviceType = "tv"
    caps = dict(
        displayWidth=width, 
        displayHeight=height,
        audioChannels=1,
        concurrentVideo=1,
        touchInteraction=False,
        communalDevice=True,
        orientations=["landscape"],
        deviceType=deviceType,
        )
    context = application.Context(deviceType, caps)

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
    
def context_for_handheld(layoutServiceContextURL, tsclient, deviceType=None, width=None, height=None):
    if deviceType == None:
        deviceType = "handheld"
    if width == None: width = 720
    if height == None: height = 1280
    caps = dict(
        displayWidth=width, 
        displayHeight=height,
        audioChannels=2,
        concurrentVideo=2,
        touchInteraction=True,
        communalDevice=False,
        orientations=['landscape', 'portrait'],
        deviceType=deviceType,
        )
    context = application.Context(deviceType, caps)
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
    parser.add_argument('--timelineServer', metavar="URL", help="Tell layout server about timeline server endpoint URL (default: %s)" % DEFAULT_TIMELINE, default=DEFAULT_TIMELINE)
    parser.add_argument('--localServers', metavar="HOST", help="Use layout and timeline service with default URLs on HOST")
    parser.add_argument('--layoutDoc', metavar="URL", help="Layout document")
    parser.add_argument('--timelineDoc', metavar="URL", help="Timeline document")
    parser.add_argument('--context', metavar="URL", help="Connect to layout context at URL (usually handheld only)")
    parser.add_argument('--kibana', action="store_true", help="Open a browser window with the Kibana log for this run (tv only)")
    parser.add_argument('--layoutRenderer', action="store_true", help="Open a browser window that renders the layout for this run (tv only)")
    parser.add_argument('--logLevel', action='store', help="Log level (default: INFO)", default="INFO")
    parser.add_argument('--wait', action='store_true', help='After creating the context wait for a newline, so other devices can be started (tv only)')
    parser.add_argument('--start', action='append', metavar='DEV', help='After creating the context, start another instance of %(prog)s for device DEV (tv only)')
    parser.add_argument('--dev', metavar='DEV', help='Use deviceId DEV (default: tv or handheld)')
    parser.add_argument('--width', type=int, metavar='W', help='Report device width as W (default 1920 for tv, 720 for handheld)')
    parser.add_argument('--height', type=int, metavar='H', help='Report device height as H (default 1080 for tv, 1280 for handheld)')
    parser.add_argument('--timeOffset', type=int, metavar='SEC', help='Start the document clock at SEC seconds into the video, to simulate late joining of a shared session (tv only)')
    
    args = parser.parse_args()
    
    logging.basicConfig()
    logger = logging.getLogger()
    #logger.setLevel(getattr(logging, args.logLevel))
    application.logLevel = getattr(logging, args.logLevel)
    logger.debug("client started")
    
    if args.localServers:
        args.layoutServer = LOCAL_LAYOUT % args.localServers
        args.timelineServer = LOCAL_TIMELINE % args.localServers
    if args.context:
        # Client mode.
        dmapp = context_for_handheld(args.context, args.tsclient, args.dev, width=args.width, height=args.height)
    else:
            
        if not args.layoutDoc:
            print("Must specify --layoutDoc")
            sys.exit(1)
        # Sanity check that all URLs are correct
        up = urlparse.urlparse(args.layoutServer)
        if not up.scheme in {'http', 'https'}:
            print('Only absolute http/https URL allowed:', args.layoutServer)
            sys.exit(1)
        up = urlparse.urlparse(args.timelineServer)
        if not up.scheme in {'http', 'https'}:
            print('Only absolute http/https URL allowed:', args.timelineServer)
            sys.exit(1)
        up = urlparse.urlparse(args.layoutDoc)
        if not up.scheme in {'http', 'https'}:
            print('Only absolute http/https URL allowed:', args.layoutDoc)
            sys.exit(1)
        if args.timelineDoc:
            up = urlparse.urlparse(args.timelineDoc)
            if not up.scheme in {'http', 'https'}:
                print('Only absolute http/https URL allowed:', args.timelineDoc)
                sys.exit(1)
        context = context_for_tv(args.layoutServer, args.dev, width=args.width, height=args.height)

        if args.kibana:
            kibana_url = KIBANA_URL % context.contextId
            webbrowser.open(kibana_url)
        
        if args.layoutRenderer:
            renderer_url = LAYOUTRENDERER_URL % (context.contextId, args.layoutServer)
            webbrowser.open(renderer_url)
            
        tsargsforclient = ""
        if args.tsserver:
            tsargsforclient = "--tsclient ws://%s:7681/ts" % args.tsserver
        print('For handheld(s) run: %s %s --context %s' % (sys.argv[0], tsargsforclient, context.layoutServiceContextURL))
        print()
        if args.start:
            for dev in args.start:
                cmd = ["python", sys.argv[0], "--context", context.layoutServiceContextURL, "--dev", dev, "--logLevel", args.logLevel]
                if args.tsserver:
                    cmd += ["--tsclient", "ws://%s:7681/ts" % args.tsserver]
                print('Starting:', ' '.join(cmd))
                p = subprocess.Popen(cmd)
        if args.wait:
            print('Press return when done -', end=' ')
            _ = sys.stdin.readline()
        
        dmapp = dmapp_for_tv(context, args.layoutServer, args.timelineServer, args.tsserver, args.timelineDoc, args.layoutDoc)
        if args.timeOffset:
            dmapp.clock.set(args.timeOffset)
            
    dmapp.start()
    dmapp.wait()

main()
