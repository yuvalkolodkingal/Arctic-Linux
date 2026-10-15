"""Complete synthetic original serial evidence; never a runtime qualification."""
import io
import json
from pathlib import Path
import types
import zipfile

import test_performance_roles as roles

ROOT = Path(__file__).parents[2]


def load(name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


contract = load('external_contract_fixture', ROOT/'tools/performance/contract.py')
comparator = load('external_compare_fixture', ROOT/'tools/performance/compare.py')


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def reseal(entries):
    """Rehash coherent adversarial data so tests exercise semantic validation."""
    state = json.loads(entries['execution.json'])
    state['files'] = {name: dict(bytes=len(content), sha256=contract.digest(content))
        for name, content in entries.items() if name not in ('execution.json', 'upload-screening.json')}
    entries['execution.json'] = encoded(state)
    screen = dict(scope='Owned synthetic QEMU VM only; no host desktop, VM disks or credentials', files={})
    for name, content in entries.items():
        if name != 'upload-screening.json':
            screen['files'][name] = dict(bytes=len(content), original_sha256=contract.digest(content),
                uploaded_sha256=contract.digest(content), redactions=0)
    entries['upload-screening.json'] = encoded(screen)
    return entries


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as target:
        for name, content in entries.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o100644 << 16
            target.writestr(info, content)
    return zipfile.ZipFile(io.BytesIO(stream.getvalue()))


def fixture():
    C = contract
    source = 'abc1234' + '0'*33
    head, parent, run_id = '1'*40, '2'*40, 31
    image = dict(run_id=9, source_sha=source, name='Arctic-Linux-1.2-candidate-9-1-x86_64.iso',
        bytes=1000, sha256='e'*64, artifact_id=8, archive_bytes=2000, archive_sha256='7'*64,
        producer_mode=C.MODE)
    receipt = dict(schema='arctic-producer-performance-receipt-v1', repository='yuvalkolodkingal/Arctic-Linux',
        workflow='.github/workflows/iso.yml', event='workflow_dispatch', source_sha=source,
        run_id=9, run_attempt=1, mode=C.MODE, release_acceptance=False,
        inputs=dict(expected_source_sha=source, release=False, tag='', prerelease=True, draft=False,
            nix_acceptance=False, performance_acceptance=False, boot_test=True, performance_mode=C.MODE),
        image={key:image[key] for key in ('name','bytes','sha256')},
        startup_results={name:dict(firmware=firmware, mode=mode, status='passed', serial_bytes=20, serial_sha256='a'*64)
            for name, firmware, mode in (('uefi-try','uefi','try'), ('bios-install','bios','install'), ('uefi-safe','uefi','safe'))})
    receipt_bytes = encoded(receipt)
    image['producer_receipt_sha256'] = C.digest(receipt_bytes)
    observer = C.observer_hashes(ROOT)
    sources = {'profiles/ci/offline.toml':'f'*64, 'shell/AppsService.qml':'b'*64, 'shell/BatteryService.qml':'9'*64}
    execution_files = {name:'8'*64 for name in C.EXECUTION_FILES}
    execution_files['tools/performance/compare.py'] = observer['comparator_sha256']
    execution_files['tools/performance/fixtures/v1.2-offline.toml'] = C.BASELINE['profile_sha256']
    plan = dict(schema='arctic-external-paired-plan-v1', ready=True, release_acceptance=False,
        performance_mode=C.MODE, image=image, baseline=C.BASELINE, candidate_source_files=sources,
        observer=observer, execution_files=execution_files)
    plan_sha = C.digest(encoded(plan))
    external = dict(schema='arctic-external-paired-context-v1', run_id=run_id, execution_source_sha=head,
        reviewed_parent_sha=parent, plan_sha256=plan_sha, observer=observer,
        image_source_sha=source, candidate_iso_sha256=image['sha256'])
    entries = {'producer-receipt.json':receipt_bytes}
    entries['vm-base-image-id.txt'] = ('sha256:'+'5'*64+'\n').encode()
    entries['vm-prepared-image-id.txt'] = ('sha256:'+'4'*64+'\n').encode()
    # Obtain actual frozen bytes from the production composer, not a fake hash.
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp)/'observer.py'
        subprocess.run(['python3','-B',str(ROOT/'tools/performance/compose-paired-probe.py'),str(path)],check=True)
        entries['observer-source.txt'] = path.read_bytes()
    toolchain = b'fixture only: immutable QEMU and firmware RPM inventory\n'
    state = dict(phase='complete_regression_gate_passed', acceleration='kvm', memory_mib=4096,
        vcpus=2, restricted_network=True, input_images_rechecked=True, observer_sha256=observer['frozen_sha256'],
        vm_base_image_id='sha256:'+'5'*64, vm_prepared_image_id='sha256:'+'4'*64,
        vm_toolchain_sha256=C.digest(toolchain), images={}, profiles={}, pristine_installed_sources={}, runs=[],
        planned_boot_order=[dict(image=name,boot=boot) for name,boot in C.ORDER])
    for name, expected_image in (('baseline',C.BASELINE),('candidate',image)):
        state['images'][name] = dict(bytes=expected_image['bytes'],sha256=expected_image['sha256'])
        state['profiles'][name] = dict(sha256=C.BASELINE['profile_sha256'] if name=='baseline' else sources['profiles/ci/offline.toml'])
        state['pristine_installed_sources'][name] = {'target.qcow2':('b' if name=='baseline' else 'c')*64,'OVMF_VARS.fd':'d'*64}
        entries[name+'-install-harness.log'] = b'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean\n'
        entries[name+'/serial-install.log'] = b'ARCTIC-INSTALL-EXIT=0\n'
        entries[name+'/vm-toolchain.txt'] = toolchain
    runs = dict(baseline=[],candidate=[])
    for index,(name,boot) in enumerate(C.ORDER,1):
        prefix='runs/'+name+'/'+str(boot)+'/'
        record=roles.role_run(name,boot)
        context=record['app_roles']['boot_context']
        context.update(external_execution=external,context_id=f'{index:032x}')
        record['identity']['boot_id']=f'00000000-0000-0000-0000-{index:012x}'
        record['observer_source_sha256']=observer['source_sha256']
        record['external_execution']=dict(context=context,observer_file_sha256=observer['frozen_sha256'])
        record['measured_payload']['battery_sha256']=sources['shell/BatteryService.qml']+'  /usr/share/arctic/shell/BatteryService.qml'
        serial='ARCTIC-PERFORMANCE-CONSOLE-RESTORED session=2 vt=2\nARCTIC-COLLECT-BEGIN\n'
        serial+='\n'.join('ARCTIC-PERFORMANCE '+json.dumps(dict(stage='installed',check=key,value=value))
            for key,value in record.items())
        serial+='\nARCTIC-INSTALLED-SMOKE-EXIT=0\nARCTIC-COLLECT-END\n'
        entries[prefix+'serial-boot.log']=serial.encode()
        entries[prefix+'harness.log']=b'fixture harness exit zero\n'
        entries[prefix+'performance-context.json']=encoded(context)
        entries[prefix+'vm-toolchain.txt']=toolchain
        state['runs'].append(dict(image=name,boot=boot,harness_exit=0,archive='/work/'+prefix.rstrip('/')))
        runs[name].append(record)
    entries['comparison.json']=encoded(comparator.compare_checked(runs,candidate_commit=source[:7],
        candidate_catalog_sha256=sources['shell/AppsService.qml'],candidate_battery_sha256=sources['shell/BatteryService.qml']))
    entries['status.json']=encoded(state)
    entries['execution.json']=encoded(dict(schema='arctic-external-paired-execution-v1',
        status='frozen_external_paired_regression_gate_passed',release_acceptance=False,run_id=run_id,run_attempt=1,
        execution_source_sha=head,reviewed_parent_sha=parent,image=image,baseline=C.BASELINE,plan_sha256=plan_sha,
        observer=observer,candidate_source_files=sources,execution_files=execution_files,files={}))
    metadata=dict(plan=plan,plan_sha256=plan_sha,image=image,execution_source_sha=head,
        reviewed_parent_sha=parent,execution_run_id=run_id,comparator=comparator,producer_receipt=receipt)
    return reseal(entries),metadata
