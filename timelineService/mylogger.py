import logging
import sys
import time
import datetime

# Make stdout unbuffered
class Unbuffered(object):
   def __init__(self, stream):
       self.stream = stream
   def write(self, data):
       self.stream.write(data)
       self.stream.flush()
   def __getattr__(self, attr):
       return getattr(self.stream, attr)

class StreamToLogger(object):
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        pass

logging.basicConfig()


# Default logging configuration: INFO for document and timeline (useful to app developers), WARNING for everything else.
DEFAULT_LOG_CONFIG="document:INFO,timeline:INFO,INFO"

class MyFormatter(logging.Formatter):

    def format(self, record):
        contextID = None
        dmappID = None
        if hasattr(record, 'contextID'):
            contextID = record.contextID
        if hasattr(record, 'dmappID'):
            dmappID = record.dmappID
        source = "TimelineService"
        level = record.levelname
        subSource = record.module
        message = logging.Formatter.format(self, record)
        logmessage = repr('"' + message)
        if logmessage[0] == 'u':
            logmessage = logmessage[1:]
        logmessage = "'" + logmessage[2:]
        
        rvList = ['2-Immerse']
        if source:
            rvList.append('source:%s' % source)
        if subSource:
            rvList.append('subSource:%s' % subSource)
        if level:
            rvList.append('level:%s' % level)
        if contextID:
            rvList.append('contextID:%s' % contextID)
        if dmappID:
            rvList.append('dmappID:%s' % dmappID)
        if hasattr(record, 'xpath'):
            rvList.append('xpath:%s ' % repr(record.xpath))
        if hasattr(record, 'dmappcID'):
            rvList.append('dmappcID:%s ' % repr(record.dmappcID))
        rvList.append('sourcetime:%s' % datetime.datetime.fromtimestamp(time.time()).isoformat())
        rvList.append('logmessage:%s' % logmessage)
        return ' '.join(rvList)

def install(noKibana, logLevel):
    if noKibana:
        global MyFormatter
        MyFormatter = logging.Formatter
        sys.stdout = Unbuffered(sys.stdout)
    else:
        sys.stdout = StreamToLogger(logging.getLogger('stdout'), logging.INFO)
        sys.stderr = StreamToLogger(logging.getLogger('stderr'), logging.INFO)
    if logLevel:
        for ll in logLevel.split(','):
            if ':' in ll:
                loggerToModify = logging.getLogger(ll.split(':')[0])
                newLevel = getattr(logging, ll.split(':')[1])
            else:
                loggerToModify = logging.getLogger()
                newLevel = getattr(logging, ll)
            loggerToModify.setLevel(newLevel)
    
    rootLogger = logging.getLogger()
    rootLogger.handlers[0].setFormatter(MyFormatter())

    rootLogger.log(logging.INFO, "timelineService: logging started")
