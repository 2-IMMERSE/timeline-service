#!/bin/sh

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`

document=$1
case $1 in
http*)
	document=$1
	;;
*)
	document=`echo $(cd $(dirname "$1") && pwd -P)/$(basename "$1")`
	;;
esac

cd $basedir/layout-service/validate
node . -d $document
