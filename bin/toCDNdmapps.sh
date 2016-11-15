#!/bin/sh
dirname=`dirname $0`
case x$1 in
x)
	echo Usage: $0 sampledir
	echo Uploads $dirname/sampledir to CDN dmapps/sampledir
	exit 1
	;;
esac
location=`basename $1`
set -x
rsync -rlvz -e "ssh -p 52225" $1/ cwi@origin.2immerse.advdev.tv:2immerse_live/dmapps/$location/
echo 'URL:' https://origin.2immerse.advdev.tv/dmapps/$location/
