#!/usr/bin/python
import sys
import json
import timeline
import xml.etree.ElementTree as ET

def genScrollText(fileName, firstTime, lastTime, interval):
    fp = open(fileName, "w")
    fp.write("[\n")
    # Unsure which of this is needed....
    item = dict(
        category="heading",
        type="act",
        text="Timecodes Act",
        time=dict(m=0, s=0)
        )
    json.dump(item, fp)

    fp.write(',\n')
    item = dict(
        category="heading",
        type="scene",
        text="Timecodes Scene",
        time=dict(m=0, s=0)
        )
    json.dump(item, fp)

    fp.write(',\n')
    item = dict(
        category="setting",
        type="entry",
        text="Here Be Timecodes...",
        who=["timecode"],
        time=dict(m=0, s=0)
        )
    json.dump(item, fp)


    curTime = firstTime
    count = 0
    while curTime < lastTime:
        ct = int(curTime)
        h = int(ct / 3600)
        m = int((ct / 60) % 60)
        s = int(ct % 60)
        fp.write(',\n')
        item = dict(
            category="heading",
            type="speaker",
            text="timecode",
            time=dict(m=m+60*h, s=s)
            )
        json.dump(item, fp)
        fp.write(',\n')
        item = dict(
            category="dialogue",
            who="timecode",
            text="%02.2d:%02.2d:%02.2d" % (h, m, s),
            time=dict(m=m+60*h, s=s)
            )
        data = json.dump(item, fp)
        curTime += interval
        count += 1
    fp.write("\n]\n")
    return count
    
def genScrollTextElement(prefix, fileName, firstTime, lastTime, interval):
    count = genScrollText(fileName, firstTime, lastTime, interval)
    if not count:
        return None
    attrs = {
        timeline.NS_2IMMERSE("dmappcid") : prefix,
        timeline.NS_2IMMERSE("class") : "scroll-text",
        timeline.NS_2IMMERSE("url") : "https://origin.2immerse.advdev.tv/dmapp-components/scroll-text/scroll-text.html",
        timeline.NS_2IMMERSE_COMPONENT("scriptUrl") : fileName,
        timeline.NS_TIMELINE_CHECK("dur") : str(lastTime-firstTime),
        }
        
    elt = ET.Element(timeline.NS_TIMELINE("ref"),attrs)
    return elt, [prefix]
    

def main():
    if len(sys.argv) != 5:
        print "Usage: %s outputfile starttime endtime interval" % sys.argv[0]
        print "Times are all in seconds. Generates scrolltext document with timecodes."
        sys.exit(1)
    count = genScrollText(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]))
    print 'Created %d lines' % count
    
if __name__ == '__main__':
    main()
    
        
