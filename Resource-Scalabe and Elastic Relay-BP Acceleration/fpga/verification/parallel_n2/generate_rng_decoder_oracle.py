#!/usr/bin/env python3
from pathlib import Path
import json, numpy as np, sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(Path(__file__).resolve().parent))
from gamma_rng_reference import vector
OUT=Path(__file__).resolve().parent
d=np.load(ROOT/'fpga/verification/memory_backed_intermediate/intermediate_input.npz');H=d['H'];priors=d['priors'];syndromes=d['syndromes'];C,V=H.shape
imgs=ROOT/'fpga/verification/memory_backed_intermediate/images';flat=lambda n:[x for w in json.load(open(imgs/f'{n}.json')) for x in w]
cp=json.load(open(imgs/'check_ptr.json'));ev=flat('edge_var')[:76];vp=json.load(open(imgs/'var_ptr.json'));ve=flat('var_edge')[:76]
def sat(x):return min(131071,max(-131072,int(x)))
def r16(x):return (x+8)//16 if x>=0 else -((-x+8)//16)
def run(seed,out):
 g1,words,state,rej=vector(seed,V);gammas=[np.full(V,2,dtype=int),np.array(g1,dtype=int)]
 with out.open('w') as f:
  f.write(f'{len(priors)} {state:016x} {rej}\n')
  f.write(' '.join(map(str,g1))+'\n')
  for si,(prior,syndrome) in enumerate(zip(priors,syndromes)):
   hand=prior.copy();conv=False;total=0
   for leg,limit in enumerate((2,3)):
    nu=prior[np.array(ev)].copy();prev=hand.copy()
    for _ in range(limit):
     total+=1;bias=np.array([sat(r16(16*prior[j]+gammas[leg][j]*(prev[j]-prior[j]))) for j in range(V)])
     mu=np.zeros(76,dtype=np.int64)
     for c in range(C):
      a,b=cp[c:c+2];vals=nu[a:b];mags=np.abs(vals);first=int(np.argmin(mags));second=int(np.min(np.delete(mags,first))) if b-a>1 else 131071;parity=int(syndrome[c])^(int(np.sum(vals<0))&1)
      for q in range(b-a):mu[a+q]=(-1 if parity^int(vals[q]<0) else 1)*(second if q==first else int(mags[first]))
     incoming=np.array([sum(mu[e] for e in ve[vp[v]:vp[v+1]]) for v in range(V)]);incoming=np.clip(incoming,-2097152,2097151)
     marg=np.array([sat(bias[v]+incoming[v]) for v in range(V)]);dec=(marg<=0).astype(np.uint8);nu=np.array([sat(marg[v]-mu[e]) for e,v in enumerate(ev)]);prev=marg;hand=marg.copy()
     if not (((H@dec)%2)^syndrome).any():conv=True;break
    if conv:break
   weight=int(dec@prior);f.write(' '.join(map(str,[si,int(conv),total,leg+1,weight,*mu,*nu,*marg,*dec]))+'\n')
for name,seed in [('engine0',8),('engine1',0x9999aaaabbbbcccc)]:run(seed,OUT/f'rng_decoder_{name}.txt')
