#!/usr/bin/env python3
"""Unqualified retained-image instrumentation calibration; never acceptance."""
import argparse
import hashlib
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parent
source = (root/'guest.py').read_text()
causal = (root/'causal.py').read_text()
comparison = (root/'compare.py').read_text()
entry = '''
import json, os, time
from pathlib import Path
if sys.argv[1] != 'installed':
    print('ARCTIC-CAUSAL-CALIBRATION live_skipped=true release_acceptance=false', flush=True)
    raise SystemExit(0)
if (Path(__file__).parent != Path('/run/t') or os.geteuid() != 0
        or measurement['run'](['systemd-detect-virt', '--vm']) not in ('qemu', 'kvm')):
    raise RuntimeError('Calibration requires the disposable installed QEMU guest')
state = dict(schema='arctic-causal-calibration-v1', release_acceptance=False,
    original_producer_status='failed_measurement_precision', retained_image_run=37903438836,
    retained_image_sha256='73a95290df7df8d1b4d47c90767e1e231cb340864ed3b3478dde2176b7bfb9c0',
    observer_sha256=OBSERVER_SHA256, comparison_sha256=COMPARISON_SHA256,
    observations=[], status='unrun')
kernel=measurement['run'](['uname','-r'])
config=Path('/boot')/('config-'+kernel)
features=('CONFIG_FTRACE','CONFIG_TRACING','CONFIG_UPROBES','CONFIG_UPROBE_EVENTS','CONFIG_PERF_EVENTS')
config_rows=[line for line in config.read_text().splitlines() if any(line.startswith(key+'=') or line=='# '+key+' is not set' for key in features)] if config.is_file() else None
lockdown=Path('/sys/kernel/security/lockdown')
clocksource=Path('/sys/devices/system/clocksource/clocksource0/current_clocksource')
state['kernel_features']=dict(kernel=kernel,config_path=str(config),config_rows=config_rows,
    lockdown=lockdown.read_text().strip() if lockdown.is_file() else 'not exposed',
    clocksource=clocksource.read_text().strip() if clocksource.is_file() else 'not exposed',
    trace_clock='mono_raw',userspace_clock='CLOCK_MONOTONIC_RAW',
    clock_assumption='One Linux monotonic raw clock for launch, IPC and kernel return; no offset conversion, no NTP/PTP discipline; not host wall-clock accuracy')
prefix=measurement['desktop']()
awake=json.loads(measurement['run'](prefix+['arctic-keep-awake','status','--json']))
if not awake.get('on'):measurement['run'](prefix+['arctic-keep-awake','on','--quiet'])
try:
    with causal.LowerBoundProbe(prefix) as tracer:
        measurement['CAUSAL_TRACER']=tracer
        state['instrumentation']=tracer.proof
        for index in range(4):
            bounds=[]
            measured=measurement['startup'](prefix,['foot'],('foot',),timeout=30,
                observations=bounds,poll_seconds=measurement['ROLE_POLL_SECONDS'],label='causal_calibration_foot')
            if len(bounds)!=1:raise RuntimeError('Calibration requires exactly one retained launch bracket')
            bound=bounds[0]
            limit=min(.005,measured*.025)
            receipt_valid=comparison['causal_precision'](bound)
            state['observations'].append(dict(launch=index,upper_seconds=measured,
                maximum_interval_seconds=limit,causal_receipt_valid=receipt_valid,
                valid=receipt_valid and bound['interval_seconds']<=limit,bound=bound))
    state['status']='calibration_precision_passed' if all(row['valid'] for row in state['observations']) else 'calibration_precision_failed'
except BaseException as error:
    state.update(status='failed_or_unrun',error=str(error))
    raise
finally:
    measurement['CAUSAL_TRACER']=None
    if not awake.get('on'):measurement['run'](prefix+['arctic-keep-awake','off','--quiet'])
    print('ARCTIC-CAUSAL-CALIBRATION '+json.dumps(state,separators=(',',':'),allow_nan=False),flush=True)
raise SystemExit(0 if state['status']=='calibration_precision_passed' else 1)
'''
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(
    '#!/usr/bin/env python3\nimport sys,types\n'
    'causal=types.ModuleType("arctic_performance_causal")\n'
    'causal.__file__=__file__\nsys.modules[causal.__name__]=causal\n'
    f'exec(compile({causal!r},__file__,"exec"),causal.__dict__)\n'
    'measurement={"__name__":"arctic_measurement","__file__":__file__}\n'
    f'exec(compile({source!r},__file__,"exec"),measurement)\n'
    'comparison={"__name__":"arctic_calibration_comparison","__file__":__file__}\n'
    f'exec(compile({comparison!r},__file__,"exec"),comparison)\n'
    f'OBSERVER_SHA256={hashlib.sha256((source+chr(0)+causal).encode()).hexdigest()!r}\n'
    f'COMPARISON_SHA256={hashlib.sha256(comparison.encode()).hexdigest()!r}\n'
    + entry)
