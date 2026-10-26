"""Bounded full-pipeline regressions; all writes stay in a new validation directory."""
from pathlib import Path
import argparse,csv,json,sys,subprocess,unittest,time,hashlib
import numpy as np
import run as pipeline
from run import algebra,tb,ROOT
HERE=Path(__file__).resolve().parent
OUT=ROOT/'results/parameterized_bb_validation'
FIXTURES={
 '18_4_3':(3,3,[(1,0),(0,0),(0,1)],[(1,0),(0,0),(1,2)],18,4),
 '72_12_6':(6,6,[(3,0),(0,1),(0,2)],[(0,3),(1,0),(2,0)],72,12),
 '144_12_12':(12,6,[(3,0),(0,1),(0,2)],[(0,3),(1,0),(2,0)],144,12),
 '288_12_18':(12,12,[(3,0),(0,2),(0,7)],[(0,3),(1,0),(2,0)],288,12),
 'new_36_A':(3,6,[(1,0),(0,0),(0,1)],[(1,0),(0,0),(1,2)],36,4),
 'new_36_B':(6,3,[(1,0),(0,0),(0,1)],[(1,0),(0,0),(1,2)],36,4)}
BASE=dict(physical_p=.003,rounds=2,shots=2,first_limit=2,later_limit=2,R=2,S=1,sample_seed=20261011,trajectory_base_seed=tb.BASE_SEED,runtime_cap_seconds=60)
class Tests(unittest.TestCase):
 def test_full_pipeline(self):
  records=[]
  for name,(l,m,a,b,n,k) in FIXTURES.items():
   for N,P in ((1,2),(2,4)):
    with self.subTest(code=name,N=N,P=P):
     cfg=dict(BASE,l=l,m=m,A=a,B=b,N=N,P=P,banking='weighted_ba2' if P==4 else 'ba2')
     path=OUT/f'{name}_N{N}_P{P}';configfile=OUT/f'{name}_N{N}_P{P}.json';configfile.write_text(json.dumps(cfg,indent=2)+'\n')
     start=time.monotonic()
     with (OUT/f'{path.name}.log').open('w') as log:
      subprocess.run([sys.executable,'-B',str(HERE/'run.py'),'--config',str(configfile),'--output',str(path)],check=True,timeout=70,stdout=log,stderr=subprocess.STDOUT)
     result=json.loads((path/'summary.json').read_text());validation=json.loads((path/'validation.json').read_text())
     self.assertEqual((result['code']['n'],result['code']['k']),(n,k));self.assertIsNone(result['code']['d']);self.assertEqual(result['dimensions']['logical_observables'],k)
     self.assertTrue(validation['all_iteration_traces_inverse_exact']);self.assertEqual(validation['status'],'PASS')
     self.assertTrue(all(0 <= r['total_failure'] <= cfg['shots'] for r in result['results'].values()))
     with self.assertRaises(FileExistsError):pipeline.run(cfg,path)
     # Every stored fault/observable target is bounds-checked by the loader.
     pkgcfg=tb.Config(code='parameterized',package=str(path/'package'),physical_p=.003,N=N,P=P,shots=2,first_limit=2,later_limit=2,R=2)
     directory,pkg,_,circuit,h,action,prior=tb.load_problem(pkgcfg)
     self.assertEqual(h.shape[0],(n//2)*3);self.assertEqual(action.shape[0],k)
     records.append(dict(code=name,N=N,P=P,n=n,k=k,dimensions=result['dimensions'],seconds=time.monotonic()-start,results=result['results']))
   # Folding and lane count cannot change math or trajectory0 for paired circuits.
   low=OUT/f'{name}_N1_P2';high=OUT/f'{name}_N2_P4'
   with (low/'per_engine.csv').open() as f:lo=[r for r in csv.DictReader(f) if r['layout']=='original']
   with (high/'per_engine.csv').open() as f:hi=[r for r in csv.DictReader(f) if r['layout']=='original' and r['engine']=='0']
   for a,b in zip(lo,hi):
    for field in ('seed','iterations','legs','decision_sha256','nonconvergence','syndrome_valid_logical_error','total_failure'):self.assertEqual(a[field],b[field])
   self.assertEqual(tb.sha(low/'package/circuit.stim'),tb.sha(high/'package/circuit.stim'))
   with np.load(low/'package/circuit_samples.npz') as a,np.load(high/'package/circuit_samples.npz') as b:
    for key in a.files:np.testing.assert_array_equal(a[key],b[key])
  pipeline.dump(OUT/'full_pipeline_results.json',records)
 def test_original_fixtures_and_gross_defaults(self):
  for name in list(FIXTURES)[:4]:
   cfg=tb.Config(code=name,first_limit=1,later_limit=1,R=2)
   directory,pkg,_,circuit,h,action,priors=tb.load_problem(cfg)
   self.assertEqual(action.shape[0],FIXTURES[name][-1])
  hx,hz=algebra.bb_code.build_matrices();x,z,_=algebra.construct(12,6,FIXTURES['144_12_12'][2],FIXTURES['144_12_12'][3])
  np.testing.assert_array_equal(hx,x);np.testing.assert_array_equal(hz,z)
  # Full fresh original Gross package must preserve every historical payload and relevant manifest fields.
  builder=pipeline.builder;baseline=ROOT/'graphs/generated/gross_circuit_level/memory_Z_r12_p0p003';pkg=json.loads((baseline/'package.json').read_text());out=OUT/'gross_original_builder_regression'
  if not out.exists():
   builder.write_package(builder.default_source('144_12_12',.003),out,'144_12_12',.003,12,pkg['sample_shots'],pkg['sample_seed'])
  fresh=json.loads((out/'package.json').read_text())
  self.assertEqual({key:fresh[key] for key in pkg},pkg)
  self.assertEqual(set(fresh)-set(pkg),{'code_parameters'} if 'code_parameters' not in pkg else set())
  self.assertEqual(fresh['code_parameters'],dict(n=144,k=12,d=12))
  for f in ('faults.npz','edge_lists.npz','circuit_samples.npz','dem_samples.npz','detector_coordinates.npz'):
   with np.load(out/f) as a,np.load(baseline/f) as b:
    self.assertEqual(a.files,b.files)
    for key in a.files:np.testing.assert_array_equal(a[key],b[key])
  for name in ('circuit.stim','detector_error_model.dem','incidence.csv'):
   self.assertEqual(tb.sha(out/name),tb.sha(baseline/name))
  freshmanifest=json.loads((out/'manifest.json').read_text());oldmanifest=json.loads((baseline/'manifest.json').read_text())
  for key in ('circuit','sampling','schema_version'):self.assertEqual(freshmanifest[key],oldmanifest[key])
  self.assertEqual({k:v for k,v in freshmanifest['graph'].items() if k!='code'}, {k:v for k,v in oldmanifest['graph'].items() if k!='code'})
  self.assertEqual(freshmanifest['graph']['code'],'BB [[144,12,12]]')
 def test_parameter_validation(self):
  cfg=dict(BASE,l=3,m=6,A=[[1,0],[0,0],[0,1]],B=[[1,0],[0,0],[1,2]])
  for changes in [dict(l=0),dict(m=True),dict(physical_p=0),dict(rounds=0),dict(N=0),dict(P=3),dict(S=3),dict(A=[[1,0],[1,0],[0,1]]),dict(B=[[1,0]]),dict(A=[[.1,0],[0,0],[0,1]]),dict(noise_model='uniform_circuit'),dict(P=2,banking='weighted_ba2'),dict(N=2,engine_seeds=[1,1])]:
   with self.subTest(changes=changes),self.assertRaises(ValueError):pipeline.validate(dict(cfg,**changes),OUT/'invalid')
  # General algebra handles more than three terms; the circuit profile explicitly rejects them.
  hx,hz,info=algebra.construct(3,3,[[0,0],[1,0]],[[0,1]])
  self.assertTrue(algebra.bb_code.matrices_commute(hx,hz))
  with self.assertRaises(ValueError):algebra.generate(3,3,[[0,0],[1,0]],[[0,1]],.003,2)
  with self.assertRaises(ValueError):algebra.generate(4,4,[[1,0],[0,0],[0,1]],[[1,0],[0,0],[1,2]],.003,2)
  hx,hz,info=algebra.construct(3,6,[[-2,0],[0,0],[0,1]],[[1,0],[0,0],[1,2]])
  x,z,_=algebra.construct(3,6,[[1,0],[0,0],[0,1]],[[1,0],[0,0],[1,2]])
  np.testing.assert_array_equal(hx,x);np.testing.assert_array_equal(hz,z)
 def test_dynamic_noise_rounds_seeds_and_syndrome_consistency(self):
  cfg=dict(BASE,l=3,m=6,A=[[1,0],[0,0],[0,1]],B=[[1,0],[0,0],[1,2]],physical_p=.007,rounds=3,N=2,P=4,engine_seeds=[123,456],sample_seed=555)
  path=OUT/'dynamic_noise_rounds';pipeline.run(cfg,path)
  result=json.loads((path/'summary.json').read_text());self.assertEqual(result['dimensions']['detectors'],72)
  with np.load(path/'package/faults.npz') as f,np.load(path/'package/dem_samples.npz') as samples:
   _,_,_,_,h,a,_=tb.load_problem(tb.Config(code='parameterized',package=str(path/'package'),physical_p=.007))
   np.testing.assert_array_equal((h@samples['faults'].T).T&1,samples['detectors'])
   np.testing.assert_array_equal((a@samples['faults'].T).T&1,samples['observables'])
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args();OUT=args.output.resolve()
 if OUT.exists():raise SystemExit('Use a fresh validation output directory; existing results protected')
 OUT.mkdir()
 # Protect all pre-existing artifacts; implementation files are recorded at their current hashes.
 dirs=['graphs/generated','graphs/sources','results','reference']
 hashes={str(f.relative_to(ROOT)):tb.sha(f) for d in dirs for f in (ROOT/d).rglob('*') if f.is_file() and OUT not in f.parents}
 start=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 unchanged=all(tb.sha(ROOT/f)==v for f,v in hashes.items())
 pipeline.dump(OUT/'validation.json',dict(status='PASS' if result.wasSuccessful() and unchanged else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),archives_unchanged=unchanged,protected_file_count=len(hashes),elapsed_seconds=time.monotonic()-start,command=sys.argv))
 pipeline.dump(OUT/'protected_hashes.json',hashes)
 raise SystemExit(0 if result.wasSuccessful() and unchanged else 1)
