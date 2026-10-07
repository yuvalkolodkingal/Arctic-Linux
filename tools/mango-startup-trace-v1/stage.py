"""Build and read back the exact additional test CD; never launch a VM."""
import sys
sys.dont_write_bytecode=True
import hashlib,importlib.util,json,os,stat,subprocess
from pathlib import Path

def require(v,m):
    if not v:raise RuntimeError(m)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
    s=importlib.util.spec_from_file_location('exact_trace_credentials',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def entries(normal,trace):
    c=json.loads((trace/'adapter-contract.json').read_text())
    require(c['schema']=='arctic-one-mango-adapter-v1' and c['CD_exact_member_count']==13,'CD contract differs')
    result=[]
    for group,base in ((c['normal_cd_files'],normal),(c['trace_cd_files'],trace)):
        for row in group:
            p=base/row['cd_name']
            require(p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and digest(p)==row['sha256'],'Staged source differs: '+row['cd_name'])
            require(row['mode'] in (0o644,0o755),'CD source mode differs')
            result.append((row,p))
    require(len(result)==13 and len({x[0]['cd_name'] for x in result})==13,'CD exact member count/name differs')
    return result
def verify_tree(tree,expected):
    require(tree.is_dir() and not tree.is_symlink(),'CD tree missing')
    require(set(p.name for p in tree.iterdir())=={row['cd_name'] for row,_ in expected},'CD readback contains missing/extra members')
    for row,_ in expected:
        p=tree/row['cd_name'];info=p.lstat()
        require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==row['mode'] and info.st_size==row['bytes'] and digest(p)==row['sha256'],'CD readback hash/type/mode differs: '+row['cd_name'])
def build(normal,trace,stage,cd,readback,ledger):
    expected=entries(normal,trace)
    for p in (stage,cd,readback,ledger):require(not p.exists() and not p.is_symlink(),'Owned staging output must be unused')
    stage.mkdir(mode=0o700)
    for row,p in expected:
        q=stage/row['cd_name']
        with q.open('xb') as f:f.write(p.read_bytes())
        q.chmod(row['mode'])
    verify_tree(stage,expected)
    subprocess.run(['xorriso','-as','mkisofs','-quiet','-V','ARCTICSAFE','-J','-R','-G',str(normal/'bootstrap-safe-v1.sh'),'-o',str(cd),str(stage)],check=True,timeout=45,stdout=subprocess.DEVNULL)
    require(cd.is_file() and not cd.is_symlink() and 0<cd.stat().st_size<=16777216 and cd.stat().st_size%2048==0,'Generated CD size/type differs')
    subprocess.run(['xorriso','-osirrox','on','-indev',str(cd),'-extract','/',str(readback)],check=True,timeout=45,stdout=subprocess.DEVNULL)
    verify_tree(readback,expected)
    value=dict(schema='arctic-trace-CD-v1',members=[row for row,_ in expected],bytes=cd.stat().st_size,sha256=digest(cd),label='ARCTICSAFE',readback_exact=True)
    with ledger.open('x') as f:json.dump(value,f,sort_keys=True);f.write('\n')
    credentials=load(trace/'credential-units.py').qemu_args(value['sha256'],value['bytes'])
    require(len(credentials)==4 and credentials[0]==credentials[2]=='-smbios','Exact two unit credentials required')
    return credentials
if __name__=='__main__':
    require(len(sys.argv)==7,'Exact six staging paths required')
    print(json.dumps(build(*(Path(p) for p in sys.argv[1:]))))
