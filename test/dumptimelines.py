#!/usr/bin/env python
import urllib
import json
import time
import argparse

TSURL="http://timeline-service.2immerse.advdev.tv/timeline/v1"

def restGet(url):
    f = urllib.urlopen(url)
    data = f.read()
    return json.loads(data)
    
def main():
    parser = argparse.ArgumentParser(description="Dump 2immerse timeline service status")
    parser.add_argument("--timeline", "-s", help="Specify timeline service URL (default=%s)" % TSURL, default=TSURL)
    
    args = parser.parse_args()
    
    tsUrl = args.timeline
    
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
    
