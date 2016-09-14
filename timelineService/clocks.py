import time
import Queue
import threading

class never:
    """This object is greater than any number"""
    pass
    
assert never > 1

def synchronized(method):
    """Annotate a mthod to use the object lock"""
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper
            
class PausableClock:
    """A clock (based on another clock) that can be pasued and resumed"""
    def __init__(self, underlyingClock):
        self.epoch = 0
        self.running = False
        self.underlyingClock = underlyingClock
        self.lock = threading.Lock()

    @synchronized
    def now(self):
        """Return current time of the clock"""
        if not self.running:
            return self.epoch
        return self.underlyingClock.now() - self.epoch

    @synchronized
    def start(self):
        """Start the clock running"""
        if not self.running:
            self.epoch = self.underlyingClock.now() - self.epoch
            self.running = True

    @synchronized
    def stop(self):
        """Stop the clock"""
        if self.running:
            self.epoch = self.underlyingClock.now() - self.epoch
            self.running = False
            
class CallbackPausableClock(PausableClock):
    """A pausable clock that also stores callbacks with certain times"""
    
    def __init__(self, underlyingClock):
        PausableClock.__init__(self, underlyingClock)
        self.queue = Queue.PriorityQueue()

    @synchronized
    def nextEventTime(self):
        """Return delta-T until earliest callback, or never"""
        try:
            peek = self.queue.get(False)
        except Queue.empty:
            return never
        self.queue.put(peek)
        t, callback, args, kwargs = peek
        return t-self.now()
        
    def sleepUntilNextEvent(self):
        """Sleep until next callback. Do not use with multithreading."""
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
        """Schedule a callback"""
        assert not self.queue.full()
        self.queue.put((self.now()+delay, callback, args, kwargs))
        
    @synchronized
    def handleEvents(self, handler):
        """Retrieve all callbacks that are runnable"""
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
