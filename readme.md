This git repository contains the source of the 2immerse Timeline Server, some auxiliary tools, some test software and a bit of documentation.

## Running for debug and testing

Directory `timelineService` has all the code for the service itself. Run with 

```
python timelineService

```

the `--help` option will show the arguments.

To run in a docker container build the container using `Dockerfile` and then start it:

```
docker build -t timeline .
docker run timeline
```

Normally, however, you would run the timeline service together with all other services through the _docker-compose_ scripts from the _deployment_ repository.

## Checking your documents

To do a quick check of playback of a timeline document you can use

```
python timelineService/document.py mydocument.xml
```

This test script has a `--help` option again. Usually you will probably run it with

```
python timelineService/document.py --fast --dump --trace mydocument.xml
```
 
This does a  syntax check of your XML document and a quick simulation run of the document (with various assumptions, such that events happen immedeately, and all A/V files are 10 seconds long unless otherwise specified). During the run, trace messages are printed to show when elements are sarted and stopped. At the end, the document is printed on standard output, with all elements annotated with their current state.

If you don't specify `--fast` the simulation runs in realtime (so "quick" may not be the correct term if you have a long document).

If you don't specify `--trace` the starting and stopping of elements isn't printed. Alternatively, if you specify `--debug` you get more verbose messages.

If you don't specify `--dump` the document dump at end of run is not shown.

## Helper scripts

There are a number of helper scripts in the `bin` directory:

- _dumptimelines.py_ contacts a running timeline service (default <https://timeline-service.platform.2immerse.eu/timeline/v1> but can be overriden with an argument) and can show all active contexts, optionally with the current state of their document. `--help` option gives more help.
- _validate\_timeline.py_ performs the document checking menthioned above.
- _validate\_layout.py_ performs some checking of the layout of a document. May not work anymore.
- _srt2scrolltxt.py_ converts SRT-style subtitles to 2immerse-style scrolling text.
		
## Other files and directories

- _client_ is a Python client for the timeline service. It uses the REST API of the service to run documents. It does not play media, but it goes through the whole motion. It does not work at the moment.
- _test_ has the test files for acceptance testing. Run with `cd test ; python -m unittest discover`.
- _samples_ has some old sample documents which may no longer work.
- _api_ has some documentation on the REST api, but it may be outdated.
