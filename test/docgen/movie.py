#!/usr/bin/python
import sys
import subprocess
import os
import images

def genMovie(fileName, width, height, bgColor, fgColor, fontSize, firstTime, lastTime, interval):
    tmpDir = fileName + '.tmpdir'
    os.mkdir(tmpDir)
    pattern = os.path.join(tmpDir, 'img%06d.png')
    count = images.genImages(pattern, width, height, bgColor, fgColor, fontSize, firstTime, lastTime, interval)
    status = subprocess.call(["ffmpeg", "-framerate", str(1.0/interval), "-i", pattern, "-c:v", "libx264", "-vf", "fps=25,format=yuv420p", fileName])
    if status == 0:
        return 1
    return 0
    
def main():
    if len(sys.argv) != 10:
        print "Usage: %s outputfile width height bgColor fgColor fontSize starttime endtime interval" % sys.argv[0]
        print "Times are all in seconds. Generates videofile with timecodes."
        sys.exit(1)
    count = genMovie(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4], base=0), int(sys.argv[5], base=0), int(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8]), float(sys.argv[9]))
    print 'Created %d lines' % count
    

if __name__ == '__main__':
    main()
    
