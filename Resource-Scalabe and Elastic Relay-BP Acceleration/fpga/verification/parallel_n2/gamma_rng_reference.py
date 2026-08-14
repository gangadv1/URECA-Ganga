#!/usr/bin/env python3
"""Bit-exact reference and fixtures for relay_bp_gamma_rng.sv."""
from __future__ import annotations
import argparse, json
from pathlib import Path

MASK=(1<<64)-1
ZERO_REMAP=0x9E3779B97F4A7C15
COUNTS={-4:17, **{q:50 for q in range(-3,11)}, 11:3}

def step(x:int)->int:
    x ^= (x<<13)&MASK; x ^= x>>7; x ^= (x<<17)&MASK
    return x&MASK

def map_region(r:int)->int:
    if r<17:return -4
    if r>=717:return 11
    return -3+(r-17)//50

def vector(seed:int,n:int):
    state=seed&MASK or ZERO_REMAP; out=[]; words=[]; rejected=0
    while len(out)<n:
        state=step(state); r=state&1023
        if r>=720: rejected+=1; continue
        out.append(map_region(r)); words.append(state)
    return out,words,state,rejected

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=Path('fpga/verification/parallel_n2/gamma_rng_vectors.txt'));a=ap.parse_args()
    cases=[(0,1),(1,20),(MASK,20),(0x123456789ABCDEF0,64),(0xCAFEBABE12345678,128)]
    with a.out.open('w') as f:
        f.write(f'{len(cases)}\n')
        for seed,n in cases:
            vals,words,state,rej=vector(seed,n);f.write(f'{seed:016x} {n} {state:016x} {rej}\n')
            for i,(v,w) in enumerate(zip(vals,words)):f.write(f'{i} {v} {w:016x}\n')
    manifest={'algorithm':'xorshift64(13,7,17)','zero_seed_remap':f'0x{ZERO_REMAP:016x}','accepted_region':'low10 < 720','counts_per_720':COUNTS,'cases':len(cases)}
    a.out.with_suffix('.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
