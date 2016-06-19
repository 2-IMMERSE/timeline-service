import sys
import requests

DEBUG=False

if DEBUG:
	import httplib
	import logging
	httplib.HTTPConnection.debuglevel = 1

	# You must initialize logging, otherwise you'll not see debug output.
	logging.basicConfig()
	logging.getLogger().setLevel(logging.DEBUG)
	requests_log = logging.getLogger("requests.packages.urllib3")
	requests_log.setLevel(logging.DEBUG)
	requests_log.propagate = True

DEVICE_ID="4200"

if len(sys.argv) != 3:
	layoutService="http://layout-service.2immerse.advdev.tv/v1"
	timelineService="http://141.105.120.225:8080/timeline/v1"
    #print 'Usage: %s layoutservice timelineservice' % sys.argv[0]
    #sys.exit(1)
else:
	layoutService = sys.argv[1]
	timelineService = sys.argv[2]


# Create the context
r = requests.post(layoutService+"/context", params=dict(deviceId=DEVICE_ID), 
	json=dict(
		displayWidth=1920, 
		displayHeight=1080,
		audioChannels=1,
		concurrentVideo=1,
		touchInteraction=True,
		sharedDevice=True
		))
if r.status_code not in (requests.codes.ok, requests.codes.created):
    print 'Error', r.status_code
    print r.text
    r.raise_for_status()
reply = r.json()   # XXXJACK the [0] may be a bug workaround
contextId = reply["contextId"]
print "contextId:", contextId

# Wait
print 'Press return to create DMApp - ',
sys.stdin.readline()

# Create DMApp
r = requests.post(layoutService + '/context/' + contextId + '/dmapp', params=dict(deviceId=DEVICE_ID),
		json=dict(
			timelineDocUrl="http://example.com/2immerse/timeline.json",
			timelineServiceUrl=timelineService + '/' + contextId,
			layoutReqsUrl="http://example.com/2immerse/layout.json"))
if r.status_code not in (requests.codes.ok, requests.codes.created):
    print 'Error', r.status_code
    print r.text
    r.raise_for_status()
reply = r.json()
dmappId = reply["DMAppId"]
print 'dmappId:', dmappId

# Create it in the timeline service
if False and timelineService:
    r = requests.post(timelineService + '/' + contextId + '/loadDMAppTimeline', params=dict(timelineUrl="http://example.com/2immerse/timeline.json"))
    if r.status_code not in (requests.codes.ok, requests.codes.created):
        print 'Error', r.status_code
        print r.text
    r.raise_for_status()
    reply=r.json()
    
