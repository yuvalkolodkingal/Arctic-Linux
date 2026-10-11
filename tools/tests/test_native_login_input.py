"""Actual Source-only login observer and QMP actions, without a VM or credentials."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_login_vmtest', ROOT/'tools/lib/vmtest.py')
vmtest = importlib.util.module_from_spec(spec); spec.loader.exec_module(vmtest)
source = (ROOT/'tools/test-install.sh').read_text()
driver = source.split("read -r -d '' DRIVER <<'PY' || true\n",1)[1].split('\nPY\n',1)[0]
FUNCTIONS = {'native_login_geometry','native_login_type','native_login_click','native_login_record'}
ns = dict(vmtest=vmtest,json=json)
exec(compile(ast.Module(body=[n for n in ast.parse(driver).body
    if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS],type_ignores=[]), '<actual-source-login-helpers>', 'exec'), ns)

class LoginInputSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'before.png'
        self.after = Path(self.temp.name)/'after.png'
        self.controls = Image.open(ROOT/'tools/tests/fixtures/sddm-password-controls.png').convert('RGB')
        im = Image.new('RGB',(1280,800),(24,28,34)); im.paste(self.controls,(479,478)); im.save(self.path)

    def test_unique_source_controls_ambiguity_and_false_wallpaper(self):
        geometry = ns['native_login_geometry'](self.path)
        self.assertIsNotNone(geometry)
        w,h,box = geometry; self.assertEqual((w,h),(1280,800))
        self.assertTrue(479 <= box[0] < box[2] <= 749)
        im = Image.new('RGB',(1280,800),(24,28,34))
        im.paste(self.controls,(300,320)); im.paste(self.controls,(650,478)); im.save(self.after)
        self.assertIsNone(ns['native_login_geometry'](self.after))
        Image.new('RGB',(1280,800),vmtest.AMBER).save(self.after)
        self.assertIsNone(ns['native_login_geometry'](self.after))
        self.assertIsNone(ns['native_login_geometry'](Path(self.temp.name)/'missing.png'))

    def test_original_key_events_delays_and_fallback_are_preserved(self):
        def make(reject=False):
            obj = vmtest.VM.__new__(vmtest.VM); obj.calls=[]
            def command(name,**args):
                obj.calls.append((name,args))
                return {'error':{'class':'GenericError','desc':'private operand'}} if reject and name=='input-send-event' else {'return':{}}
            obj.cmd=command; return obj
        for reject,expected in ((False,'accepted'),(True,'mixed-error')):
            ordinary=make(reject); observed=make(reject); original=observed.cmd
            with mock.patch.object(vmtest.time,'sleep') as old_sleep:
                ordinary.type_text('aB-',gap=.3); delays=list(old_sleep.call_args_list)
            with mock.patch.object(vmtest.time,'sleep') as new_sleep:
                value=ns['native_login_type'](observed,'aB-')
                self.assertEqual(list(new_sleep.call_args_list),delays)
            self.assertEqual(value,expected); self.assertEqual(observed.calls,ordinary.calls)
            self.assertIs(observed.cmd,original)

    def test_primary_exception_and_foreign_command_replacement_are_preserved(self):
        class Owned:
            def __init__(self):self.cmd=lambda *a,**k:{'return':{}}
            def type_text(self,*a,**k):raise primary
        primary=RuntimeError('private unknown credential/error'); obj=Owned(); original=obj.cmd
        with self.assertRaises(RuntimeError) as raised:ns['native_login_type'](obj,'private text')
        self.assertIs(raised.exception,primary); self.assertIs(obj.cmd,original)
        replacement=lambda *a,**k:{'return':{}}
        obj=Owned()
        obj.type_text=lambda *a,**k:setattr(obj,'cmd',replacement)
        self.assertEqual(ns['native_login_type'](obj,'private text'),'unobserved')
        self.assertIs(obj.cmd,replacement)

    def test_pointer_is_only_normal_observed_tablet_action_or_no_action(self):
        class Owned:
            def __init__(self,reply):self.reply=reply;self.calls=[]
            def cmd(self,*a,**k):self.calls.append((a,k));return self.reply
        obj=Owned({'return':{}})
        self.assertEqual(ns['native_login_click'](obj,self.path),'accepted')
        self.assertEqual(len(obj.calls),1); command,args=obj.calls[0]
        self.assertEqual(command,('input-send-event',)); self.assertEqual(set(args),{'events'})
        events=args['events']; self.assertEqual([e['type'] for e in events],['abs','abs','btn','btn'])
        self.assertTrue(all(0<=e['data']['value']<=32767 for e in events[:2]))
        self.assertEqual([e['data'] for e in events[2:]],[dict(down=True,button='left'),dict(down=False,button='left')])
        obj=Owned({'return':{}})
        self.assertEqual(ns['native_login_click'](obj,None),'not-attempted-geometry-unknown'); self.assertEqual(obj.calls,[])
        obj=Owned({'error':{'desc':'private forbidden value'}})
        self.assertEqual(ns['native_login_click'](obj,self.path),'rejected')

    def test_finite_projection_does_not_attest_password_delivery_or_pam(self):
        logs=[]; ns['log']=logs.append
        ns['native_login_record'](self.path,self.path,1,'accepted','not-attempted-keyboard-only')
        row=json.loads(logs[-1].split(' ',1)[1]); self.assertEqual(row['password_region'],'unchanged')
        self.assertEqual(row['authentication'],'not-attested');self.assertFalse(row['release_acceptance'])
        self.assertEqual(row['role'],'keyboard-only');self.assertEqual(row['password_focus_visual'],'source-amber-ring-observed')
        im=Image.open(self.path).convert('RGB'); _,_,(x0,y0,x1,y1)=ns['native_login_geometry'](self.path); ImageDraw.Draw(im).rectangle((x0+48,y0+8,x0+54,y0+12),fill='white');im.save(self.after)
        ns['native_login_record'](self.path,self.after,2,'mixed-error','accepted')
        row=json.loads(logs[-1].split(' ',1)[1]);self.assertEqual(row['password_region'],'changed')
        self.assertEqual(row['authentication'],'not-attested');self.assertEqual(row['role'],'pointer-then-keyboard')
        for message in logs:
            self.assertNotIn('private',message);self.assertNotIn('credential',message)
            self.assertEqual(set(json.loads(message.split(' ',1)[1])),{'schema','attempt','role','qmp','pointer','password_focus_visual','password_region','authentication','release_acceptance'})

if __name__=='__main__':unittest.main()
