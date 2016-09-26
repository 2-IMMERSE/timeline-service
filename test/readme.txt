To run the test:
- (possibly build) and run the layout service:
	$ ifconfig # And remember the IP address 1.2.3.4
	$ cd layout-service
	$ docker build -t layout-service .
	$ docker run -ti -p 9000:8000 layout-service
- (possibly build) and run the timeline service:
	$ cd timeline-service
	$ docker build -t timeline-service .
	$ docker run -ti -p 9090:8080 timeline-service
	
	For the last line, if you want debug output, use
	$ docker run -ti -p 9090:8080 timeline-service /usr/bin/python /usr/src/timeline-service/timelineService --logLevel DEBUG
	
- run the tv
	$ cd timeline-service
	$ H=1.2.3.4 # Use the local host IP address here
	$ python client --layout http://$H:9000/layout/v2 --timeline http://$H:9090/timeline/v1 --tsserver $H
	# Check the output for the handheld client command line
	
	(If you leave out the --tsserver option then the wall clock is used as opposed to the dvb synced clock)

Deployment notes (for Jack himself):
- The documentation for running and deploying on mantl is in gitlab deployment, mantlinstances.md and
  mantlhowto.md.
- More detailed info is in the email thread with Erik, subject "Putting timeline server on mantl".
  This includes getting access to stderr and such, he'll move that info to the files above, at some point.
  
