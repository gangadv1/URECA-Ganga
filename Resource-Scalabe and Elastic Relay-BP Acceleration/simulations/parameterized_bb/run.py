"""Bounded configuration-driven BB construction -> circuit -> graph -> banked Relay smoke."""
from pathlib import Path
from dataclasses import asdict
import argparse,csv,json,sys,subprocess,time,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'simulations/configurable_testbench'),str(ROOT/'graphs')]
import testbench as tb
import parameterized_bb as algebra
import build_circuit_level as builder

def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v.item())+'\n')
def digest(a):
    a=np.ascontiguousarray(a)
    return hashlib.sha256(str(a.dtype).encode()+str(a.shape).encode()+a.tobytes()).hexdigest()
def validate(config,output):
    allowed={'l','m','A','B','physical_p','rounds','N','P','shots','first_limit','later_limit','R','S','sample_seed','trajectory_base_seed','engine_seeds','output','banking','runtime_cap_seconds','max_data_qubits','noise_model'}
    if set(config)-allowed:raise ValueError('Unknown configuration keys: '+str(sorted(set(config)-allowed)))
    for key in ('l','m','A','B','physical_p','rounds'):
        if key not in config:raise ValueError('Missing required configuration key: '+key)
    if config.get('noise_model','gari_uniform_p_memory_z')!='gari_uniform_p_memory_z':
        raise ValueError('Generic generation supports only gari_uniform_p_memory_z; canonical Relay pinned circuits are a separate importer')
    for key,default in [('runtime_cap_seconds',120),('max_data_qubits',512)]:
        v=config.get(key,default)
        if type(v) is not int or v<1:raise ValueError(key+' must be a positive integer')
    if config.get('runtime_cap_seconds',120)>600:raise ValueError('Smoke runtime cap cannot exceed600 seconds')
    if type(config['l']) is not int or type(config['m']) is not int or min(config['l'],config['m'])<1:raise ValueError('l/m must be positive integers')
    if 2*config['l']*config['m']>config.get('max_data_qubits',512):raise ValueError('Construction exceeds explicit max_data_qubits resource guard')
    if type(config['rounds']) is not int or config['rounds']<1:raise ValueError('rounds must be a positive integer')
    if type(config['physical_p']) not in (int,float) or not np.isfinite(config['physical_p']) or not 0<config['physical_p']<1:raise ValueError('physical_p must be finite in (0,1)')
    cfg=tb.Config(code='parameterized',package=str(Path(output).resolve()/'package'),physical_p=config['physical_p'],
                  **{k:config.get(k,d) for k,d in dict(N=2,P=4,shots=2,first_limit=2,later_limit=2,R=2,S=1,sample_seed=20261011,trajectory_base_seed=tb.BASE_SEED,engine_seeds=None).items()})
    cfg.validate()
    if cfg.engine_seeds is not None and (len(set(cfg.engine_seeds)) != cfg.N or (cfg.R > 1 and 0 in cfg.engine_seeds)):
        raise ValueError('Independent trajectories require distinct engine seeds and nonzero xorshift seeds for retries')
    bank=config.get('banking','ba2')
    if bank not in ('original','ba2','weighted_ba2'):raise ValueError('Choose original, ba2 or weighted_ba2 banking')
    if bank=='weighted_ba2' and cfg.P!=4:raise ValueError('Existing weighted BA2 optimizer is validated only at P4')
    # Validate monomials before any output writes or expensive circuit work.
    for name in ('A','B'):
        terms=algebra.normalized_terms(config[name],config['l'],config['m'])
        if len(terms)!=3 or len(set(terms))!=3:raise ValueError('Circuit profile requires three distinct modulo-torus monomials in '+name)
    return cfg

def banking(h,action,probabilities,p,cfg):
    ba=tb.module('parameterized_banking',ROOT/'results/bank-aware-folding-layout/run_bank_aware_layout.py')
    ba.P=p;fm=tb.configure_folding(ba.fm,p)
    ec,ev,ve=fm.original_edge_tables(h)
    g=dict(C=h.shape[0],V=h.shape[1],O=action.shape[0],E=h.nnz,H=h,A=action,p=probabilities,edge_check=ec,edge_fault=ev,variable_edges=ve)
    conv=[chunk for c in range(g['C']) for chunk in fm.chunks(ev[h.indptr[c]:h.indptr[c+1]])]
    relay=[ev[chunk] for chunk in fm.chunks(np.arange(g['E']))]
    edges=[chunk for v in ve for chunk in fm.chunks(v)]
    fw=(3*ba.pair_matrix(g['V'],conv)+3*ba.pair_matrix(g['V'],relay)).tocsr()
    ew=(5*ba.pair_matrix(g['E'],edges)).tocsr()
    fr,fs=ba.greedy_residues(fw,np.asarray(h.sum(axis=0)).ravel()*2,np.zeros(g['V'],np.int8),.25,0.)
    er,es=ba.greedy_residues(ew,np.full(g['E'],2.),np.zeros(g['E'],np.int8),.25,0.)
    original=dict(name='original',check_order=np.arange(g['C']),fault_order=np.arange(g['V']),check_edges=[np.arange(h.indptr[c],h.indptr[c+1]) for c in range(g['C'])],variable_edges=ve,edge_fault=ev,edge_check=ec)
    layouts={'original':original,'ba2':ba.bank_layout('ba2',g,fr,er)}
    optimization={'weighted_available':p==4,'weight_source':'predeclared maximum iteration/leg budgets, no samples or logical labels'}
    weighted=tb.module('parameterized_weighted',ROOT/'simulations/configurable_testbench/pilots/weighted_ba2_validated_20261010/compare_weighted.py')
    if p==4:
        relay=[ev[layouts['ba2']['edge_new_to_old'][chunk]] for chunk in fm.chunks(np.arange(g['E']))]
        candidate,stats=weighted.weighted_assignment(ba,conv,relay,fr,cfg.first_limit+(cfg.R-1)*cfg.later_limit,cfg.R)
        layouts['weighted_ba2']=ba.bank_layout('weighted_ba2',g,candidate,er)
        if not np.array_equal(layouts['weighted_ba2']['edge_old_to_new'],layouts['ba2']['edge_old_to_new']):raise ValueError('Weighted optimization changed fixed BA2 edge map')
        optimization.update(stats)
    profiles={name:fm.profile(layout,np.zeros(g['C'],int),np.zeros(g['V'],int)) for name,layout in layouts.items()}
    if p==4:
        it,legs=cfg.first_limit+(cfg.R-1)*cfg.later_limit,cfg.R
        budget_cost=lambda name:it*sum(profiles[name][0][x]['estimated_cycles'] for x in ('check','variable','convergence'))+legs*profiles[name][0]['relay_init']['estimated_cycles']
        optimization['BA2_budget_weighted_cycles']=int(budget_cost('ba2'))
        optimization['selected_budget_weighted_cycles']=int(budget_cost('weighted_ba2'))
        optimization['measured_structural_budget_objective_improved']=budget_cost('weighted_ba2')<budget_cost('ba2')
        if budget_cost('weighted_ba2')>budget_cost('ba2'):raise ValueError('Weighted candidate regressed under declared structural budget objective')
    return ba,g,layouts,profiles,optimization,weighted

def run(config,output):
    output=Path(output).resolve();cfg=validate(config,output)
    if output.exists():raise FileExistsError('Refusing to overwrite any existing output directory: '+str(output))
    start=time.monotonic()
    circuit,hx,hz,lz,metadata=algebra.generate(config['l'],config['m'],config['A'],config['B'],cfg.physical_p,config['rounds'])
    output.mkdir(parents=True,exist_ok=False)
    dump(output/'configuration.json',dict(config,output=str(output)))
    source=output/'generated_source.stim';source.write_text(str(circuit)+'\n')
    np.savez_compressed(output/'code_matrices.npz',hx=hx,hz=hz,logical_z=lz)
    builder.write_package(source,output/'package',metadata['matrix_sha256'][:16],cfg.physical_p,config['rounds'],cfg.shots,cfg.sample_seed,construction=metadata)
    directory,pkg,manifest,circuit,h,action,priors=tb.load_problem(cfg)
    syndromes,logicals=tb.samples(cfg,directory,pkg,circuit)
    with np.load(directory/'faults.npz') as data:probabilities=data['probabilities'].copy()
    ba,g,layouts,profiles,opt,weighted=banking(h,action,probabilities,cfg.P,cfg)
    dump(output/'banking_profiles.json',{name:dict(phases=phases,all_phases_once=total) for name,(phases,total) in profiles.items()})
    dump(output/'bank_optimization.json',opt)
    mapped={};invariants={}
    for name,layout in layouts.items():
        if name=='original':continue
        inv,hp,ap,pp=ba.invariance(g,layout);hp.sort_indices();ap.sort_indices();fo,fn=layout['fault_old_to_new'],layout['fault_new_to_old']
        oldkeys=g['edge_check']*g['V']+g['edge_fault'];keys=np.repeat(np.arange(g['C']),np.diff(hp.indptr))*g['V']+fn[hp.indices]
        dto=np.searchsorted(oldkeys,keys)
        if not np.array_equal(oldkeys[dto],keys):raise ValueError('Decoder edge identity correspondence failed')
        otd=np.empty(g['E'],int);otd[dto]=np.arange(g['E'])
        if not np.array_equal(priors[fn][fo],priors):raise ValueError('Prior correspondence failed')
        mapped[name]=(hp,ap,fo,fn,otd)
        invariants[name]=inv
        np.savez_compressed(output/(name+'_storage_maps.npz'),**{k:layout[k] for k in ('fault_old_to_new','fault_new_to_old','edge_old_to_new','edge_new_to_old','fault_residues','edge_residues')})
    engine_rows=[];shot_rows=[];traces=[]
    for shot,(syndrome,logical) in enumerate(zip(syndromes,logicals)):
        shot_engines={name:[] for name in layouts}
        for engine,seed in enumerate(tb.trajectory_seeds(cfg,shot)):
            configs,_,_=weighted.schedule(seed,cfg,g['V'],np.arange(g['V']))
            def decode(matrix,prior,legs,fo=None,otd=None):
                trace=[]
                def callback(event):
                    hashes={}
                    for field in ('gamma_float','gamma_int','lambda_bias','beliefs','decoded_error'):
                        hashes[field]=digest(event[field] if fo is None else event[field][fo])
                    for field in ('check_to_var','var_to_check'):
                        hashes[field]=digest(event[field] if otd is None else event[field][otd])
                    hashes['residual']=digest(event['residual'])
                    trace.append(dict(leg=int(event['leg_index']),iteration=int(event['iteration']),global_iteration=int(event['global_iteration']),converged=bool(event['converged']),saturations=event['saturation_counts'],hashes=hashes))
                decoder=tb.FixedRelayBPDecoder(matrix,tb.FixedRelayConfig(fixed=tb.FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=tuple(legs),R=cfg.R,S=cfg.S,seed=0),iteration_callback=callback)
                return decoder.decode(prior,syndrome),trace
            result,trace=decode(h,priors,configs);decision=result.decoded_error.astype(np.uint8);score=tb.score(h,action,decision,syndrome,logical)
            for name in layouts:
                if name!='original':
                    hp,ap,fo,fn,otd=mapped[name];_,legs,_=weighted.schedule(seed,cfg,g['V'],fn)
                    other,othertrace=decode(hp,priors[fn],legs,fo,otd)
                    if (trace!=othertrace or not np.array_equal(other.decoded_error[fo],decision) or not np.array_equal(other.beliefs[fo],result.beliefs) or other.total_iterations!=result.total_iterations or other.relay_legs!=result.relay_legs or tb.score(hp,ap,other.decoded_error,syndrome,logical)!=score):
                        raise ValueError('Exact inverse-mapped decoder equivalence failed for '+name)
                phases=profiles[name][0];cost=result.total_iterations*sum(phases[x]['estimated_cycles'] for x in ('check','variable','convergence'))+result.relay_legs*phases['relay_init']['estimated_cycles']
                e=dict(layout=name,shot=shot,engine=engine,seed=int(seed),iterations=result.total_iterations,legs=result.relay_legs,syndrome_converged=not bool(score['nonconvergence']),result_cycles=int(cost),decision_sha256=hashlib.sha256(decision.tobytes()).hexdigest(),**score)
                shot_engines[name].append(e);engine_rows.append(e)
            traces.append(dict(shot=shot,engine=engine,original_trace=trace,inverse_mapped_layouts_exact=list(mapped)))
        for name,engines in shot_engines.items():
            cycles,winner=tb.select(engines)
            score={k:engines[winner][k] for k in ('nonconvergence','syndrome_valid_logical_error','total_failure')} if winner>=0 else dict(nonconvergence=1,syndrome_valid_logical_error=0,total_failure=1)
            shot_rows.append(dict(layout=name,shot=shot,winner=winner,modeled_completion_cycles=int(cycles),provisioned_lanes=cfg.N*cfg.P,provisioned_lane_cycles=int(cycles)*cfg.N*cfg.P,**score))
    for name,rows in [('per_engine.csv',engine_rows),('per_shot.csv',shot_rows)]:
        with (output/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    dump(output/'decoder_equivalence.json',traces)
    summary=dict(code=metadata,N=cfg.N,P=cfg.P,dimensions=dict(detectors=h.shape[0],faults=h.shape[1],logical_observables=action.shape[0],edges=h.nnz),
                 selected_banking=config.get('banking','ba2'),timing_label='structural extrapolation; not measured RTL/FPGA timing; excludes controller/RNG/cancellation/drain overhead',
                 exact_cancellation_aware_work=None,elapsed_PE_utilization=None,bank_occupancy_label='issued-group lane occupancy, not elapsed PE utilization',
                 results={name:dict(total_failure=sum(r['total_failure'] for r in shot_rows if r['layout']==name),shots=cfg.shots,mean_completion_cycles=float(np.mean([r['modeled_completion_cycles'] for r in shot_rows if r['layout']==name])),mean_iterations=float(np.mean([r['iterations'] for r in engine_rows if r['layout']==name]))) for name in layouts},elapsed_seconds=time.monotonic()-start)
    dump(output/'summary.json',summary)
    dump(output/'validation.json',dict(status='PASS',CSS_commute=True,n_k_rank_derived=True,distance_unknown=True,logical_quotient_valid=True,DEM_fault_mapping_sample_reconstruction=True,graph_dimensions_derived=True,labels_used_only_for_scoring=True,banking_invariants=invariants,all_iteration_traces_inverse_exact=True))
    sources=[ROOT/'graphs/build_circuit_level.py',ROOT/'simulations/configurable_testbench/testbench.py',ROOT/'results/bank-aware-folding-layout/run_bank_aware_layout.py',ROOT/'results/graph-partitioning-folding-model/run_folding_layout_comparison.py',Path(weighted.__file__),Path(__file__)]
    dump(output/'provenance.json',dict(command=sys.argv,versions=dict(numpy=np.__version__,stim=builder.stim.__version__),resolved_decoder_config=asdict(cfg),circuit_profile=metadata['noise_model'],generator_sources=metadata['generator_sources'],sources={str(f.relative_to(ROOT)):tb.sha(f) for f in sources},output_hashes={str(f.relative_to(output)):tb.sha(f) for f in output.rglob('*') if f.is_file()}))
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True,type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
    config=json.loads(args.config.read_text());output=args.output or config.get('output')
    if not output:raise ValueError('Provide output in configuration or --output')
    validate(config,output)
    if Path(output).exists():raise FileExistsError('Output directory already exists')
    if args.worker:print(json.dumps(run(config,output),indent=2))
    else:
        try:subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--config',str(args.config.resolve()),'--output',str(Path(output).resolve()),'--worker'],check=True,timeout=config.get('runtime_cap_seconds',120))
        except subprocess.TimeoutExpired:
            if Path(output).exists():dump(Path(output)/'STOPPED.json',dict(reason='Explicit smoke runtime cap exceeded; partial outputs retained',runtime_cap_seconds=config.get('runtime_cap_seconds',120)))
            raise SystemExit('Stopped: smoke runtime cap exceeded; no results claimed')
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,FileExistsError,subprocess.CalledProcessError) as e:raise SystemExit(str(e))
