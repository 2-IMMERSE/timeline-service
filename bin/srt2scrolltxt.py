#!/usr/bin/env python
from __future__ import print_function
import pysrt
import json
import sys

CATEGORY="dialogue"
WHO="onscreen"

def srt2scrolltext(filename):
    rv = [dict(category="setting", text="setting", who=[WHO], type="entry", time=dict(m=0,s=0))]
    fp = pysrt.open(filename)
    for st in fp:
        tm = dict(m=st.start.minutes, s=st.start.seconds)
#        tm = dict(h=st.start.hours, m=st.start.minutes, s=st.start.seconds)
        rv.append(dict(category="heading", text=WHO, type="speaker", time=tm))
        rv.append(dict(category=CATEGORY, text=st.text, who=WHO, time=tm))
    return rv
    
def main():
    if len(sys.argv) != 3:
        print("Usage: %s subtitles.srt scrolltext.json" % sys.argv[0], file=sys.stderr)
        print("Converts SRT subtitles to 2immerse scrolling text format", file=sys.stderr)
        sys.exit(1)
    subtitles = srt2scrolltext(sys.argv[1])
    json.dump(subtitles, open(sys.argv[2], 'w'))
    
if __name__ == '__main__':
    main()
