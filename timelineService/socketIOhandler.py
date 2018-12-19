from __future__ import absolute_import
from __future__ import unicode_literals
from socketIO_client import SocketIO, SocketIONamespace, LoggingNamespace
from . import document
import logging
import threading

logger = logging.getLogger(__name__)

UsedNamespace=LoggingNamespace

class SocketIOHandler(threading.Thread):
    def __init__(self, timeline, toTimeline=None, fromTimeline=None):
        threading.Thread.__init__(self)
        
        self.timeline = timeline
        self.socket = None
        self.channel = None
        self.roomIncomingUpdates = None
        self.roomOutgoingStatus = None
        self.logger = document.MyLoggerAdapter(logger, dict(contextID=self.timeline.contextId, dmappID=self.timeline.dmappId))
        self.logger.debug('SocketIOhandler: created')
        if not toTimeline:
            self.logger.error("SocketIOHandler requires toTimeline argument (missing)")
            return
        if not 'server' in toTimeline or not 'channel' in toTimeline or not 'room' in toTimeline:
            self.logger.error("SocketIOHandler: missing required argument in toTimeline: %s" % repr(toTimeline))
            return
        self.logger.debug("SocketIOHandler: connecting to %s" % toTimeline['server'])
        self.socket = SocketIO(toTimeline['server'], Namespace=UsedNamespace)
        self.channel = self.socket.define(UsedNamespace, toTimeline['channel'])
        self.roomIncomingUpdates = toTimeline['room']

        if fromTimeline:
            # If this parameter is set this timeline should send status updates back to the editor backend.
            # For now we assume the backchannel is the same as the forward channel
            assert fromTimeline['server'] == toTimeline['server']
            assert fromTimeline['channel'] == toTimeline['channel']
            self.roomOutgoingStatus = fromTimeline['room']
        self.logger.debug('SocketIOHandler: url=%s channel=%s roomIncoming=%s roomOutgoing=%s' % (toTimeline['server'], toTimeline['channel'], self.roomIncomingUpdates, self.roomOutgoingStatus))
        self._setup()
        self.channel.on_connect = self._setup
        
    def _setup(self):
        self.logger.debug('SocketIOHandler: JOIN and setup callbacks')
        self.channel.on('UPDATES', self._incomingUpdates)
        self.channel.emit('JOIN', self.roomIncomingUpdates)

    def start(self):
        self.logger.debug('SocketIOHandler: thread listener starting')
        threading.Thread.start(self)
        
    def close(self):
        if not self.socket:
            return
        if self.roomIncomingUpdates:
            self.channel.emit('LEAVE', self.roomIncomingUpdates)
        self.running = False
        self.socket = None
        self.channel = None
        
    def __del__(self):
        self.close()
        
    def run(self):
        self.running = True
        self.logger.debug('SocketIOHandler: thread listener running')
        while self.running and self.socket:
            self.logger.debug('SocketIOHandler: calling socket.wait()')
            try:
                self.socket.wait(5)
            except:
                # I hate bare except clauses, but I don't know what to do else...
                import traceback
                traceback.print_exc()
            if self.channel:
                self.channel.emit('PING')
        self.logger.debug('SocketIOHandler: thread listener finished')

    def _incomingUpdates(self, modifications):
        self.logger.debug('SocketIOHandler._incomingUpdates(%s)' % repr(modifications))
        assert 'generation' in modifications
        assert 'operations' in modifications
        self.timeline.updateDocument(modifications['generation'], modifications['operations'])
        
    def wantStatusUpdate(self):
        return not not self.roomOutgoingStatus
        
    def sendStatusUpdate(self, documentState):
        self.logger.debug('SocketIOHandler.sendStatusUpdate(%s) to %s' % (repr(documentState), self.roomOutgoingStatus))
        assert self.socket
        assert self.channel
        assert self.roomOutgoingStatus
        self.channel.emit("BROADCAST_STATUS", self.roomOutgoingStatus, documentState)
        
