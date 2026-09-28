import os,subprocess,time,json,pathlib,datetime
out=pathlib.Path('/Users/gangadevi.aa/Desktop/URECA-Ganga/Resource-Scalabe and Elastic Relay-BP Acceleration/results/gari-native-reproduction')
env=os.environ.copy();env.update(PATH='/tmp/gari-native-py311/bin:'+env['PATH'],PYTHONUNBUFFERED='1',MPLCONFIGDIR='/tmp/gari-native-mpl',PYTHONPATH=str(out/'observer'),GARI_CAPTURE_DIR=str(out/'python311'))
cmd=(out/'command.txt').read_text().strip().split()
start=time.perf_counter(); started=datetime.datetime.now(datetime.timezone.utc).isoformat()
with (out/'python311/run_stdout.txt').open('w') as stdout,(out/'python311/run_stderr.txt').open('w') as stderr:
 p=subprocess.Popen(cmd,cwd='/tmp/gari-native-6380d52',env=env,stdout=stdout,stderr=stderr)
 (out/'python311/process.json').write_text(json.dumps(dict(pid=p.pid,started_utc=started,command=cmd),indent=2))
 rc=p.wait()
record=dict(exit_code=rc,wall_seconds=time.perf_counter()-start,started_utc=started,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'python311/completion.json').write_text(json.dumps(record,indent=2)); print(json.dumps(record))
