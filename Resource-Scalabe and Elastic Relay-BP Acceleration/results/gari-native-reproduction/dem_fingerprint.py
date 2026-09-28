import stim,hashlib,json
c=stim.Circuit.from_file('/tmp/gari-native-6380d52/data/circuits/BB_n144_k12_d12_CL_both_0.002.stim')
dem=c.detector_error_model(decompose_errors=False,flatten_loops=True,ignore_decomposition_failures=True)
print(json.dumps(dict(stim=stim.__version__,dem_sha256=hashlib.sha256(str(dem).encode()).hexdigest(),dem_errors=dem.num_errors),indent=2))
