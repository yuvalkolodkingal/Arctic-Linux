"""Replay active records through the unchanged bounded transport primitives."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


F=load('active_transport_contract_fixtures',HERE/'test_active_contract.py')
T=load('active_transport_wire_fixtures',HERE/'test_evidence.py')
E=load('active_transport_real_decoder',HERE/'evidence.py')
A=load('active_transport_producer',HERE/'active-guest.py')


def wire():
    report,state,_,media,_=F.fixture()
    T.Controls.setUpClass();builder=T.Controls()
    builder.context=state['context'];builder.identity={key:report[key] for key in E.IDENTITY}
    builder.root=report['evidence_root'];builder.report=report
    builder.begin=dict(T.Controls.begin,context=builder.context,**builder.identity)
    builder.proof=dict(T.Controls.proof,context=builder.context,**builder.identity)
    builder.end=dict(T.Controls.end,binding_id=builder.context['binding_id'],**builder.identity)
    builder.files={name:media['installer/'+name] for name in F.A.GUEST_IMAGES}
    builder.files['installer-report.json']=(json.dumps(report,sort_keys=True)+'\n').encode()
    builder.requests=state['guest']['requests']
    return builder


class Controls(unittest.TestCase):
    def test_actual_decoder_accepts_only_active_four_png_three_request_transport(self):
        builder=wire();port,serial=builder.wire(builder.rows())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'port').write_bytes(port);(root/'serial').write_bytes(serial)
            result=E.extract(root/'port',root/'serial',root/'decoded',builder.context)
        self.assertEqual(result['state']['status'],'passed');self.assertEqual(result['state']['required_pngs'],4)
        self.assertEqual(result['state']['received_requests'],3);self.assertFalse(result['state']['release_acceptance'])

    def test_idle_request_matrix_cannot_be_relabelled_active(self):
        builder=wire();requests=copy.deepcopy(builder.requests);requests.append(copy.deepcopy(requests[-1]))
        port,serial=builder.wire(builder.rows(),requests)
        with self.assertRaises(RuntimeError):E.block(port,serial,builder.context)

    def test_active_request_is_bound_to_exact_observation_not_baseline_replay(self):
        builder=wire();builder.requests[0]['elapsed_ns']=builder.report['baseline']['elapsed_ns']
        builder.files['installer-report.json']=(json.dumps(builder.report,sort_keys=True)+'\n').encode()
        port,serial=builder.wire(builder.rows())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'port').write_bytes(port);(root/'serial').write_bytes(serial)
            result=E.extract(root/'port',root/'serial',root/'decoded',builder.context)
        self.assertEqual(result['state']['status'],'failed')

    def test_producer_and_independent_contract_pin_all_current_gui_sources(self):
        actual={str(path.relative_to(HERE.parents[1]/'installer-ui')) for path in (HERE.parents[1]/'installer-ui').rglob('*')
                if path.is_file() and (path.suffix=='.qml' or path.name=='qmldir')}
        self.assertEqual(set(A.GUI_FILES),set(F.A.GUI_FILES));self.assertEqual(set(A.GUI_FILES),actual)


if __name__=='__main__':unittest.main()
