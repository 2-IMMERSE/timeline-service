FROM alpine:3.8
MAINTAINER Jack Jansen <Jack.Jansen@cwi.nl>


WORKDIR /usr/src/app

COPY requirements.txt requirements.txt
COPY timelineService/ timelineService/
COPY samples/ samples/
COPY test/ test/

COPY ./client-certs/ /usr/local/share/ca-certificates

# Install new package indices
RUN apk update

# Install Python3 dependencies
RUN apk add python3 py3-pip py-lxml py-gevent
RUN pip3 install --upgrade pip setuptools
RUN pip3 install -r /usr/src/app/requirements.txt

EXPOSE 8080

WORKDIR /usr/src/app
# CMD [ "python3", "-m", "timelineService", "--noKibana", "--logLevel", "document:DEBUG,timeline:DEBUG,WARN" ]
# CMD [ "python3", "-m", "timelineService", "--logLevel", "logs:DEBUG,socketIOhandler:DEBUG" ]
CMD [ "python3", "-m", "timelineService"]
