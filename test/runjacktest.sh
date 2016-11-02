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

timelineDoc=http://origin.2immerse.advdev.tv/sandbox/sample-hello/timeline.xml
layoutDoc=http://origin.2immerse.advdev.tv/sandbox/sample-hello/layout.json

python $basedir/timeline-service/client \
	--layout http://$hostname:8000/layout/v2 \
	--timeline http://$hostname:8001/timeline/v1 \
	--layoutDoc $layoutDoc \
	--timelineDoc $timelineDoc \
	--tsserver $hostname
