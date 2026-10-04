from test_arctic_settings import Home, stub
import json


class CustomizationTests(Home):
    def test_dodge_capability_is_reported_without_rewriting_preferences(self):
        self.env['MANGO_INSTANCE_SIGNATURE']='test'
        stub(self.bin,'mmsg',"echo '{\"error\":\"unknown command\"}'")
        self.assertFalse(self.helper('shell-options')['barDodgeAvailable'])
        stub(self.bin,'mmsg',"echo '{\"client_geometry_events\":true}'")
        self.assertTrue(self.helper('shell-options')['barDodgeAvailable'])
        stub(self.bin,'mmsg','exit 1')
        self.assertFalse(self.helper('shell-options')['barDodgeAvailable'])

    def test_visibility_modes_legacy_migration_and_scoped_reset(self):
        path=self.home/'.config/arctic/shell.json'
        original=json.dumps({'barAutoHide':True,'barPosition':'right','futureOption':42})
        path.write_text(original)
        self.assertEqual(self.helper('shell-options')['barHideMode'],'auto')
        self.assertEqual(path.read_text(),original)  # reading does not rewrite preferences
        for mode in ('always','auto','dodge'):
            data=self.helper('shell-option-set','barHideMode',mode)
            self.assertEqual(data['barHideMode'],mode)
            self.assertEqual(data['barAutoHide'],mode=='auto')
        self.helper('shell-option-set','barHideMode','sometimes',ok=False)
        self.helper('shell-option-set','barAutoHide','true')
        self.assertEqual(self.helper('shell-options')['barHideMode'],'auto')
        self.helper('shell-option-set','barHideMode','dodge')
        data=self.helper('shell-options-reset','barAutoHide')
        self.assertEqual(data['barHideMode'],'always')
        self.assertFalse(data['barAutoHide'])
        self.assertEqual(data['barPosition'],'right')
        self.assertEqual(json.loads(path.read_text())['futureOption'],42)

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
        for position in ('left', 'right', 'bottom', 'top'):
            data=self.helper('shell-option-set','barPosition',position)
            self.assertEqual(data['barPosition'],position)
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

class BuiltinCustomizationTests(Home):
    def setUp(self):
        super().setUp()
        import shutil
        from test_arctic_settings import DOTFILES
        (self.share/'mango').mkdir()
        for name in ('apps.conf','binds.conf'):
            shutil.copy(DOTFILES/'.config/mango/arctic'/name,self.share/'mango'/name)
            target=self.home/'.config/mango/arctic'/name
            target.unlink()
            target.symlink_to(self.share/'mango'/name)

    def entry(self, action):
        return next(b for b in self.helper('binds')['builtin'] if b['action']==action)

    def test_remap_conflict_reset_and_packaged_files_untouched(self):
        original=(self.share/'mango/binds.conf').read_text()
        row=self.entry('killclient')
        self.helper('builtin-bind','set',row['id'],'SUPER+ALT','F9')
        self.assertEqual((self.share/'mango/binds.conf').read_text(),original)
        self.assertEqual(self.entry('killclient')['key'],'F9')
        self.assertTrue(any(b['action']=='reload_config' and b['mods']==['ALT','CTRL','SUPER'] for b in self.helper('binds')['all']))
        self.helper('builtin-bind','set',row['id'],'SUPER','Return',ok=False)
        self.assertEqual(self.entry('killclient')['key'],'F9')
        self.helper('builtin-bind','set',row['id'],'SUPER+CTRL+ALT','F12',ok=False)
        self.helper('builtin-bind','reset-all')
        self.assertTrue((self.home/'.config/mango/arctic/binds.conf').is_symlink())
        self.assertEqual(self.entry('killclient')['key'],row['key'])

    def test_template_update_preserves_remap_and_manual_edits_are_refused(self):
        row=self.entry('killclient')
        self.helper('builtin-bind','set',row['id'],'SUPER+ALT','F9')
        template=self.share/'mango/binds.conf'
        template.write_text(template.read_text().replace('bind=SUPER,q,killclient', 'bind=SUPER+ALT,q,killclient')+'\n# new package comment\nbind=SUPER+ALT,F10,spawn,true\n')
        self.helper('builtin-bind','sync')
        target=self.home/'.config/mango/arctic/binds.conf'
        self.assertIn('new package comment',target.read_text())
        self.assertEqual(self.entry('killclient')['key'],'F9')
        self.assertNotEqual(self.entry('killclient')['originalLabel'],row['originalLabel'])
        target.write_text(target.read_text()+'\n# manual change\n')
        self.helper('builtin-bind','reset-all',ok=False)
        self.assertIn('manual change',target.read_text())

    def test_recovery_conflict_and_plain_typing_key_are_rejected(self):
        row=self.entry('killclient')
        self.helper('builtin-bind','set',row['id'],'NONE','a',ok=False)
        self.helper('bind-add','SUPER+CTRL+ALT','F12','true')
        self.helper('builtin-bind','set',row['id'],'SUPER+ALT','F9',ok=False)
        self.assertTrue((self.home/'.config/mango/arctic/binds.conf').is_symlink())

    def test_removed_action_is_reported_for_review_at_login(self):
        row=self.entry('killclient')
        self.helper('builtin-bind','set',row['id'],'SUPER+ALT','F9')
        template=self.share/'mango/binds.conf'
        template.write_text('\n'.join(line for line in template.read_text().splitlines() if ',killclient' not in line)+'\n')
        notices=self.helper('notices')
        self.assertTrue(any(n['id'].startswith('builtin-orphaned-') for n in notices['notices']))
        self.assertIn(row['id'],self.helper('binds')['orphaned'])
