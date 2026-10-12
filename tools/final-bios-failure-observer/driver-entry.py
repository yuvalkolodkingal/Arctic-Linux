#!/usr/bin/env python3
"""Container-only exact embedded Source driver entry; no original input changes."""
import hashlib,json,os,pathlib,re,sys
import observer
sys.path.insert(0,'/arctic-lib')
import vmtest

def main():
    manifest=json.loads(pathlib.Path(__file__).with_name('observer-manifest.json').read_bytes())
    raw=os.environ['DRIVER'].encode();token=os.environ.get('ARCTIC_DICTATION_HOST_TOKEN','')
    if not re.fullmatch('[0-9a-f]{32}',token):raise ValueError('Owned finite channel absent')
    def emit(cause):
        value={'schema':'arctic-bios-inner-source-cause-v1','nonce':token,'cause':cause,'release_acceptance':False}
        text=json.dumps(value,sort_keys=True,separators=(',',':'))
        if len(text.encode())<=8192:print('ARCTIC-BIOS-INNER-CAUSE '+text,flush=True)
    namespace={'__name__':'__main__','__builtins__':__builtins__}
    return observer.run_original_driver(raw,namespace,vmtest,emit,manifest['driver_sha256'],
        pathlib.Path(vmtest.__file__).read_bytes(),manifest['original_execution_files']['tools/lib/vmtest.py'])

if __name__=='__main__':main()
