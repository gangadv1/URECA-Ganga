"""Convert a binary sparse graph and shots into deterministic P=4 RTL images."""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json
import numpy as np
from scipy import sparse

def pack(values, lanes=4, pad=0):
    values=list(map(int,values)); values += [pad]*((-len(values))%lanes)
    return [values[i:i+lanes] for i in range(0,len(values),lanes)]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def convert(h, priors, syndromes, out, gamma):
    out.mkdir(parents=True,exist_ok=True); csr=sparse.csr_matrix(h,dtype=np.uint8);csc=csr.tocsc()
    edge_var=csr.indices.astype(int).tolist(); edge_lookup={}
    for c in range(csr.shape[0]):
      for e in range(csr.indptr[c],csr.indptr[c+1]): edge_lookup[(int(edge_var[e]),c)]=e
    var_edges=[]
    for v in range(csr.shape[1]):
      for p in range(csc.indptr[v],csc.indptr[v+1]): var_edges.append(edge_lookup[(v,int(csc.indices[p]))])
    images={"check_ptr":csr.indptr.tolist(),"edge_var":pack(edge_var),"var_ptr":csc.indptr.tolist(),
            "var_edge":pack(var_edges),"prior":[pack(x) for x in priors],
            "syndrome":[pack(x) for x in syndromes],"gamma":[pack(x) for x in gamma]}
    files={}
    for name,data in images.items():
      p=out/f"{name}.json";p.write_text(json.dumps(data,separators=(',',':'))+'\n');files[name]={"path":p.name,"sha256":sha(p)}
    meta={"checks":csr.shape[0],"variables":csr.shape[1],"incidences":csr.nnz,"P":4,
      "packing":"logical index e -> word floor(e/4), lane e mod 4; zero padded tail",
      "padding":{"edge_words":(-csr.nnz)%4,"variable_words":(-csr.shape[1])%4,"check_words":(-csr.shape[0])%4},
      "widths":{"pointer":max(1,int(csr.nnz).bit_length()),"edge_id":max(1,(csr.nnz-1).bit_length()),
        "variable_id":max(1,(csr.shape[1]-1).bit_length()),"check_id":max(1,(csr.shape[0]-1).bit_length()),
        "message":18,"gamma":5,"decision":1},"files":files}
    (out/'memory_manifest.json').write_text(json.dumps(meta,indent=2)+'\n');return images,meta
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--npz');ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    d=np.load(a.npz);convert(d['H'],d['priors'],d['syndromes'],a.out,d['gamma'])
if __name__=='__main__':main()
