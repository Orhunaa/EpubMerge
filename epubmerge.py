#!/usr/bin/python
# -*- coding: utf-8 -*-

# epubmerge.py 1.0

# ... [copyright and licensing information] ...

import sys
import os
import glob
import re
import string
from optparse import OptionParser
import zlib
import zipfile
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
from time import time

# Removed 'from exceptions import KeyError' as it's not needed in Python 3

from xml.dom.minidom import parse, parseString, getDOMImplementation
        
def main(argv):
    usage = "usage: %prog [options]"
    parser = OptionParser(usage)
    parser.add_option("-o", "--output", dest="outputopt", default="merge.epub",
                      help="Set OUTPUT file, Default: merge.epub", metavar="OUTPUT")
    parser.add_option("-t", "--title", dest="titleopt", default=None,
                      help="Use TITLE as the metadata title.  Default: '<first epub title> Anthology'", metavar="TITLE")
    parser.add_option("-d", "--description", dest="descopt", default=None,
                      help="Use DESC as the metadata description.  Default: '<epub title> by <author>' for each epub.", metavar="DESC")
    parser.add_option("-a", "--author",
                      action="append", dest="authoropts", default=[],
                      help="Use AUTHOR as a metadata author, multiple authors may be given, Default: <All authors from epubs>", metavar="AUTHOR")
    parser.add_option("-f", "--first",
                      action="store_true", dest="fromfirst", default=False,
                      help="Take all metadata from first input epub",)
    parser.add_option("-n", "--titles-in-toc",
                      action="store_true", dest="titlenavpoints",
                      help="Put an entry in the TOC for each epub, in addition to each epub's chapters.",)
    parser.add_option("-s", "--strip-title-toc",
                      action="store_true", dest="striptitletoc",
                      help="Strip any title_page.xhtml and toc_page.xhtml files.",)
    
    (options, args) = parser.parse_args()
    
    epub_files = glob.glob('*.epub')
    print("Found EPUB files:", epub_files)  

    ## Add .epub if not already there.
    if not options.outputopt.lower().endswith(".epub"):
        options.outputopt=options.outputopt+".epub"

    print("output file: " + options.outputopt)
    doMerge(options.outputopt,
            epub_files,  # Use the found EPUB files
            options.authoropts,
            options.titleopt,
            options.descopt,
            options.fromfirst,
            options.titlenavpoints,
            options.striptitletoc)

    # output = StringIO.StringIO()
    # files = []
    # for file in args:
    #     f = open(file,"rb")
    #     fio = StringIO.StringIO(f.read())
    #     f.close()
    #     files.append(fio)

    # doMerge(output,files,authoropts,titleopt,descopt,fromfirst,titlenavpoints,striptitletoc)

    # out = open(outputopt,"wb")
    # out.write(output.getvalue())
    
def doMerge(outputio, files, authoropts=[], titleopt=None, descopt=None,
            fromfirst=False,
            titlenavpoints=True,
            striptitletoc=False,
            forceunique=True):
    '''
    [Function documentation]
    '''
    filecount=0
    source=None
    
    outputepub = ZipFile(outputio, "w", compression=ZIP_STORED)
    outputepub.debug = 3
    outputepub.writestr("mimetype", "application/epub+zip")
    outputepub.close()
    
    outputepub = ZipFile(outputio, "a", compression=ZIP_DEFLATED)
    outputepub.debug = 3
    
    containerdom = getDOMImplementation().createDocument(None, "container", None)
    containertop = containerdom.documentElement
    containertop.setAttribute("version","1.0")
    containertop.setAttribute("xmlns","urn:oasis:names:tc:opendocument:xmlns:container")
    rootfiles = containerdom.createElement("rootfiles")
    containertop.appendChild(rootfiles)
    rootfiles.appendChild(newTag(containerdom,"rootfile",{"full-path":"content.opf",
                                                          "media-type":"application/oebps-package+xml"}))
    outputepub.writestr("META-INF/container.xml",containerdom.toprettyxml(indent='   ',encoding='utf-8'))
    
    items = [] # list of (id, href, type) tuples(all strings) -- From .opfs' manifests
    items.append(("ncx","toc.ncx","application/x-dtbncx+xml")) ## we'll generate the toc.ncx file,
                                                               ## but it needs to be in the items manifest.
    itemrefs = [] # list of strings -- idrefs from .opfs' spines
    navmaps = [] # list of navMap DOM elements -- TOC data for each from toc.ncx files

    booktitles = [] # list of strings -- Each book's title
    allauthors = [] # list of lists of strings -- Each book's list of authors.

    filelist = []
    
    booknum=1
    firstmetadom = None
    
    for file in files:
        if file is None:
            continue

        try:
            epub = ZipFile(file, 'r')
        except zipfile.BadZipFile:
            print(f"Skipping bad or invalid EPUB file: {file}")
            continue  # Skip this file
    
    for file in files:
        if file == None : continue
        
        book = "%d" % booknum
        bookdir = ""
        bookid = ""
        if forceunique:
            bookdir = "%d/" % booknum
            bookid = "a%d" % booknum
        #print "book %d" % booknum
        
        epub = ZipFile(file, 'r')

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
        if booknum==1:
            firstmetadom = metadom.getElementsByTagName("metadata")[0]
            try:
                source=firstmetadom.getElementsByTagName("dc:source")[0].firstChild.data.encode("utf-8")
            except:
                source=""
            #print "Source:%s"%source

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
                    navpoint.setAttribute("id",bookid+navpoint.getAttribute("id"))

                for content in tocdom.getElementsByTagName("content"):
                    content.setAttribute("src",bookdir+relpath+content.getAttribute("src"))

                navmaps.append(tocdom.getElementsByTagName("navMap")[0])
            else:
                id = bookid + item.getAttribute("id")
                href = bookdir + relpath + item.getAttribute("href")    
                
                if not striptitletoc or not re.match(r'.*/(title|toc)_page\.xhtml',
                                          item.getAttribute("href")):
                    if href not in filelist:
                        try:
                            file_content = epub.read(relpath + item.getAttribute("href"))
                            outputepub.writestr(href, file_content)  # href is a string, file_content is bytes
                            if re.match(r'.*/(file|chapter)\d+\.xhtml', href):
                                filecount += 1
                            items.append((id, href, item.getAttribute("media-type")))  # href as a string
                            filelist.append(href)
                        except KeyError as ke:
                            pass

                
        for itemref in metadom.getElementsByTagName("itemref"):
            if not striptitletoc or not re.match(r'(title|toc)_page', itemref.getAttribute("idref")):
                itemrefs.append(bookid+itemref.getAttribute("idref"))

        booknum=booknum+1;
    
    uniqueid="epubmerge-uid-%d" % int(time())  # Added int() for type consistency
    
    contentdom = getDOMImplementation().createDocument(None, "package", None)
    package = contentdom.documentElement
    if fromfirst and firstmetadom:
        metadata = firstmetadom
        firstpackage = firstmetadom.parentNode
        package.setAttribute("version",firstpackage.getAttribute("version"))
        package.setAttribute("xmlns",firstpackage.getAttribute("xmlns"))
        package.setAttribute("unique-identifier",firstpackage.getAttribute("unique-identifier"))
    else:
        package.setAttribute("version","2.0")
        package.setAttribute("xmlns","http://www.idpf.org/2007/opf")
        package.setAttribute("unique-identifier","epubmerge-id")
        metadata=newTag(contentdom,"metadata",
                        attrs={"xmlns:dc":"http://purl.org/dc/elements/1.1/",
                               "xmlns:opf":"http://www.idpf.org/2007/opf"})
        metadata.appendChild(newTag(contentdom,"dc:identifier",text=uniqueid,attrs={"id":"epubmerge-id"}))
        if not booktitles:
            print("No titles found in the input files.")
            return  # Or handle the error as you see fit

        if titleopt is None:
            titleopt = booktitles[0] + " Anthology"
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
                if author not in usedauthors:
                    usedauthors[author]=author
                    metadata.appendChild(newTag(contentdom,"dc:creator",
                                                attrs={"opf:role":"aut"},
                                                text=author))
    
        metadata.appendChild(newTag(contentdom,"dc:contributor",text="epubmerge",attrs={"opf:role":"bkp"}))
        metadata.appendChild(newTag(contentdom,"dc:rights",text="Copyrights as per source stories"))
        metadata.appendChild(newTag(contentdom,"dc:language",text="en"))
    
        if not descopt:
            description = newTag(contentdom, "dc:description", text="Anthology containing:\n")
            for booknum in range(len(booktitles)):
                booktitle = booktitles[booknum]
                authors = allauthors[booknum]
                author_text = " by " + authors[0] if authors else " by Unknown Author"
                book_info = booktitle + author_text + "\n"
                description.appendChild(contentdom.createTextNode(book_info))
        else:
            description = newTag(contentdom, "dc:description", text=descopt)
        metadata.appendChild(description)   
    
    package.appendChild(metadata)
    
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

    ## TOC navPoints can be nested, but this flattens them for
    ## simplicity, plus adds a navPoint for each epub.
    
    if not descopt:
        description = newTag(contentdom, "dc:description", text="Anthology containing:\n")
    else:
        description = newTag(contentdom, "dc:description", text=descopt)

    
    booknum=0
    for booknum, navmap in enumerate(navmaps):
        navpoints = navmap.getElementsByTagName("navPoint")
        if len(navpoints) == 0:
            print(f"Creating basic TOC entry for book {booknum+1} without navPoints")
            # Create a basic TOC entry for the book
            newnav = tocncxdom.createElement("navPoint")
            newnav.setAttribute("id", "book" + str(booknum+1))
            newnav.setAttribute("playOrder", str(booknum+1))
            navlabel = tocncxdom.createElement("navLabel")
            navlabel_text = tocncxdom.createElement("text")
            navlabel_text.appendChild(tocncxdom.createTextNode("Book " + str(booknum+1)))
            navlabel.appendChild(navlabel_text)
            newnav.appendChild(navlabel)

            content = tocncxdom.createElement("content")
            content.setAttribute("src", "path/to/start/of/book" + str(booknum+1) + ".xhtml") # Adjust the path
            newnav.appendChild(content)

            tocnavMap.appendChild(newnav)
            continue

        newnav = navpoints[0].cloneNode(True)
        newnav.setAttribute("id", "book" + newnav.getAttribute("id"))
        
        if booknum >= len(booktitles):
            break  # Break the loop if there are no more titles

        # Generate TOC entry
        newnav = navmap.getElementsByTagName("navPoint")[0].cloneNode(True)
        newnav.setAttribute("id", "book" + newnav.getAttribute("id"))
        book_title = booktitles[booknum]
        author_text = " by " + allauthors[booknum][0] if allauthors[booknum] else " by Unknown Author"
        toc_text = str(booknum+1).zfill(2) + ". " + book_title
        newtext = newTag(tocncxdom, "text", text=toc_text)
        text = newnav.getElementsByTagName("text")[0]
        text.parentNode.replaceChild(newtext, text)
        tocnavMap.appendChild(newnav)

        # Add to description
        if not descopt:
            description_info = toc_text + author_text + "\n"
            description.appendChild(contentdom.createTextNode(description_info))

    metadata.appendChild(description)


            
    #for navpoint in navpoints:
    navpoint = newnav
    #print "navpoint:%s"%navpoint.getAttribute("id")
    if not striptitletoc or not re.match(r'(title|toc)_page',navpoint.getAttribute("id")):
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

    return (source, filecount)

# Utility method for creating new tags.
def newTag(dom, name, attrs=None, text=None):
    tag = dom.createElement(name)
    if( attrs is not None ):
        for attr in attrs.keys():
            tag.setAttribute(attr,attrs[attr])
    if( text is not None ):
        tag.appendChild(dom.createTextNode(text))
    return tag
    
if __name__ == "__main__":
    main(sys.argv[1:])

