To run the test:
- (possibly build) and run the layout service:
	$ ifconfig # And remember the IP address 1.2.3.4
	$ cd layout-service
	$ docker build -t layout-service
	$ docker run -ti -p 9000:8000 layout-service
- (possibly build) and run the timeline service:
	$ cd timeline-service
	$ docker build -t timeline-service
	$ docker run -ti -p 9090:8080 timeline-service
- run the tv
	$ cd timeline-service
	$ python client http://1.2.3.4:9000/layout/v1 http://1.2.3.4:9090/timeline/v1
	# Check the output for the handheld client command line
	
