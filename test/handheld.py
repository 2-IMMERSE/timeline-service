import sys
import time
import requests
import pprint

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

DEVICE_ID="handheld"

if len(sys.argv) != 2:
    print 'Usage: %s layoutServiceContextURL' % sys.argv[0]
    sys.exit(1)
else:
	layoutServiceContextUrl = sys.argv[1]


# Join the context
print 'Joining context at the layout service'
r = requests.post(layoutServiceContextUrl+"/devices", params=dict(reqDeviceId=DEVICE_ID), 
# 	json=dict(
# 		displayWidth=1920, 
# 		displayHeight=1080,
# 		audioChannels=1,
# 		concurrentVideo=1,
# 		touchInteraction=True,
# 		sharedDevice=True
# 		)
		)
if r.status_code not in (requests.codes.ok, requests.codes.created):
    print 'Error', r.status_code
    print r.text
    r.raise_for_status()
reply = r.json()   # XXXJACK the [0] may be a bug workaround
contextId = reply["contextId"]
print "contextId:", contextId

print 'DMAppId?',
sys.stdout.flush()
dmappId = sys.stdin.readline().strip()
print 'DMAppId:', dmappId

# Check what is happening by polling the layout service
print 'Check status every second'
pp = pprint.PrettyPrinter()
status_for_component = {}
last_status_report_for_component = {}
epoch = None
while True:
    print 'Get status for', DEVICE_ID
    r = requests.get(layoutServiceContextUrl + '/dmapp/' + dmappId, params=dict(reqDeviceId=DEVICE_ID))
    if r.status_code not in (requests.codes.ok, requests.codes.created):
        print 'Error', r.status_code
        print r.text
        r.raise_for_status()
    reply = r.json()
    # Start the "clock" running, if it isn't already
    if epoch == None:
        epoch = time.time()
    #pp.pprint(reply)
    # Iterate over all components, see which ones are new
    for comp in reply['components']:
        componentId = comp['componentId']
        if not componentId in status_for_component:
            status_for_component[componentId] = None 
            last_status_report_for_component[componentId] = comp
            print 'New component:', componentId
            # Status will be reported further down
        elif comp != last_status_report_for_component[componentId]:
            print 'Status report changed for component:', componentId
            last_status_report_for_component[componentId] = comp
    # Iterate over all components, see which ones have a new status
    for componentId in status_for_component.keys():
        startTime = last_status_report_for_component[componentId]['startTime']
        if startTime: startTime = float(startTime)
        stopTime = last_status_report_for_component[componentId]['stopTime']
        if stopTime: stopTime = float(stopTime)
        now = time.time() - epoch
        if stopTime != None and now >= stopTime:
            newStatus = "stopped"
        elif startTime != None and now >= startTime:
            newStatus = "started"
        else:
            newStatus = "inited"
        if newStatus != status_for_component[componentId]:
            status_for_component[componentId] = newStatus 
            print 'Status for', componentId, 'is now', status_for_component[componentId]
            # Report status for new component
            r = requests.post(layoutServiceContextUrl + '/dmapp/' + dmappId + '/component/' + componentId + '/actions/status', params=dict(reqDeviceId=DEVICE_ID),
                    json=dict(status=status_for_component[componentId]))
            if r.status_code not in (requests.codes.ok, requests.codes.no_content, requests.codes.created):
                print 'Error', r.status_code
                print r.text
                r.raise_for_status()
        else:
            pass # print 'Status for', componentId, 'is still', status_for_component[componentId], (now, startTime, stopTime)

    print
    time.sleep(1)

