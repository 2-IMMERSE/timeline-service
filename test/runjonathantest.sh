#!/bin/sh
set -ex

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`

exec /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --disable-web-security --user-data-dir 'http://origin.platform.2immerse.eu/client-api/master/dist/test/general-test/dist/index.html#?layoutService=http://flauwte.dis.cwi.nl:8000/layout/v3&websocketService=http://flauwte.dis.cwi.nl:3000/&timelineService=http://flauwte.dis.cwi.nl:8001/timeline/v1&sharedStateService=https://shared-state-service.platform.2immerse.eu/&loggingService=https://logging-service.platform.2immerse.eu/&wallclockService=wss://wallclock-service.platform.2immerse.eu'
