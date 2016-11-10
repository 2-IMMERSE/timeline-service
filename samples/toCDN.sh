#!/bin/sh
dirname=`dirname $0`
case x$1 in
x)
	echo Usage: $0 sampledir
	echo Uploads $dirname/sampledir to CDN sandbox/sampledir
	exit 1
	;;
esac
set -x
rsync -rlvz -e "ssh -p 52225" $1/ cwi@origin.2immerse.advdev.tv:2immerse_live/sandbox/$1/
