import requests
import requests
import time

class Context:
    def __init__(self, deviceId, caps):
        self.deviceId = deviceId
        self.caps = caps
        self.orientation = self.caps['orientations'][0]
        self.contextId = None
        self.layoutServiceContextURL = None
        
    def create(self, layoutServiceURL):
        r = requests.post(
                layoutServiceURL+"/context", 
                params=dict(reqDeviceId=self.deviceId, deviceId=self.deviceId, orientation=self.orientation), 
                json=self.caps
                )
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            print 'Error', r.status_code
            print r.text
            r.raise_for_status()
        reply = r.json()
        self.contextId = reply["contextId"]
        self.layoutServiceContextURL = layoutServiceURL + '/context/' + self.contextId

    def join(self, layoutServiceContextURL):
        self.layoutServiceContextURL = layoutServiceContextURL
        r = requests.post(
                self.layoutServiceContextURL+"/devices", 
                params=dict(reqDeviceId=self.deviceId, deviceId=self.deviceId, orientation=self.orientation), 
                json=self.caps
                )
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            print 'Error', r.status_code
            print r.text
            r.raise_for_status()
        reply = r.json()
        self.contextId = reply["contextId"]
        print "contextId:", self.contextId
        
    def createDMApp(self, urls):
        r = requests.post(
                self.layoutServiceContextURL + '/dmapp', 
                params=dict(reqDeviceId=self.deviceId),
                json=urls
                )
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            print 'Error', r.status_code
            print r.text
            r.raise_for_status()
        reply = r.json()
        dmappId = reply["DMAppId"]
        print 'dmappId:', dmappId
        return Application(self, dmappId, True)

    def getDMApp(self):
        r = requests.get(
                self.layoutServiceContextURL + '/dmapp', 
                params=dict(reqDeviceId=self.deviceId)
                )
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            print 'Error', r.status_code
            print r.text
            r.raise_for_status()
        reply = r.json()
        if type(reply) != type([]) or len(reply) != 1:
            print 'Error: excepted array with one dmappId but got:', repl(reply)
        dmappId = reply[0]
        return Application(self, dmappId, False)
        
class Application:
    def __init__(self, context, dmappId, isMaster):
        self.context = context
        self.dmappId = dmappId
        self.layoutServiceApplicationURL = self.context.layoutServiceContextURL + '/dmapp/' + dmappId
        if isMaster:
            self.clock = MasterClock(self)
        else:
            self.clock = SlaveClock()
        self.components = {}
        
    def start(self):
        self.clock.start()
        self.run()
        
    def wait(self):
        pass

    def run(self):
        # Non-threaded polling. But interface (start/run/wait) is ready for threading and event-based reports.
        while True:
            inst = self._getLayoutInstruction()
            self._doLayoutInstruction(inst)
            self.clock.report()
            for component in self.components.values():
                component.tick()
            time.sleep(1)
            
    def _getLayoutInstruction(self):
        r = requests.get(self.layoutServiceApplicationURL, params=dict(reqDeviceId=self.context.deviceId))
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            print 'Error', r.status_code
            print r.text
            r.raise_for_status()
        reply = r.json()
        return reply
        
    def _doLayoutInstruction(self, inst):
        oldComponents = set(self.components)
        for componentInfo in inst['components']:
            componentId = componentInfo['componentId']
            if componentId in oldComponents:
                # Update status for existing components
                self.components[componentId].update(componentInfo)
                oldComponents.remove(componentId)
            else:
                # Create new components
                c = Component(self, componentId, componentInfo)
                self.components[componentId] = c
        # Remove components that no longer exist
        for componentId in oldComponents:
            self.components[componentId].destroy()
            del self.components[componentId]
            
class Component:
    def __init__(self, application, componentId, componentInfo):
        self.application = application
        self.layoutServiceComponentURL = self.application.layoutServiceApplicationURL + '/component/' + componentId
        self.componentId = componentId
        self.componentInfo = componentInfo
        self.status = 'inited'
        self._reportStatus()
        
    def update(self, componentInfo):
        if componentInfo != self.componentInfo:
            self.componentInfo = componentInfo
            
    def destroy(self):
        pass
        
    def tick(self):
        now = self.application.clock.now()
        startTime = self.componentInfo['startTime']
        if startTime: startTime = float(startTime)
        stopTime = self.componentInfo['stopTime']
        if stopTime: stopTime = float(stopTime)
        if stopTime != None and now >= stopTime:
            newStatus = "stopped"
        elif startTime != None and now >= startTime:
            newStatus = "started"
        else:
            newStatus = "inited"
        if newStatus != self.status:
            self.status = newStatus
            self._reportStatus()
            
    def _reportStatus(self):
        print 'Status for', self.componentId, 'is now', self.status
        # Report status for new component
        r = requests.post(self.layoutServiceComponentURL + '/actions/status', params=dict(reqDeviceId=self.application.context.deviceId),
                json=dict(status=self.status))
        if r.status_code not in (requests.codes.ok, requests.codes.no_content, requests.codes.created):
            print 'Error', r.status_code
            print r.text
            r.raise_for_status()
        
        
class GlobalClock:
    def __init__(self):
        self.epoch = 0
        self.running = False
        
    def start(self):
        if self.running: return
        now = self.epoch
        self.epoch = time.time()
        self.epoch -= now
        self.running = True
        
    def stop(self):
        if not self.running: return
        self.epoch = self.now()
        self.running = False
        
    def set(self, now):
        wasRunning = self.running
        self.stop()
        self.epoch = now
        if wasRunning:
            self.start()
            
    def skew(self, delta):
        self.set(self.now()+delta)
        
    def now(self):
        if not self.running: return self.epoch
        return time.time() - self.epoch
        
    def report(self):
        pass
        
class MasterClock(GlobalClock):
    def __init__(self, application):
        self.application = application
        GlobalClock.__init__(self)
        
    def report(self):
        # Should also broadcast to the slave clocks or something
        url = self.application.layoutServiceApplicationURL
        # For now, remove everything after /context
        print '%s (wallclock=%s):' % (self.now(), time.time())
        #return # For now layout-service implementation is incomplete (July 1)
        #cEnd = url.find('/dmapp')
        #url = url[:cEnd]
        r = requests.post(
                url+"/actions/clockChanged", 
                #params=dict(reqDeviceId=self.application.context.deviceId), 
                json=dict(
                    wallClock=time.time(),
                    contextClock=self.now()
                    )
                )
        if r.status_code not in (requests.codes.ok, requests.codes.no_content, requests.codes.created):
            print 'Error', r.status_code
            print r.text
            r.raise_for_status()

class SlaveClock(GlobalClock):
    pass
    
