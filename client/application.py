import requests
import requests
import time
import dvbclock
import logging

logLevel = None

class Context:
    def __init__(self, deviceId, caps):
        self.deviceId = deviceId
        self.logger = logging.getLogger(deviceId)
        if logLevel:
            self.logger.setLevel(logLevel)
        self.logger.debug("Device %s created" % deviceId)
        self.caps = caps
#        self.regionList = {}
        self.orientation = self.caps['orientations'][0]
        self.contextId = None
        self.layoutServiceContextURL = None
        
    def create(self, layoutServiceURL):
        r = requests.post(
                layoutServiceURL+"/context", 
                params=dict(reqDeviceId=self.deviceId), 
                )
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            self.logger.error('create: Error %s: %s' % (r.status_code, r.text))
            r.raise_for_status()
        reply = r.json()
        self.contextId = reply["contextId"]
        self.layoutServiceContextURL = layoutServiceURL + '/context/' + self.contextId
        self.join(self.layoutServiceContextURL)

    def join(self, layoutServiceContextURL):
        self.layoutServiceContextURL = layoutServiceContextURL
        r = requests.post(
                self.layoutServiceContextURL+"/devices", 
                params=dict(reqDeviceId=self.deviceId, deviceId=self.deviceId, orientation=self.orientation), 
                json={
                    'capabilities' : self.caps,
#                   'regionList' : self.regionList,
                    }
                )
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            self.logger.error('join: Error %s: %s' % (r.status_code, r.text))
            r.raise_for_status()
        reply = r.json()
        self.contextId = reply["contextId"]
        self.logger.info("Join: ContextId: %s"%self.contextId)
        
    def createDMApp(self, urls):
        r = requests.post(
                self.layoutServiceContextURL + '/dmapp', 
                params=dict(reqDeviceId=self.deviceId),
                json=urls
                )
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            self.logger.error('createDMApp: Error %s: %s' % (r.status_code, r.text))
            r.raise_for_status()
        reply = r.json()
        dmappId = reply["DMAppId"]
        self.logger.info("createDMApp: dmappId=%s" % dmappId)
        return Application(self, dmappId, True)

    def getDMApp(self):
        r = requests.get(
                self.layoutServiceContextURL + '/dmapp', 
                params=dict(reqDeviceId=self.deviceId)
                )
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            self.logger.error('getDMApp: Error %s: %s' % (r.status_code, r.text))
            r.raise_for_status()
        reply = r.json()
        if type(reply) != type([]) or len(reply) != 1:
            self.logger.error('getDMApp: Error: excepted array with one dmappId but got: %s'%repr(reply))
        dmappId = reply[0]
        return Application(self, dmappId, False)
        
class Application:
    def __init__(self, context, dmappId, isMaster, clockParams={}):
        self.context = context
        self.logger = self.context.logger
        self.dmappId = dmappId
        self.isMaster = isMaster
        self.currentMasterClockComponent = None
        self.layoutServiceApplicationURL = self.context.layoutServiceContextURL + '/dmapp/' + dmappId
        self.clock = None
        self.components = {}
        
    def selectClock(self, clockParams):
        # We need to select either a DVB clock or a free-running one, in master or non-master one.
        # This is for debugging purposes, really.
        assert not self.clock
        if self.isMaster:
            if clockParams:
                self.clock = DvbMasterClock(self, **clockParams)
            else:
                self.clock = MasterClock(self)
        else:
            if clockParams:
                self.clock = DvbSlaveClock(**clockParams)
            else:
                self.clock = SlaveClock()
        assert self.clock
        
    def start(self):
        assert self.clock
        # Start clock only when masterVideo is started: self.clock.start()
        self.run()
        
    def wait(self):
        pass

    def run(self):
        # Non-threaded polling. But interface (start/run/wait) is ready for threading and event-based reports.
        while True:
            self.logger.debug("run: clock=%s, wallclock=%s" % (self.clock.now(), time.time()))
            inst = self._getLayoutInstruction()
            oldClockStatus = self.clock.status()
            self._doLayoutInstruction(inst)
            if self.clock.status() != oldClockStatus:
                self.clock.report()
            for component in self.components.values():
                component.tick()
            time.sleep(1)
            
    def _getLayoutInstruction(self):
        r = requests.get(self.layoutServiceApplicationURL, params=dict(reqDeviceId=self.context.deviceId))
        if r.status_code not in (requests.codes.ok, requests.codes.created):
            self.logger.error('_getLayoutInstructions: Error %s: %s' % (r.status_code, r.text))
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
                # Debug: if the component has debug=skip we simply return "skipped"
                # u'parameters': {u'debug-2immerse-debug': u'skip'}
                if 'parameters' in componentInfo:
                    p = componentInfo['parameters']
                    if p.get('debug-2immerse-debug') == 'skip':
                        c = debugSkipComponent(self, componentId, componentInfo)
                        self.components[componentId] = c
                        continue
                # Create new components
                c = Component(self, componentId, componentInfo)
                self.components[componentId] = c
        # Remove components that no longer exist
        for componentId in oldComponents:
            self.components[componentId].destroy()
            del self.components[componentId]

class debugSkipComponent:
    def __init__(self, application, componentId, componentInfo):
        self.logger = application.logger
        self.logger.info("%f: component %s: skipped" % (self.application.clock.now(), componentId))
        # Report status for new component
        layoutServiceComponentURL = application.layoutServiceApplicationURL + '/component/' + componentId
        r = requests.post(layoutServiceComponentURL + '/actions/status', params=dict(reqDeviceId=application.context.deviceId),
                json=dict(status='skipped'))
        if r.status_code not in (requests.codes.ok, requests.codes.no_content, requests.codes.created):
            self.logger.error('status: Error %s: %s' % (r.status_code, r.text))
            r.raise_for_status()
 
    def update(self, componentInfo):
        pass
        
    def destroy(self):
        pass
        
    def tick(self):
        pass
        
class Component:
    def __init__(self, application, componentId, componentInfo):
        self.application = application
        self.logger = application.logger
        params = componentInfo.get('parameters')
        if not params: params = {}
        syncMode = params.get('syncMode')
        if not syncMode: syncMode = None
        self.canBeMasterClock = syncMode == 'master'
#        if self.canBeMasterClock: 
#            self.application.currentMasterClockComponent = self
        self.layoutServiceComponentURL = self.application.layoutServiceApplicationURL + '/component/' + componentId
        self.componentId = componentId
        self.componentInfo = componentInfo
        self.status = 'inited'
        self._reportStatus()
        
    def update(self, componentInfo):
        if componentInfo != self.componentInfo:
            self.componentInfo = componentInfo
        # Workaround (similar to client-api) for when the document starts without any clock:
        # we start a default clock
#        print 'xxxjack', self.status, self.componentId, self.application.currentMasterClockComponent
        if self.status == 'started' and not self.application.currentMasterClockComponent:
            self.canBeMasterClock = True
#            print 'xxxjack grabbed clock'
        if self.canBeMasterClock and self.status == 'started':
            self.application.currentMasterClockComponent = self
        if self.application.currentMasterClockComponent == self:
            if self.status == 'started':
                self.application.clock.start()
            else:
                self.application.clock.stop()
            
    def destroy(self):
        pass
        
    def tick(self):
        now = self.application.clock.now()
        startTime = self.componentInfo['startTime']
        if startTime: startTime = float(startTime)
        stopTime = self.componentInfo['stopTime']
        if stopTime: stopTime = float(stopTime)
        if stopTime != None and now >= stopTime:
            newStatus = "idle"
        elif startTime != None and now >= startTime:
            newStatus = "started"
        else:
            newStatus = "inited"
        if newStatus != self.status:
            self.status = newStatus
            self._reportStatus()
            
    def _reportStatus(self):
        self.logger.info("%f: component %s: %s" % (self.application.clock.now(), self.componentId, self.status))
        # Report status for new component
        r = requests.post(self.layoutServiceComponentURL + '/actions/status', params=dict(reqDeviceId=self.application.context.deviceId),
                json=dict(status=self.status))
        if r.status_code not in (requests.codes.ok, requests.codes.no_content, requests.codes.created):
            self.logger.error('_reportStatus: Error %s: %s' % (r.status_code, r.text))
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
        
    def getSpeed(self):
        if self.running: return 1.0
        return 0.0
        
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
        
    def status(self):
        return self.epoch, self.running
        
class MasterClockMixin:
    def __init__(self, application):
        self.application = application
        self.logger = self.application.logger
        
    def report(self):
        # Should also broadcast to the slave clocks or something
        url = self.application.layoutServiceApplicationURL
        self.logger.info("%f: clock rate=%d wallClock=%f" % (self.now(), self.getSpeed(), time.time()))
        r = requests.post(
                url+"/actions/clockChanged", 
                #params=dict(reqDeviceId=self.application.context.deviceId), 
                json=dict(
                    wallClock=time.time(),
                    contextClock=self.now(),
                    contextClockRate=self.getSpeed(),
                    )
                )
        if r.status_code not in (requests.codes.ok, requests.codes.no_content, requests.codes.created):
            self.logger.error('_clockChanged: Error %s: %s' % (r.status_code, r.text))
            r.raise_for_status()

class MasterClock(MasterClockMixin, GlobalClock):
    def __init__(self, application):
        GlobalClock.__init__(self)
        MasterClockMixin.__init__(self, application)

class SlaveClock(GlobalClock):
    pass
    
class DvbMasterClock(MasterClockMixin, dvbclock.DvbServerClock):
    def __init__(self, application, **kwargs):
        dvbclock.DvbServerClock.__init__(self, **kwargs)
        MasterClockMixin.__init__(self, application)
        
class DvbSlaveClock(dvbclock.DvbClientClock):
    pass
    
