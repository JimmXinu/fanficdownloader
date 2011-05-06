#!/usr/bin/python
# -*- coding: utf-8 -*-

# epubmerge.py 1.0

# Copyright 2011, Jim Miller

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import getopt
import os

import zlib
import zipfile
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
from time import time

from xml.dom.minidom import parse, parseString, getDOMImplementation
    
def usage():
    print "epubmerge 1.0    Merges multiple epub format ebooks together"
    print "\nUsage: " + sys.argv[0]+" [options] <input epub> [<input epub> ...]\n"
    print " Options:"
    print " -h                 --help"
    print " -o <output file>   --output=<output file>   Default: merge.epub"
    print " -t <output title>  --title=<output title>   Default: '<First Title> Anthology'"
    print " -a <author name>   --author=<author name>   Default: <All authors from epubs>"
    print "                                             Multiple authors may be given."
    
def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "t:a:o:h", ["title=","author=", "output=","help"])
    except getopt.GetoptError, err:
        # print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        usage()
        sys.exit(2)

    if( len(args) < 1 ):
        usage()
        sys.exit()
        
    outputopt = "merge.epub"
    titleopt = None
    authoropts = [] # list of strings
    
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-t", "--title"):
            titleopt = a
        elif o in ("-a", "--author"):
            authoropts.append(a)
        elif o in ("-o", "--output"):
            outputopt = a
        else:
            assert False, "unhandled option"

    ## Add .epub if not already there.
    if( not outputopt.lower().endswith(".epub") ):
        outputopt=outputopt+".epub"

    print "output file: "+outputopt
        
    ## Write mimetype file, must be first and uncompressed.
    ## Older versions of python(2.4/5) don't allow you to specify
    ## compression by individual file.
    ## Overwrite if existing output file.
    outputepub = ZipFile(outputopt, "w", compression=ZIP_STORED)
    outputepub.debug = 3
    outputepub.writestr("mimetype", "application/epub+zip")
    outputepub.close()

    ## Re-open file for content.
    outputepub = ZipFile(outputopt, "a", compression=ZIP_DEFLATED)
    outputepub.debug = 3

    ## Create META-INF/container.xml file.  The only thing it does is
    ## point to content.opf
    containerdom = getDOMImplementation().createDocument(None, "container", None)
    containertop = containerdom.documentElement
    containertop.setAttribute("version","1.0")
    containertop.setAttribute("xmlns","urn:oasis:names:tc:opendocument:xmlns:container")
    rootfiles = containerdom.createElement("rootfiles")
    containertop.appendChild(rootfiles)
    rootfiles.appendChild(newTag(containerdom,"rootfile",{"full-path":"content.opf",
                                                          "media-type":"application/oebps-package+xml"}))
    outputepub.writestr("META-INF/container.xml",containerdom.toprettyxml(indent='   ',encoding='utf-8'))    

    ## Process input epubs.
    
    items = [] # list of (id, href, type) tuples(all strings) -- From .opfs' manifests
    items.append(("ncx","toc.ncx","application/x-dtbncx+xml")) ## we'll generate the toc.ncx file,
                                                               ## but it needs to be in the items manifest.
    itemrefs = [] # list of strings -- idrefs from .opfs' spines
    navmaps = [] # list of navMap DOM elements -- TOC data for each from toc.ncx files

    booktitles = [] # list of strings -- Each book's title
    allauthors = [] # list of lists of strings -- Each book's list of authors.
    
    booknum=1
    for filename in args:
        print "input file: "+filename
        book = "%d" % booknum
        
        epub = ZipFile(filename, 'r')

        ## Find the .opf file.
        container = epub.read("META-INF/container.xml")
        containerdom = parseString(container)
        rootfilenodelist = containerdom.getElementsByTagName("rootfile")
        rootfilename = rootfilenodelist[0].getAttribute("full-path")

        ## Save the path to the .opf file--hrefs inside it are relative to it.
        relpath = os.path.dirname(rootfilename)
        if( len(relpath) > 0 ):
            relpath=relpath+"/"
            
        metadom = parseString(epub.read(rootfilename))

        ## Save indiv book title
        booktitles.append(metadom.getElementsByTagName("dc:title")[0].firstChild.data)

        ## Save authors.
        authors=[]
        for creator in metadom.getElementsByTagName("dc:creator"):
            if( creator.getAttribute("opf:role") == "aut" ):
                authors.append(creator.firstChild.data)
        allauthors.append(authors)

        for item in metadom.getElementsByTagName("item"):
            if( item.getAttribute("media-type") == "application/x-dtbncx+xml" ):
                # TOC file is only one with this type--as far as I know.
                # grab the whole navmap, deal with it later.
                tocdom = parseString(epub.read(relpath+item.getAttribute("href")))
                
                for navpoint in tocdom.getElementsByTagName("navPoint"):
                    navpoint.setAttribute("id","a"+book+navpoint.getAttribute("id"))

                for content in tocdom.getElementsByTagName("content"):
                    content.setAttribute("src",book+"/"+relpath+content.getAttribute("src"))

                navmaps.append(tocdom.getElementsByTagName("navMap")[0])
            else:
                id="a"+book+item.getAttribute("id")
                href=book+"/"+relpath+item.getAttribute("href")
                href=href.encode('utf8')
                items.append((id,href,item.getAttribute("media-type")))
                outputepub.writestr(href,
                                    epub.read(relpath+item.getAttribute("href")))
                
        for itemref in metadom.getElementsByTagName("itemref"):
            itemrefs.append("a"+book+itemref.getAttribute("idref"))

        booknum=booknum+1;

    ## create content.opf file. 
    uniqueid="epubmerge-uid-%d" % time() # real sophisticated uid scheme.
    contentdom = getDOMImplementation().createDocument(None, "package", None)
    package = contentdom.documentElement
    package.setAttribute("version","2.0")
    package.setAttribute("xmlns","http://www.idpf.org/2007/opf")
    package.setAttribute("unique-identifier","epubmerge-id")
    metadata=newTag(contentdom,"metadata",
                    attrs={"xmlns:dc":"http://purl.org/dc/elements/1.1/",
                           "xmlns:opf":"http://www.idpf.org/2007/opf"})
    package.appendChild(metadata)
    metadata.appendChild(newTag(contentdom,"dc:identifier",text=uniqueid,attrs={"id":"epubmerge-id"}))
    if( titleopt is None ):
        titleopt = booktitles[0]+" Anthology"
    metadata.appendChild(newTag(contentdom,"dc:title",text=titleopt))

    # If cmdline authors, use those instead of those collected from the epubs
    # (allauthors kept for TOC & description gen below.
    if( len(authoropts) > 1  ):
        useauthors=[authoropts]
    else:
        useauthors=allauthors
        
    usedauthors=dict()
    for authorlist in useauthors:
        for author in authorlist:
            if( not usedauthors.has_key(author) ):
                usedauthors[author]=author
                metadata.appendChild(newTag(contentdom,"dc:creator",
                                            attrs={"opf:role":"aut"},
                                            text=author))

    metadata.appendChild(newTag(contentdom,"dc:contributor",text="epubmerge",attrs={"opf:role":"bkp"}))
    metadata.appendChild(newTag(contentdom,"dc:rights",text="Copyrights as per source stories"))
    metadata.appendChild(newTag(contentdom,"dc:language",text="en"))

    # created now, but not filled in until TOC generation to save loops.
    description = newTag(contentdom,"dc:description",text="Anthology containing:\n")
    metadata.appendChild(description)
    
    manifest = contentdom.createElement("manifest")
    package.appendChild(manifest)
    for item in items:
        (id,href,type)=item
        manifest.appendChild(newTag(contentdom,"item",
                                       attrs={'id':id,
                                              'href':href,
                                              'media-type':type}))
        
    spine = newTag(contentdom,"spine",attrs={"toc":"ncx"})
    package.appendChild(spine)
    for itemref in itemrefs:
        spine.appendChild(newTag(contentdom,"itemref",
                                    attrs={"idref":itemref,
                                           "linear":"yes"}))

    ## create toc.ncx file
    tocncxdom = getDOMImplementation().createDocument(None, "ncx", None)
    ncx = tocncxdom.documentElement
    ncx.setAttribute("version","2005-1")
    ncx.setAttribute("xmlns","http://www.daisy.org/z3986/2005/ncx/")
    head = tocncxdom.createElement("head")
    ncx.appendChild(head)
    head.appendChild(newTag(tocncxdom,"meta",
                            attrs={"name":"dtb:uid", "content":uniqueid}))
    head.appendChild(newTag(tocncxdom,"meta",
                            attrs={"name":"dtb:depth", "content":"1"}))
    head.appendChild(newTag(tocncxdom,"meta",
                            attrs={"name":"dtb:totalPageCount", "content":"0"}))
    head.appendChild(newTag(tocncxdom,"meta",
                            attrs={"name":"dtb:maxPageNumber", "content":"0"}))
    
    docTitle = tocncxdom.createElement("docTitle")
    docTitle.appendChild(newTag(tocncxdom,"text",text=titleopt))
    ncx.appendChild(docTitle)
    
    tocnavMap = tocncxdom.createElement("navMap")
    ncx.appendChild(tocnavMap)

    ## TOC navPoints can ge nested, but this flattens them for
    ## simplicity, plus adds a navPoint for each epub.
    booknum=0
    for navmap in navmaps:
        navpoints = navmap.getElementsByTagName("navPoint")
        ## Copy first navPoint of each epub, give a different id and
        ## text: bookname by authorname
        newnav = navpoints[0].cloneNode(True)
        newnav.setAttribute("id","book"+newnav.getAttribute("id"))
        ## For purposes of TOC titling & desc, use first book author
        newtext = newTag(tocncxdom,"text",text=booktitles[booknum]+" by "+allauthors[booknum][0])
        description.appendChild(contentdom.createTextNode(booktitles[booknum]+" by "+allauthors[booknum][0]+"\n"))
        text = newnav.getElementsByTagName("text")[0]
        text.parentNode.replaceChild(newtext,text)
        tocnavMap.appendChild(newnav)
        
        for navpoint in navpoints:
            tocnavMap.appendChild(navpoint)
        booknum=booknum+1;

    ## Force strict ordering of playOrder
    playorder=1
    for navpoint in tocncxdom.getElementsByTagName("navPoint"):
        navpoint.setAttribute("playOrder","%d" % playorder)
        if( not navpoint.getAttribute("id").startswith("book") ):
            playorder = playorder + 1

    ## content.opf written now due to description being filled in
    ## during TOC generation to save loops.
    outputepub.writestr("content.opf",contentdom.toxml('utf-8'))
    outputepub.writestr("toc.ncx",tocncxdom.toxml('utf-8'))
    
    # declares all the files created by Windows.  otherwise, when
    # it runs in appengine, windows unzips the files as 000 perms.
    for zf in outputepub.filelist:
        zf.create_system = 0
    outputepub.close()

## Utility method for creating new tags.
def newTag(dom,name,attrs=None,text=None):
    tag = dom.createElement(name)
    if( attrs is not None ):
        for attr in attrs.keys():
            tag.setAttribute(attr,attrs[attr])
    if( text is not None ):
        tag.appendChild(dom.createTextNode(text))
    return tag
    
if __name__ == "__main__":
    main()
