import time
import Queue


class PausableClock:
    def __init__(self, underlyingClock):
        self.epoch = 0
        self.running = False
        self.underlyingClock = underlyingClock

    def now(self):
        if not self.running:
            return self.epoch
        return self.underlyingClock.now() - self.epoch

    def start(self):
        if not self.running:
            self.epoch = self.underlyingClock.now() - self.epoch
            self.running = True

    def stop(self):
        if self.running:
            self.epoch = self.underlyingClock.now() - self.epoch
            self.running = False
            
class CallbackPausableClock(PausableClock):
    def __init__(self, underlyingClock):
        PausableClock.__init__(self, underlyingClock)
        self.queue = Queue.PriorityQueue()

    def sleepUntilNextEvent(self):
        try:
            peek = self.queue.get(False)
        except Queue.Empty:
            assert 0, "No events are forthcoming"
        assert peek, "No events are forthcoming"
        self.queue.put(peek)
        t, callback, args, kwargs = peek
        delta = t-self.now()
        if delta > 0:
            self.underlyingClock.sleep(delta)
        
    def schedule(self, delay, callback, *args, **kwargs):
        assert not self.queue.full()
        self.queue.put((self.now()+delay, callback, args, kwargs))
        
    def handleEvents(self, handler):
        while True:
            try:
                peek = self.queue.get(False)
            except Queue.Empty:
                return
            if not peek: return
            t, callback, args, kwargs = peek
            if self.now() >= t:
                handler.schedule(callback, *args, **kwargs)
            else:
                assert not self.queue.full()
                self.queue.put(peek)
                return
       
class FastClock:
    def __init__(self):
        self._now = 0
        
    def now(self):
        return self._now
        
    def sleep(self, duration):
        self._now += duration

class SystemClock:
    def __init__(self):
        pass
        
    def now(self):
        return time.time()
        
    def sleep(self, duration):
        time.sleep(duration)
