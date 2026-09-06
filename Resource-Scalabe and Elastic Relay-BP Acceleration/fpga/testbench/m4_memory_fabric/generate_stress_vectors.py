#!/usr/bin/env python3
"""Deterministic legal shared-memory stress traffic."""
from pathlib import Path
import random
p=Path(__file__).resolve().parent/'stress_vectors.txt';r=random.Random(20260901);out=[]
for cycle in range(5000):
 e0=r.random()<.82;e1=r.random()<.82;a0=r.randrange(256);mode=r.randrange(5)
 if mode==0:a1=a0                         # same address
 elif mode in (1,2):a1=(r.randrange(64)*4)+(a0%4) # same bank
 else:a1=r.randrange(256)
 out.append(f'{int(e0)} {a0} {int(e1)} {a1}')
p.write_text('\n'.join(out)+'\n');print(p)
