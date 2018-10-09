FROM alpine:3.7
MAINTAINER Jack Jansen <Jack.Jansen@cwi.nl>


WORKDIR /usr/src/app

COPY requirements.txt requirements.txt
COPY timelineService/ timelineService/
COPY samples/ samples/
COPY test/ test/

COPY ./client-certs/ /usr/local/share/ca-certificates

# Install certificate dependencies
RUN apk add --no-cache ca-certificates
RUN update-ca-certificates

# Install Python3 dependencies
RUN apk add --no-cache python3 py3-pip py-lxml py-gevent
RUN pip3 install --upgrade pip setuptools
RUN pip3 install -r /usr/src/app/requirements.txt

EXPOSE 8080

WORKDIR /usr/src/app
# CMD [ "python3", "-m", "timelineService", "--noKibana", "--logLevel", "document:DEBUG,timeline:DEBUG,WARN" ]
CMD [ "python3", "-m", "timelineService"]
