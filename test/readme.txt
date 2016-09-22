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
- run the tv
	$ cd timeline-service
	$ python client --layout http://1.2.3.4:9000/layout/v1 --timeline http://1.2.3.4:9090/timeline/v1 --tsserver 1.2.3.4
	# Check the output for the handheld client command line
	
	(If you leave out the --tsserver option then the wall clock is used as opposed to the dvb synced clock)

