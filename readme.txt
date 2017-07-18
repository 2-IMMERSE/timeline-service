This git repository contains the source of the 2immerse Timeline Server, some
auxiliary tools, some test software and a bit of documentation.

timelineService has all the code for the service itself.
Run with "python timelineService", the --help option will show the arguments.

To run in a docker container build the container using the Dockerfile.
The file test/readme.txt has a little help on how to do this.

To run without a docker container check out client-api from the gitlab, and look
at client-api/test/run_local_servers.sh.

To do a quick check of playback of a timeline document you can use
	python timlineService/document.py mydocument.xml
This test script has a --help option again. Usually you will probably run it
with --fast --dump --trace (and possibly also --debug).
This script does a syntax check of your XML document and a quick simulation run
of the document (with various assumptions, such that events happen immedeately,
and all A/V files are 10 seconds long unless otherwise specified). If you
don't specify "--fast" the simulation runs in realtime (so "quick" may not be the
correct term if you have a long document).

Directory api contains the following files:
	document.md
		contains the description of the timeline XML format.
	*.xml
		example timeline documents.
	timeline-service.raml
		the interface definition. Only for programmers.
	dmappc-states.*
		
		
