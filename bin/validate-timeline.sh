#!/bin/sh

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`
PYTHONPATH="$basedir/timeline-service:$PYTHONPATH"

exec python -m timelineService.document $@
