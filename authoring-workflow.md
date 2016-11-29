Here is a tentative workflow for creating new DMApp documents.

### Prerequisites:

- You should install pydvbcss (and possibly its dependencies) into your Python.
  See https://pypi.python.org/pypi/pydvbcss/0.4.0 , I think the following should do the trick, possibly with either the
  `--user` option, or with `sudo`:
  
```
sudo pip install pydvbcss
```

- If you want to test on an Odroid you must first install the 2immerse Odroid image. Jack or Jonathan can help you with this.
- Then, you use Chrome to download http://origin.2immerse.advdev.tv/client-api/android-general-test.apk and you install it.
- On a "normal" Android device (phone, tablet) you only follow the second step.

### Workflow:

- Create a folder with a `timeline.xml` and `layout.json`, or copy them from somewhere.
  The folder name is what is going to appear on the CDN. I'll use `sample-dmapp` here.

- validate your timeline document with

```
./bin/validate-timeline.sh --attributes --trace sample-dmapp/timeline.xml
```

- if you also want to validate that all dmapp components are mentioned in the layout specification you use

```
./bin/validate-timeline.sh --attributes --trace --layout sample-dmapp/layout.json sample-dmapp/timeline.xml
```

- validate your layout document with

```
./bin/validate-layout.sh sample-dmapp/layout.json
```

- Upload you document to the CDN (for a document that lives in sandbox use `toCDNsandbox.sh`
  in stead of `toCDNdmapps.sh`). Both scripts will print the URL at which the
  directory is accessible over the net.
  
```
./bin/toCDNdmapps.sh sample-dmapp
```

- Optionally, run your document with the symbolic execution engine, it will give
  different errors than the real playback engine. The `--layoutRenderer` opens a browser
  window that will give you a live preview of where things will be rendered.
  The `--kibana` option opens a browser window that will show you all the output of the timeline and
  layout services for this run.
  
```
./bin/dryrun.sh --layoutRenderer --kibana --layoutDoc https://origin.2immerse.advdev.tv/dmapps/sample-dmapp/layout.json --timelineDoc https://origin.2immerse.advdev.tv/dmapps/sample-dmapp/timeline.xml

```

- It is possible to use the `dry-run` script to test multiple devices at the same time,
  use `--help` for more information. Look at `--start` and `--wait` options.

- If you want to actually play back your document in Chrome, using the real client, run:

```
./bin/play.sh https://origin.2immerse.advdev.tv/dmapps/sample-dmapp/layout.json https://origin.2immerse.advdev.tv/dmapps/sample-dmapp/timeline.xml
```

- In here, you can press the "DEBUG" button in the lower right corner to get some debug info. There, you can
  also select to open a new tab with the logger output (as with `dryrun.sh --kibana`). 
  
- Instructions for then running on the Odroid to be provided.

- Instructions for then running on Odroid+tablet to be provided.
