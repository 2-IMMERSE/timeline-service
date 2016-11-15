#!/bin/sh
urlencode() {
    # urlencode <string>

    local length="${#1}"
    for (( i = 0; i < length; i++ )); do
        local c="${1:i:1}"
        case $c in
            [a-zA-Z0-9.~_-]) printf "$c" ;;
            *) printf '%s' "$c" | xxd -p -c1 |
                   while read c; do printf '%%%s' "$c"; done ;;
        esac
    done
}

urldecode() {
    # urldecode <string>

    local url_encoded="${1//+/ }"
    printf '%b' "${url_encoded//%/\\x}"
}

dirname=`dirname $0`
dirname=`cd $dirname; pwd`
basedir=`cd $dirname/../..; pwd`

case x$2 in
x)
	echo Usage: $0 layoutDocUrl timelineDocUrl
	exit 1
	;;
esac

case `uname` in
Darwin)
	chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
	;;
*)
	echo Unknown platform, please edit $0 to tell me where Chrome resides
	exit 1
	;;
esac

url="https://origin.2immerse.advdev.tv/client-api/dist/test/general-test/dist/index.html"

fullUrl="$url#layoutDocUrl=`urlencode $1`&timelineDocUrl=`urlencode $2`"

exec "$chrome" --disable-web-security "$fullUrl"
