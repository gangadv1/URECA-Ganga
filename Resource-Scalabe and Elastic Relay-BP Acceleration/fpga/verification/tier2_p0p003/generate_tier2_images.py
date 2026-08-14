from pathlib import Path
import hashlib,json,math,numpy as np
ROOT=Path(__file__).resolve().parents[3];SRC=ROOT/'graphs/generated/gross_circuit_level/memory_Z_r12_p0p003';OUT=Path(__file__).resolve().parent/'images';OUT.mkdir(parents=True,exist_ok=True)
C,V,E=1728,67752,391320;P=4
edges=np.load(SRC/'edge_lists.npz')['detector_edges'] # [fault, detector]
order=np.lexsort((edges[:,0],edges[:,1]));co=edges[order];check_fault=co[:,0].astype(int);check_deg=np.bincount(co[:,1],minlength=C);cp=np.r_[0,np.cumsum(check_deg)]
vo=np.lexsort((edges[:,1],edges[:,0]));var_pairs=edges[vo];edge_number={(int(f),int(c)):int(e) for e,(f,c) in enumerate(co)};var_edge=np.array([edge_number[(int(f),int(c))] for f,c in var_pairs],dtype=int);var_deg=np.bincount(var_pairs[:,0],minlength=V);vp=np.r_[0,np.cumsum(var_deg)]
prob=np.load(SRC/'faults.npz')['probabilities'];prior=np.rint(np.log((1-prob)/prob)).astype(int);prior=np.clip(prior,-131072,131071)
sample=np.load(SRC/'dem_samples.npz');syn=sample['detectors'][0].astype(int);decision=sample['faults'][0].astype(int)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_scalar(name,vals,width):
 p=OUT/f'{name}.memh';digits=(width+3)//4;p.write_text(''.join(f'{int(x)&((1<<width)-1):0{digits}x}\n' for x in vals));return entry(p,len(vals),len(vals),width,0)
def write_pack(name,vals,width):
 vals=list(map(int,vals));pad=(-len(vals))%P;vals+=([0]*pad);p=OUT/f'{name}.memh';digits=(width*P+3)//4
 with p.open('w') as f:
  for i in range(0,len(vals),P):
   word=sum((vals[i+k]&((1<<width)-1))<<(k*width) for k in range(P));f.write(f'{word:0{digits}x}\n')
 return entry(p,len(vals)-pad,len(vals)//P,width*P,pad)
def write_banks(name,vals,width):
 out=[]
 for bank in range(P):out.append(write_scalar(f'{name}_b{bank}',np.asarray(vals)[bank::P],width))
 return out
def entry(p,items,words,width,pad):return {'path':p.name,'logical_items':items,'packed_words':words,'word_width':width,'padding_lanes':pad,'sha256':sha(p)}
files={};files['check_row_ptr']=write_scalar('check_row_ptr',cp,19);files['check_edge_fault_ids']=write_pack('check_edge_fault_ids',check_fault,17);files['variable_row_ptr']=write_scalar('variable_row_ptr',vp,19);files['variable_to_edge']=write_pack('variable_to_edge',var_edge,19);files['priors']=write_pack('priors',prior,18);files['syndrome_shot0']=write_pack('syndrome_shot0',syn,1);files['decision_shot0']=write_pack('decision_shot0',decision,1)
source_hash=hashlib.sha256((SRC/'manifest.json').read_bytes()+(SRC/'edge_lists.npz').read_bytes()+(SRC/'faults.npz').read_bytes()).hexdigest()
manifest={'source':str(SRC.relative_to(ROOT)),'source_package_hash':source_hash,'dimensions':{'checks':C,'variables':V,'incidences':E},'degrees':{'check_min':int(check_deg.min()),'check_max':int(check_deg.max()),'variable_min':int(var_deg.min()),'variable_max':int(var_deg.max())},'packing':'lane 0 occupies least-significant field; tail lanes zero','prior':'round(log((1-p_j)/p_j)), clamp signed b18','sample_index':0,'files':files}
# Scalar mirrors support open-source transaction-level RTL verification; the
# packed images above are the scalable hardware representation.
for name,vals,width in [('check_edge_fault_ids_scalar',check_fault,17),('variable_to_edge_scalar',var_edge,19),('priors_scalar',prior,18),('syndrome_shot0_scalar',syn,1)]:
 files[name]=write_scalar(name,vals,width)
for name,vals,width in [('check_edge_fault_ids',check_fault,17),('variable_to_edge',var_edge,19),('priors',prior,18),('syndrome_shot0',syn,1)]:
 for bank,item in enumerate(write_banks(name,vals,width)):files[f'{name}_b{bank}']=item
# Deterministic gamma fixture used by the one-iteration RTL equivalence run.
gamma_fixture=np.full(V,2,dtype=np.int64)
for bank,item in enumerate(write_banks('next_gamma',gamma_fixture,5)):files[f'next_gamma_b{bank}']=item
# Deterministic locked-b18 first-iteration oracle: gamma=2 and M(0)=prior.
nu0=np.array([prior[f] for f in check_fault],dtype=np.int64);mu=np.empty(E,dtype=np.int64)
for c in range(C):
 a,b=int(cp[c]),int(cp[c+1]);x=nu0[a:b];mag=np.abs(x);first=int(np.argmin(mag));second=int(np.min(np.delete(mag,first)));par=int(syn[c])^(int(np.sum(x<0))&1)
 for k in range(b-a):
  outmag=second if k==first else int(mag[first]);mu[a+k]=-outmag if par^int(x[k]<0) else outmag
sum_mu=np.zeros(V,dtype=np.int64)
for v in range(V):sum_mu[v]=mu[var_edge[vp[v]:vp[v+1]]].sum()
marg=np.clip(prior+sum_mu,-131072,131071).astype(np.int64);hard=(marg<=0).astype(np.int64);nu1=np.empty(E,dtype=np.int64)
for v in range(V):
 ee=var_edge[vp[v]:vp[v+1]];nu1[ee]=np.clip(marg[v]-mu[ee],-131072,131071)
for name,vals,width in [('nu_initial_scalar',nu0,18),('mu_expected_scalar',mu,18),('marginal_expected_scalar',marg,18),('decision_expected_scalar',hard,1),('nu_expected_scalar',nu1,18)]:
 files[name]=write_scalar(name,vals,width)
manifest['oracle']={'gamma':2,'iteration':1,'mu_sha256':files['mu_expected_scalar']['sha256'],'nu_sha256':files['nu_expected_scalar']['sha256'],'marginal_sha256':files['marginal_expected_scalar']['sha256'],'decision_sha256':files['decision_expected_scalar']['sha256']}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
# Representative rows and Python min-sum oracle for deterministic nu.
starts=cp[:-1];ids=np.arange(C);candidates=[int(np.argmin(check_deg)),int(np.argmin(abs(check_deg-check_deg.mean()))),int(np.argmax(check_deg)),int(np.flatnonzero((starts%4!=0)&(ids>2))[0]),int(np.flatnonzero((check_deg%4!=0)&(ids>3))[0])];checks=list(dict.fromkeys(candidates));nu=np.array([(-1 if e%3==0 else 1)*(1+e%101) for e in range(E)],dtype=int)
selected=[]
for c in checks:
 a,b=int(cp[c]),int(cp[c+1]);x=nu[a:b];m=np.abs(x);first=int(np.argmin(m));second=int(np.min(np.delete(m,first)));par=int(syn[c])^(int(np.sum(x<0))&1);mu=[]
 for k in range(len(x)):mag=second if k==first else int(m[first]);mu.append(-mag if par^int(x[k]<0) else mag)
 selected.append({'check':c,'start':a,'end':b,'degree':b-a,'syndrome':int(syn[c]),'nu':x.tolist(),'mu':mu})
(OUT.parent/'selected_checks.json').write_text(json.dumps(selected,indent=2)+'\n')
print(json.dumps({'files':len(files),'selected_checks':[(x['check'],x['degree']) for x in selected],'manifest':str(OUT/'manifest.json')}))
