#!/usr/bin/env python3
"""Prepare an honest blocked Vivado study; never substitutes analytical data for inference."""
from pathlib import Path
import csv,json,hashlib,shutil,subprocess
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];PACK=ROOT/'results/relaybp-memory-m4-cycle-model/bram_packing.csv'
OUT.mkdir(parents=True,exist_ok=True);(OUT/'reports').mkdir(exist_ok=True)
def rows(p):
 with open(p,newline='') as f:return list(csv.DictReader(f))
def wc(p,x,fields=None):
 x=list(x);fields=fields or list(x[0]);
 with open(p,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(x)
def wj(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
viv=shutil.which('vivado');version=None
if viv:
 try:version=subprocess.run([viv,'-version'],capture_output=True,text=True,timeout=30).stdout.splitlines()[0]
 except Exception:version='available but version query failed'
target=None;clock=None
env=f'''Vivado executable: {viv or "NOT FOUND"}\nVivado version: {version or "NOT AVAILABLE"}\nTarget FPGA part: NOT SPECIFIED IN REPOSITORY\nTarget family: UNKNOWN\nPackage/speed grade: UNKNOWN\nBoard: NOT SPECIFIED\nClock period: NOT SPECIFIED\nSynthesis mode intended: out_of_context\nMemory family: UNKNOWN UNTIL TARGET PART IS PROVIDED\nSynthesis launched: NO\n\nRepository evidence:\n- results/vivado-n1-baseline/summary.json: blocked_before_synthesis\n- no .xpr or .xdc exists\n- docs/research_proposal/relay_bp_fpga_research_proposal.md leaves target insertion as future work\n- the VU29P in GARI documents is a literature-comparison device, not a Relay-BP project target\n'''
(OUT/'vivado_environment.txt').write_text(env)
(OUT/'synthesis_commands.txt').write_text('''# Do not run until the project owner supplies exact values.\nexport TARGET_PART='<exact complete Vivado part string>'\nexport CLOCK_PERIOD_NS='<approved out-of-context clock period>'\nvivado -mode batch -source fpga/testbench/m4_memory_fabric/synth_m4_matrix.tcl -log results/m4-memory-fabric-synthesis/reports/vivado.log -journal results/m4-memory-fabric-synthesis/reports/vivado.jou\n''')
wr=[]
for n in ['m4_shared_tdp_bank','m4_private_bank','m4_message_ram','m4_memory_fabric_top']:
 wr.append(dict(wrapper=n,status='NOT EXECUTED',target_part='',vivado_version='',parameters='representative/full-depth matrix prepared',RAMB36='',RAMB18='',LUTRAM='',LUT='',FF='',DSP='',inferred_port_mode='',read_latency='',warnings='target FPGA and Vivado unavailable'))
wc(OUT/'wrapper_resource_summary.csv',wr)
classes=[];packing=[];tdp=[]
for x in rows(PACK):
 classes.append(dict(memory=x['memory'],logical_width=x['width'],logical_depth=x['depth'],banks=x['banks'],analytical_BRAM36=x['total_BRAM36'],vivado_status='NOT EXECUTED',inferred_primitive='',RAMB36='',RAMB18='',LUTRAM='',FF='',replication_factor='',packing_efficiency='',unused_capacity='',warnings=''))
 packing.append(dict(memory=x['memory'],logical_width=x['width'],logical_depth=x['depth'],banks=x['banks'],analytical_BRAM36=x['total_BRAM36'],vivado_BRAM36_equivalent='',difference='',difference_percent='',classification='UNVERIFIED',reason='Vivado and exact target unavailable'))
 if not x['memory'].startswith(('E0_','E1_')):
  tdp.append(dict(memory=x['memory'],analytical_BRAM36_without_replication=x['total_BRAM36'],vivado_BRAM36_equivalent='',inferred_TDP='',replication_factor='',port_cost_difference='',status='NOT EXECUTED'))
wc(OUT/'memory_class_resource_summary.csv',classes);wc(OUT/'packing_vs_analytical.csv',packing);wc(OUT/'tdp_inference_check.csv',tdp)
wc(OUT/'full_fabric_resources.csv',[dict(configuration='M4 full isolated memory fabric',status='NOT EXECUTED',measured_or_extrapolated='neither',RAMB36='',RAMB18='',BRAM36_equivalent='',LUT='',FF='',LUTRAM='',DSP='',warnings='cannot sum unmeasured inference results',analytical_reference_BRAM36=980)])
wc(OUT/'timing_summary.csv',[dict(configuration='M4 isolated memory fabric',status='NOT EXECUTED',target_clock_ns='',WNS_ns='',TNS_ns='',estimated_Fmax_MHz='',critical_path='',reason='no approved clock, target part, or Vivado')])
wc(OUT/'gari_memory_recomparison.csv',[dict(design='GARI one core',BRAM=704,basis='measured published',difference_vs_M4_inferred='',comparison='M4 inferred unavailable'),dict(design='GARI three cores',BRAM=2121,basis='measured published',difference_vs_M4_inferred='',comparison='M4 inferred unavailable'),dict(design='Relay-BP M4',BRAM='',basis='Vivado inferred NOT AVAILABLE',difference_vs_M4_inferred='',comparison='analytical reference remains 980; not substituted here')])
(OUT/'read_write_semantics.md').write_text('''# Read/write semantics status\n\nThe standalone RTL declares read-first private RAM behavior and prohibits same-address message read/write in normal M4 operation. Functional Icarus tests passed, but Vivado primitive configuration and collision-mode reporting were not produced. Compatibility with a selected FPGA's RAMB18/RAMB36 modes is therefore **not synthesis-confirmed**.\n''')
(OUT/'synthesis_warnings.md').write_text('''# Synthesis warnings and risks\n\nNo Vivado warning log exists because synthesis was not launched. Architecture-relevant unknowns remain: block-RAM versus LUTRAM inference, true-dual-port mapping, replication, width adaptation, cascade depth, initialization, reset handling, collision mode, unused bits, and timing. Treating the absence of warnings as a pass would be incorrect.\n''')
manifest=dict(status='BLOCKED BEFORE SYNTHESIS',required_action='TARGET FPGA AND VIVADO REQUIRED',vivado_available=bool(viv),vivado_version=version,target_part=target,target_family=None,speed_grade=None,clock_period_ns=clock,synthesis_mode='out_of_context intended',synthesis_launched=False,reports_generated=0,analytical_reference_BRAM36=980,inferred_BRAM36=None,packing_difference=None,M0_analytical_BRAM36=1800,GARI_one_core_measured_BRAM=704,GARI_three_core_measured_BRAM=2121,decision='UNCLASSIFIED — A/B/C/D require inference evidence',blockers=['Exact complete FPGA part is absent','No board, XDC, or Vivado project exists','No approved clock period exists','Vivado executable is unavailable'],full_decoder_integrated=False)
wj(OUT/'study_manifest.json',manifest)
(OUT/'README.md').write_text('''# M4 isolated Vivado BRAM-inference study — blocked\n\nNo synthesis was executed. The repository does not define an FPGA part or clock and this host has no Vivado executable. Empty inferred-resource fields are intentional. The analytical 980-BRAM36 value is retained only as a reference and is never presented as inferred. Parameterized Tcl and an exact command template are prepared; see `vivado_environment.txt` and `synthesis_commands.txt`.\n''')
(OUT/'final_synthesis_report.md').write_text('''# Final synthesis report\n\n## Outcome\n\n**BLOCKED BEFORE SYNTHESIS — TARGET FPGA AND VIVADO REQUIRED.**\n\nThe requested isolated inference study cannot be run reproducibly because the repository supplies no exact part, speed grade/package, board, XDC, or approved clock, and Vivado is not installed. The earlier N=1 Vivado audit reached the same conclusion. The VU29P device mentioned in GARI literature is not a Relay-BP project target and was not adopted.\n\nNo RAMB36, RAMB18, LUTRAM, LUT, FF, DSP, warning, collision-mode, packing, replication, WNS, TNS, or Fmax result is claimed. The 980-BRAM36 M4 number remains analytical. Consequently the requested A/B/C/D architecture decision cannot honestly be made from synthesis evidence.\n\n## Prepared work\n\nThe standalone RTL remains functionally validated. `synth_m4_matrix.tcl` contains out-of-context full-depth jobs for shared metadata, degree, prior, syndrome, message, marginal, gamma, and decision bank classes. It deliberately fails unless `TARGET_PART` and `CLOCK_PERIOD_NS` are supplied.\n''')
print(json.dumps(manifest,indent=2))
