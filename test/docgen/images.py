#!/usr/bin/python
import sys
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import xml.etree.ElementTree as ET
import timeline
import qrcode

FONT="/Library/Fonts/Andale Mono.ttf"

def genImages(pattern, heading, width, height, bgColor, fgColor, fontSize, firstTime, lastTime, interval):
    font = ImageFont.truetype(FONT, fontSize)
    im = Image.new("RGB", (width, height))
    count = 0
    curTime = firstTime
    while curTime < lastTime:
        ct = int(curTime)
        h = int(ct / 3600)
        m = int((ct / 60) % 60)
        s = int(ct % 60)
        tc = "%s %02d:%02d:%02d" % (heading, h, m, s)
    
        im = Image.new("RGB", (width, height), bgColor)
        draw = ImageDraw.Draw(im)
        
        # Draw a cross
        draw.line((0, 0, width, height), fill=fgColor)
        draw.line((0, height, width, 0), fill=fgColor)
        
        # Draw the text timecode
        textWidth, textHeight = draw.textsize(tc, font=font)
        x = (width-textWidth) / 2
        y = textHeight
        draw.text((x, y), tc, font=font, fill=fgColor)
        
        # draw the QR code timecode
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(tc)
        qrImage = qr.make_image()
        w, h = qrImage.size
        l =  (width-w)/2
        t =  3*textHeight + (height-3*textHeight-h)/2
        im.paste(qrImage, (l, t))
        
        fileName = pattern % count
        im.save(fileName)

        curTime += interval
        count += 1
    return count
    
def genImagesElement(prefix, pattern, heading, width, height, bgColor, fgColor, fontSize, firstTime, lastTime, interval):
    count = genImages(pattern, heading, width, height, bgColor, fgColor, fontSize, firstTime, lastTime, interval)
    if not count:
        return None
    seqElt = ET.Element(timeline.NS_TIMELINE("seq"))
    allids = []
    for i in range(count):
        thisId = prefix + '_' + str(i)
        fileName = pattern % i
        allids.append(thisId)
        attrs = {
            timeline.NS_2IMMERSE("dmappcid") : thisId,
            timeline.NS_2IMMERSE("class") : "image",
            timeline.NS_2IMMERSE("url") : "https://origin.2immerse.advdev.tv/dmapp-components/image/image.html",
            timeline.NS_2IMMERSE_COMPONENT("mediaUrl") : fileName,
            }
        
        elt = ET.Element(timeline.NS_TIMELINE("ref"),attrs)
        sleepElt = ET.Element(timeline.NS_TIMELINE("sleep"), {timeline.NS_TIMELINE("dur") : str(interval)})
        parElt = ET.Element(timeline.NS_TIMELINE("par"))
        parElt.append(sleepElt)
        parElt.append(elt)
        seqElt.append(parElt)
    return seqElt, allids
    
def main():
    if len(sys.argv) != 10:
        print "Usage: %s pattern width height bgColor fgColor fontSize starttime endtime interval" % sys.argv[0]
        print "pattern has %d to show where image number goes, for example imagedir/img%06d.png"
        print "Times are all in seconds. Generates images with timecodes."
        sys.exit(1)
    count = genImages(sys.argv[1], 'heading', int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4], base=0), int(sys.argv[5], base=0), int(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8]), float(sys.argv[9]))
    print 'Created %d images' % count

if __name__ == '__main__':
    main()
    
        