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
def restore_calibration_desktop(prefix):
    # The console collector changes VT. Unlike paired acceptance, this research
    # run has no performance-context file to request collect.sh's VT restoration.
    # Restore the existing authenticated desktop; never invent an output or
    # change its compositor/configuration, and finish before timing starts.
    import pwd, re
    if prefix[:2] != ['runuser','-u']:
        raise RuntimeError('Calibration requires the actual desktop user prefix')
    fields=[item.split('=',1)[1] for item in prefix if item.startswith('XDG_SESSION_ID=')]
    if len(fields)!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',fields[0]):
        raise RuntimeError('Missing unique actual calibration desktop session')
    session=fields[0]
    uid=pwd.getpwnam(prefix[2]).pw_uid
    def property_value(name):
        return measurement['run'](['loginctl','show-session',session,'-p',name,'--value'],timeout=2)
    vt=property_value('VTNr')
    if (uid==0 or property_value('Type')!='wayland' or property_value('User')!=str(uid)
            or not vt.isdecimal() or not 0<int(vt)<=63):
        raise RuntimeError('Calibration session is not the actual non-root Wayland VT')
    measurement['run'](['chvt',vt],timeout=10)
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        if property_value('Active')=='yes':
            value=json.loads(measurement['run'](prefix+['mmsg','get','all-monitors'],timeout=2))
            monitors=value.get('monitors') if type(value) is dict else None
            if (type(monitors) is list and monitors and len(monitors)<=16
                    and all(type(m) is dict and type(m.get('name')) is str and m['name']
                        and type(m.get('width')) is int and m['width']>0
                        and type(m.get('height')) is int and m['height']>0 for m in monitors)
                    and len({m['name'] for m in monitors})==len(monitors)):
                # Mango also retains disabled monitor objects. Require real
                # advertised enabled heads and their current physical modes.
                outputs=json.loads(measurement['run'](prefix+['wlr-randr','--json'],timeout=2))
                if (type(outputs) is not list or len(outputs)>16
                        or any(type(o) is not dict or type(o.get('name')) is not str or not o['name'] for o in outputs)
                        or len({o['name'] for o in outputs})!=len(outputs)):
                    raise RuntimeError('Invalid actual calibration output inventory')
                enabled=[]
                for output in outputs:
                    if output.get('enabled') is not True:continue
                    modes=output.get('modes')
                    current=[m for m in modes if type(m) is dict and m.get('current') is True] if type(modes) is list else []
                    if (len(current)!=1 or type(current[0].get('width')) is not int or current[0]['width']<=0
                            or type(current[0].get('height')) is not int or current[0]['height']<=0
                            or output['name'] not in {m['name'] for m in monitors}):
                        raise RuntimeError('Enabled calibration output has no matching current physical mode')
                    enabled.append(dict(name=output['name'],width=current[0]['width'],height=current[0]['height']))
                if enabled:
                    return dict(session=session,desktop_uid=uid,vt=int(vt),active=True,
                        monitors=[{key:m[key] for key in ('name','width','height')} for m in monitors],
                        enabled_outputs=enabled,
                        scope='Research-only actual desktop restoration before instrumentation and timing')
        time.sleep(.1)
    raise RuntimeError('Actual calibration desktop did not restore visible monitors')

prefix=measurement['desktop']()
awake=None
try:
    state['desktop_readiness']=restore_calibration_desktop(prefix)
    awake=json.loads(measurement['run'](prefix+['arctic-keep-awake','status','--json']))
    if not awake.get('on'):measurement['run'](prefix+['arctic-keep-awake','on','--quiet'])
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
    if awake is not None and not awake.get('on'):measurement['run'](prefix+['arctic-keep-awake','off','--quiet'])
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
