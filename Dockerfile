FROM alpine:3.7
MAINTAINER Jack Jansen <Jack.Jansen@cwi.nl>


WORKDIR /usr/src/app

COPY requirements.txt requirements.txt
COPY timelineService/ timelineService/
COPY samples/ samples/
COPY test/ test/

COPY ./client-certs/ /usr/local/share/ca-certificates

# Install Python and certificate dependencies
RUN apk add --no-cache python2 py2-pip py2-lxml ca-certificates
RUN update-ca-certificates
RUN pip install --upgrade pip setuptools
RUN pip install -r /usr/src/app/requirements.txt

EXPOSE 8080

WORKDIR /usr/src/app
# CMD [ "python", "-m", "timelineService", "--noKibana", "--logLevel", "document:DEBUG,timeline:DEBUG,WARN" ]
CMD [ "python", "-m", "timelineService"]
