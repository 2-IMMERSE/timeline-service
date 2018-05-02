FROM ubuntu:16.04
MAINTAINER Jack Jansen <Jack.Jansen@cwi.nl>

# Install Python dependencies
RUN apt-get -qq update \
    && apt-get -qq install -y python2.7 python-webpy python-requests --no-install-recommends \
    && mkdir -p /usr/src/app \
    && apt-get -qq clean && rm -fr /var/lib/apt/lists/*

WORKDIR /usr/src/app

# Install app dependencies
COPY timelineService/ timelineService/
COPY samples/ samples/

EXPOSE 8080

ENTRYPOINT [ "/usr/bin/python" ]
CMD [ "/usr/src/app/timelineService", "--noKibana", "--logLevel", "document:DEBUG,timeline:DEBUG,INFO" ]
# CMD [ "/usr/src/app/timelineService" ]
