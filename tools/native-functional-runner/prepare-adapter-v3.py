#!/usr/bin/env python3
"""Deterministic audit-only standalone adapter; replace only the native main."""
import ast
import hashlib
import json
from pathlib import Path

NATIVE_SHA = '2bf89d4771baad6c948c15d38379393c8c57488ff497a2c68e398f360b2d0489'
HERE = Path(__file__).resolve().parent
LAUNCHER_SHA = hashlib.sha256((HERE/'native-launcher-v3.py').read_bytes()).hexdigest()
MAIN = r'''def main():
    # This sole replaced entrypoint binds the original harness location/stage.
    import base64
    import importlib.util
    import sys
    import traceback
    import zlib
    stage = sys.argv[1] if len(sys.argv) == 2 else 'invalid'
    native_source_sha = '__NATIVE_SHA__'
    original_roots = set(Path('/tmp').glob('arctic-native-smoke-*'))
    report, error, export_complete = None, None, False
    roots = []
    expected_uid = None
    begin = dict(stage=stage, native_source_sha256=native_source_sha,
                 checker_sha256=digest(Path(__file__)), release_acceptance=False)
    print('ARCTIC-NATIVE-RUNNER-BEGIN '+json.dumps(begin,sort_keys=True),flush=True)
    try:
        require(Path(__file__).resolve() == Path('/run/t/guest-check.py'),
                'requires the reviewed read-only /run/t guest-check.py bundle')
        require(len(sys.argv) == 2 and stage in ('live','installed'), 'requires exactly one explicit live/installed stage')
        guest_guard(stage,True)
        helper = Path('/run/t/native-launcher.py')
        require(hashlib.sha256(helper.read_bytes()).hexdigest() == '__LAUNCHER_SHA__', 'owned launcher helper changed')
        spec = importlib.util.spec_from_file_location('arctic_native_launcher_library',str(helper))
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        launcher_proof = launcher.verify_barrier(stage,'__LAUNCHER_SHA__')
        prefix = discover_desktop()
        expected_uid = pwd.getpwnam(prefix[2]).pw_uid
        require(launcher_proof['foot']['uid'] == expected_uid, 'launcher and measured desktop UIDs differ')
        provenance = dict(stage=stage, native_source_sha256=native_source_sha,
                          checker_sha256=begin['checker_sha256'],
                          boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                          cmdline=Path('/proc/cmdline').read_text().strip(),
                          desktop_uid=expected_uid, launcher=launcher_proof, release_acceptance=False)
        session = next(item[15:] for item in prefix if item.startswith('XDG_SESSION_ID='))
        kind = execute(['loginctl','show-session',session,'-p','Type','--value'])[1]
        active = execute(['loginctl','show-session',session,'-p','Active','--value'])[1]
        require(kind.strip() == 'wayland' and active.strip() == 'yes', 'actual desktop session is not active Wayland')
        provenance['active_desktop_session'] = session
        cards = Path('/proc/asound/cards').read_text()
        require(re.search(r'^\s*\d+\s+\[[^]]+\]',cards,re.M), 'test virtual audio card is unavailable')
        provenance['virtual_audio_cards'] = cards
        if stage == 'installed':
            source = execute(['findmnt','-n','-o','SOURCE','/'])[1]
            device = source.split('[',1)[0]
            require(device.startswith('/dev/mapper/'), 'installed root is not a mapped encrypted volume')
            encryption = execute(['cryptsetup','status',Path(device).name])[1]
            require(re.search(r'^\s*type:\s+LUKS2\s*$',encryption,re.M), 'installed root is not active LUKS2')
            provenance['encrypted_root'] = dict(source=source,device=device,status=encryption,type='LUKS2')
        print('ARCTIC-NATIVE-PROVENANCE '+json.dumps(provenance,sort_keys=True),flush=True)
        report = run_checks(prefix,stage,disposable_guest=True)
        require(report['schema'] == SCHEMA and report['stage'] == stage
                and report['release_acceptance'] is False, 'native report identity differs')
        require(report['status'] == 'limited-smoke-passed', 'native functional gate or cleanup failed')
    except BaseException as exc:
        error = type(exc).__name__+': '+str(exc)
        traceback.print_exc()
    finally:
        # Export only owned guest JSON/screens/logs/text, even after failed gates.
        # Raw serial is retained if bounded export itself fails or is interrupted.
        try:
            if report is not None:
                roots = [Path(report['evidence_root'])]
            elif expected_uid is not None:
                roots = sorted(set(Path('/tmp').glob('arctic-native-smoke-*'))-original_roots)
            require(len(roots) <= 1, 'ambiguous partial native evidence roots')
            entries, encoded = [], []
            total = 0
            for root in roots:
                require(root.parent == Path('/tmp') and root.name.startswith('arctic-native-smoke-')
                        and not root.is_symlink() and root.resolve() == root
                        and root.is_dir() and root.stat().st_uid == expected_uid,
                        'unproved native evidence root')
                for path in sorted(root.rglob('*')):
                    require(not path.is_symlink(), 'native evidence tree contains a symlink')
                    if not path.is_file() or path.suffix.lower() not in ('.json','.png','.log','.txt','.tsv'):
                        continue
                    relative = path.relative_to(root).as_posix()
                    require(len(entries) < 128 and path.stat().st_size <= 4*1024*1024,
                            'native evidence file count/size exceeded bound')
                    data = path.read_bytes()
                    total += len(data)
                    require(total <= 16*1024*1024, 'native evidence total exceeded bound')
                    compressed = zlib.compress(data,9)
                    chunks = [compressed[i:i+24576] for i in range(0,len(compressed),24576)]
                    entry = dict(path=relative,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                                 compressed_bytes=len(compressed),chunks=len(chunks),encoding='zlib+base64')
                    entries.append(entry)
                    encoded.append((entry,chunks))
            for entry,chunks in encoded:
                for index,chunk in enumerate(chunks):
                    print('ARCTIC-NATIVE-EVIDENCE-CHUNK '+json.dumps(dict(path=entry['path'],index=index,
                          data=base64.b64encode(chunk).decode()),sort_keys=True),flush=True)
            print('ARCTIC-NATIVE-EVIDENCE-MANIFEST '+json.dumps(dict(schema='arctic-native-evidence-v1',
                  stage=stage,files=entries,bytes=total,evidence_root=str(roots[0]) if roots else None),sort_keys=True),flush=True)
            export_complete = True
        except BaseException as exc:
            export_error = type(exc).__name__+': '+str(exc)
            error = (error+'; ' if error else '')+'evidence export: '+export_error
            traceback.print_exc()
        passed = error is None and export_complete and report is not None and report['status']=='limited-smoke-passed'
        print('ARCTIC-NATIVE-RUNNER-END '+json.dumps(dict(stage=stage,status='passed' if passed else 'failed',
              error=error,evidence_export_complete=export_complete,release_acceptance=False),sort_keys=True),flush=True)
    return 0 if passed else 1'''.replace('__NATIVE_SHA__',NATIVE_SHA).replace('__LAUNCHER_SHA__',LAUNCHER_SHA)


def build(source, target):
    original=source.read_text()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == NATIVE_SHA, 'native source is not the frozen reviewed version'
    tree=ast.parse(original)
    main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    lines=original.splitlines(keepends=True)
    start,end=sum(map(len,lines[:main.lineno-1])),sum(map(len,lines[:main.end_lineno]))
    adapter=original[:start]+MAIN+'\n'+original[end:]
    revised=ast.parse(adapter)
    retained=[]
    byname={node.name:node for node in revised.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='main':
            other=byname[node.name]
            assert ast.dump(node,include_attributes=False)==ast.dump(other,include_attributes=False)
            segment=ast.get_source_segment(original,node)
            assert segment==ast.get_source_segment(adapter,other)
            retained.append(dict(name=node.name,sha256=hashlib.sha256(segment.encode()).hexdigest()))
    assert original[:start]==adapter[:start] and original[end:]==adapter[start+len(MAIN)+1:]
    compile(adapter,str(target),'exec')
    target.write_text(adapter)
    parity=dict(native_source_sha256=NATIVE_SHA,adapter_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                sole_changed_top_level_function='main',all_other_top_level_bytes_and_ast_equal=True,
                all_other_source_bytes_equal=True,retained=retained)
    return parity


if __name__=='__main__':
    source=HERE/'native_smoke.py'
    # The owner file is read only. The target lives solely in this audit bundle.
    result=build(source,HERE/'guest-check-native-v3.py')
    (HERE/'adapter-parity-v3.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
