from __future__ import absolute_import
from __future__ import unicode_literals
from socketIO_client import SocketIO, SocketIONamespace, LoggingNamespace
from . import document
import logging
import threading

logger = logging.getLogger(__name__)

UsedNamespace=SocketIONamespace

class SocketIOHandler(threading.Thread):
    def __init__(self, timeline, toTimeline=None, fromTimeline=None):
        threading.Thread.__init__(self)
        
        self.timeline = timeline
        self.socketOut = None
        self.socketIn = None
        self.channelOut = None
        self.channelIn = None
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
        self.socketIn = SocketIO(toTimeline['server'], Namespace=UsedNamespace)
        self.channelIn = self.socketIn.define(UsedNamespace, toTimeline['channel'])
        self.roomIncomingUpdates = toTimeline['room']

        if fromTimeline:
            # If this parameter is set this timeline should send status updates back to the editor backend.
            # For now we assume the backchannel is the same as the forward channel
            assert fromTimeline['server'] == toTimeline['server']
            assert fromTimeline['channel'] == toTimeline['channel']
            self.roomOutgoingStatus = fromTimeline['room']
            self.socketOut = SocketIO(toTimeline['server'], Namespace=UsedNamespace)
            self.channelOut = self.socketOut.define(UsedNamespace, toTimeline['channel'])
        self.logger.debug('SocketIOHandler: url=%s channel=%s roomIncoming=%s roomOutgoing=%s' % (toTimeline['server'], toTimeline['channel'], self.roomIncomingUpdates, self.roomOutgoingStatus))
        self.logger.debug('SocketIOHandler: JOIN setup callbacks')
        self.channelIn.on('UPDATES', self._incomingUpdates)
        self.channelIn.on('reconnect', self._setupJoin)
        self._setupJoin()
        
    def _setupJoin(self):
        self.logger.debug('SocketIOHandler: rejoining room after reconnect')
        self.channelIn.emit('JOIN', self.roomIncomingUpdates)

    def start(self):
        self.logger.debug('SocketIOHandler: thread listener starting')
        threading.Thread.start(self)
        
    def close(self):
        if self.socketIn and self.roomIncomingUpdates:
            self.channelIn.emit('LEAVE', self.roomIncomingUpdates)
        self.running = False
        self.socketIn = None
        self.channelIn = None
        self.socketOut = None
        self.channelOut = None
        
    def __del__(self):
        self.close()
        
    def run(self):
        self.running = True
        self.logger.debug('SocketIOHandler: thread listener running')
        while self.running and self.socketIn:
            self.logger.debug('SocketIOHandler: calling socket.wait()')
            try:
                self.socketIn.wait(5)
            except:
                # I hate bare except clauses, but I don't know what to do else...
                import traceback
                traceback.print_exc()
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
        assert self.socketOut
        assert self.channelOut
        assert self.roomOutgoingStatus
        self.channelOut.emit("BROADCAST_STATUS", self.roomOutgoingStatus, documentState)
        
