# Seamless
Seamless is a tool intended to help performing sensitivity analysis in RF coexistence studies, by automating the generation of workspaces for Seamcat and the simulations for all combinations of values of several variables to explore.
More informations on Seamcat on https://cept.org/eco/eco-tools-and-services/seamcat-spectrum-engineering-advanced-monte-carlo-analysis-tool

## Usage
A prerequisite is to have the following packages installed : `pip install xxhash numpy xmldiff pandas lxml`

The main idea is to proceed as follows
* Generate a first "reference" Seamcat project file `ref.sws` (which is actually a zip file containing an XML subfile)
* For every variable you want to explore
  * start from `ref.sws` and change the proper parameter to another value and save the workspaces to a dedicated file `variable_n.sws`
  * Identify which XML node(s) is changed with `seamless makepatch ref.sws variable_n.sws [-o outfile]` (if -o is specified, the result is stored in outfile rather than displayed on the console). Such a change may be a single node or multiple nodes (e.g. in case of a vector change)
  * You may also more visually look at the differences between two .sws files with `seamless diffhtml ref.sws, variable_n.sws [-d onlydiff]` (if -d is specified, then only additions/suppressions are displayed rather than all the XML lines). This opens a web browser with an HTML page displaying the diff
* Create a configuration file (cf. following section) containing a description of all the XML nodes and the corresponding exploration domain for each variable
* Run the computation with `seamless compute conf_file.conf ref.sws output.npy` (which will generate the temporary .sws and .swr files in `seamless_out/` for each combination of value for all variables in the config file) and store one variable within the results (for the moment only "Average bitrate loss (ref. cell)") into an n-d array `output.npy`
* You may then use this .npy to explore/export the results and perform data analysis in Python. You may also generate an HTML report from the resulting hypercube (n-d array) with `seamless showres output.npy`. This opens a web browser with an HTML page displaying the report

## Configuration file format
WARNING : for convenience and brevity of the code, eval() is currently used (this might change in the future e.g. by using TOML instead of a raw Python string, but that's the situation now), therefore care should be taken to only use trusted configuration files and valid variable ranges/lists !

The main scheme is
* from toplevel: the conf file is a Python dictionary `{"variable1" : description1, "variable2" : description2, ...}`
* each "description" is an array of sub-descriptions (because several XML nodes may have to change simultaneously).
* each sub-description is a 3-uplet made of
  * String representing the XML node + XML attribute that is to be changed. If this string ends with "/" it is expected to be a vector entry (xpath containing the parent XML node, all sub-nodes to be replaced). Otherwise it is a scalar node that should contain XML node + XML attribute (written as `xpath@attrib`). If `$$` is used then this becomes a template (see next point)
  * Array of location values that will substitute `$$` in the above template (if `$$` is not used then this may just be []. For vector nodes this is assumed to be always non-empty).
  * Array of values for the variable. For vector entries, every "value" is an array of 2-uplet or 3-uplet (only 2d or 3d points are supported). For scalar nodes where len(location_array)>0, every "value" is an array of len(location_array) entries so that all those nodes are changed simultaneously

OK, maybe better with an example :)
```python
{
"mask" : [
    ('/Workspace/systems/system[$$]/configuration/transmitter/emissionCharacteristics/emissionMask/', [1,2,3,5,6,7],
    [ [(-30,-60,200),(-0.5,-60,200),(-0.35,-49,200),(-0.101,-30,200),(-0.1,0,200),(0.1,0,200),(0.101,-30,200),(0.35,-49,200),(0.5,-60,200),(30,-60,200)],
    [(-20,-1000,200),(-0.5001099999999999,-1000,200),(-0.5,-60,200),(-0.35,-49,200),(-0.101,-30,200),(-0.1,0,200),(0.1,0,200),(0.101,-30,200),(0.35,-49,200),(0.5,-60,200),(0.5001099999999999,-1000,200),(20,-1000,200)] ] )
],
"DC" : [
("/Workspace/systems/system[$$]/configuration/transmitter/emissionCharacteristics/power/distribution/user-defined-stair/point2d[1]@y", [1,2,3,5,6,7], [ [0.9,0.976,0.999]*2, [0.94,0.985,0.9994]*2]
)],
"Density" : [
("/Workspace/links/link[$$]/path/correlationSettings/customUI/customItem[2]@activeTx", [1,2,3,4], [ [4,16,78,1], [7,32,156,3] ]
)]
}
```

In that example above, we have 3 variables "mask", "DC" and "Density"
* "mask" has an XML vector node (ending with "/") that should be changed in 6 places simultaneously ("system1","system2","system3","system5","system6","system7") and two possible values for the vector
* "DC" is a scalar node. For the 1st "value" of this node, system1=0.9, system2=0.976, etc. For the 2nd "value" of this node, the 2nd sub-array will be used i.e. system1=0.94, system2=0.985, etc.
* "Density" is a scalar node and the same as above applies i.e. For the 1st "value" of this node, system1=4, system2=16, etc. and for the 2nd "value" of this node, system1=7, system2=32, etc.

# DISCLAIMER
This is work-in-progress and has only been tested on a few scenarios in personal simulations. It may contain bugs or not work for your case (feedback welcome !)
N.B. for the moment, it has only been tested with "Average bitrate loss (ref. cell)" as an output variable
