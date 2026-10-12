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
        for key,item in self.value['broker_shape_binding'].items():
            if type(item)is bool:
                wrong=json.loads(json.dumps(self.value));wrong['broker_shape_binding'][key]=int(item)
                with self.subTest(key=key),self.assertRaises(RuntimeError):self.common.manifest(wrong)
        wrong=json.loads(json.dumps(self.value))
        wrong['broker_shape_binding']['selected_observer_path']=wrong['broker_shape_binding']['requested_observer_path']
        wrong['broker_shape_binding']['selected_observer_sha256']=wrong['broker_shape_binding']['requested_observer_sha256']
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
        self.assertEqual(state['broker_shape_mapping'],self.value['broker_shape_binding'])
        wrapper=observed.__globals__['original_evidence']
        binding=captured(wrapper,'configured')
        self.assertIs(type(binding),tuple);self.assertEqual(len(binding),11)
        module,owner,function,attributes,observer_owner,helper,helper_owner,scanners,common_owner,runs=binding[:-1]
        self.assertIs(function,module.diagnostic_broker_factory_shape)
        self.assertIs(function.__globals__,module.__dict__)
        self.assertTrue(owner.unchanged());self.assertTrue(observer_owner.unchanged())
        self.assertTrue(helper_owner.unchanged());self.assertTrue(common_owner.unchanged())
        self.assertTrue(all(held.unchanged()for held in runs))
        self.assertEqual(module.__file__,str(ROOT/self.value['broker_shape_binding']['diagnostic_path']))
        self.assertIsNone(state['strict']['finite'])
        self.assertIs(state['runtime_cause_proven'],False);self.assertIs(state['release_acceptance'],False)
        self.assertIs(self.common.manifest(self.value,True),self.value)

    def test_selected_observer_drift_and_missing_dependency_deny(self):
        def loader(path,digest):
            raw=path.read_bytes()
            if path==ROOT/self.value['broker_shape_binding']['selected_observer_path']:
                return raw+b'\n# foreign Source drift\n'
            return raw
        with self.assertRaises(RuntimeError):self.composition.build(ROOT,self.value,loader,lambda *args:None)
        wrong=json.loads(json.dumps(self.value))
        del wrong['execution_files'][wrong['broker_shape_binding']['diagnostic_path']]
        with self.assertRaises(RuntimeError):self.common.manifest(wrong)


if __name__=='__main__':unittest.main(verbosity=2)
