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

timelineDoc=https://origin.platform.2immerse.eu/sandbox/sample-hello/timeline.xml
layoutDoc=https://origin.platform.2immerse.eu/sandbox/sample-hello/layout.json

python $basedir/timeline-service/client \
	--layoutServer http://$hostname:8000/layout/v3 \
	--timelineServer http://$hostname:8001/timeline/v1 \
	--layoutDoc $layoutDoc \
	--timelineDoc $timelineDoc \
	--tsserver $hostname
