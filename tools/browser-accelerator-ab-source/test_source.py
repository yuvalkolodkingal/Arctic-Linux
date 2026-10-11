import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parent
CACHE = Path('/tmp/arctic-epiphany-static-symbols-20261011')
PREP = Path('/tmp/arctic-browser-accelerator-ab-source-preparation-20261011')


def load(name, path):
    import types
    module = types.ModuleType(name);module.__file__ = str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    return module


candidate = load('accelerator_candidate', ROOT/'candidate.py')
recipe = load('accelerator_recipe', ROOT/'build_recipe.py')
profile = load('accelerator_profile', ROOT/'profile.py')


class SourceTests(unittest.TestCase):
    def test_candidate_whole_inverse(self):
        original = (CACHE/'epiphany-debugsource-member-0254').read_bytes()
        changed = candidate.patched_window(original)
        self.assertEqual(changed.replace(candidate.NEW.encode(),candidate.OLD.encode()),original)
        self.assertEqual(changed.count(candidate.NEW.encode()),1)
        self.assertEqual(changed.count(b'gtk_widget_get_default_direction ()'),original.count(b'gtk_widget_get_default_direction ()'))
        self.assertEqual(len(re.findall(rb'^@@ ',candidate.window_patch(original),re.M)),1)
        self.assertLess(len(candidate.window_patch(original)),32768)

    def test_wrong_candidate_source_rejects(self):
        for raw in (b'',(CACHE/'epiphany-debugsource-member-0254').read_bytes()+b'\n'):
            with self.assertRaisesRegex(RuntimeError,'candidate_source_binding'):candidate.patched_window(raw)

    def test_immutable_table_and_navigation_counts(self):
        text=(CACHE/'epiphany-debugsource-member-0254').read_text()
        tables=text[text.index('const struct {'):text.index('#define SETTINGS_CONNECTION_DATA_KEY')]
        default=tables.split('}, accels_navigation_ltr')[0]
        names=re.findall(r'^  \{ "([^"]+)"',default,re.M)
        self.assertEqual(len(names),43);self.assertEqual(len(set(names)),43)
        self.assertTrue(all(n.startswith(('win.','toolbar.','tab.')) for n in names))
        self.assertEqual(len(re.findall(r'^  \{ "',tables,re.M)),47)

    def test_exact_dynamic_setter_sources(self):
        shell=(CACHE/'epiphany-debugsource-member-0242').read_bytes()
        extension=(PREP/'epiphany-50.6-webextension-commands.c').read_bytes()
        self.assertEqual(hashlib.sha256(shell).hexdigest(),'a09768a74b4ef58a0b06cb7e9b63e9339488935bb5788374977e6e55ce4cf897')
        self.assertEqual(hashlib.sha256(extension).hexdigest(),'c968b47c84d2282ac494b33c684a87b98389f1a167a74d14ad5f73c95e9c9376')
        self.assertIn(b'app.webextension-command-%s-%s',extension)
        self.assertIn(b'gtk_application_set_accels_for_action (GTK_APPLICATION (shell),',shell)
        census=json.loads((PREP/'signed-source-accelerator-census.json').read_text())
        # The exhaustive census is Source evidence, not a runtime interceptor.
        self.assertEqual(census['all_source_c_h_scanned'],341)
        self.assertEqual(shell.count(b'gtk_application_set_accels_for_action'),1)

    def test_exhaustive_signed_payload_setter_census(self):
        import types
        script=CACHE/'extract-exact-public-rpm-evidence.py'
        tree=ast.parse(script.read_bytes())
        retained=[node for node in tree.body if isinstance(node,(ast.Import,ast.ImportFrom))
                  or isinstance(node,ast.FunctionDef) and node.name=='parse']
        module=types.ModuleType('owned_bounded_debugsource_parser')
        exec(compile(ast.Module(body=retained,type_ignores=[]),str(script),'exec'),module.__dict__)
        raw=(CACHE/'epiphany-debugsource-50.6-1.fc44.x86_64.rpm').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'10233b81d99524affa491c6c228acb755097b49f83b13d04565b7454af2ddd03')
        files,_,_,_=module.parse(raw,'epiphany-debugsource')
        sources={name:value for name,value in files.items() if name.endswith(('.c','.h'))}
        self.assertEqual(len(sources),341)
        setter={name:hashlib.sha256(value).hexdigest() for name,value in sources.items()
                if b'gtk_application_set_accels_for_action' in value}
        expected={x['path']:x['sha256'] for x in json.loads((PREP/'signed-source-accelerator-census.json').read_text())['rows']}
        self.assertEqual(setter,expected)
        self.assertFalse(any(b'g_object_run_dispose' in value for value in sources.values()))

    def test_spec_whole_inverse(self):
        original=(PREP/'official-epiphany-50.6.spec').read_bytes()
        changed=candidate.candidate_spec(original)
        self.assertEqual(changed.replace(b'Patch1:         arctic-accelerator-candidate.patch\n',b''),original)
        for section in (b'%build\n%meson\n%meson_build\n',b'%check\n'):
            self.assertIn(section,changed)
        with self.assertRaises(RuntimeError):candidate.candidate_spec(original+b'\n')

    def build(self, **change):
        arguments=dict(container_digest='registry.fedoraproject.org/fedora@sha256:'+'1'*64,
            dependency_census_sha256='2'*64,macro_census_sha256='3'*64,
            srpm_raw=(PREP/recipe.SRPM['name']).read_bytes(),spec_raw=(PREP/'official-epiphany-50.6.spec').read_bytes(),
            window_raw=(CACHE/'epiphany-debugsource-member-0254').read_bytes(),
            patch_raw=candidate.window_patch((CACHE/'epiphany-debugsource-member-0254').read_bytes()),candidate=candidate)
        arguments.update(change);return recipe.build_plan(**arguments)

    def test_disabled_matching_build_plan(self):
        plan=self.build()
        self.assertFalse(plan['ready']);self.assertFalse(plan['runtime_overlay_ready']);self.assertFalse(plan['install_payload'])
        self.assertEqual(plan['runs'][0]['argv'],plan['runs'][1]['argv'])
        self.assertTrue(all(x['full_checks'] and x['clean_same_topdir_before'] for x in plan['runs']))
        self.assertEqual(plan['VM_runs'],0);self.assertFalse(plan['performance_acceptance'])

    def test_build_bindings_reject(self):
        for changes in ({'container_digest':'registry.fedoraproject.org/fedora:44'},
                        {'dependency_census_sha256':'guess'},{'macro_census_sha256':'guess'},
                        {'srpm_raw':b'foreign'},{'spec_raw':b'foreign'},
                        {'window_raw':b'foreign'},{'patch_raw':b'foreign'}):
            with self.assertRaises(RuntimeError):self.build(**changes)

    def test_low_hook_profile_whole_inverse(self):
        raw=(ROOT/'profile.py').read_text();proof=json.loads((ROOT/'source-inverse.json').read_text())
        for pair in reversed(proof['replacements']):
            self.assertEqual(raw.count(pair['new']),1);raw=raw.replace(pair['new'],pair['old'])
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(),proof['profile_original_sha256'])
        original=ast.parse(raw);updated=ast.parse((ROOT/'profile.py').read_text())
        oldfunctions={x.name:ast.dump(x) for x in original.body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
        newfunctions={x.name:ast.dump(x) for x in updated.body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
        for name in oldfunctions:
            if name not in ('PhaseProbe','require_launch_phases'):self.assertEqual(newfunctions[name],oldfunctions[name],name)
        self.assertEqual(profile.MAX_EVENTS,8192);self.assertEqual(profile.MAX_LINE,16384)
        self.assertEqual(set(profile.PHASES),{'application_run','window_construct','window_constructed','accelerator_set'})
        self.assertTrue(all(registers is None for _,_,registers in profile.PHASES.values()))

    def test_closed_accelerator_event(self):
        entry=profile.parse_event('epiphany-123 [001] .... 1.000001: accelerator_set_enter: private_operand_never_exported')
        self.assertEqual(set(entry),{'tid','timestamp_ns','timestamp_resolution_ns','phase','point'})
        self.assertNotIn('private_operand',json.dumps(entry))
        with self.assertRaises(RuntimeError):profile.parse_event('epiphany-123 [001] .... 1.000001: widget_visibility_enter:')

    def test_required_low_hook_phases(self):
        values=[dict(phase=p,point='enter') for p in ('application_run','window_constructed','accelerator_set')]
        profile.require_launch_phases(values)
        for index in range(3):
            with self.assertRaisesRegex(RuntimeError,'required_accelerator_phase_not_observed'):
                profile.require_launch_phases(values[:index]+values[index+1:])

    def test_narrowed_profile_owned_FD_generation_and_real_cancel(self):
        # Reuse unchanged retained real-file/virtual-provider controls against
        # THIS narrowed profile. Nothing is read from an actual guest/process.
        retained=Path('/tmp/arctic-browser-main-library-source-20261011/tools/browser-main-library-source/test_source.py')
        raw=retained.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'a465bfffeea1afdc71e3f3adc570a32913b9dd5ea7420cda513725fdaef8be1e')
        controls=load('retained_public_source_controls',retained)
        controls.PROFILE=profile
        suite=unittest.TestSuite(controls.Controls(name) for name in (
            'test_map_forwarding_exact_owned_whole_fd_and_process_generation',
            'test_map_absence_oversize_and_generation_reuse_deny',
            'test_map_denial_and_original_cancel_object_preserved_no_fd_leak',
            'test_actual_sigint_inventory_callback_preserves_handler_and_descriptors'))
        result=unittest.TestResult();suite.run(result)
        self.assertEqual(result.testsRun,4)
        self.assertEqual(result.skipped,[])
        self.assertEqual(result.errors,[])
        self.assertEqual(result.failures,[])

    def test_actual_gobject_candidate_block(self):
        text=(CACHE/'epiphany-debugsource-member-0254').read_text()
        tables=text[text.index('const struct {'):text.index('#define SETTINGS_CONNECTION_DATA_KEY')]
        # Compile and execute the exact candidate block with real GObject
        # lifetimes/data. The GTK setter and direction below are controlled
        # semantic fixtures, not claims of real GTK dispatch/performance.
        source=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <signal.h>
typedef unsigned long GType;
typedef struct _GObject GObject;
extern GType g_object_get_type(void);
extern void *g_object_new(GType,const char *,...);
extern void *g_object_get_data(GObject *,const char *);
extern void g_object_set_data(GObject *,const char *,void *);
extern void g_object_unref(void *);
#define G_OBJECT(p) ((GObject *)(p))
#define GTK_APPLICATION(p) (p)
#define G_N_ELEMENTS(a) (sizeof(a)/sizeof((a)[0]))
#define GINT_TO_POINTER(v) ((void *)(intptr_t)(v))
#define TRUE 1
#define GTK_TEXT_DIR_LTR 0
static int direction;
static int gtk_widget_get_default_direction(void) { return direction; }
''' + tables + r'''
struct fixture {void *app;unsigned calls,defaults,navigation;const char *keys[47];const char *first[47];};
static struct fixture fixtures[8];
static unsigned count;
static sigjmp_buf cancelled;
static int fail_after;
static volatile sig_atomic_t interrupted;
static void cancel_signal(int number) {(void)number;interrupted=1;siglongjmp(cancelled,1);}
static struct fixture *get(void *app) {
  for(unsigned i=0;i<count;i++)if(fixtures[i].app==app)return &fixtures[i];
  assert(count<8);fixtures[count].app=app;return &fixtures[count++];
}
static void gtk_application_set_accels_for_action(void *app,const char *name,const char *const *values) {
  struct fixture *f=get(app);unsigned i;
  f->calls++;
  if(strncmp(name,"toolbar.navigation-",19)==0)f->navigation++;else f->defaults++;
  for(i=0;i<47&&f->keys[i]&&strcmp(f->keys[i],name);i++);
  assert(i<47);f->keys[i]=name;f->first[i]=values[0];
  if(fail_after&&f->calls==(unsigned)fail_after)raise(SIGINT);
}
static const char *lookup(void *app,const char *name) {
  struct fixture *f=get(app);
  for(unsigned i=0;i<47&&f->keys[i];i++)if(!strcmp(f->keys[i],name))return f->first[i];
  return NULL;
}
static void construct(void *app) {unsigned i;
''' + candidate.NEW + r'''
  accels_navigation_ltr_rtl = gtk_widget_get_default_direction () == GTK_TEXT_DIR_LTR ?
                              accels_navigation_ltr : accels_navigation_rtl;
  for (i = 0; i < G_N_ELEMENTS (accels_navigation_ltr); i++) {
    gtk_application_set_accels_for_action (GTK_APPLICATION (app),
                                           accels_navigation_ltr_rtl[i].action_and_target,
                                           accels_navigation_ltr_rtl[i].accelerators);
  }
}
int main(void) {
 assert(G_N_ELEMENTS(accels)==43);
 void *one=g_object_new(g_object_get_type(),NULL),*two=g_object_new(g_object_get_type(),NULL);
 construct(one);assert(get(one)->defaults==43&&get(one)->navigation==2);
 assert(!strcmp(lookup(one,"win.new-tab"),"<Primary>T"));
 construct(one);assert(get(one)->defaults==43&&get(one)->navigation==4);
 direction=1;construct(one);assert(get(one)->defaults==43&&get(one)->navigation==6);
 assert(!strcmp(lookup(one,"toolbar.navigation-back"),"<alt>Right"));
 direction=0;construct(one);assert(!strcmp(lookup(one,"toolbar.navigation-back"),"<alt>Left"));
 construct(two);assert(get(two)->defaults==43&&get(two)->navigation==2);
 const char *remap[]={"F13",NULL};
 gtk_application_set_accels_for_action(one,"app.preferences",remap);
 gtk_application_set_accels_for_action(one,"app.webextension-command-guid-command",remap);
 construct(one);assert(!strcmp(lookup(one,"app.preferences"),"F13"));
 assert(!strcmp(lookup(one,"app.webextension-command-guid-command"),"F13"));
 gtk_application_set_accels_for_action(one,"app.webextension-command-guid-command",(const char *const[]){NULL});
 construct(one);assert(lookup(one,"app.webextension-command-guid-command")==NULL);
 /* Explicit experiment policy: foreign direct default remaps persist. */
 gtk_application_set_accels_for_action(one,"win.new-tab",remap);construct(one);
 assert(!strcmp(lookup(one,"win.new-tab"),"F13"));
 void *partial=g_object_new(g_object_get_type(),NULL);fail_after=7;
 struct sigaction old_handler,handler={0},readback;handler.sa_handler=cancel_signal;
 sigemptyset(&handler.sa_mask);assert(sigaction(SIGINT,&handler,&old_handler)==0);
 if(!sigsetjmp(cancelled,1)) {construct(partial);assert(0);}
 assert(interrupted==1);assert(sigaction(SIGINT,NULL,&readback)==0);
 assert(readback.sa_handler==cancel_signal);assert(sigaction(SIGINT,&old_handler,NULL)==0);
 assert(g_object_get_data(G_OBJECT(partial),"ephy-window-default-accelerators-registered-50-6")==NULL);
 fail_after=0;construct(partial);assert(get(partial)->defaults==50&&get(partial)->navigation==2);
 assert(g_object_get_data(G_OBJECT(partial),"ephy-window-default-accelerators-registered-50-6")!=NULL);
 g_object_unref(one);g_object_unref(two);g_object_unref(partial);
 /* Use a fresh fixture inventory even if allocator reuses a pointer. */
 count=0;memset(fixtures,0,sizeof(fixtures));
 void *replacement=g_object_new(g_object_get_type(),NULL);construct(replacement);
 assert(get(replacement)->defaults==43&&get(replacement)->navigation==2);
 g_object_unref(replacement);
 puts("GOBJECT_LIFETIME_CONTROLLED_GTK_DEFAULTS_DIRECTION_DYNAMIC_PARTIAL_PASS");
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='owned-accelerator-C-') as tmp:
            path=Path(tmp);(path/'control.c').write_text(source)
            proc=subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',str(path/'control.c'),
                '-Wl,-l:libgobject-2.0.so.0','-Wl,-l:libglib-2.0.so.0','-o',str(path/'control')],capture_output=True,timeout=30)
            self.assertEqual(proc.returncode,0,proc.stderr.decode())
            result=subprocess.run([str(path/'control')],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'GOBJECT_LIFETIME_CONTROLLED_GTK_DEFAULTS_DIRECTION_DYNAMIC_PARTIAL_PASS\n')


if __name__=='__main__':unittest.main(verbosity=2)
