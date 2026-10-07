#!/usr/bin/env python3
"""Pure fixed-base default-off integration generation; no Git writes or VM."""
import difflib,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE='aee90aea1c8f6cb827f2044f62a6b47eff475145'
def replace(text,before,after):
 if text.count(before)!=1:raise RuntimeError('unique integration anchor missing: '+before[:80])
 return text.replace(before,after,1)
def harness(base):
 text=replace(base,'PCMANFM_DIAGNOSTIC=""\n','PCMANFM_DIAGNOSTIC=""\nGTK_INPUT_PREFLIGHT=""\n')
 text=replace(text,'    --pcmanfm-diagnostic) PCMANFM_DIAGNOSTIC="$2"; shift 2 ;;',
              '    --pcmanfm-diagnostic) PCMANFM_DIAGNOSTIC="$2"; shift 2 ;;\n    --gtk-input-preflight) GTK_INPUT_PREFLIGHT="$2"; shift 2 ;;')
 start=base.index('if [[ -n "$PCMANFM_DIAGNOSTIC" ]]; then');end=base.index('\nfi\n',start)+4
 guard=base[start:end].replace('PCMANFM_DIAGNOSTIC','GTK_INPUT_PREFLIGHT').replace('pcmanfm-controller.py','preflight-controller.py')
 guard=replace(guard,'if [[ -n "$GTK_INPUT_PREFLIGHT" ]]; then','if [[ -n "$GTK_INPUT_PREFLIGHT" ]]; then\n  [[ -z "$PCMANFM_DIAGNOSTIC" ]] || arctic_die "mixed diagnostic modes forbidden"')
 text=replace(text,base[start:end],guard+'\n'+base[start:end])
 text=replace(text,'if [[ -n "$PCMANFM_DIAGNOSTIC" ]]; then\n  [[ ! -e "$OUT" ]]',
              'if [[ -n "$PCMANFM_DIAGNOSTIC" || -n "$GTK_INPUT_PREFLIGHT" ]]; then\n  [[ ! -e "$OUT" ]]')
 start=base.index('if os.environ.get("PCMANFM_DIAGNOSTIC") == "1":');end=base.index('\n# 2. Splash and boot:',start)
 driver=base[start:end].replace('PCMANFM_DIAGNOSTIC','GTK_INPUT_PREFLIGHT').replace('PCMANFM_CHECKER_SHA','GTK_CHECKER_SHA').replace('/pcmanfm-diagnostic/pcmanfm-controller.py','/gtk-input-preflight/preflight-controller.py').replace('/pcmanfm-diagnostic/bulk-channel.py','/gtk-input-preflight/bulk-channel.py')
 text=replace(text,base[start:end],driver+'\n'+base[start:end])
 text=replace(text,'if [ "$PCMANFM_DIAGNOSTIC" = 1 ]; then\n  pkgs+=(xorriso)',
              'if [ "$PCMANFM_DIAGNOSTIC" = 1 ] || [ "$GTK_INPUT_PREFLIGHT" = 1 ]; then\n  pkgs+=(xorriso)')
 text=replace(text,'[ "$PCMANFM_DIAGNOSTIC" != 1 ] || disk_size=40G',
              '[ "$PCMANFM_DIAGNOSTIC" != 1 ] || disk_size=40G\n[ "$GTK_INPUT_PREFLIGHT" != 1 ] || disk_size=40G')
 start=base.index('if [ "$PCMANFM_DIAGNOSTIC" = 1 ]; then\n  mkdir /tmp/diagnostic-data');end=base.index('\npython3 -c "$DRIVER"',start)
 data=base[start:end].replace('PCMANFM_DIAGNOSTIC','GTK_INPUT_PREFLIGHT').replace('/pcmanfm-diagnostic','/gtk-input-preflight').replace('guest-pcmanfm-diagnostic.py','guest-preflight.py')
 oldfiles='native_smoke.py native-launcher.py atspi-snapshot.py gtk-entry-control.py bounded-launch.py security-collector.py bulk-channel.py gtk-physical.py runtime-pins.json bootstrap-diagnostic.sh original-h264-aac-1s.mp4 codec-fixture-manifest.json'
 newfiles='native_smoke.py native-launcher.py gtk-entry-control.py security-collector.py bulk-channel.py runtime-pins.json bootstrap-diagnostic.sh preflight-core.py preflight-proof.py arctic-wtype-sentinel build-payload-pins.json candidate-input-libraries.json input-collector.py wire-input.py candidate-data-mappings.json data-mapping-proof.py'
 data=replace(data,oldfiles,newfiles).replace('pcmanfm-toolchain.txt','gtk-preflight-toolchain.txt')
 text=replace(text,base[start:end],base[start:end]+'\n'+data)
 text=replace(text,'diagnostic_args=()\ndiagnostic_enabled=0',
              'gtk_enabled=0\ngtk_checker_sha=""\ngtk_args=()\nif [[ -n "$GTK_INPUT_PREFLIGHT" ]]; then\n  gtk_enabled=1\n  gtk_args=(-v "$GTK_INPUT_PREFLIGHT:/gtk-input-preflight:ro")\n  gtk_checker_sha="$(sha256sum "$GTK_INPUT_PREFLIGHT/guest-preflight.py")"\n  gtk_checker_sha="${gtk_checker_sha%% *}"\nfi\ndiagnostic_args=()\ndiagnostic_enabled=0')
 text=replace(text,'"$engine" run --rm "${diagnostic_args[@]}"',
              '"$engine" run --rm "${gtk_args[@]}" "${diagnostic_args[@]}"')
 text=replace(text,'  -e PCMANFM_DIAGNOSTIC="$diagnostic_enabled"',
              '  -e GTK_INPUT_PREFLIGHT="$gtk_enabled" -e GTK_CHECKER_SHA="$gtk_checker_sha" -e PCMANFM_DIAGNOSTIC="$diagnostic_enabled"')
 return text
def workflow(base):
 text=replace(base,'    inputs:\n','''    inputs:
      same_iso_gtk_input_preflight:
        description: One finite owned GTK original/sentinel input preflight only (fixed ISO; no product/build/install/release)
        type: boolean
        default: false
''')
 text=replace(text,'!inputs.same_iso_pcmanfm_diagnostic) }}','!inputs.same_iso_pcmanfm_diagnostic && !inputs.same_iso_gtk_input_preflight) }}')
 # Every existing selected recovery/native/diagnostic job is excluded in this new mode.
 for expression in ('inputs.same_iso_recovery && !inputs.same_iso_native_smoke && !inputs.same_iso_pcmanfm_diagnostic }}',
                    'inputs.same_iso_native_smoke && !inputs.same_iso_pcmanfm_diagnostic }}',
                    'inputs.same_iso_pcmanfm_diagnostic }}'):
  text=text.replace(expression,expression[:-3]+' && !inputs.same_iso_gtk_input_preflight }}')
 job=base[base.index('\n  same-iso-pcmanfm-diagnostic:'):]
 job=job.replace('same-iso-pcmanfm-diagnostic','same-iso-gtk-input-preflight').replace('inputs.same_iso_pcmanfm_diagnostic','inputs.same_iso_gtk_input_preflight')
 job=job.replace('      PCMANFM_DIAGNOSTIC_MODE: "true"','      GTK_INPUT_PREFLIGHT_MODE: "true"\n      PCMANFM_DIAGNOSTIC_MODE: ${{ inputs.same_iso_pcmanfm_diagnostic && \'true\' || \'false\' }}')
 job=job.replace('arctic-pcmanfm-diagnostic-','arctic-gtk-input-preflight-').replace('tools/pcmanfm-diagnostic/diagnostic-runner.py','tools/gtk-input-preflight/preflight-runner.py').replace('tools/pcmanfm-diagnostic"','tools/gtk-input-preflight"').replace('pcmanfm-diagnostic-v3-37507582946-','gtk-input-preflight-v1-37507582946-')
 job=job.replace('One fresh live-only reviewed GTK keymap and bounded virtio-data diagnostic VM','One fresh live-only finite original/sentinel GTK input preflight VM')
 return text+job
def main():
 for source,target,generate in [('base-test-iso.sh','registered-test-iso.sh',harness),('base-iso.yml','registered-iso-preflight.yml',workflow)]:
  original=(HERE/source).read_text();result=generate(original);(HERE/target).write_text(result)
  (HERE/(target+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),result.splitlines(True),fromfile=source,tofile=target)))
if __name__=='__main__':main()
