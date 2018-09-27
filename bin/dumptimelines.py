#!/usr/bin/env python
import urllib
import json
import time
import argparse
import sys

TSURL="https://timeline-service.platform.2immerse.eu/timeline/v1"
TSURL_EDGE="https://timeline-service.edge.platform.2immerse.eu/timeline/v1"
TSURL_TEST="https://timeline-service.test.platform.2immerse.eu/timeline/v1"

def restGet(url):
    f = urllib.urlopen(url)
    data = f.read()
    return json.loads(data)
    
def main():
    parser = argparse.ArgumentParser(description="Dump 2immerse timeline service status")
    parser.add_argument("--timelineServer", "-s", metavar="URL", help="Specify timeline service URL (default: %s)" % TSURL, default=TSURL)
    parser.add_argument("--edge", action="store_true", help="Use edge timeline service")
    parser.add_argument("--test", action="store_true", help="Use test timeline service")
    parser.add_argument("--document", "-d", action="store_true", help="Only retrieve current document for single context")
    parser.add_argument("--nodocument", "-D", action="store_true", help="Don't show document")
    parser.add_argument("context", nargs="*", help="Context to dump (default: all)")
    
    args = parser.parse_args()
    
    tsUrl = args.timelineServer
    if args.edge:
        tsUrl = TSURL_EDGE
    if args.test:
        tsUrl = TSURL_TEST
    
    if args.context:
        contextIds = args.context
    else:
        contextIds = restGet(tsUrl + "/context")
    
    if args.document:
        if len(contextIds) != 1:
            print >>sys.stderr, "%s: Use --document only for single context"
            sys.exit(1)
        dump = restGet(tsUrl + '/context/' + contextIds[0] + '/dump')
        print dump['document'].encode('utf-8')
        sys.exit(0)
    print 'Number of contextts active:', len(contextIds)
    for c in contextIds:
        print '------------- Context', c
        try:
            dump = restGet(tsUrl + '/context/' + c + '/dump')
        except ValueError:
            print '** Warning: dump did not return JSON data'
            continue
        if 'document' in dump:
            if not args.nodocument:
                print '---------- Document and document state:'
                print dump['document']
                print '----------'
            del dump['document']
        else:
            print '** Warning: no document in dump'
        if 'creationTime' in dump:
            print 'Created:\t', time.ctime(dump['creationTime'])
            del dump['creationTime']
        keys = dump.keys()
        keys.sort()
        for k in keys:
            print '%s:\t%s' % (k, dump[k])
        print
        
if __name__ == '__main__':
    main()
    
