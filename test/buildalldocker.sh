#!/bin/sh
set -ex

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`

cd $basedir/layout-service
git pull
docker build -t layout-service .

cd $basedir/timeline-service
git pull
docker build -t timeline-service .

cd $basedir/websocket-service
git pull
docker build -t websocket-service .

#cd $basedir/client-api
#git pull
#make -j
