import sys
import argparse
import application

def dmapp_for_tv(layoutServiceURL, timelineServiceURL, tsserver):
    caps = dict(
        displayWidth=1920, 
        displayHeight=1080,
        audioChannels=1,
        concurrentVideo=1,
        touchInteraction=False,
        sharedDevice=True,
        orientations=["landscape"]
        )
    context = application.Context("TV", caps)
    context.create(layoutServiceURL)
    appSettings = dict(
        timelineDocUrl="http://example.com/2immerse/timeline.json",
        timelineServiceUrl=timelineServiceURL,
        extLayoutServiceUrl=layoutServiceURL,  # For now: the layout service cannot determine this itself....
        layoutReqsUrl="http://example.com/2immerse/layout.json"
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
        sharedDevice=False,
        orientations=['landscape', 'portrait']
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
    parser.add_argument('--layout', metavar="URL", help="Create context and app at layout server endpoint URL (usually tv only)")
    parser.add_argument('--timeline', metavar="URL", help="Tell layout server about timeline server endpoint URL (usually tv only)")
    parser.add_argument('--context', metavar="URL", help="Connect to layout context at URL (usually handheld only)")
    args = parser.parse_args()
    if args.context:
        # Client mode.
        if args.layout or args.timeline:
            print "Specify either --context (handheld) or both --layout and --timeline (tv)"
            sys.exit(1)
        dmapp = dmapp_for_handheld(args.context, args.tsclient)
    else:
        if not args.layout or not args.timeline:
            print "Specify either --context (handheld) or both --layout and --timeline (tv)"
            sys.exit(1)
        dmapp = dmapp_for_tv(args.layout, args.timeline, args.tsserver)
        tsargsforclient = ""
        if args.tsserver:
            tsargsforclient = "--tsclient ws://%s:7681/ts" % args.tsserver
        print 'For handheld run: %s %s --context %s' % (sys.argv[0], tsargsforclient, dmapp.context.layoutServiceContextURL)
    dmapp.start()
    dmapp.wait()

main()
