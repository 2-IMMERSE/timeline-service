#!/bin/sh
set -ex

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`

hostname=`hostname`

case `uname` in
Darwin)
	myRunCommand() {
		(cat | osascript -) << xyzzy
tell app "Terminal"
	do script "$@"
end tell
xyzzy
	}
	;;
*)
	myRunCommand() {
		$@ &
	}
	;;
esac

cd $basedir/websocket-service
myRunCommand docker run -ti -p 3000:3000 websocket-service

cd $basedir/timeline-service
myRunCommand docker run -ti -p 8001:8080 timeline-service

cd $basedir/layout-service
myRunCommand docker run -ti -p 8000:8000 layout-service npm start -- -w http://$hostname:3000/
