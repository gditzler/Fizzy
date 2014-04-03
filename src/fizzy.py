#!/usr/bin/env python
import os
import sys
import argparse
import scipy.sparse as sp
import json
import numpy
import threading

__authors__ = [ "Gregory Ditzler", "Calvin Morrison" ]
__copyright__ = "Copyright 2014, EESI Laboratory (Drexel University)"
__license__ = "GPL"
__maintainer__ = "Gregory Ditzler"
__email__ = "gregory.ditzler@gmail.com"
__status__ = "Alpha"

def load_biom(fname):
  """
  load a biom file and return a dense matrix 
  :fname - string containing the path to the biom file
  :data - numpy array containing the OTU matrix
  :samples - list containing the sample IDs (important for knowing 
    the labels in the data matrix)
  :features - list containing the feature names
  """
  o = json.loads(open(fname,"U").read())
  if o["matrix_type"] == "sparse":
    data = load_sparse(o)
  else:
    data = load_dense(o)

  samples = []
  for sid in o["columns"]:
    samples.append(sid["id"])
  features = []
  for sid in o["rows"]:
    # check to see if the taxonomy is listed, this will generally lead to more 
    # descriptive names for the taxonomies. 
    if sid.has_key("metadata") and sid["metadata"] != None:
      if sid["metadata"].has_key("taxonomy"):
        # using json.dumps is a quick way to convert the dictionary to a string
        features.append(json.dumps(sid["metadata"]["taxonomy"]))
      else:
        features.append(sid["id"])
    else:
      features.append(sid["id"])
  return data, samples, features 

def load_dense(obj):
  """
  load a biom file in dense format
  :obj - json dictionary from biom file
  :data - dense data matrix
  """
  n_feat,n_sample = obj["shape"]
  data = numpy.array(obj["data"])
  return data.transpose()

def load_sparse(obj):
  """
  load a biom file in sparse format
  :obj - json dictionary from biom file
  :data - dense data matrix
  """
  n_feat,n_sample = obj["shape"] 
  data = numpy.zeros((n_feat, n_sample))
  for val in obj["data"]:
    data[val[0], val[1]] = val[2]
  data = data.transpose() 
  return data

def load_map(fname):
  """
  load a map file. this function does not have any dependecies on qiime's
  tools. the returned object is a dictionary of dictionaries. the dictionary 
  is indexed by the sample_ID and there is an added field for the the 
  available meta-data. each element in the dictionary is a dictionary with 
  the keys of the meta-data. 
  :fname - string containing the map file path
  :meta_data - dictionary containin the mapping file information  
  """
  f = open(fname, "U")
  mfile = []
  for line in f: 
    mfile.append(line.replace("\n","").replace("#","").split("\t"))
  meta_data_header = mfile.pop(0)

  meta_data = {}
  for sample in mfile:
    sample_id = sample[0]
    meta_data[sample_id] = {}
    for identifier, value in map(None, meta_data_header, sample):
      meta_data[sample_id][identifier] = value 
  return meta_data

def get_fs_methods():
  """
  get_fs_methods()
  return the feature selection methods that are 
  available for use in a list. note that the options
  are case sensitive. 
  """
  return ['CIFE','CMIM','CondMI','Condred','ICAP','JMI','MIM','MIFS','mRMR']

def convert_to_discrete(items):
  map_dic = {}
  discrete_arr = []

  # skip the "sample"
  disc_val = 0
  for item in items:
    if item not in map_dic:
       map_dic[item] = disc_val
       disc_val += 1
    discrete_arr.append(map_dic[item])

  return (map_dic, discrete_arr)

def run_pyfeast(data, labels, features, args):
  """
  run_pyfeast(data, labels, method)
  @data - numpy data (dense)
  @labels - vector of class labels (discrete)
  @features - list of feature names
  @method - feature selection method
  @n_select - number of features to select

  The feature selection method is based off of the FEAST 
  C variable selection toolbox. 

  Reference:
  Gavin Brown, Adam Pocock, Ming-Jie Zhao, and Mikel Lujan, "Conditional 
    Likelihood Maximisation: A Unifying Framework for Information Theoretic 
    Feature Selection," Journal of Machine Learning Research, vol. 13, 
    pp. 27--66, 2012.
    (http://jmlr.csail.mit.edu/papers/v13/brown12a.html)
  """
  try:
    fs_method = getattr(feast, args.fs_method)
  except AttributeError:
    raise AttributeError("Unknown feature selection method is being specified "
        +"for PyFeast. Make sure the feature selection method being selected "
        +"is a valid one. ")

  if len(data.transpose()) < args.select:
    raise ValueError("n_select must be less than the number of observations.")
  if args.select <= 0:
    raise ValueError("n_select cannot be less than or equal to zero.")

  sf = fs_method(data, labels, args.select)
  reduced_set = []
  for k in range(len(sf)):
    reduced_set.append(features[int(sf[k])])

  output_fh = open(args.output_file,"w")
  for feat in reduced_set:
    output_fh.write(str(feat) + "\n")

def main():

  parser = argparse.ArgumentParser(description="Fizzy implements feature subset " 
    +"selection for biological data formats, which are commonly used in metagenomic "
    +"data analysis.  \n")
  parser.add_argument("-n", "--select", type=int, help="number of features to select", 
    default=15)
  parser.add_argument("-l", "--label", help="name of column of the mapping file that "
    +"indicates the labels")
  parser.add_argument("-f", "--fs-method", help="Feature selection method. Available: "
    +"CIFE CMIM CondMI Condred ICAP JMI MIM MIFS mRMR", default="MIM")
  parser.add_argument("-i", "--input-file", help="biom format file", required=True)
  parser.add_argument("-m", "--map-file", help="CSV mapping file", required=True)
  parser.add_argument("-o", "--output-file", help="output file where selected OTU IDs "
    +"are stored", required=True)

  args = parser.parse_args()

  try:
    global feast
    import feast
  except ImportError:
    parser.error("Error loading the PyFeast module. is PyFeast installed?")

  # Make sure our input exist
  if not os.path.isfile(args.input_file):
    parser.error("input file not found")

  if not os.path.isfile(args.map_file):
    parser.error("map file not found")

  if args.select < 1:
    parser.error("you must select at least one result")

  if args.fs_method not in get_fs_methods():
    parser.error("fs method not found. please select from " + ' '.join(get_fs_methods()))

  data, samples, features = load_biom(args.input_file)
  data = numpy.array(data)

  map_arr = load_map(args.map_file)

  labels = []
  for sample_id in samples:
    labels.append(map_arr[sample_id][args.label])

  labels_disc_dic, labels_disc_arr = convert_to_discrete(labels)

  t = threading.Thread(target=run_pyfeast, args=[data, numpy.array(labels_disc_arr), features, args])
  t.daemon = True
  t.start()

  while t.is_alive(): # wait for the thread to exit
    t.join(1)

if __name__ == "__main__":
  sys.exit(main())

