FROM ubuntu:16.04
MAINTAINER Jack Jansen <Jack.Jansen@cwi.nl>

# Install Python dependencies
RUN apt-get update \
    && apt-get install -y python2.7 python-pip python-webpy python-requests --no-install-recommends \
    && mkdir -p /usr/src/app \
    && apt-get -qq clean && rm -fr /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools

WORKDIR /usr/src/app

# Install app dependencies
COPY requirements.txt requirements.txt

RUN pip install -r /usr/src/app/requirements.txt


COPY timelineService/ timelineService/
COPY samples/ samples/

RUN mkdir /usr/share/ca-certificates/2immerse
COPY ./client-certs/ /usr/share/ca-certificates/2immerse
RUN ln -s /usr/share/ca-certificates/2immerse/* /etc/ssl/certs
RUN echo 2immerse/2immerseCA.crt >> /etc/ca-certificates.conf
RUN update-ca-certificates

EXPOSE 8080

ENTRYPOINT [ "/usr/bin/python" ]
# CMD [ "/usr/src/app/timelineService", "--noKibana", "--logLevel", "document:DEBUG,timeline:DEBUG,WARN" ]
CMD [ "/usr/src/app/timelineService" ]
