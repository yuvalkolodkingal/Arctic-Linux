"""Compose the exact existing observer with failure-only in-memory age sealing."""
import hashlib,json,os,types
from pathlib import Path
OLD_COMPOSITION='tools/final-bios-unit-record-install/composition.py'
OLD_MANIFEST='tools/final-bios-unit-record-install/execution-manifest.json'
SEAL='tools/private-record-seal-source/seal.py'
SCANNER='tools/bounded-complete-csi-source/scanner.py'
DIAGNOSTIC='tools/unit-record-observation-source/diagnostic.py'
SEAL_STAGE_UNKNOWN='private-seal-stage-unknown'
SEAL_STAGE_LABELS=frozenset({
    'private-seal-stage-finite-contract','private-seal-stage-traceback-binding',
    'private-seal-stage-scanner-frame','private-seal-stage-match-locals',
    'private-seal-stage-unit-family','private-seal-stage-source-replay',
    'private-seal-stage-record-boundary','private-seal-stage-record-roundtrip',
    'private-seal-stage-encryption',SEAL_STAGE_UNKNOWN})
SEAL_DIAGNOSTIC_PREFIX='ARCTIC-PRIVATE-SEAL-DIAGNOSTIC='
def report_seal_failure(sealer,error):
    label=SEAL_STAGE_UNKNOWN
    try:
        candidate=sealer.closed_failure_label(error)
        if type(candidate)is str and candidate in SEAL_STAGE_LABELS:label=candidate
    except BaseException:pass
    print(SEAL_DIAGNOSTIC_PREFIX+label,flush=True)
    return label
def require(value):
    if not value:raise RuntimeError('Private review composition differs')
def load(raw,path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module
def build(root,value,source_loader,new_guard,age_binary,sealed_out):
    root=Path(root);pins=value['execution_files'];binding=value['private_review_binding']
    raw_composition=source_loader(root/OLD_COMPOSITION,pins[OLD_COMPOSITION])
    old=load(raw_composition,root/OLD_COMPOSITION,'private_review_prior_composition')
    old_value=json.loads(source_loader(root/OLD_MANIFEST,pins[OLD_MANIFEST]))
    wrapped,observed,exact,state=old.build(root,old_value,source_loader,
        lambda projected,source,inputs=None:new_guard(value,source,inputs))
    raw_seal=source_loader(root/SEAL,pins[SEAL])
    require(hashlib.sha256(raw_seal).hexdigest()==binding['seal_sha256'])
    sealer=load(raw_seal,root/SEAL,'private_record_sealer')
    scanner_raw=source_loader(root/SCANNER,pins[SCANNER])
    diagnostic_raw=source_loader(root/DIAGNOSTIC,pins[DIAGNOSTIC])
    def private_review():
        try:
            return wrapped()
        except BaseException as error:
            try:
                sealer.seal_failure(error,state['strict'],scanner_raw,diagnostic_raw,root/DIAGNOSTIC,
                    age_binary,binding['recipient'],binding['recipient_sha256'],sealed_out,{
                        'execution_commit':os.environ['GITHUB_SHA'],
                        'source_commit':binding['source_commit'],
                        'image_sha256':value['image']['sha256']})
            except BaseException as sealing_error:
                report_seal_failure(sealer,sealing_error)
            raise
    return private_review,wrapped,observed,exact,state
