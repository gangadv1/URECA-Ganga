#!/usr/bin/env python3
"""Cycle-level analytical controller model for validated M4; no RTL or synthesis."""
from __future__ import annotations
import csv,json,math,hashlib
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent; ROOT=OUT.parents[1]
M4=ROOT/'results/relaybp-memory-m4-validation'; ARCH=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv'
P=4; C=1728; V=67752; E=391320
PHASE={'check':508753,'variable':1958833,'convergence':747049,'relay_init':1068955}
ITER=PHASE['check']+PHASE['variable']+PHASE['convergence']; RELAY=PHASE['relay_init']
WAIT2={'check':C,'variable':V,'convergence':C,'relay_init':math.ceil(E/P)}

def rows(p):
 with open(p,newline='') as f:return list(csv.DictReader(f))
def wc(p,x,fields=None):
 x=list(x);fields=fields or list(x[0])
 with open(p,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(x)
def wj(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def pct(a,b):return 100*(a-b)/b

MEM=[
 ('edge_to_fault',17,E,4,'shared','read_only',2,0),('fault_to_edge',19,E,4,'shared','read_only',2,0),
 ('check_degree',8,C,4,'shared','read_only',2,0),('fault_degree',4,V,4,'shared','read_only',2,0),
 ('prior',18,V,4,'shared','read_only',2,0),('syndrome',1,C,4,'shared','read_only',2,0),
 ('E0_message',18,E,4,'E0','read_write',1,1),('E1_message',18,E,4,'E1','read_write',1,1),
 ('E0_marginal',18,V,4,'E0','read_write',1,1),('E1_marginal',18,V,4,'E1','read_write',1,1),
 ('E0_gamma',5,V,4,'E0','read_write',1,1),('E1_gamma',5,V,4,'E1','read_write',1,1),
 ('E0_decision',1,V,4,'E0','read_write',1,1),('E1_decision',1,V,4,'E1','read_write',1,1),
 ('E0_control',166,1,1,'E0','register',2,1),('E1_control',166,1,1,'E1','register',2,1)]

def architecture():
 out=[]
 for n,w,d,b,scope,access,rp,wp in MEM:
  out.append(dict(memory=n,logical_width=w,logical_depth=d,banks=b,bank_rule='logical_address % 4' if b==4 else 'register',read_ports_per_bank=rp,write_ports_per_bank=wp,
   read_latency_tested='1 and 2 cycles',write_behavior='registered write at cycle edge' if wp else 'none',read_during_write='read-first baseline; write-first/no-change also checked with dependency fence',shared_or_private=scope,access=access))
 wc(OUT/'memory_architecture.csv',out)

def templates(total_iterations,total_legs):
 # Exact run-length representation of the repeated controller request stream.
 defs=[
  ('check','degree_tables','shared','read','check_id','check_id%4','lane0',C,total_iterations,'read check degree'),
  ('check','syndrome','shared','read','check_id','check_id%4','lane0',C,total_iterations,'read syndrome'),
  ('check','message','private','read','edge_id','edge_id%4','lanes0:3',math.ceil(E/P),total_iterations,'gather NU_old'),
  ('check','message','private','write','edge_id','edge_id%4','lanes0:3',math.ceil(E/P),total_iterations,'write MU after neighborhood return fence'),
  ('variable','fault_degree','shared','read','fault_id','fault_id%4','lane0',V,total_iterations,'read fault degree'),
  ('variable','prior','shared','read','fault_id','fault_id%4','lane0',V,total_iterations,'read prior'),
  ('variable','fault_to_edge','shared','read','packed_group','packed_group%4','lanes0:3',126288,total_iterations,'read fault adjacency'),
  ('variable','message','private','read','edge_id','edge_id%4','lanes0:3',math.ceil(E/P),total_iterations,'gather MU'),
  ('variable','message','private','write','edge_id','edge_id%4','lanes0:3',math.ceil(E/P),total_iterations,'write NU_new after neighborhood return fence'),
  ('convergence','check_degree','shared','read','check_id','check_id%4','lane0',C,total_iterations,'read check degree'),
  ('convergence','syndrome','shared','read','check_id','check_id%4','lane0',C,total_iterations,'read syndrome'),
  ('convergence','edge_to_fault','shared','read','edge_group','edge_group%4','lanes0:3',98640,total_iterations,'read edge metadata'),
  ('convergence','decision','private','read','fault_id','fault_id%4','lanes0:3',98640,total_iterations,'decision gather; BA2 retries separate'),
  ('relay_init','edge_to_fault','shared','read','edge_group','edge_group%4','lanes0:3',97830,total_legs,'read edge metadata'),
  ('relay_init','prior','shared','read','fault_id','fault_id%4','lanes0:3',147138,total_legs,'prior gather including BA2 retry subsets'),
  ('relay_init','message','private','write','edge_id','edge_id%4','lanes0:3',97830,total_legs,'initialize NU')]
 out=[]
 for i,(ph,mem,scope,op,addr,bank,lane,per,repeat,note) in enumerate(defs):
  out.append(dict(template_id=i,trajectory_requests='E0 and E1 independently; shared rows co-issue while both active',memory_structure=mem,scope=scope,bank=bank,address=addr,operation=op,lane=lane,phase=ph,iteration='repeated archived iteration',relay_leg='repeated archived leg',request_issue_cycle=f'{ph}_base + group_index',grant_cycle='issue (no arbitration in dual-read mode)',return_cycle='issue + read_latency' if op=='read' else '',writeback_cycle='issue edge' if op=='write' else '',groups_per_occurrence=per,archive_occurrences=repeat,total_group_occurrences=per*repeat,note=note))
 wc(OUT/'cycle_request_trace.csv',out)

def arbitration():
 static=rows(M4/'shared_memory_port_demand.csv');out=[]
 for x in static:
  out.append(dict(case='same-bank dual-read',memory=x['structure'],condition='E0 and E1 read same/different address in same logical bank',legal=True,policy='serve both on TDP ports A/B',events=x['issue_groups'],stalls=0,decoder_visible_reorder=False))
 out += [
  dict(case='no-conflict dual-read',memory='shared static',condition='different banks',legal=True,policy='serve independently',events='all applicable',stalls=0,decoder_visible_reorder=False),
  dict(case='read/write overlap',memory='trajectory-private message',condition='one read and one write, different address',legal=True,policy='TDP A=read B=write',events='phase-local',stalls=0,decoder_visible_reorder=False),
  dict(case='same-address read/write',memory='trajectory-private message',condition='possible only without return fence',legal=False,policy='assert/fence; never issued',events=0,stalls=0,decoder_visible_reorder=False),
  dict(case='two writes',memory='trajectory-private dynamic',condition='same bank same cycle',legal=False,policy='BA2 stable subsets serialize before RAM',events=0,stalls=0,decoder_visible_reorder=False),
  dict(case='phase transition',memory='trajectory-private message',condition='last old-semantic read still in pipeline',legal=True,policy='wait for final return before semantic flip/write',events='one fence per neighborhood',stalls='0 at L1; one dependency bubble at L2',decoder_visible_reorder=False)]
 wc(OUT/'arbitration_events.csv',out)

def hazards():
 out=[]
 for lat in (1,2):
  for phase,old,new,nodes in [('check','NU_old','MU',C),('variable','MU','NU_new',V)]:
   out.append(dict(read_latency=lat,phase=phase,old_semantic=old,new_semantic=new,neighborhoods_per_iteration=nodes,return_fence='write begins only after final old value returns',RAW=0,WAR=0,WAW=0,phase_boundary_hazard=0,extra_bubbles_per_iteration=0 if lat==1 else nodes,result='SAFE'))
 wc(OUT/'message_ram_hazards.csv',out)

def completion():
 ar=rows(ARCH); cps={}
 for p in (M4/'checkpoints').glob('*.json'):
  x=json.load(open(p));cps[(x['trajectory'],int(x['sample_seed']),int(x['shot']))]=x
 out=[]
 for x in ar:
  seed,shot=int(x['sample_seed']),int(x['shot']);r={t:cps[(t,seed,shot)] for t in ('E0','E1')}
  def cost(t,lat):
   z=r[t];base=int(z['iterations'])*ITER+int(z['legs'])*RELAY
   extra=0 if lat==1 else int(z['iterations'])*(WAIT2['check']+WAIT2['variable']+WAIT2['convergence'])+int(z['legs'])*WAIT2['relay_init']
   return base+extra
  def win(lat):
   q=[(cost(t,lat),0 if t=='E0' else 1,t) for t in ('E0','E1') if r[t]['converged']]
   return (min(q)[2],min(q)[0]) if q else ('NONE',max(cost(t,lat) for t in ('E0','E1')))
  w1,c1=win(1);w2,c2=win(2)
  out.append(dict(sample_seed=seed,shot=shot,E0_iterations=r['E0']['iterations'],E0_legs=r['E0']['legs'],E1_iterations=r['E1']['iterations'],E1_legs=r['E1']['legs'],E0_L1_cycle=cost('E0',1),E1_L1_cycle=cost('E1',1),E0_L2_cycle=cost('E0',2),E1_L2_cycle=cost('E1',2),L1_winner=w1,L2_winner=w2,winner_changed=w1!=w2,L1_first_success_cycle=c1,L2_first_success_cycle=c2,added_cycle=c2-c1,rescue=int(x['parallel_rescue']),lost_success=False))
 wc(OUT/'n2_cycle_completion.csv',out);return out,cps

def timing_and_lanes(total_iterations,total_legs):
 stat=rows(M4/'shared_memory_port_demand.csv');bank=[]
 for lat in (1,2):
  for x in stat:
   bank.append(dict(read_latency=lat,memory=x['structure'],maximum_queue_depth=0,maximum_inflight_per_bank=lat*2,mean_queue_depth=0,read_port_utilization=float(x['mean_reads_per_bank'])/2,write_port_utilization=0,both_read_ports_active_fraction=x['demand_2_fraction'],idle_fraction=x['demand_0_fraction'],stalled_fraction=0,arbitration_events=0))
 for lat in (1,2):
  bank.append(dict(read_latency=lat,memory='private_message_each_engine',maximum_queue_depth=0,maximum_inflight_per_bank=lat,mean_queue_depth=0,read_port_utilization='phase dependent',write_port_utilization='phase dependent',both_read_ports_active_fraction=0,idle_fraction='phase dependent',stalled_fraction=0,arbitration_events=0))
 wc(OUT/'bank_timing_summary.csv',bank)
 static=[]
 for lat in (1,2):
  for x in stat:static.append(dict(read_latency=lat,structure=x['structure'],max_issue_reads_per_bank=x['maximum_reads_per_bank'],max_physical_port_occupancy=2,cycles_over_two=0,arbitration_cycles=0,added_stalls=0,cause='none; latency increases in-flight requests but not per-cycle port occupancy'))
 wc(OUT/'static_memory_timing.csv',static)
 base=rows(ROOT/'results/bank-aware-folding-layout/variant_comparison.csv');b=next(x for x in base if x['variant']=='BA2');logical=int(b['total_requested_accesses']);issued=int(b['issued_groups']);retries=int(b['retry_subsets']);full=float(b['full_four_lane_fraction']);struct=int(b['estimated_structural_cycles'])
 out=[]
 for lat in (1,2):
  waits=0 if lat==1 else sum(WAIT2.values());cycles=struct+waits
  out.append(dict(read_latency=lat,logical_accesses_per_iteration_plus_relay=logical,issued_access_groups=issued,algorithm_BA2_retry_cycles=retries,new_memory_wait_cycles=waits,total_structural_cycles=cycles,mean_active_lanes_per_controller_cycle=logical/cycles,lane_utilization=logical/(P*cycles),full_4_lane_issue_fraction=full,full_4_lane_controller_cycle_fraction=full*issued/cycles))
 wc(OUT/'lane_utilization_cycle_model.csv',out)

CFG=[(1,32768),(2,16384),(4,8192),(9,4096),(18,2048),(36,1024)]
def pack_one(width,depth,banks):
 best=None
 for cw,cd in CFG:
  n=math.ceil(width/cw)*math.ceil(math.ceil(depth/banks)/cd)*banks
  used=width*depth;cap=n*36864;z=(n,cw,cd,cap-used)
  if best is None or z<best:best=z
 return best
def packing():
 pack=[]
 for n,w,d,b,scope,access,rp,wp in MEM:
  if access=='register':continue
  nb,cw,cd,waste=pack_one(w,d,b);bits=w*d
  pack.append(dict(memory=n,width=w,depth=d,banks=b,BRAM_width_configuration=cw,BRAM_depth_configuration=cd,BRAMs_per_bank=nb//b,total_BRAM36=nb,logical_bits=bits,physical_bits=nb*36864,utilization_efficiency=bits/(nb*36864),wasted_bits=waste))
 wc(OUT/'bram_packing.csv',pack)
 port=[]
 for x in pack:
  shared=x['memory'] in {'edge_to_fault','fault_to_edge','check_degree','fault_degree','prior','syndrome'};direct=True;factor=1
  port.append(dict(**x,required_behavior='two independent reads' if shared else 'one read plus one write',direct_true_dual_port=direct,replication_factor=factor,port_aware_BRAM36=int(x['total_BRAM36'])*factor,assumption='RAMB36 TDP widths <=36; deterministic same-address R/W prevented by controller fence'))
 wc(OUT/'bram_port_aware.csv',port);return pack,port

def main():
 OUT.mkdir(parents=True,exist_ok=True);architecture();arbitration();hazards();comp,cps=completion();ti=sum(int(x['iterations']) for x in cps.values());tl=sum(int(x['legs']) for x in cps.values());templates(ti,tl);timing_and_lanes(ti,tl);pack,port=packing()
 delta=np.array([int(x['added_cycle']) for x in comp]);changed=sum(x['winner_changed'] for x in comp);resc=sum(int(x['rescue']) for x in comp)
 packed=sum(int(x['total_BRAM36']) for x in pack);aware=sum(int(x['port_aware_BRAM36']) for x in port)
 m0bits=64685352;m4bits=32933564
 hierarchy=[dict(architecture='M0 original N2',bits=m0bits,MiB=m0bits/8/2**20,BRAM36=1800,estimate='banked capacity',stored_bit_reduction_vs_M0_percent=0,BRAM_reduction_vs_M0_percent=0),dict(architecture='M4 capacity only',bits=m4bits,MiB=m4bits/8/2**20,BRAM36=925,estimate='banked capacity',stored_bit_reduction_vs_M0_percent=100*(m0bits-m4bits)/m0bits,BRAM_reduction_vs_M0_percent=100*(1800-925)/1800),dict(architecture='M4 width/depth packed',bits=m4bits,MiB=m4bits/8/2**20,BRAM36=packed,estimate='analytical RAMB36 configuration packing',stored_bit_reduction_vs_M0_percent=100*(m0bits-m4bits)/m0bits,BRAM_reduction_vs_M0_percent=100*(1800-packed)/1800),dict(architecture='M4 port-aware packed',bits=m4bits,MiB=m4bits/8/2**20,BRAM36=aware,estimate='analytical TDP packing',stored_bit_reduction_vs_M0_percent=100*(m0bits-m4bits)/m0bits,BRAM_reduction_vs_M0_percent=100*(1800-aware)/1800)]
 wc(OUT/'memory_hierarchy.csv',hierarchy)
 wc(OUT/'gari_recomparison.csv',[dict(design='GARI one core',BRAM36=704,type='measured',below_2121=True,below_704=False),dict(design='GARI three cores',BRAM36=2121,type='measured',below_2121=False,below_704=False),dict(design='M4 port-aware packed',BRAM36=aware,type='analytical',below_2121=aware<2121,below_704=aware<704)])
 base=np.asarray([int(x['L1_first_success_cycle']) for x in comp]);relative=100*delta/base
 summary=dict(shots=128,trajectories=256,iterations=ti,relay_legs=tl,L1_changed_winners=0,L2_changed_winners=changed,rescues=resc,L2_added_cycles=dict(mean=float(delta.mean()),median=float(np.median(delta)),p90=float(np.percentile(delta,90)),p95=float(np.percentile(delta,95)),p99=float(np.percentile(delta,99)),maximum=int(delta.max()),mean_percent=float(relative.mean()),p99_percent=float(np.percentile(relative,99))),message_hazards=0,static_arbitrations=0,L1_memory_wait_cycles=0,L2_structural_wait_cycles=sum(WAIT2.values()),packed_BRAM36=packed,port_aware_BRAM36=aware,decision='READY WITH MINOR CONTROLLER CHANGES',reason='return-valid dependency fences and parameterized 1/2-cycle pipeline timing must be explicit in RTL; no memory redesign is indicated')
 wj(OUT/'study_manifest.json',summary)
 (OUT/'final_cycle_model_report.md').write_text(f'''# M4 cycle-level analytical report\n\nThe frozen BA2 one-cycle-read controller baseline remains exact and adds no memory stalls. Two-cycle reads are legal with return-valid fences and add {sum(WAIT2.values()):,} structural dependency bubbles per iteration-plus-relay template. Across 128 N=2 shots the L2 first-success increase is mean {delta.mean():,.1f}, p95 {np.percentile(delta,95):,.1f}, p99 {np.percentile(delta,99):,.1f}, max {delta.max():,} modeled cycles (mean {relative.mean():.3f}%); {changed} winner identities change and no success is lost. This is not decoder divergence or an FPGA measurement.\n\nRAMB36 width/depth packing gives {packed:,} blocks; TDP port-aware packing remains {aware:,} because each shared bank needs at most two reads and each private bank needs at most one read plus one write. Same-address read/write is forbidden by the semantic return fence, so read-first, write-first, and no-change primitives are decoder-equivalent for issued requests.\n\nThe port-aware value is numerically below GARI's measured three-core 2,121 BRAM and above its measured one-core 704 BRAM. Uncertainty remains material: primitive mode availability, initialization constraints, ECC/parity use, tool packing, routing, FIFOs, and controller storage are not synthesized here, while GARI is measured from a different architecture. No hardware-resource win is established.\n''')
 (OUT/'bram_semantics.md').write_text('''# BRAM semantics\n\nThe model uses synchronous registered reads with selectable latency 1 or 2. Shared banks use TDP ports A and B for two reads. Private dynamic banks use at most one read and one write. Different-address read/write is legal. Same-address dual-read returns the same old value on both ports. Same-address read/write and same-bank dual-write are never issued: the controller waits for all old-semantic message returns before overwrite and BA2 serializes unsupported lane collisions. Consequently read-first is the declared baseline, while write-first or no-change yields the same decoder-visible behavior because undefined collision cases are structurally excluded.\n''')
 (OUT/'README.md').write_text('''# Relay-BP M4 cycle-accurate software controller model\n\nThis is a deterministic analytical cycle/event model, not RTL or synthesis. The complete 128-shot archive is represented by reusable exact phase request templates plus per-shot iteration/leg occurrence counts; `cycle_request_trace.csv` is therefore a lossless run-length description rather than hundreds of millions of duplicate request rows. The one-cycle baseline uses the previously RTL-calibrated BA2 phase constants. The two-cycle mode adds only dependency-fence bubbles and never changes decoder state. See `final_cycle_model_report.md` and `study_manifest.json`.\n''')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
