#!/usr/bin/env python
import urllib
import json
import time
import argparse

TSURL="https://timeline-service-edge.platform.2immerse.eu/timeline/v1"

def restGet(url):
    f = urllib.urlopen(url)
    data = f.read()
    return json.loads(data)
    
def main():
    parser = argparse.ArgumentParser(description="Dump 2immerse timeline service status")
    parser.add_argument("--timelineServer", "-s", metavar="URL", help="Specify timeline service URL (default: %s)" % TSURL, default=TSURL)
    parser.add_argument("context", nargs="*", help="Context to dump (default: all)")
    
    args = parser.parse_args()
    
    tsUrl = args.timelineServer
    
    if args.context:
        contextIds = args.context
    else:
        contextIds = restGet(tsUrl + "/context")
    
    print 'Number of contextts active:', len(contextIds)
    for c in contextIds:
        print '------------- Context', c
        dump = restGet(tsUrl + '/context/' + c + '/dump')
        if 'document' in dump:
            print '---------- Document and document state:'
            print dump['document']
            del dump['document']
            print '----------'
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
    
