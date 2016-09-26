FROM ubuntu
MAINTAINER Jack Jansen "Jack.Jansen@cwi.nl"
# Install Python dependencies
RUN apt-get update
RUN apt-get install -y python2.7 python-webpy python-requests
# Create app directory
RUN \
  mkdir -p /usr/src/timeline-service && \
  mkdir -p /usr/src/timeline-service/timelineService && \
  mkdir -p /usr/src/timeline-service/samples
WORKDIR /usr/src/timeline-service

# Install app dependencies
COPY timelineService/* timelineService/
COPY samples/* samples/

EXPOSE 8080
CMD [ "/usr/bin/python", "/usr/src/timeline-service/timelineService" ]
