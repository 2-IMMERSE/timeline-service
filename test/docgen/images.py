#!/usr/bin/python
import sys
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

FONT="/Library/Fonts/Andale Mono.ttf"

def genImages(pattern, width, height, bgColor, fgColor, fontSize, firstTime, lastTime, interval):
    font = ImageFont.truetype(FONT, fontSize)
    im = Image.new("RGB", (width, height))
    count = 0
    curTime = firstTime
    while curTime < lastTime:
        ct = int(curTime)
        h = int(ct / 3600)
        m = int((ct / 60) % 60)
        s = int(ct % 60)
        tc = "%02d:%02d:%02d" % (h, m, s)
    
        im = Image.new("RGB", (width, height), bgColor)
        draw = ImageDraw.Draw(im)
        
        textWidth, textHeight = draw.textsize(tc, font=font)
        x = (width-textWidth) / 2
        y = (height-textHeight) / 2
        draw.text((x, y), tc, font=font, fill=fgColor)
        
        fileName = pattern % count
        im.save(fileName)

        curTime += interval
        count += 1
    return count
    
def main():
    if len(sys.argv) != 10:
        print "Usage: %s pattern width height bgColor fgColor fontSize starttime endtime interval" % sys.argv[0]
        print "pattern has %d to show where image number goes, for example imagedir/img%06d.png"
        print "Times are all in seconds. Generates images with timecodes."
        sys.exit(1)
    count = genImages(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4], base=0), int(sys.argv[5], base=0), int(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8]), float(sys.argv[9]))
    print 'Created %d images' % count

if __name__ == '__main__':
    main()
    
        
