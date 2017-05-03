#!/bin/sh
set -ex

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`

hostname=`hostname`
case x$hostname in
*.local)
	hostname=`ipconfig getifaddr en0`
	;;
esac

## The services
#layoutServer=http://$hostname:8000/layout/v3
#timelineServer=http://$hostname:8001/timeline/v1
layoutServer=http://layout-service.platform.2immerse.eu/layout/v3
timelineServer=http://timeline-service.platform.2immerse.eu/timeline/v1
#layoutServer=http://layout-service-test.platform.2immerse.eu/layout/v3
#timelineServer=http://timeline-service-test.platform.2immerse.eu/timeline/v1

## The document
#timelineDoc=https://origin.platform.2immerse.eu/sandbox/sample-hello/timeline.xml
#layoutDoc=https://origin.platform.2immerse.eu/sandbox/sample-hello/layout.json
timelineDoc=https://origin.platform.2immerse.eu/dmapps/theatre-at-home/timeline-ultra.xml
layoutDoc=https://origin.platform.2immerse.eu/dmapps/theatre-at-home/layoutPrefSize.json

python $basedir/timeline-service/client \
	--layoutServer $layoutServer \
	--timelineServer $timelineServer \
	--layoutDoc $layoutDoc \
	--timelineDoc $timelineDoc \
	--tsserver $hostname \
	--logLevel DEBUG
