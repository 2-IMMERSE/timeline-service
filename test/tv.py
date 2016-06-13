import sys
import requests

DEVICE_ID="4200"

if len(sys.argv) != 3:
    print 'Usage: %s layoutservice timelineservice' % sys.argv[0]
    sys.exit(1)
    
layoutService = sys.argv[1]
timelineService = sys.argv[2]

# Create the context
r = requests.post(layoutService+"/context", params=dict(deviceId=DEVICE_ID), json=dict(displayWidth=1920, displayHeight=1080))
if r.status_code not in (requests.codes.ok, requests.codes.created):
    print 'Error', r.status_code
    print r.text
    r.raise_for_status()
reply = r.json()[0]   # XXXJACK the [0] may be a bug workaround
contextId = reply["contextId"]
print "contextId:", contextId

# Create it in the timeline service (until layout does this)
if timelineService:
    r = requests.post(timelineService, params=dict(contextId=contextId))
    if r.status_code not in (requests.codes.ok, requests.codes.created):
        print 'Error', r.status_code
        print r.text
    r.raise_for_status()
    reply=r.json()
    assert reply['contextId'] == contextId

# Wait
print 'Press return to create DMApp - ',
sys.stdin.readline()

# Create DMApp
r = requests.post(layoutService + '/context/' + contextId + '/dmapp', params=dict(deviceId=DEVICE_ID), json=dict(timelineUrl="http://example.com/2immerse/timeline.json", layoutReqsUrl="http://example.com/2immerse/layout.json"))
if r.status_code not in (requests.codes.ok, requests.codes.created):
    print 'Error', r.status_code
    print r.text
    r.raise_for_status()
reply = r.json()
dmappId = reply["DMAppId"]

# Create it in the timeline service
if timelineService:
    r = requests.post(timelineService + '/' + contextId + '/loadDMAppTimeline', params=dict(timelineUrl="http://example.com/2immerse/timeline.json"))
    if r.status_code not in (requests.codes.ok, requests.codes.created):
        print 'Error', r.status_code
        print r.text
    r.raise_for_status()
    reply=r.json()
    
