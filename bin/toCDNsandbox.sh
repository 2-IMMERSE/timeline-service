#!/bin/sh
dirname=`dirname $0`
case x$1 in
x)
	echo Usage: $0 sampledir
	echo Uploads $dirname/sampledir to CDN sandbox/sampledir
	exit 1
	;;
esac
location=`basename $1`
set -x
aws s3 sync $1 s3://origin.platform.2immerse.eu/sandbox/$location/
echo 'URL:' https://origin.platform.2immerse.eu/sandbox/$location/
