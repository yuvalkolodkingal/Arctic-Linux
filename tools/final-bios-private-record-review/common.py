#!/usr/bin/env python3
"""Disabled admission for encrypted private review of one exact rejected record."""
import hashlib,importlib.util,re,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE='cf4ef587746f01b4d03dc7ef5ef404b335e41be4'
BRANCH='codex/final-bios-private-record-review-20261012'
MARKER='.github/final-bios-private-record-review-20261012.activate'
WORKFLOW='Final exact-image BIOS encrypted private record review'
SOURCE_COMMIT='32735de7e41d0b1145df453ebaee43742e34aa2f'
SOURCE_TREE='c24b9505debc97e2bed5ddffdd722bd235e069ca'
ADDITIONS={
 '.github/workflows/final-bios-private-record-review-20261012.yml',
 *{'tools/private-record-seal-source/'+n for n in ('README.md','seal.py','source-manifest.json','test_source.py')},
 *{'tools/final-bios-private-record-review/'+n for n in
   ('README.md','common.py','composition.py','execution-manifest.json','run.py','test_composition.py')}}
OLD_PATH=ROOT/'tools/final-bios-unit-record-install/common.py'
_spec=importlib.util.spec_from_file_location('private_review_prior_common',OLD_PATH)
_old=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_old)
OLD_FILES=frozenset(_old.FILES)
DEPENDENCY_FILES={'tools/final-bios-unit-record-install/execution-manifest.json'}
FILES=set(OLD_FILES)|DEPENDENCY_FILES|(ADDITIONS-{'tools/final-bios-private-record-review/execution-manifest.json'})
require=_old.require;strict_json=_old.strict_json;regular=_old.regular;digest_file=_old.digest_file
load=_old.load;git=_old.git;exclusive=_old.exclusive
AGE={
 'version':'v1.2.1',
 'archive_url':'https://github.com/FiloSottile/age/releases/download/v1.2.1/age-v1.2.1-linux-amd64.tar.gz',
 'archive_bytes':5194720,'archive_sha256':'7df45a6cc87d4da11cc03a539a7470c15b1041ab2b396af088fe9990f7c79d50',
 'proof_url':'https://github.com/FiloSottile/age/releases/download/v1.2.1/age-v1.2.1-linux-amd64.tar.gz.proof',
 'proof_bytes':1544,'proof_sha256':'55b941732d9fc88b0db9f954f2de2bb5a8bacb6479063b2cf5f244ffbb9b3f3a',
 'binary_sha256':'aaec874ed903da4b02a9d503778ae05ee5005b2acc0f4a4cf10e5d0f17fd4384',
 'keygen_sha256':'50f849de5f05dc136de3dba623dd2b7e166e7badb9d4e3d83da88f2dbdb2d439'}
def manifest(value,operational=False):
    expected=set(_old.strict_json((_old.ROOT/'tools/final-bios-unit-record-install/execution-manifest.json').read_bytes()))
    require(type(value)is dict and set(value)==expected|{'private_review_binding'},
        'Private review manifest fields differ')
    projected={k:v for k,v in value.items()if k!='private_review_binding'}
    projected['schema']='arctic-final-bios-unit-record-install-v1'
    projected['execution_files']={k:v for k,v in value['execution_files'].items()if k in OLD_FILES}
    _old.manifest(projected,False)
    require(value['schema']=='arctic-final-bios-private-record-review-v1'
            and type(value['ready'])is bool and value['release_acceptance']is False
            and set(value['execution_files'])==FILES,'Private review execution inventory differs')
    binding=value['private_review_binding']
    require(type(binding)is dict and set(binding)=={
        'schema','source_commit','source_tree','source_manifest_sha256','seal_sha256',
        'recipient','recipient_sha256','recipient_generated_outside_github','age',
        'plaintext_file_created','plaintext_digest_exported','plaintext_length_exported',
        'privacy_gate_changed','runtime_gate_changed','scanner_changed','release_acceptance'},
        'Private review binding fields differ')
    require(binding['schema']=='arctic-private-record-review-binding-v1'
            and binding['source_commit']==SOURCE_COMMIT and binding['source_tree']==SOURCE_TREE
            and re.fullmatch('[0-9a-f]{64}',binding['source_manifest_sha256'])
            and re.fullmatch('[0-9a-f]{64}',binding['seal_sha256'])
            and binding['age']==AGE
            and all(binding[k]is False for k in ('plaintext_file_created','plaintext_digest_exported',
                'plaintext_length_exported','privacy_gate_changed','runtime_gate_changed',
                'scanner_changed','release_acceptance')),
        'Private review binding values differ')
    if value['ready']:
        recipient=binding['recipient'];recipient_sha=binding['recipient_sha256']
        require(binding['recipient_generated_outside_github']is True
                and type(recipient)is str and len(recipient)==62 and recipient.startswith('age1')
                and type(recipient_sha)is str and hashlib.sha256((recipient+'\n').encode()).hexdigest()==recipient_sha,
                'Private review recipient binding differs')
    else:
        require(binding['recipient']is None and binding['recipient_sha256']is None
                and binding['recipient_generated_outside_github']is False,
                'Disabled private review recipient must be absent')
    if operational:require(value['ready']is True,'Private review remains disabled pending local key generation')
    return value

_guard_globals=_old.guard.__globals__.copy()
_guard_globals.update(BASE=BASE,BRANCH=BRANCH,MARKER=MARKER,WORKFLOW=WORKFLOW,
    ADDITIONS=ADDITIONS,FILES=FILES,manifest=manifest)
_guard=types.FunctionType(_old.guard.__code__,_guard_globals,_old.guard.__name__,
                          _old.guard.__defaults__,_old.guard.__closure__)
def guard(value,source,inputs=None):
    return _guard(value,source,inputs)
