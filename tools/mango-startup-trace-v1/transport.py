"""Existing ARCTIC-RENDER framing/caps, one replacement post-34 arm only."""
import base64,hashlib,json,os,re,zlib
MAX_FRAME=262144
MAX_FILE=4194304
MAX_TOTAL=12582912
PREFIX='ARCTIC-RENDER-'

def require(v,m):
    if not v:raise RuntimeError(m)
def sha(v):return hashlib.sha256(v).hexdigest()
def wire(kind,value):
    raw=(PREFIX+kind+' '+json.dumps(value,sort_keys=True)+'\n').encode()
    require(len(raw)<=MAX_FRAME,'Existing serial marker cap exceeded')
    return raw

def export(report,bodies):
    require(type(report) is dict and report.get('startup_perturbation') is True and report.get('release_acceptance') is False and report.get('safe_visual_gate')=='OPEN','Invalid trace meaning')
    # Validate every full body/reference before any success frames. The report
    # is a small receipt; full semantic bodies are preserved without trimming.
    data=dict(bodies);data['report.json']=json.dumps(report,sort_keys=True).encode()+b'\n'
    require(len(data)<=12 and sum(len(v) for v in data.values())<=MAX_TOTAL and all(type(v) is bytes and 0<len(v)<=MAX_FILE for v in data.values()),'Existing body/total cap exceeded')
    require(len(wire('REPORT',report))<=MAX_FRAME,'Existing report cap exceeded')
    frames=[wire('BEGIN',dict(schema='arctic-one-mango-trace-v1',release_acceptance=False,startup_perturbation=True))]
    manifest=[];chunks=[]
    for name,raw in sorted(data.items()):
        require(re.fullmatch('[a-z0-9][a-z0-9.-]{0,63}',name) is not None,'Unsafe body name')
        packed=zlib.compress(raw);pieces=[packed[i:i+49152] for i in range(0,len(packed),49152)]
        manifest.append(dict(path=name,bytes=len(raw),sha256=sha(raw),compressed_bytes=len(packed),chunks=len(pieces)))
        chunks.extend(wire('CHUNK',dict(path=name,index=i,data=base64.b64encode(v).decode())) for i,v in enumerate(pieces))
    status='collected' if report.get('status')=='diagnostic-collected-visual-open' else 'failed'
    require(status=='collected' or str(report.get('status','')).startswith('failed-'),'Unknown export completion meaning')
    frames+=[wire('REPORT',report),wire('MANIFEST',dict(schema='arctic-render-files-v1',encoding='zlib+base64',files=manifest,bytes=sum(len(v) for v in data.values()))),*chunks,wire('END',dict(status=status,release_acceptance=False,startup_perturbation=True,safe_visual_gate='OPEN'))]
    return frames

def send(frames):
    # FD1 is inherited from the owned root service's exact serial redirection;
    # all explicitly acquired diagnostic FDs/target resources must already have
    # closed. No new serial device FD or alternative channel is opened here.
    for raw in frames:
        offset=0
        while offset<len(raw):
            n=os.write(1,raw[offset:]);require(n>0,'Serial inherited-FD write failed');offset+=n

def strict_json(raw):
    def object_pairs(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=object_pairs,parse_constant=lambda v:(_ for _ in ()).throw(RuntimeError('Nonfinite JSON value')))

def decode(text):
    require(type(text) is str and len(text.encode())<=33554432,'Existing finite serial bound exceeded')
    rows=[]
    for line in text.splitlines(keepends=True):
        if not line.startswith(PREFIX):continue
        require(line.endswith('\n') and len(line.encode())<=MAX_FRAME,'Incomplete/overbound final marker')
        marker,raw=line[:-1].split(' ',1);kind=marker[len(PREFIX):]
        require(kind in {'BEGIN','REPORT','MANIFEST','CHUNK','END'},'Unknown completed marker')
        rows.append((kind,strict_json(raw)))
    require(len(rows)>=5 and [kind for kind,_ in rows[:3]]==['BEGIN','REPORT','MANIFEST'] and rows[-1][0]=='END' and all(kind=='CHUNK' for kind,_ in rows[3:-1]),'Missing/duplicate/order-invalid completed protocol')
    begin,report,manifest,end=rows[0][1],rows[1][1],rows[2][1],rows[-1][1]
    require(begin=={'schema':'arctic-one-mango-trace-v1','release_acceptance':False,'startup_perturbation':True} and type(begin['release_acceptance']) is bool and type(begin['startup_perturbation']) is bool,'Wrong BEGIN meaning/types')
    require(end=={'status':'collected','release_acceptance':False,'startup_perturbation':True,'safe_visual_gate':'OPEN'} and type(end['release_acceptance']) is bool and type(end['startup_perturbation']) is bool,'Failed/contradictory END')
    require(type(manifest) is dict and set(manifest)=={'schema','encoding','files','bytes'} and manifest['schema']=='arctic-render-files-v1' and manifest['encoding']=='zlib+base64' and type(manifest['bytes']) is int and 0<manifest['bytes']<=MAX_TOTAL and type(manifest['files']) is list and 1<=len(manifest['files'])<=12,'Typed manifest invalid')
    files={};chunk_rows=rows[3:-1];index=0;total=0
    for item in manifest['files']:
        require(type(item) is dict and set(item)=={'path','bytes','sha256','compressed_bytes','chunks'},'Invalid body entry shape')
        name=item['path'];require(type(name) is str and re.fullmatch('[a-z0-9][a-z0-9.-]{0,63}',name) is not None and name not in files,'Duplicate/unsafe body name')
        require(all(type(item[k]) is int and item[k]>0 for k in ('bytes','compressed_bytes','chunks')) and item['bytes']<=MAX_FILE and item['compressed_bytes']<=MAX_FILE+65536 and item['chunks']<=128 and re.fullmatch('[0-9a-f]{64}',item['sha256']) is not None,'Untyped/overbound body')
        packed=bytearray()
        for number in range(item['chunks']):
            require(index<len(chunk_rows),'Missing chunk');row=chunk_rows[index][1];index+=1
            require(type(row) is dict and set(row)=={'path','index','data'} and row['path']==name and type(row['index']) is int and row['index']==number and type(row['data']) is str,'Chunk identity/order/types differ')
            piece=base64.b64decode(row['data'],validate=True);require(0<len(piece)<=49152,'Chunk bound');packed.extend(piece)
            require(len(packed)<=item['compressed_bytes'],'Compressed body exceeded declared bound')
        require(len(packed)==item['compressed_bytes'],'Compressed body truncated')
        d=zlib.decompressobj();raw=d.decompress(bytes(packed),item['bytes']+1)
        require(len(raw)==item['bytes'] and d.eof and not d.unused_data and not d.unconsumed_tail and sha(raw)==item['sha256'],'Body hash/size/compression differs')
        files[name]=raw;total+=len(raw)
    require(index==len(chunk_rows) and total==manifest['bytes'],'Extra/missing chunks or total')
    require('report.json' in files and strict_json(files['report.json'])==report,'Reserved report body differs')
    require(report.get('schema')=='arctic-one-mango-trace-v1' and report.get('status')=='diagnostic-collected-visual-open' and report.get('startup_perturbation') is True and report.get('normal_session_fidelity') is False and report.get('complete_chain') is False and report.get('release_acceptance') is False and report.get('safe_visual_gate')=='OPEN' and report.get('active_scanout_pixels')=='UNAVAILABLE','Trace cannot claim normal/visual/startup/pixels qualification')
    return report,files

def validate_evidence(report,files):
    required={'report.json','terminal.json','log-report.json','stderr.raw','line-proofs.json','owned-state.json','journal-before.log','journal-after.log'}
    require(set(files)==required,'Missing/extra trace semantic bodies')
    require(report.get('candidate_source')=='fe4742c8b9414c45f0bcbb0a4191f116383c60d1' and report.get('intended_iso_sha256')=='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718' and type(report.get('boot_id')) is str and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',report['boot_id']) is not None,'Candidate/boot provenance differs')
    terminal=strict_json(files['terminal.json']);full=strict_json(files['log-report.json']);state=strict_json(files['owned-state.json']);lines=strict_json(files['line-proofs.json'])
    require(terminal==report['native_report'] and terminal.get('all_owned_FDs_closed') is True and terminal.get('controlled_stop') is True and terminal.get('normal_session_fidelity') is False and terminal.get('complete_chain') is False,'Terminal receipt substituted/claim differs')
    for key,value in full.items():
        if key=='rows':continue
        require(key in terminal and json.dumps(value,sort_keys=True)==json.dumps(terminal[key],sort_keys=True),'Duplicated terminal/full body value or type differs')
    ref=terminal['sender_ranges_body'];require(ref=={'path':'log-report.json','bytes':len(files['log-report.json']),'sha256':sha(files['log-report.json']),'rows':len(full['rows'])} and type(ref['bytes']) is int and type(ref['rows']) is int,'Full semantic range reference differs')
    pid=full['child_pid'];require(type(pid) is int and pid>0 and full['status']=='owned-trace-collected' and full['controlled_stop'] is True and full['cleanup']=='owned-child-reaped' and full['unowned_inherited_writers_signalled'] is False and full['future_inherited_writer_tail_qualified'] is False,'Owned native lifecycle meaning differs')
    image=full['native_identity'];logger=report['logger_identity']
    require(all(type(image[k]) is int and image[k]>0 for k in ('pid','ppid','pgrp','session','start_ticks')) and type(image['uid']) is int and image['uid']==1000 and image['pid']==pid and image['ppid']==logger['pid'] and image['cmdline']==['mango','-d'] and image['executable_sha256']=='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866' and image['executable']=='/usr/bin/mango','Actual selected native image/process binding differs')
    require(type(logger['pid']) is int and logger['pid']>0 and logger['pid']!=pid and type(logger['start_ticks']) is int and logger['start_ticks']>0 and type(logger['uid']) is int and logger['uid']==1000 and logger['executable_sha256']=='0d64bd6d66d68dac91cdadafc46e22d4f09f22bdc997aaae870f42865b024a3e' and logger['selected_helper_parent']['executable_sha256']=='93ab003b0453179eb1f0e6a7a51a20ee322af4992300d095403c5f728b7a68e4' and all(image[k]==logger[k] for k in ('session','pgrp','cwd','stdin','stdout')),'Logger/helper/inherited boundary differs')
    require(full.get('owned_pidfd_identity')=={'pid':pid,'kernel_fdinfo_bound':True,'signal0_permission_checked':True} and type(full['owned_pidfd_identity']['pid']) is int and type(full['owned_pidfd_identity']['kernel_fdinfo_bound']) is bool and type(full['owned_pidfd_identity']['signal0_permission_checked']) is bool and type(full.get('owned_child_start_ticks')) is int and full['owned_child_start_ticks']==image['start_ticks'] and full.get('expected_sender_uid_gid')=={'uid':1000,'gid':1000} and all(type(v) is int for v in full['expected_sender_uid_gid'].values()),'Owned pidfd/start/UID/GID binding differs')
    raw=files['stderr.raw'];require(len(raw)==full['raw_bytes'] and sha(raw)==full['raw_sha256'] and len(raw)==terminal['raw_bytes'] and sha(raw)==terminal['raw_sha256'],'Full raw source log differs')
    rows=full['rows'];require(type(rows) is list and len(rows)<=8192 and all(type(full[k]) is int and full[k]>0 for k in ('start_monotonic_ns','end_monotonic_ns')) and full['end_monotonic_ns']>=full['start_monotonic_ns'],'Invalid native timing/rows')
    offset=0;prior=full['start_monotonic_ns']
    for row in rows:
        require(type(row) is dict and set(row)=={'pid','uid','gid','begin','end','received_monotonic_ns','sha256','origin'} and all(type(row[k]) is int and row[k]>=0 for k in ('pid','uid','gid','begin','end','received_monotonic_ns')) and row['pid']>0 and row['begin']==offset<row['end']<=len(raw) and prior<=row['received_monotonic_ns']<=full['end_monotonic_ns'] and sha(raw[row['begin']:row['end']])==row['sha256'],'Typed sender range/hash/time coverage differs')
        require(row['origin']==('owned-launch-process' if row['pid']==pid else 'other-sender-unqualified') and (row['pid']!=pid or (row['uid']==1000 and row['gid']==1000)),'Kernel sender attribution differs')
        offset=row['end'];prior=row['received_monotonic_ns']
    require(offset==len(raw),'Sender ranges omit raw bytes')
    expected=[];offset=0
    for line in raw.splitlines(keepends=True):
        stop=offset+len(line);touch=[r for r in rows if r['begin']<stop and r['end']>offset];owned=bool(touch) and all(r['pid']==pid and r['uid']==1000 and r['gid']==1000 for r in touch)
        expected.append(dict(begin=offset,end=stop,complete=line.endswith(b'\n'),authenticated_writer=owned,status='owned-complete-line' if owned and line.endswith(b'\n') else 'ambiguous-or-incomplete',sha256=sha(line)));offset=stop
    require(lines==expected and len(lines)<=8192,'Complete direct-writer line proof differs')
    for key,name in [('security_before','journal-before.log'),('security_after','journal-after.log')]:
        security=report[key];journal=files[name];records=[strict_json(line) for line in journal.splitlines() if line]
        require(records and all(type(v) is dict and v.get('_BOOT_ID')==report['boot_id'].replace('-','') and 'MESSAGE' in v for v in records),'Not whole same-boot raw journal')
        denied=[v for v in records if v.get('_TRANSPORT') in ('kernel','audit') and re.search(r'\bavc:\s*denied\b',str(v['MESSAGE']),re.I)]
        fields=dict(v.split(None,1) for v in security['audit_status'].splitlines() if len(v.split(None,1))==2)
        require(security.get('qualified') is True and security['selinux']=='Enforcing' and fields.get('enabled') in ('1','2') and fields.get('lost')=='0' and security.get('full_unfiltered') is True and not denied and security['avc_records']==[] and all(type(security[k]) is int for k in ('journal_total_bytes','journal_retained_bytes','current_boot_journal_records')) and security['journal_total_bytes']==security['journal_retained_bytes']==len(journal) and security['current_boot_journal_records']==len(records) and security['journal_retained_sha256']==sha(journal),'Security/full-journal evidence contradicts gate')
    require(report.get('root_cleanup')=={'owned_runtime_config_removed':True,'owned_generated_files_removed':True,'owned_readonly_CD_unmounted':True,'underlying_owned_mount_directory_removed':True,'root_owned_descriptors_closed':True,'normal_SDDM_cache_restored':False,'normal_target_replacement':False} and all(type(v) is bool for v in report['root_cleanup'].values()),'Root cleanup/normal-session scope differs')
    require(state.get('startup_perturbation') is True and state.get('complete_chain') is False and state.get('normal_fidelity') is False and state.get('safe_visual_gate')=='OPEN','Owned target state scope differs')
    return dict(status='one-target-perturbed-trace-collected',release_acceptance=False,safe_visual_gate='OPEN',normal_fidelity=False,renderer='requires-independent-authenticated-log-review',active_pixels='UNAVAILABLE')
