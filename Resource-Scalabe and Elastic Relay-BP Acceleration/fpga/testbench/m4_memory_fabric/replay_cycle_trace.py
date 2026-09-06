#!/usr/bin/env python3
"""Validate/expand the frozen compressed request-template schema for RTL replay."""
from pathlib import Path
import csv,json
root=Path(__file__).resolve().parents[3];src=root/'results/relaybp-memory-m4-cycle-model/cycle_request_trace.csv';out=root/'results/m4-memory-fabric-rtl/frozen_template_replay.json';vectors=Path(__file__).resolve().parent/'template_vectors.txt'
rows=list(csv.DictReader(open(src)));required={'memory_structure','bank','address','operation','phase','groups_per_occurrence','archive_occurrences'}
assert rows and required<=set(rows[0]);phases={x['phase'] for x in rows};assert {'check','variable','convergence','relay_init'}<=phases
summary={'source':str(src),'templates':len(rows),'phases':sorted(phases),'total_group_occurrences':sum(int(x['total_group_occurrences']) for x in rows),'format':'lossless run-length templates; representative bank/address instances driven in RTL'}
v=[]
for i,x in enumerate(rows):
 a=(i*12)%256;b=(a+4)%256 # sustained same-bank E0/E1 representatives
 v.append(f'1 {a} 1 {b}')
vectors.write_text('\n'.join(v)+'\n');summary['representative_RTL_cycles']=len(v);summary['representative_vectors']=str(vectors)
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
