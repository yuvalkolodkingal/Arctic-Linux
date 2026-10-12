"""Affected current Source joins only; no ISO, guest, provider or inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import types
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def load(name,path):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec',dont_inherit=True,optimize=0),module.__dict__)
    return module


def captured(function,name):
    return function.__closure__[function.__code__.co_freevars.index(name)].cell_contents


class CurrentJoins(unittest.TestCase):
    def setUp(self):
        self.common=load('current_bios_common',HERE/'common.py')
        self.composition=load('current_bios_composition',HERE/'composition.py')
        self.value=json.loads((HERE/'execution-manifest.json').read_bytes())

    def test_typed_mapping_denies_before_any_source_loader(self):
        self.common.manifest(self.value)
        for key,item in self.value['unit_record_binding'].items():
            if type(item)is bool:
                wrong=json.loads(json.dumps(self.value));wrong['unit_record_binding'][key]=int(item)
                with self.subTest(key=key),self.assertRaises(RuntimeError):self.common.manifest(wrong)
        wrong=json.loads(json.dumps(self.value))
        wrong['unit_record_binding']['selected_observer_path']=wrong['unit_record_binding']['requested_observer_path']
        wrong['unit_record_binding']['selected_observer_sha256']=wrong['unit_record_binding']['requested_observer_sha256']
        with self.assertRaises(RuntimeError):self.common.manifest(wrong)

    def test_actual_build_keeps_main_and_selected_compiler_callback_ownership(self):
        reads=[]
        def source_loader(path,digest):
            raw=path.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            reads.append(path.relative_to(ROOT).as_posix());return raw
        def no_guard(*args,**kwargs):raise AssertionError('No operational guard in Source-only build')
        wrapped,observed,exact,state=self.composition.build(ROOT,self.value,source_loader,no_guard)
        self.assertIs(wrapped.__code__,exact.__code__)
        self.assertIs(observed.__code__,exact.__code__)
        self.assertEqual(set(reads),set(self.value['execution_files']))
        self.assertEqual(len(reads),132)
        self.assertEqual(state['mapping'],self.value['scanner_binding'])
        self.assertEqual(state['public_shape_mapping'],self.value['public_shape_binding'])
        self.assertEqual(state['unit_record_mapping'],self.value['unit_record_binding'])
        wrapper=observed.__globals__['original_evidence']
        binding=captured(wrapper,'configured')
        self.assertIs(type(binding),tuple);self.assertEqual(len(binding),11)
        module,owner,function,attributes,observer_owner,helper,helper_owner,scanners,common_owner,runs=binding[:-1]
        self.assertIs(function,module.diagnostic_unit_record_family)
        self.assertIs(function.__globals__,module.__dict__)
        self.assertTrue(owner.unchanged());self.assertTrue(observer_owner.unchanged())
        self.assertTrue(helper_owner.unchanged());self.assertTrue(common_owner.unchanged())
        self.assertTrue(all(held.unchanged()for held in runs))
        self.assertEqual(module.__file__,str(ROOT/self.value['unit_record_binding']['diagnostic_path']))
        self.assertIsNone(state['strict']['finite'])
        self.assertIs(state['runtime_cause_proven'],False);self.assertIs(state['release_acceptance'],False)
        self.assertIs(self.common.manifest(self.value,True),self.value)

    def test_selected_observer_drift_and_missing_dependency_deny(self):
        def loader(path,digest):
            raw=path.read_bytes()
            if path==ROOT/self.value['unit_record_binding']['selected_observer_path']:
                return raw+b'\n# foreign Source drift\n'
            return raw
        with self.assertRaises(RuntimeError):self.composition.build(ROOT,self.value,loader,lambda *args:None)
        wrong=json.loads(json.dumps(self.value))
        del wrong['execution_files'][wrong['unit_record_binding']['diagnostic_path']]
        with self.assertRaises(RuntimeError):self.common.manifest(wrong)


    def test_exact_source_receipt_image_and_no_admission_contract(self):
        binding=self.value['unit_record_binding']
        self.assertEqual(binding['source_commit'],'6b2cc6325519fca979c7c42fd80890caaa1c9b75')
        self.assertEqual(binding['source_tree'],'edeab87d75937c883342be28ce5ac534078b2e6c')
        receipt=json.loads((ROOT/binding['source_review_receipt_path']).read_text())
        self.assertEqual(receipt['source_commit'],binding['source_commit'])
        self.assertEqual(receipt['source_tree'],binding['source_tree'])
        self.assertEqual((receipt['tests_run'],receipt['tests_passed'],receipt['returncode']),(8,8,0))
        for role in ('selected_observer','diagnostic','source_manifest','source_review_receipt'):
            self.assertEqual(hashlib.sha256((ROOT/binding[role+'_path']).read_bytes()).hexdigest(),
                             binding[role+'_sha256'])
        for key in ('private_operand_exported','private_operand_digest_exported','private_operand_length_exported',
                    'private_numeric_field_exported','private_excerpt_exported','scanner_changed',
                    'privacy_admission_changed','runtime_cause_proven','release_acceptance'):
            self.assertIs(binding[key],False)
        image=self.value['image']
        self.assertEqual(image['bytes'],1929719808)
        self.assertEqual(image['sha256'],'807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c')
        self.assertEqual((self.value['install_timeout'],self.value['harness_seconds']),(2400,6600))
        self.assertIs(self.value['release_acceptance'],False)


if __name__=='__main__':unittest.main(verbosity=2)
