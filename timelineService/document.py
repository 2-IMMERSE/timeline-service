import sys
import urllib
import xml.etree.ElementTree as ET

class Document:
    def __init__(self):
        self.tree = None
        self.root = None
        
    def load(self, url):
        fp = urllib.urlopen(url)
        self.tree = ET.parse(fp)
        self.root = self.tree.getroot()
        
    def dump(self, fp):
        self.tree.write(fp)
        
def main():
    d = Document()
    d.load(sys.argv[1])
    d.dump(sys.stdout)
    
if __name__ == '__main__':
    main()
