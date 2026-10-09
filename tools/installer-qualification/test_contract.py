"""Synthetic adversarial contract controls; never evidence of a real image pass."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

C=load('installer_acceptance_contract',HERE/'contract.py')
G=load('installer_guest_fixtures',HERE/'test_guest.py')
D=load('installer_driver_fixture',HERE/'driver.py')


def fixture():
    context=G.context(); engine=G.engine(); uid=1000; boot='11111111-1111-1111-1111-111111111111'
    def proc(pid,owner,exe,argv,ppid=1):
        return dict(pid=pid,uid=owner,ppid=ppid,start_ticks=123+pid,executable=exe,
                    executable_sha256='a'*64,argv=argv,overrides_absent=True)
    identities=dict(gui=proc(100,uid,'/usr/bin/quickshell',['quickshell','-p','/usr/share/arctic/installer-ui']),
                    bridge=proc(101,uid,'/usr/bin/arctic-install',['arctic-install','bridge'],100),
                    daemon=proc(102,0,'/usr/bin/arcticd',['arcticd']),
                    service=dict(MainPID='102',InvocationID='b'*32,ExecMainStartTimestampMonotonic='12',ActiveState='active',NRestarts='0'),
                    listener=dict(path='/run/arcticd.sock',filesystem_device=5,filesystem_inode=6,uid=0,mode=0o660,stream_inode=7,serving_pid=102,listening_fds=[3]))
    keyboard={path:dict(bytes=120,sha256='c'*64,uid=owner,mode=0o644) for path,owner in
              (('/etc/arctic/mango/keyboard.conf',0),('/home/liveuser/.config/arctic/live-keyboard.conf',uid))}
    stable=dict(engine=engine,identities=identities,keyboard_files=keyboard,gui_log_counts=dict(available=False,reason='canonical log absent'))
    media={}; files={}
    def observed(name='Virtual-1',count=2):
        state=G.state();state['window']['screen']=name
        outputs=[G.output('Virtual-1',count==2 or name=='Virtual-1'),G.output('Virtual-2',count==2 or name=='Virtual-2')]
        visible=dict(window=state['window'],layers=G.layers(name),output=next(o for o in outputs if o['name']==name),physical_size=[1280,720])
        return dict(state=state,outputs=outputs,visible=visible)
    def capture(name,item):
        image=Image.new('RGB',(1280,720),(32,36,40));stream=io.BytesIO();image.save(stream,format='PNG');data=stream.getvalue()
        media['installer/'+name]=data;files[name]=dict(bytes=len(data),sha256=C.digest(data))
        return dict(path=name,**files[name],size=[1280,720],background=[32,36,40],pixels=[[32,36,40]]*9,region=[1269,359,1272,362],tolerance=3)
    baseline=dict(**copy.deepcopy(stable),**observed(),initial_wizard=dict(current='welcome'),rpc_peer=dict(pid=1,uid=0),
                  packaged_sources=C.packaged_source_hashes(HERE.parents[1]),
                  drm_heads=dict(pci_vendor='0x1af4',pci_device='0x1050',driver='/sys/bus/virtio/drivers/virtio_gpu',
                                 outputs={name:dict(head=n,connector_id=10+n) for n,name in enumerate(('Virtual-1','Virtual-2'))}))
    baseline['capture']=capture('baseline.png',baseline)
    def request(kind,cycle,**extra):
        return dict(schema='arctic-installer-request-v1',kind=kind,cycle=cycle,token=context['token'],boot_id=boot,engine_sha256=C.hash_value(engine),**extra)
    cases=[];requests=[]
    for kind in ('vt','output'):
        for cycle in range(3):
            if kind=='vt':
                away=dict(session='1',uid=uid,vt=2,active=False,foreground='tty6')
                req=request('vt-away',cycle,away=away,original_vt=2)
                disruption=dict(away=away,request=req,prepared_state=copy.deepcopy(stable),returned_vt=2);requests.append(req)
            else:
                mode='all' if cycle==1 else 'hosting-only';count=0 if mode=='all' else 1
                common=dict(mode=mode,hosting_output='Virtual-1',hosting_head=0,enabled_outputs=['Virtual-1','Virtual-2'])
                absent=dict(**copy.deepcopy(stable),enabled_output_count=count)
                if mode=='all':absent.update(outputs=[G.output('Virtual-1',False),G.output('Virtual-2',False)],state=G.state(),installer_layers=[])
                else:
                    absent.update(observed('Virtual-2',1));absent['capture']=capture('output-'+str(cycle)+'-relocated.png',absent)
                dis=request('output-disconnect',cycle,**common)
                restore=request('output-restore',cycle,**common,enabled_output_count=count,outputs=absent['outputs'],outputs_sha256=C.hash_value(absent['outputs']))
                disruption=dict(mode=mode,hosting_output='Virtual-1',hosting_head=0,disconnect_request=dis,unavailable=absent,restore_request=restore)
                requests.extend([dis,restore])
            case=dict(kind=kind,cycle=cycle,status='passed',**copy.deepcopy(stable),**observed(),disruption=disruption)
            case['capture']=capture(kind+'-'+str(cycle)+'.png',case);cases.append(case)
    report=dict(schema='arctic-live-installer-restoration-v1',stage='live',status='passed',context=context,release_acceptance=False,
                boot_id=boot,desktop_uid=uid,active_desktop_session='1',original_vt=2,errors=[],captures=9,baseline=baseline,cases=cases,
                cleanup=dict(original_vt_restored=True,owned_gui_stopped=True,owned_bridge_stopped=True,engine_retained=True,
                             engine_snapshot_sha256=C.hash_value(engine),pretest_wizard_reset_claim=False,errors=[]),
                security=dict(selinux='Enforcing',observed_new_avcs=0,audit_enabled=True))
    inputs={name:'a'*64 for name in C.EXECUTION_FILES}
    inputs['tools/installer-qualification/guest.py']=context['checker_sha256']
    inputs['tools/native-functional/taskbar-runtime.py']=context['runtime_sha256'];inputs['tools/native-functional/native_smoke.py']=context['native_sha256']
    receipts=[]
    for req in requests:
        receipt=dict(request=req,request_sha256=C.hash_value(req))
        if req['kind']=='vt-away':
            image=Image.new('L',(1280,720),0);ImageDraw.Draw(image).rectangle((20,20,120,35),fill=255)
            stream=io.BytesIO();image.save(stream,format='PNG');data=stream.getvalue();name='installer-vt-away-'+str(req['cycle'])+'.png'
            media['host/'+name]=data;receipt['capture']=dict(path=name,bytes=len(data),sha256=C.digest(data),console_pixel_guard_passed=True,manual_console_review_required=True)
        else:
            heads={0,1} if req['kind']=='output-restore' else (set() if req['mode']=='all' else {1})
            receipt['display']=dict(schema='arctic-installer-host-output-v1',qemu_pid=200,qemu_uid=0,gpu_id='arctic_taskbar_gpu',bus_owner=':1.5',enabled_heads=sorted(heads),
                applied=[dict(head=n,width=1280 if n in heads else 0,height=720 if n in heads else 0,xoff=n*1280,yoff=0) for n in (0,1)])
        receipts.append(receipt)
    serial=b'ARCTIC-CONSOLE-READY='+b'f'*32+b' user=liveuser uid=1000\n'
    guest=dict(status='passed',context=context,report=report,requests=requests,collector=dict(boot_id=boot,desktop_uid=uid,active_desktop_session='1'),serial=dict(bytes=len(serial),sha256=C.digest(serial)))
    with tempfile.TemporaryDirectory() as root:
        # Preserve the real argv builder while avoiding external firmware input.
        from unittest.mock import patch
        with patch.object(D.shutil,'copyfile'):
            argv=D.prepare_vm(type('Display',(),{'display_arg':'dbus,addr=unix:path=/tmp/arctic-tb-display-test/bus,gl=off'})(),Path(root),'uefi')
    host=dict(status='host_completed_pending_guest_evidence_validation_and_visual_review',context=context,firmware='uefi',errors=[],iso_booted=True,
              owned_qemu_stopped=True,owned_private_bus_closed=True,execution_inputs={name:inputs[name] for name in C.HOST_EXECUTION_FILES},host_transitions=receipts,qemu_argv=argv,
              console_authentication=dict(status='exact_liveuser_uid_response',nonce='f'*32),
              display_preparation=dict(controller_sha256=inputs['tools/native-functional/taskbar-display.py'],status='uiinfo_applied_pending_guest_two_output_evidence',
                gpu_id='arctic_taskbar_gpu',display_backend='dbus',qemu_uid=0,qemu_pid=200,bus_pid=201,bus_owner=':1.5',guest_monitor_verification_required=True,
                heads=[dict(head=n,console_id=n,device_address='pci/0000/01.0',width=1280,height=720) for n in (0,1)]))
    image=dict(source_sha=context['source_sha'],sha256=context['iso_sha256'],bytes=context['iso_bytes'],name='test.iso')
    state=dict(schema='arctic-installer-execution-v1',status='live_installer_restoration_passed_pending_manual_visual_review',release_acceptance=False,
               image=image,execution=dict(source_sha=context['execution_sha']),context=context,source_inputs=inputs,guest=guest,host=host,
               required_images={name:C.digest(data) for name,data in media.items()},build=dict(schema='arctic-taskbar-tools-v1',release_acceptance=False,
                binaries={'raw-screencopy':context['capture_sha256']},sources={name:inputs[name] for name in ('tools/native-functional/taskbar-screencopy.c','shell/dev/virtual-pointer.c','shell/dev/wlr-screencopy-unstable-v1.xml')}),
               transport=dict(status='passed',report_path='installer/installer-report.json',report_sha256=C.digest((json.dumps(report,sort_keys=True)+'\n').encode()),serial_sha256=C.digest(serial)))
    return report,state,files,media,serial


class Controls(unittest.TestCase):
    def test_complete_synthetic_report_and_execution_are_coherent_but_pending_manual(self):
        report,state,files,media,serial=fixture()
        result=C.validate_report(report,state['context'],files,lambda name:media['installer/'+name],report['baseline']['packaged_sources'])
        self.assertEqual(result['status'],'passed_pending_manual_visual_review');self.assertEqual(len(result['requests']),9)
        self.assertEqual(C.validate_execution(state,state['image'],state['context']['execution_sha'],serial,media.__getitem__)['images'],list(C.REQUIRED_IMAGES))

    def test_report_rejects_engine_pid_page_config_layer_and_output_contradictions(self):
        mutations=[lambda r:r['cases'][0]['engine']['hello'].update(mock=True),
                   lambda r:r['cases'][1]['identities']['daemon'].update(pid=999),
                   lambda r:r['cases'][2]['state'].update(page='install'),
                   lambda r:r['cases'][3]['keyboard_files']['/etc/arctic/mango/keyboard.conf'].update(sha256='d'*64),
                   lambda r:r['cases'][4]['visible']['layers'].append(copy.deepcopy(r['cases'][4]['visible']['layers'][0])),
                   lambda r:r['cases'][4]['disruption']['unavailable'].update(installer_layers=[{'name':'arctic-installer'}]),
                   lambda r:r['cases'][5]['disruption']['unavailable']['visible']['window'].update(screen='Virtual-1'),
                   lambda r:r['cleanup'].update(engine_retained=False),lambda r:r['security'].update(selinux='Permissive'),
                   lambda r:r['baseline']['identities']['listener'].update(serving_pid=999),
                   lambda r:r['cases'][0]['engine']['hello'].update(mock=0),
                   lambda r:r['cases'][1]['identities']['daemon'].update(uid=False)]
        for mutate in mutations:
            report,state,files,media,serial=fixture();mutate(report)
            with self.assertRaises(RuntimeError):C.validate_report(report,state['context'],files,lambda name:media['installer/'+name],report['baseline']['packaged_sources'])

    def test_hash_bound_physical_pixels_are_replayed(self):
        report,state,files,media,serial=fixture()
        image=Image.new('RGB',(1280,720),(0,0,0));stream=io.BytesIO();image.save(stream,format='PNG');data=stream.getvalue()
        cap=report['baseline']['capture'];cap.update(bytes=len(data),sha256=C.digest(data));files['baseline.png']=dict(bytes=len(data),sha256=C.digest(data));media['installer/baseline.png']=data
        with self.assertRaises(RuntimeError):C.validate_report(report,state['context'],files,lambda name:media['installer/'+name],report['baseline']['packaged_sources'])

    def test_execution_rejects_empty_inputs_wrong_receipts_uid_console_and_hardware(self):
        mutations=[lambda s:s['host'].update(execution_inputs={}),lambda s:s['host']['host_transitions'].reverse(),
                   lambda s:s['host']['host_transitions'][3]['display'].update(qemu_pid=999),
                   lambda s:s['host']['host_transitions'][3]['display'].update(enabled_heads=[0,1]),
                   lambda s:s['host']['host_transitions'][4]['display'].update(bus_owner=':1.6'),
                   lambda s:s['host']['host_transitions'][0].update(request_sha256='0'*64),
                   lambda s:s['host']['console_authentication'].update(nonce='e'*32),
                   lambda s:s['host'].update(firmware='bios'),lambda s:s['host']['qemu_argv'].extend(['-nic','user']),
                   lambda s:s['host'].update(owned_private_bus_closed=False),lambda s:s['required_images'].pop('host/installer-vt-away-0.png'),
                   lambda s:s['required_images'].update({'installer/baseline.png':'0'*64}),
                   lambda s:s['host']['display_preparation'].update(bus_owner=':1.9')]
        for mutate in mutations:
            report,state,files,media,serial=fixture();mutate(state)
            with self.assertRaises(RuntimeError):C.validate_execution(state,state['image'],state['context']['execution_sha'],serial,media.__getitem__)

    def test_host_capture_replay_rejects_delayed_graphical_image_even_if_hash_updated(self):
        report,state,files,media,serial=fixture();path='host/installer-vt-away-0.png';data=media['installer/baseline.png'];media[path]=data
        state['required_images'][path]=C.digest(data);state['host']['host_transitions'][0]['capture'].update(bytes=len(data),sha256=C.digest(data))
        with self.assertRaises(RuntimeError):C.validate_execution(state,state['image'],state['context']['execution_sha'],serial,media.__getitem__)

    def test_generated_wrapper_hash_uses_exact_source_and_rejects_alternative(self):
        with tempfile.TemporaryDirectory() as root:
            tree=Path(root)
            for installed,source in C.PACKAGED_SOURCES.items():
                path=tree/source;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((HERE.parents[1]/source).read_bytes())
            hashes=C.packaged_source_hashes(tree);self.assertEqual(hashes,C.packaged_source_hashes(HERE.parents[1]))
            path=tree/'dotfiles/.local/bin/arctic-installer';path.parent.mkdir(parents=True);path.write_text('replacement')
            with self.assertRaises(RuntimeError):C.packaged_source_hashes(tree)


if __name__=='__main__':unittest.main()
