"""
Run this once to discover real Herbie variable names for HRRR.
Print results and record them before writing fetch_live_hrrr.py.
"""
from herbie import Herbie
import xarray as xr
from datetime import datetime

# Use a recent date where HRRR is known to be available
# Herbie 2024.8.0 on Python 3.9 has a tz-aware comparison bug — use tz-naive
run_time = datetime(2024, 12, 10, 6)

SEARCH = (
    ":(TMP|DPT|RH):2 m above ground|"
    ":UGRD:10 m above ground|"
    ":VGRD:10 m above ground|"
    ":HPBL:|"
    ":TCDC:boundary layer cloud layer|"
    ":HGT:cloud base"
)

print(f"Downloading HRRR {run_time} fxx=1...")
H = Herbie(run_time, model="hrrr", product="sfc", fxx=1,
           save_dir="/tmp/hrrr_live")

result = H.xarray(SEARCH)

if isinstance(result, list):
    print(f"  Herbie returned list of {len(result)} datasets — merging")
    ds = xr.merge(result, compat="override", join="override")
else:
    ds = result

print("\nVariables in merged dataset:")
for var in sorted(ds.data_vars):
    shape = ds[var].shape
    sample = float(ds[var].values.ravel()[0])
    print(f"  {var:30s}  shape={shape}  sample={sample:.3f}")

print("\nDimensions:", dict(ds.dims))
print("\nCoordinates:", list(ds.coords))
