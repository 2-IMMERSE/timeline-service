#!/bin/sh

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`

exec python $basedir/timeline-service/timelineService/document.py $@
