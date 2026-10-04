from test_arctic_settings import Home
import json


class CustomizationTests(Home):
    def test_edit_shortcut_and_conflict_preserves_original(self):
        self.helper('bind-add','SUPER+ALT','F8','true')
        self.helper('bind-edit','0','SUPER+ALT','F8','echo updated')
        self.assertEqual(self.helper('binds')['mine'][0]['command'],'echo updated')
        before=self.settings
        self.helper('bind-edit','0','SUPER','Return','false',ok=False)
        self.assertEqual(self.settings,before)
        self.helper('bind-edit','-1','SUPER+ALT','F9','false',ok=False)
        self.assertEqual(self.settings,before)

    def test_reset_custom_shortcuts_preserves_window_settings_and_defaults(self):
        self.helper('set','borderpx=3')
        self.helper('bind-add','SUPER+ALT','F8','true')
        before=self.helper('binds')['all']
        self.helper('bind-reset')
        after=self.helper('binds')
        self.assertEqual(after['mine'],[])
        self.assertIn('borderpx=3',self.settings)
        self.assertEqual(len(after['all']),len(before)-1)
        self.assertTrue(any(b['action']=='reload_config' for b in after['all']))

    def test_bar_validation_and_scoped_reset(self):
        path=self.home/'.config/arctic/shell.json'
        path.write_text(json.dumps({'frame':False,'futureOption':42,'weather':True}))
        self.helper('shell-option-set','barPosition','bottom')
        self.helper('shell-option-set','barSize','40')
        self.helper('shell-option-set','barAutoHide','true')
        for key,value in [('barPosition','evil'),('barSize','0'),('barSize','999'),('barAutoHide','yes')]:
            self.helper('shell-option-set',key,value,ok=False)
        data=self.helper('shell-options-reset','barPosition','barSize','barAutoHide')
        self.assertEqual(data['barPosition'],'top')
        self.assertFalse(data['barAutoHide'])
        persisted=json.loads(path.read_text())
        self.assertFalse(persisted['frame'])
        self.assertEqual(persisted['futureOption'],42)
        self.assertTrue(persisted['weather'])
