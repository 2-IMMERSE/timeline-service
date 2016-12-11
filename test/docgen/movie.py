#!/usr/bin/python
import sys
import subprocess
import os
import images
import shutil
import timeline
import xml.etree.ElementTree as ET

def genMovie(fileName, width, height, bgColor, fgColor, fontSize, firstTime, lastTime, interval):
    tmpDir = fileName + '.tmpdir'
    shutil.rmtree(tmpDir, True)
    os.mkdir(tmpDir)
    pattern = os.path.join(tmpDir, 'img%06d.png')
    count = images.genImages(pattern, width, height, bgColor, fgColor, fontSize, firstTime, lastTime, interval)
    status = subprocess.call(["ffmpeg", "-framerate", str(1.0/interval), "-i", pattern, "-c:v", "libx264", "-vf", "fps=25,format=yuv420p", fileName])
    if status == 0:
        shutil.rmtree(tmpDir)
        return 1
    return 0
    
def genMovieElement(prefix, isMaster, fileName, *args, **kwargs):
    count = genMovie(fileName, *args, **kwargs)
    if not count:
        return None
    attrs = {
        timeline.NS_2IMMERSE("dmappcid") : prefix,
        timeline.NS_2IMMERSE("class") : "movie",
        timeline.NS_2IMMERSE_COMPONENT("mediaUrl") : fileName,
        }
    if isMaster:
        attrs[NS_2IMMERSE_COMPONENT("syncMode")] = "master"
        
    elt = ET.Element(timeline.NS_TIMELINE("ref"),attrs)
    return elt
    
def main():
    if len(sys.argv) != 10:
        print "Usage: %s outputfile width height bgColor fgColor fontSize starttime endtime interval" % sys.argv[0]
        print "Times are all in seconds. Generates videofile with timecodes."
        sys.exit(1)
    count = genMovie(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4], base=0), int(sys.argv[5], base=0), int(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8]), float(sys.argv[9]))
    print 'Created %d files' % count
    

if __name__ == '__main__':
    main()
    
