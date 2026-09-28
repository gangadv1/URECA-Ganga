from pathlib import Path
import subprocess,json,hashlib,os,sys,importlib.metadata as md,platform,shutil
out=Path('/Users/gangadevi.aa/Desktop/URECA-Ganga/Resource-Scalabe and Elastic Relay-BP Acceleration/results/gari-native-reproduction')
repo=Path('/tmp/gari-native-6380d52')
(out/'python311').mkdir(exist_ok=True)
(out/'observer').mkdir(exist_ok=True)
(out/'raw').mkdir(exist_ok=True)
cmd='python3 stim_batched_data_v2.py 12 0.002 400 0.96875 1 0 2 16 100 0 i 4'
(out/'command.txt').write_text(cmd+'\n')
env=os.environ.copy();env['MPLCONFIGDIR']='/tmp/gari-native-mpl'
pre=subprocess.run([sys.executable,'-c','import stim,sinter,ldpc,numpy,scipy,networkx,matplotlib,pymatching; import stim_batched_data_v2; print("All runtime imports and C library load succeeded")'],cwd=repo,env=env,capture_output=True,text=True)
(out/'python311/preflight_stdout.txt').write_text(pre.stdout);(out/'python311/preflight_stderr.txt').write_text(pre.stderr)
assert pre.returncode==0,pre.stderr
import stim
f=repo/'data/circuits/BB_n144_k12_d12_CL_both_0.002.stim';c=stim.Circuit.from_file(str(f))
info=dict(gari_commit='6380d52e76d8c9cb0b4eedf3e8d2429b24cef78d',ureca_commit='c4dc34e560c7af78b7e6397e506ba6d27f3e7eb7',official_url='https://github.com/astra-decoders/gari-nms.git',python=sys.version,python_executable=sys.executable,platform=platform.platform(),machine=platform.machine(),stim=stim.__version__,dependencies={x:md.version(x) for x in ['ldpc','stim','sinter','numpy','scipy','networkx','matplotlib','pymatching']},circuit=dict(path=str(f.relative_to(repo)),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),qubits=c.num_qubits,detectors=c.num_detectors,observables=c.num_observables,rounds=12,p=0.002,noise_model='CL: p1=p2=p3=p4=0.002; use_both=True; memory Z'),sampling_seed=None,schedule_seed=1,ensemble_size=1,threads=4,working_directory=str(repo),observer='read-only Python trace of driver locals after decoder timing ends; saves native returned arrays; no changes to decoder inputs, RNG, control flow or outputs',prior_attempt='Concurrent Python 3.13.6 attempt in /tmp/gari-nms-audit; original root run_stdout/run_stderr preserved until completion; supplied prior history recorded in README')
build=subprocess.run(['make','-B'],cwd=repo/'my_decoders',capture_output=True,text=True)
(out/'build_stdout.txt').write_text(build.stdout);(out/'build_stderr.txt').write_text(build.stderr);assert build.returncode==0
info['build']={'command':'make clean && make (initial); make -B (captured repeat)','returncode':build.returncode,'compiler':subprocess.check_output(['clang','--version'],text=True),'library_sha256':hashlib.sha256((repo/'my_decoders/hbplib_v2.so').read_bytes()).hexdigest(),'linkage':subprocess.check_output(['otool','-L',str(repo/'my_decoders/hbplib_v2.so')],text=True)}
(out/'environment.json').write_text(json.dumps(info,indent=2)+'\n')
(out/'requirements-freeze.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
shutil.copy2(f,out/'raw'/f.name)
for fn in ['stim_batched_data_v2.py','helper_functions.py','my_decoders/hbp_decoder_v2.c','my_decoders/hbplib_wrapper_v2.py','my_decoders/Makefile','README.md']:
 p=out/'official_source'/fn;p.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(repo/fn,p)
print(json.dumps(info,indent=2))
