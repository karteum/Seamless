#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Seamless : a tool to automate the generation of workspaces for Seamcat, for all combinations of values of several variables to explore
(More informations on Seamcat on https://cept.org/eco/eco-tools-and-services/seamcat-spectrum-engineering-advanced-monte-carlo-analysis-tool )
@author: Adrien DEMAREZ

Generate the set of changesets to cover all the combinations of changes for all parameters
    Input : arbitrary number of parameter in a list such as [('xpath1','xattname1', oldvalue (ignored), newvalue (ignored), 'varname1','["free_space","HATA rural"]'),('xpath2','xattname2',oldvalue (ignored), newvalue (ignored), 'varname2','[1,2,3]'),('xpath3','xattname3',oldvalue (ignored), newvalue (ignored), 'varname3','range(15,19)'), ...]
    Where -> xpath/xattname: XML node ID and attribute name (e.g. from xmldiff), varname: param name (for sws filename), last_parameter: Python list or generator with the range of values for that parameter
"""

SEAMCAT="/opt/Seamcat/SEAMCAT-5.4.1.jar"
OUTPUT_VAR="Average bitrate loss (ref. cell)"
DEFAULT_EVENTS=5000
DEFAULT_OUTFILENAMES='seamless_out/seamres'

from lxml import etree as ET #import xml.etree.cElementTree as ET
from zipfile import ZipFile,ZIP_DEFLATED
from xmldiff import main as xdiff
from xmldiff.actions import UpdateAttrib
from itertools import product
import os,sys
import subprocess
import numpy as np
import pandas as pd
import tempfile,webbrowser
import difflib
import xxhash
from io import StringIO
import argparse
#import toml
#from graphtage import xml as gxml
#from textwrap import fill

#plist = {"aaa" : [("xpath1","att1", [1,2,3]),("xpath2","att2", [4,5,6]),],"ccc" : [("xpath3", ["valname1","valname2"],[[(1,2,3),(4,5,6)], [(1,3,8),(2,7,6)] ] )]}
def plist_parse(plist1):
    # FIXME: because of eval(), this code is _unsafe_ and care should be taken to only enter trusted and valid variable ranges/lists...
    # => Maybe use TOML parsing instead of eval() when the code is more mature...
    plist=eval(open(plist1).read().replace('\n','')) if isinstance(plist1,str) else plist1
    # TODO: check consistency
#    for changeset in plist.values():
#        reflength = len(changeset[0][2])
#        for change in changeset:
#            assert(len(change[2])==reflength)
    return plist

def gencombinations(myvars):
    myvars_idx = {k:range(len(v[0][2])) for k,v in myvars.items() if len(v)>0}
    return product(*myvars_idx.values())

def swsgenallfiles(oldsws, plist, basefilename=DEFAULT_OUTFILENAMES):
    root_old=swsload(oldsws)
    myvars = plist_parse(plist)
    resmatrix = np.empty([len(v[0][2]) for v in myvars.values()])
    patches_idx=gencombinations(myvars)
    #aaa=0
    for patchidx in patches_idx:
        newsws_filename=basefilename+'_'
        patch=[]
        for var_changeset,varidx in zip(myvars.values(),range(len(myvars.values()))):
            var_val_index=patchidx[varidx]
            newsws_filename += '%c%d' % (chr(ord('A')+varidx),var_val_index) # Don't use directly the variable name or value in the filename (otherwise issues such as "" and spaces could appear in the filename, and it could also potentially be long) => use the variable index (A, B, C, ... for var name, and 1, 2, 3, ... for var index value)
            for xpath_ext,xnoderange,valrange in var_changeset:
                if len(xnoderange)>0:
                    for nodeindex,nodeindexindex in zip(xnoderange,range(len(xnoderange))):
                        xpath=xpath_ext.replace("$$",str(nodeindex)) # xpath unfortunately does not enable to express conveniently a subset array of nodes so we have to do it manually...
                        if xpath.endswith('/'):  # this is a vector => rewrite it as a whole for each nodeindex location. FIXME: the same plist should ensure that the same vector is not changed multiple times as part of the changeset for different variables !
                            xpath_final=xpath[:-1]
                            xml_changevec(root_old,xpath_final,valrange[var_val_index])
                        elif "@" in xpath:
                            newval = valrange[var_val_index][nodeindexindex]
                            xpath_final,xpath_attrib=xpath.split('@') # xpath is originally not a "real" valid xpath but rather xpath@attrib => need to separate the two
                            patch.append(UpdateAttrib(xpath_final, xpath_attrib, str(newval)))
                        else:
                            print("__error__ : " + xpath)
                elif "@" in xpath_ext:
                    newval = valrange[var_val_index]
                    xpath_final,xpath_attrib=xpath_ext.split('@')
                    patch.append(UpdateAttrib(xpath_final, xpath_attrib, str(newval)))
                else:
                    print("__error__ : " + xpath_ext)
        swsgenfile(root_old, newsws_filename+".sws", patch)
        swsexec(newsws_filename+".sws")
        res = swrget(newsws_filename+'.swr')
        #print('\n_____\n')
        #aaa+=1
        #res=aaa
        resmatrix[patchidx]=res
    return resmatrix

def xml_changevec(xmlroot,xpath,vec): # WARNING: only works with vectors of Point2d or Point3d !
    #print(f"changevec {xpath} -> {vec}")
    node=xmlroot.xpath(xpath)[0]
    parser = ET.XMLParser(remove_blank_text=True)
    for k in node:
        node.remove(k)
    l=len(vec[0])
    assert(l==2 or l==3)
    for k in vec:
        z=f'z="{k[2]}"' if l==3 else ""
        xmlnode=f'<point{l}d x="{k[0]}" y="{k[1]}" {z} />'
        node.append(ET.XML(xmlnode,parser))        
    #ET.dump(node)

def swsgenfile(oldsws_root, newsws_filename, patch):
    #print((oldsws_root, newsws_filename, patch))
    root_new=xdiff.patch_tree(patch, oldsws_root)
    doc_new=ET.tostring(root_new, pretty_print=True, encoding='utf-8', xml_declaration=True)
    with ZipFile(newsws_filename, mode="w", compression=ZIP_DEFLATED, compresslevel=5) as swsdata:
        swsdata.writestr("scenario.xml", doc_new)

#from numpy_html import array_to_html
#    html_res=array_to_html(mat)
def ndarray_html(mat,plist):
    html='<html><head><title>Results</title><style>\nbody {font-family:"arial";font-size: 11;}\ntable {border-collapse: collapse;}</style></head><body>'
    myvars = plist_parse(plist)
    allvars=list(myvars.keys())
    varname_cols=allvars[-1]
    cols_changeset=list(myvars.values())[-1]
    label_cols=list(cols_changeset[0][2]) if len(cols_changeset)==1 and len(cols_changeset[0][1])==0 else None
    varname_lines=allvars[-2]
    lines_changeset=list(myvars.values())[-2]
    label_lines=list(lines_changeset[0][2]) if len(lines_changeset)==1 and len(lines_changeset[0][1])==0 else None
    idxprev=[0]*(len(mat.shape)-2)
    idxlevel=1
    for idx in product(*[range(x) for x in mat.shape[:-2]]): # iterate over all dimensions of the n-d array and only keep a 2D array (i.e. 2 last dimensions) for each iteration
        if len(mat.shape)>2:
            params=[]
            for k in range(len(idx)):
                if idxlevel==0 and idx[k]!=idxprev[k]:
                    idxlevel=k+1
                varname = allvars[k]
                changeset=list(myvars.values())[k]
                varvalue = changeset[0][2][idx[k]] if len(changeset)==1 and len(changeset[0][1])==0 else idx[k]
                params.append('%s=%s' % (varname,varvalue))
            html+="<h%d>%s</h%d>" % (idxlevel,','.join(params),idxlevel)
            idxprev=idx
            idxlevel=0
        df=pd.DataFrame(mat[idx], index=label_lines, columns=label_cols)
        df.columns.name=varname_cols ; df.index.name=varname_lines
        html+=df.to_html()
    html+='</body></html>'
    return html

def openbrowser(html):
    with tempfile.NamedTemporaryFile('w', delete=False) as f:
        f.write(html)
        webbrowser.open('file://' + f.name)

def swsload(swsfile):
    xmldata = ZipFile(swsfile).open("scenario.xml").read()
    parser = ET.XMLParser(remove_blank_text=True, encoding="utf8")
    return ET.XML(xmldata,parser)

def swsdiff(oldsws,newsws):
    root_old=swsload(oldsws)
    root_new=swsload(newsws)
    diffs=xdiff.diff_trees(root_old,root_new, diff_options={'F': 0.5, 'ratio_mode': 'accurate'})
    res=[]
    for patch in diffs:
        if isinstance(patch,UpdateAttrib):
            orig_node = root_old.xpath(patch[0]) #orig_node = root_old.findall('.'+patch[0])
            orig_value = orig_node[0].attrib[patch[1]] if orig_node and patch[1] in orig_node[0].attrib else "_"
            res.append((patch[0], patch[1], orig_value, str(patch[2])))
    return diffs,res

def diff_lines_html(old,new,onlydiffs=False):
    # Fast compute and show diff between two files (comparison at a line level, not at a word level !). "old" and "new" are strings
    # Principle : for both documents and for each line, compute a hash of the data in the line (using xxhash which is fast) => then the whole document becomes a list of hashes ([hash_line1, hash_line2, ...])
    # Then we can use difflib (or any other diff algorithm on those two lists of hashes)
    xxh1=[] ; xxh2=[]
    # First pass : preprocess and compute xxhash for each line (fast operation)
    fp1=StringIO(old)
    fp2=StringIO(new)
    for line in fp1.readlines():
        xxh1.append(xxhash.xxh32(line).hexdigest())
    for line in fp2.readlines():
        xxh2.append(xxhash.xxh32(line).hexdigest())

    # Second pass : compute diff between stream of xxhashes (much faster than computing diff on data itself, which alleviates difflib's inherent slowness), and generate HTML
    html = []
    fp1=StringIO(old)
    fp2=StringIO(new)
    d = difflib.Differ()
    for a in d.compare(xxh1,xxh2):
        if a[0] == '+':
            data = fp2.readline()
            htmlop1 = "<ins>"
            htmlop2 = "</ins>"
        elif a[0] == '-':
            data = fp1.readline()
            htmlop1 = "<del>"
            htmlop2 = "</del>"
        elif a[0] == "?" or len(a)<10: # FIXME: what does it mean ?
            print(a)
            continue
        else:
            data = fp1.readline()
            data2 = fp2.readline() # increase the file pointer to keep sync
            if onlydiffs:
                data=""
                data2=""
            assert(data==data2)
            htmlop1 = ""
            htmlop2 = ""
        text = data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "&para;<br>\n")
        html.append("%s%s%s" % (htmlop1, text, htmlop2))
    res = """<html><head><title></title><style>\nbody {font-family:"lucida console";font-size: 11;}\nins {background:#e6ffe6;}\ndel {background:#ffe6e6;}\n</style></head><body>\n\n"""
    res += "".join(html).replace("</ins><ins>","").replace("</del><del>",'') # FIXME: ideally the diff should not be line-by-line but rather block-by-block. We use this small hack until this is improved
    res += "\n</body></html>\n"
    return res

def swsexec(swsfile,events=DEFAULT_EVENTS):
    print("________\nExecuting: " + swsfile)
    outfile = os.path.splitext(swsfile)[0] +'.swr'
    CMD = f'java -classpath "{SEAMCAT}" org.seamcat.CommandLine "{swsfile}" result="{outfile}" events={events}' # -cp instead of -classpath
    #subprocess.call(CMD, shell=False)
    os.system(CMD)

def swrget(swrfile, param=OUTPUT_VAR):
    xmldata = ZipFile(swrfile).open("results.xml").read()
    parser = ET.XMLParser(remove_blank_text=True, encoding="utf8")
    root=ET.XML(xmldata,parser)
    node=root.findall("./SEAMCATResults/item[1]/SingleValues/Single[@name='%s']" % (param))[0]
    return float(node.attrib['value']) if node.attrib['type']=='double' else node.attrib['value']

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    parser_makepatch = subparsers.add_parser('makepatch', help="Make patch based on XML diff")
    parser_makepatch.add_argument("sws1", help="File 1")
    parser_makepatch.add_argument("sws2", help="File 2")
    parser_makepatch.add_argument("--outfile", "-o", help="Output patch file", default=None)

    parser_diffhtml = subparsers.add_parser('diffhtml', help="HTML diff")
    parser_diffhtml.add_argument("sws1", help="File 1")
    parser_diffhtml.add_argument("sws2", help="File 2")
    parser_diffhtml.add_argument("--onlydiffs", "-d", help="Show only diffs", action='store_true', default=False)

    parser_gensws = subparsers.add_parser('compute', help="Make computations")
    parser_gensws.add_argument("conffile", help="Configuration file")
    parser_gensws.add_argument("infile", help="Input sws file")
    parser_gensws.add_argument("outfile", help="Output npy file")

    parser_showres = subparsers.add_parser('showres', help="Generate HTML report")
    parser_showres.add_argument("conffile", help="Configuration file")
    parser_showres.add_argument("outfile", help="Output npy file")

    args = parser.parse_args()

    if args.subcommand=='makepatch': # diff
        file1=sys.argv[2]
        file2=sys.argv[3]
        diff,plist=swsdiff(args.sws1,args.sws2)
        print('\n'.join([str(x) for x in plist]))
        if args.outfile:
            with open(args.outfile,'w') as fp:
                fp.write('\n'.join([str(x) for x in plist])) # str(plist).replace("),","),\n")
    elif args.subcommand=='diffhtml':
        ET1=swsload(args.sws1)
        ET2=swsload(args.sws2)
        xml1=ET.tostring(ET1, pretty_print=True, encoding='utf-8', xml_declaration=True)
        xml2=ET.tostring(ET2, pretty_print=True, encoding='utf-8', xml_declaration=True)
        html=diff_lines_html(xml1.decode(),xml2.decode(), args.onlydiffs)
        openbrowser(html)
    elif args.subcommand=='compute': # gen
        os.makedirs(os.path.dirname(DEFAULT_OUTFILENAMES), exist_ok=False)
        hypercube=swsgenallfiles(args.infile,args.conffile)
        np.save(args.outfile,hypercube)
    elif args.subcommand=='showres':
        plist = sys.argv[2]
        hypercube=np.load(args.outfile)
        html=ndarray_html(hypercube,args.conffile)
        openbrowser(html)

##################################
# Old code

#def swsexecall():
#    pool = Pool(processes=cpu_count())
#    filelist= ["bar/res_a24.sws","bar/res_a25.sws","bar/res_a26.sws","bar/res_a27.sws"]
#    filelist2= ["bar/res_a24.swr","bar/res_a25.swr","bar/res_a26.swr","bar/res_a27.swr"]
#    pool.map(swsexec, filelist)
#    res={}
#    for outfile in filelist2:
#        res[os.path.basename(outfile)]=swrget(outfile)
#    print(str(res))
