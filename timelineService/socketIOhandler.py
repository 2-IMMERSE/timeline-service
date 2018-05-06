from socketIO_client import SocketIO, SocketIONamespace
import document
import logging
import Threading

logger = logging.getLogger(__name__)

class SocketIOHandler(Threading.thread):
    def __init__(self, timeline, toTimeline=None, fromTimeline=None):
        self.timeline = timeline
        self.socket = None
        self.channel = None
        self.roomIncomingUpdates = None
        self.roomOutgoingStatus = None
        self.logger = document.MyLoggerAdapter(logger, dict(contextID=self.timeline.contextId, dmappID=self.timeline.dmappId))
        if not toTimeline:
            self.logger.error("SocketIOHandler requires toTimeline argument (missing)")
            return
        if not 'server' in toTimeline or not 'channel' in toTimeline or not 'room' in toTimeline:
            self.logger.error("SocketIOHandler: missing required argument in toTimeline: %s" % repr(toTimeline))
            return
        self.socket = SocketIO(toTimeline['server'])
        self.channel = self.socket.define(SocketIONamespace, toTimeline['channel'])
        self.roomIncomingUpdates = toTimeline['room']

        if fromTimeline:
            # If this parameter is set this timeline should send status updates back to the editor backend.
            # For now we assume the backchannel is the same as the forward channel
            assert fromTimeline['server'] == toTimeline['server']
            assert fromTimeline['channel'] == toTimeline['channel']

    def start(self):
        pass
        
    def close(self):
        if not self.socket:
            return
        if self.roomIncomingUpdates:
            self.channel.emit('LEAVE', self.roomIncomingUpdates)
        if self.roomOutgoingStatus:
            self.channel.emit('LEAVE', self.roomOutgoingStatus)
        self.running = False
        self.socket = None
        
    def __del__(self):
        self.close()
        
    def run(self):
        self.running = True
