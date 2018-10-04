from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
from builtins import str
from builtins import object
import sys
import signal
import traceback
import argparse
from . import timeline
from . import app
from . import mylogger

if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf-8')
    
_real_stderr = sys.stderr
def _dump_app_stacks(*args):
    _dump_app_stacks_to(_real_stderr)
    _dump_app_stacks_to(sys.stderr)
def _dump_app_stacks_to(file):
    print("timelineService: QUIT received, dumping all stacks, %d threads:" % len(sys._current_frames()), file=file)
    for threadId, stack in list(sys._current_frames().items()):
        print("\nThreadID:", threadId, file=file)
        traceback.print_stack(stack, file=file)
        print(file=file)
    print("timelineService: End of stack dumps", file=file)

def main():
    signal.signal(signal.SIGQUIT, _dump_app_stacks)
    if hasattr(signal, 'SIGPOLL'):
        signal.signal(signal.SIGPOLL, _dump_app_stacks)
    if hasattr(signal, 'SIGINFO'):
        signal.signal(signal.SIGINFO, _dump_app_stacks)
    parser = argparse.ArgumentParser(description='Run 2immerse Timeline Service')
    parser.add_argument('--layoutService', metavar="URL", help="Override URL for contacting layout service")
    parser.add_argument('--port', type=int, help="Set port to listen on")
    parser.add_argument('--logLevel', metavar='SPEC', help="Set log levels (comma-separated list of [loggername:]LOGLEVEL)", default=mylogger.DEFAULT_LOG_CONFIG)
    parser.add_argument('--noKibana', action='store_true', help="Use human-readable log formatting in stead of Kibana-style formatting")
    parser.add_argument('--noVerify', action='store_true', help="Disable all client-side SSL verification")
    args = parser.parse_args()
    
    mylogger.install(args.noKibana, args.logLevel)
    print("timelineService: Python version %s" % sys.version)
    print("timelineService: running from %s" % __file__)

    if args.noVerify:
        # Temporary measure: the origin server certificate is untrusted on our docker containers.
        rootLogger.log(logging.WARN, "https verification disabled for now (Nov 2016)")
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
    if args.layoutService:
        timeline.LAYOUTSERVICE = args.layoutService

    server = app.app_singleton(args.port) 
    server.run()

main()
