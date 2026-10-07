"""Source-only bounded attestation patch generator; never runs Git mutations/VM."""
import argparse
import difflib
import hashlib
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('unchanged_safe_source_generator',HERE/'prepare-safe-source.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

def change(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Source replacement anchor differs: '+old[:80])
    return text.replace(old,new)

def harness(base):
    text=P.harness(base)
    text=change(text,'''  [[ -c /dev/kvm && -f "$SAFE_DIAGNOSTIC/guest-safe-collector-v1.py" && -f "$SAFE_DIAGNOSTIC/safe-driver-v1.py"
     && -f "$SAFE_DIAGNOSTIC/guest-render-collector-v1.py" && -f "$SAFE_DIAGNOSTIC/render-driver-v1.py" && -f "$SAFE_DIAGNOSTIC/fixed-rows-v1.py"
     && -f "$SAFE_DIAGNOSTIC/bootstrap-safe-v1.sh" ]]''','''  [[ -c /dev/kvm && -f "$SAFE_DIAGNOSTIC/guest-safe-collector-v1.py" && -f "$SAFE_DIAGNOSTIC/attest-startup-v1.py"
     && -f "$SAFE_DIAGNOSTIC/attest-host-v1.py" && -f "$SAFE_DIAGNOSTIC/attestation-driver-v1.py"
     && -f "$SAFE_DIAGNOSTIC/original-safe-driver-v1.py" && -f "$SAFE_DIAGNOSTIC/bootstrap-attest-v1.sh" ]]''')
    begin=text.index('if safe_diagnostic:\n    sys.path.insert(0, "/safe-diagnostic")')
    end=text.index('\n# 2. Splash and boot:',begin)
    text=text[:begin]+'''if safe_diagnostic:
    sys.path.insert(0, "/safe-diagnostic")
    import importlib.util
    spec = importlib.util.spec_from_file_location('startup_attestation_driver', '/safe-diagnostic/attestation-driver-v1.py')
    driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)
    spec = importlib.util.spec_from_file_location('original_qemu_clock', '/safe-diagnostic/original-safe-driver-v1.py')
    origin = importlib.util.module_from_spec(spec); spec.loader.exec_module(origin)
    try:
        driver.run(vm, out, origin.qemu_process_origin(vm.proc.pid),
                   safe_entry_origin if menu_seen else None, menu_seen)
    finally:
        vm.quit()
    sys.exit(0)
''' +text[end:]
    text=change(text,'cp /safe-diagnostic/{guest-safe-collector-v1.py,guest-render-collector-v1.py,fixed-rows-v1.py} /tmp/safe-data/',
                'cp /safe-diagnostic/{guest-safe-collector-v1.py,attest-startup-v1.py,bootstrap-attest-v1.sh} /tmp/safe-data/')
    text=change(text,'/safe-diagnostic/{guest-safe-collector-v1.py,safe-driver-v1.py,guest-render-collector-v1.py,render-driver-v1.py,fixed-rows-v1.py}',
                '/safe-diagnostic/{guest-safe-collector-v1.py,attest-startup-v1.py,attest-host-v1.py,attestation-driver-v1.py,bootstrap-attest-v1.sh}')
    text=text.replace('bootstrap-safe-v1.sh','bootstrap-attest-v1.sh')
    text=text.replace('SAFE_DIAGNOSTIC','STARTUP_ATTESTATION').replace('safe_diagnostic','startup_attestation').replace('safe_entry_origin','startup_entry_origin')
    text=text.replace('safe-diagnostic','startup-attestation').replace('safe-data','startup-data').replace('ARCTICSAFE','ARCTICATTEST')
    text=text.replace('safe-toolchain.txt','attestation-toolchain.txt').replace('Safe diagnostic','Startup attestation')
    text=change(text,'cp /startup-attestation/{guest-safe-collector-v1.py,attest-startup-v1.py,bootstrap-attest-v1.sh} /tmp/startup-data/',
                'cp /startup-attestation/{guest-safe-collector-v1.py,attest-startup-v1.py,bootstrap-attest-v1.sh,toolkit.py,sealed_environment.py,guest-credential-primitive.py,runtime-fixtures-v1.py,synthetic-handoff-observer.py,env-probe.c,env-seal-static-probe.c,argv-probe.c,env-native-v1,env-seal-native-v1,argv-native-v1,runtime-probe-pins-v1.json} /tmp/startup-data/\n  chmod 0644 /tmp/startup-data/*.py /tmp/startup-data/*.c /tmp/startup-data/*.json /tmp/startup-data/*.sh\n  chmod 0555 /tmp/startup-data/{env-native-v1,env-seal-native-v1,argv-native-v1}')
    text=change(text,'/startup-attestation/{guest-safe-collector-v1.py,attest-startup-v1.py,attest-host-v1.py,attestation-driver-v1.py,bootstrap-attest-v1.sh}',
                '/startup-attestation/{guest-safe-collector-v1.py,attest-startup-v1.py,attest-host-v1.py,attestation-driver-v1.py,bootstrap-attest-v1.sh,toolkit.py,sealed_environment.py,guest-credential-primitive.py,runtime-fixtures-v1.py,synthetic-handoff-observer.py,env-probe.c,env-seal-static-probe.c,argv-probe.c,env-native-v1,env-seal-native-v1,argv-native-v1,runtime-probe-pins-v1.json}')
    return text

def workflow(base):
    text=P.workflow(base)
    text=text.replace('safe_visual_diagnostic','startup_attestation').replace('safe-visual-diagnostic','startup-attestation')
    text=text.replace('Safe execution source','startup attestation execution source').replace('Safe diagnostic','startup attestation')
    text=text.replace('safe-execution-source','startup-execution-source').replace('tools/safe-visual-diagnostic','tools/startup-attestation')
    text=text.replace('safe_root','startup_root').replace('arctic-safe-','arctic-startup-attest-')
    text=text.replace('safe-diagnostic-37507582946-','startup-attestation-37507582946-')
    text=text.replace('One fresh passive and separated-input Safe diagnosis','One fresh attestation-only Safe boot, no session hook')
    text=text.replace('Run original and additional host adverse controls before any VM','Run attestation/source adverse controls before any VM')
    text=text.replace('SAFE_DIAGNOSTIC_MODE','STARTUP_ATTESTATION_MODE').replace('SAFE_ROOT','STARTUP_ROOT')
    text=change(text,"      STARTUP_ATTESTATION_MODE: ${{ inputs.startup_attestation && 'true' || 'false' }}",
                     "      STARTUP_ATTESTATION_MODE: ${{ inputs.startup_attestation && 'true' || 'false' }}\n      SAFE_DIAGNOSTIC_MODE: 'false'")
    text=text.replace('safe-runner-v1.py','attestation-runner-v1.py').replace('test_safe_v1.py','test_execution.py').replace('test_render_v1.py','test_attestation.py')
    text=change(text,'          python3 startup-execution-source/tools/startup-attestation/test_attestation.py',
                     '          python3 startup-execution-source/tools/startup-attestation/test_attestation.py\n          python3 startup-execution-source/tools/startup-attestation/test_attest_host.py')
    text=text.replace('Diagnose fixed candidate Safe graphics only; no build, install, release or acceptance pass',
                      'Collect exact fixed-ISO startup metadata only; no build, install, session hook or release')
    return text

def main():
    args=argparse.ArgumentParser(description=__doc__);args.add_argument('--out',type=Path,required=True);value=args.parse_args()
    if value.out.exists():raise RuntimeError('Generator output must be unused')
    value.out.mkdir(mode=0o700,parents=True)
    base_test,base_workflow=P.base_sources()
    for original,output,name,target in [(base_test,harness(base_test),'prepared-test-iso.sh','tools/test-iso.sh'),
                                       (base_workflow,workflow(base_workflow),'registered-iso.yml','.github/workflows/iso.yml')]:
        (value.out/name).write_text(output)
        (value.out/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),output.splitlines(True),fromfile='a/'+target,tofile='b/'+target)))

if __name__=='__main__':main()
