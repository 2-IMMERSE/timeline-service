#!/bin/sh
set -ex

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`

case x$1 in
x)
	cocmd=true
	;;
*)
	cocmd="git checkout $1"
	;;
esac

cd $basedir
set -x
for dir in */; do
	(cd $dir ; git fetch ; $cocmd ; git pull)
done
