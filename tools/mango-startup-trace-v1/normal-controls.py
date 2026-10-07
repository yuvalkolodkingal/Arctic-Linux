"""Run unchanged normal assertions on their exact pinned normal snapshot."""
import sys
sys.dont_write_bytecode=True
import hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
FIXTURES={
 'normal-test-iso.sh':'978b2454e13434947b9245cfe21bc8f1c80e8f00c22857c284d228e9cf45bbbe',
 'normal-iso.yml':'e4a78f10f7faccfecbb93d07e26f8e47cd19f0bd2bf45ba5ee1d9e6eba2d5326',
 'base-test-iso.sh':'9beb039d69dad07176e00a8e890c7e099631ff68175235a83be8b6394f63434f',
 'base-iso.yml':'5b0c1493333288acb43d7baaecb19ae40c662189d9ff0a591ce183a04871d2dd',
 'vm-only-recovery-v2.py':'0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'}
def require(v,m):
    if not v:raise RuntimeError(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(root,here=HERE):
    require(not root.exists(),'Normal assertion snapshot must be unused')
    source=here/'normal-control-sources'
    require(set(p.name for p in source.iterdir())==set(FIXTURES),'Normal control fixture set differs')
    for name,h in FIXTURES.items():
        p=source/name;require(p.is_file() and not p.is_symlink() and sha(p)==h,'Pinned normal/base fixture differs: '+name)
    normal=json.loads((here/'normal-base-pins.json').read_text())
    for rel,h in normal.items():
        old=here.parents[1]/rel
        if rel not in ('tools/test-iso.sh','.github/workflows/iso.yml'):require(old.is_file() and not old.is_symlink() and sha(old)==h,'Normal assertion source changed: '+rel)
        new=root/rel;new.parent.mkdir(parents=True,exist_ok=True)
        if rel=='tools/test-iso.sh':shutil.copyfile(source/'normal-test-iso.sh',new)
        elif rel=='.github/workflows/iso.yml':shutil.copyfile(source/'normal-iso.yml',new)
        else:shutil.copyfile(old,new)
        new.chmod(0o755 if rel=='tools/test-iso.sh' else 0o644)
        require(sha(new)==h,'Normal assertion snapshot body differs: '+rel)
    bundle=root/'tools/safe-visual-diagnostic'
    for name in ('base-test-iso.sh','base-iso.yml'):shutil.copyfile(source/name,bundle/name)
    frozen=root/'tools/same-iso-recovery';frozen.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source/'vm-only-recovery-v2.py',frozen/'vm-only-recovery-v2.py')
    return bundle
def run():
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};env['PYTHONDONTWRITEBYTECODE']='1'
    with tempfile.TemporaryDirectory(prefix='arctic-normal-assertions-') as td:
        root=Path(td)/'snapshot';bundle=snapshot(root)
        for name in ('test_safe_v1.py','test_render_v1.py'):
            subprocess.run([sys.executable,'-B','-Werror::ResourceWarning',str(bundle/name)],cwd=root,env=env,check=True,timeout=180)
if __name__=='__main__':run()
