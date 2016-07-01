import application
import sys

def dmapp_for_tv(layoutServiceURL, timelineServiceURL):
    caps = dict(
        displayWidth=1920, 
        displayHeight=1080,
        audioChannels=1,
        concurrentVideo=1,
        touchInteraction=False,
        sharedDevice=True
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
    return dmapp
    
def dmapp_for_handheld(layoutServiceContextURL):
    caps = dict(
        displayWidth=720, 
        displayHeight=1280,
        audioChannels=2,
        concurrentVideo=2,
        touchInteraction=True,
        sharedDevice=False
        )
    context = application.Context("handheld", caps)
    context.join(layoutServiceContextURL)
    dmapp = context.getDMApp()
    return dmapp
    
def main():
    if len(sys.argv) == 3:
        dmapp = dmapp_for_tv(sys.argv[1], sys.argv[2])
        print 'For handheld run: %s %s' % (sys.argv[0], dmapp.context.layoutServiceContextURL)
    elif len(sys.argv) == 2:
        dmapp = dmapp_for_handheld(sys.argv[1])
    else:
        print 'Usage for TV: %s layoutServiceURL timelineServiceURL' % sys.argv[0]
        print 'Usage for Handheld: %s layoutServiceContextURL' % sys.argv[0]
        sys.exit(1)
    dmapp.start()
    dmapp.wait()

main()
