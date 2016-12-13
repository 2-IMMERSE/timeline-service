#!/usr/bin/python
import sys
import timeline
import movie
import images
import scrolltext
import os
import json

BEGIN=0
END=120
INTERVAL=1

layoutConstraints = []

def main():
    if len(sys.argv) != 2 or os.path.exists(sys.argv[1]):
        print 'Usage: %s dirname' % sys.argv[0]
        print 'Dir should not exist, and complete document (timeline, layout, media) is created in this directory'
        sys.exit(1)
    os.mkdir(sys.argv[1])
    os.chdir(sys.argv[1])
    os.mkdir('media')
    fpTimeline = open('timeline.xml', 'w')
    
    tree, mainPar = timeline.genDocument()
    
    mainVideo, ids = movie.genMovieElement("mainVideo", True, "media/mainVideo.mp4", "mainVideo", 1280, 720, 0xf0f000, 0x101020, 80, BEGIN, END, INTERVAL)
    mainPar.append(mainVideo)
    for i in ids:
        c = dict(componentId=i, personal=dict(priority=0), communal=dict(priority=20, minSize=dict(width=100,height=100)))
        layoutConstraints.append(c)
    
    auxVideo, ids = movie.genMovieElement("auxVideo", False, "media/auxVideo.mp4", "auxVideo", 1280, 720, 0x00f0f0, 0x101020, 80, BEGIN, END, INTERVAL)
    mainPar.append(auxVideo)
    for i in ids:
        c = dict(componentId=i, personal=dict(priority=10, minSize=dict(width=100,height=100)), communal=dict(priority=0))
        layoutConstraints.append(c)
    
    scrollText, ids = scrolltext.genScrollTextElement("scrollingTimecodes", "media/scrolltext.json", BEGIN, END, INTERVAL)
    mainPar.append(scrollText)
    for i in ids:
        c = dict(componentId=i, personal=dict(priority=0), communal=dict(priority=20, minSize=dict(width=100,height=100)))
        layoutConstraints.append(c)
    
    scrollText2, ids = scrolltext.genScrollTextElement("scrollingTimecodesHH", "media/scrolltextHH.json", BEGIN, END, INTERVAL)
    mainPar.append(scrollText2)
    for i in ids:
        c = dict(componentId=i, personal=dict(priority=20, minSize=dict(width=100,height=100)), communal=dict(priority=0))
        layoutConstraints.append(c)
    
    imgs, ids = images.genImagesElement("image", "media/images%04d.png", "image", 500, 500, 0xf000f0, 0x101020, 40, BEGIN, END, INTERVAL)
    mainPar.append(imgs)
    for i in ids:
        c = dict(componentId=i, personal=dict(priority=0), communal=dict(priority=20, minSize=dict(width=100,height=100)))
        layoutConstraints.append(c)
    
    images2, ids = images.genImagesElement("imageHH", "media/imagesHH%04d.png", "imageHH", 500, 500, 0xf0f0f0, 0x101020, 40, BEGIN, END, INTERVAL)
    mainPar.append(images2)
    for i in ids:
        c = dict(componentId=i, personal=dict(priority=20, minSize=dict(width=100,height=100)), communal=dict(priority=0))
        layoutConstraints.append(c)
    
    tree.write(fpTimeline)
    fpTimeline.write('\n')
    
    fourQuarters = [
        dict(region=dict(id="region-topleft", position=dict(x=0,y=0), size=dict(width=0.5, height=0.5))),
        dict(region=dict(id="region-topright", position=dict(x=0,y=0.5), size=dict(width=0.5, height=0.5))),
        dict(region=dict(id="region-topleft", position=dict(x=0.5,y=0), size=dict(width=0.5, height=0.5))),
        dict(region=dict(id="region-topright", position=dict(x=0.5,y=0.5), size=dict(width=0.5, height=0.5))),
        ]
    commonLayout=dict(
        communal=dict(
            portrait=fourQuarters,
            landscape=fourQuarters,
            ),
        personal=dict(
            portrait=fourQuarters,
            landscape=fourQuarters,
            ),
        )

    layout = dict(
        version=3, 
        dmapp=sys.argv[1],
        constraints=layoutConstraints,
        layoutModel="template",
        templates=[
            dict(
                deviceType="default",
                layout=commonLayout,
                ),
            dict(
                deviceType="standalone",
                layout=commonLayout,
                ),
            dict(
                deviceType="tv",
                layout=commonLayout,
                ),
            dict(
                deviceType="handheld",
                layout=commonLayout,
                ),
            ],
        )
    fp = open('layout.json', 'w')
    json.dump(layout, fp)
    
if __name__ == '__main__':
    main()
    
    
