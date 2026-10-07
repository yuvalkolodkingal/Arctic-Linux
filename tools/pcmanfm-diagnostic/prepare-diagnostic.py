#!/usr/bin/env python3
"""Reproduce a reviewable execution tree from a fixed Git base; no Git writes/VM."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

BASE='92aa52c0ef324a2cb5ad4af9f0c47c5e8b273bec'
HERE=Path(__file__).resolve().parent


def replace(value,before,after):
    if value.count(before)!=1:raise RuntimeError('patch anchor must occur exactly once: '+before[:90])
    return value.replace(before,after)


def initial_harness(base):
    value=replace(base,'COLLECT=0\n','COLLECT=0\nPCMANFM_DIAGNOSTIC=""\n')
    value=replace(value,'    --collect) COLLECT=1; shift ;;',
                  '    --collect) COLLECT=1; shift ;;\n    --pcmanfm-diagnostic) PCMANFM_DIAGNOSTIC="$2"; shift 2 ;;')
    guard='''if [[ -n "$PCMANFM_DIAGNOSTIC" ]]; then
  [[ "$FIRMWARE" == uefi && "$MODE" == try && "$KVM" == 1 && "$SECUREBOOT" == 0 && "$COLLECT" == 0 \\
     && "$MEMORY" == 4096 && "$SMP" == 2 && "$VGA" == virtio && "$TIMEOUT" == 900 && -c /dev/kvm \\
     && "${ARCTIC_VM_TOOLS_PREPARED:-0}" == 1 ]] || arctic_die "invalid explicit diagnostic VM mode/tools"
  [[ "$APPEND" == " console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1" ]] \\
    || arctic_die "diagnostic requires exact native serial arguments"
  PCMANFM_DIAGNOSTIC="$(cd "$PCMANFM_DIAGNOSTIC" && pwd)"
  [[ -f "$PCMANFM_DIAGNOSTIC/pcmanfm-controller.py" && -f "$PCMANFM_DIAGNOSTIC/runtime-pins.json" \\
     && -f "$PCMANFM_DIAGNOSTIC/bootstrap-diagnostic.sh" ]] || arctic_die "diagnostic source packet absent"
fi
'''
    value=replace(value,'[[ -f "$ISO" ]] || arctic_die',guard+'[[ -f "$ISO" ]] || arctic_die')
    value=replace(value,'rm -rf "$OUT"; mkdir -p "$OUT"','''if [[ -n "$PCMANFM_DIAGNOSTIC" ]]; then
  [[ ! -e "$OUT" ]] || arctic_die "diagnostic output must be unused"
  mkdir -p "$OUT"
else
  rm -rf "$OUT"; mkdir -p "$OUT"
fi''')
    value=replace(value,'# 2. Splash and boot:', '''if os.environ.get("PCMANFM_DIAGNOSTIC") == "1":
    import importlib.util
    spec = importlib.util.spec_from_file_location('pcmanfm_controller', '/pcmanfm-diagnostic/pcmanfm-controller.py')
    controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
    try:
        controller.run(vm, out, menu_seen, os.environ['PCMANFM_CHECKER_SHA'])
    finally:
        vm.quit()
    sys.exit(0)

# 2. Splash and boot:''')
    value=replace(value,'dnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"', '''if [ "$PCMANFM_DIAGNOSTIC" = 1 ]; then
  pkgs+=(xorriso)
  rpm -q "${pkgs[@]}" >/dev/null
else
  dnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"
fi''')
    value=replace(value,'qemu-img create -q -f qcow2 /tmp/target.qcow2 64G', '''disk_size=64G
[ "$PCMANFM_DIAGNOSTIC" != 1 ] || disk_size=40G
qemu-img create -q -f qcow2 /tmp/target.qcow2 "$disk_size"''')
    data='''if [ "$PCMANFM_DIAGNOSTIC" = 1 ]; then
  mkdir /tmp/diagnostic-data
  cp /pcmanfm-diagnostic/guest-pcmanfm-diagnostic.py /tmp/diagnostic-data/guest-check.py
  for f in native_smoke.py native-launcher.py atspi-snapshot.py gtk-entry-control.py bounded-launch.py runtime-pins.json bootstrap-diagnostic.sh original-h264-aac-1s.mp4 codec-fixture-manifest.json; do
    cp "/pcmanfm-diagnostic/$f" /tmp/diagnostic-data/
  done
  printf '%s\\n' '#!/bin/bash' 'set -euo pipefail' 'exec python3 /run/t/guest-check.py' > /tmp/diagnostic-data/run.sh
  xorriso -as mkisofs -quiet -V ARCTICDIAG -J -R -G /pcmanfm-diagnostic/bootstrap-diagnostic.sh \\
    -o /tmp/diagnostic-data.iso /tmp/diagnostic-data
  # Match the frozen native v4 device choices; only task paths/data payload differ.
  args=(qemu-system-x86_64 -machine q35 -accel kvm -cpu max -smp "$SMP" -m "$MEMORY"
        -display none -vga virtio -qmp "unix:$OUT/qmp.sock,server=on,wait=off"
        -serial "file:$OUT/serial.log" -monitor none -no-reboot
        -drive file=/tmp/target.qcow2,if=none,id=disk,discard=unmap -device virtio-blk-pci,drive=disk,bootindex=1
        -drive file=/tmp/diagnostic-data.iso,media=cdrom,readonly=on,if=none,id=data -device ide-cd,drive=data,bus=ide.0
        -netdev user,id=net0,restrict=on -device virtio-net-pci,netdev=net0
        -device qemu-xhci -device usb-tablet -rtc base=utc
        -audiodev "wav,id=native_audio,path=$OUT/diagnostic-audio.wav,out.frequency=48000,out.channels=2,out.format=s16"
        -device intel-hda -device hda-output,audiodev=native_audio
        -drive file=/iso,media=cdrom,readonly=on,if=none,id=cd -device ide-cd,drive=cd,bus=ide.1,bootindex=0
        -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=/tmp/vars.fd")
  {
    qemu-system-x86_64 --version
    rpm -q "${pkgs[@]}"
    sha256sum "$(command -v qemu-system-x86_64)" "$code" "$vars" /tmp/diagnostic-data.iso /pcmanfm-diagnostic/*.py
    printf '%q ' "${args[@]}"; printf '\\n'
    printf '%s\\n' 'Actual new tools/data payload; no earlier tool byte parity or audio acceptance claim.'
  } > "$OUT/pcmanfm-toolchain.txt"
fi
'''
    value=replace(value,'python3 -c "$DRIVER" "${args[@]}"',data+'python3 -c "$DRIVER" "${args[@]}"')
    value=replace(value,'"$engine" run --rm "${name_args[@]}"', '''diagnostic_args=()
diagnostic_enabled=0
checker_sha=""
if [[ -n "$PCMANFM_DIAGNOSTIC" ]]; then
  diagnostic_enabled=1
  diagnostic_args=(-v "$PCMANFM_DIAGNOSTIC:/pcmanfm-diagnostic:ro")
  checker_sha="$(sha256sum "$PCMANFM_DIAGNOSTIC/guest-pcmanfm-diagnostic.py")"
  checker_sha="${checker_sha%% *}"
fi
"$engine" run --rm "${diagnostic_args[@]}" "${name_args[@]}"''')
    value=replace(value,'  -e OUT=/out -e MODE=',
        '  -e PCMANFM_DIAGNOSTIC="$diagnostic_enabled" -e PCMANFM_CHECKER_SHA="$checker_sha" -e OUT=/out -e MODE=')
    return value


def initial_workflow(base):
    value=replace(base,'    inputs:\n','''    inputs:
      same_iso_pcmanfm_diagnostic:
        description: One bounded fixed-image native PCManFM input diagnostic only (no build/install/release)
        type: boolean
        default: false
''')
    value=replace(value,'(!inputs.same_iso_recovery && !inputs.same_iso_native_smoke)',
                  '(!inputs.same_iso_recovery && !inputs.same_iso_native_smoke && !inputs.same_iso_pcmanfm_diagnostic)')
    value=value.replace('inputs.same_iso_recovery && !inputs.same_iso_native_smoke }}',
                        'inputs.same_iso_recovery && !inputs.same_iso_native_smoke && !inputs.same_iso_pcmanfm_diagnostic }}')
    value=replace(value,"github.event_name == 'workflow_dispatch' && inputs.same_iso_native_smoke }}",
                  "github.event_name == 'workflow_dispatch' && inputs.same_iso_native_smoke && !inputs.same_iso_pcmanfm_diagnostic }}")
    job='''
  same-iso-pcmanfm-diagnostic:
    if: ${{ github.event_name == 'workflow_dispatch' && inputs.same_iso_pcmanfm_diagnostic }}
    runs-on: ubuntu-24.04
    timeout-minutes: 45
    permissions:
      contents: read
      actions: read
    env:
      PCMANFM_DIAGNOSTIC_MODE: "true"
      RECOVERY_MODE: ${{ inputs.same_iso_recovery && 'true' || 'false' }}
      NATIVE_SMOKE_MODE: ${{ inputs.same_iso_native_smoke && 'true' || 'false' }}
      RELEASE_REQUESTED: ${{ inputs.release && 'true' || 'false' }}
      CONTAINER_ENGINE: docker
      NIX_REQUESTED: ${{ inputs.nix_acceptance && 'true' || 'false' }}
      PERFORMANCE_REQUESTED: ${{ inputs.performance_acceptance && 'true' || 'false' }}
      BOOT_TEST_REQUESTED: ${{ inputs.boot_test && 'true' || 'false' }}
    steps:
      - name: Checkout immutable candidate source
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          ref: fe4742c8b9414c45f0bcbb0a4191f116383c60d1
          path: candidate-source
          persist-credentials: false
          sparse-checkout: |
            tools
            profiles/ci
      - name: Checkout original clean recovery execution
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          ref: ae55fbc9d48cec5ecc786cf61994ed986296d1bb
          path: recovery-source
          persist-credentials: false
          sparse-checkout: |
            tools
            .github/workflows
      - name: Checkout separate reviewed diagnostic execution
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          ref: ${{ github.sha }}
          fetch-depth: 0
          path: diagnostic-source
          persist-credentials: false
          sparse-checkout: |
            tools
            .github/workflows
      - name: Declare unused diagnostic paths
        shell: bash
        run: |
          set -euo pipefail
          diagnostic_root="$RUNNER_TEMP/arctic-pcmanfm-diagnostic-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
          test ! -e "$diagnostic_root"
          mkdir "$diagnostic_root"
          echo "DIAGNOSTIC_ROOT=$diagnostic_root" >> "$GITHUB_ENV"
      - name: Verify fixed metadata and exact clean diagnostic source pins
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          python3 diagnostic-source/tools/pcmanfm-diagnostic/diagnostic-runner.py preflight \\
            --source "$GITHUB_WORKSPACE/candidate-source" --bundle "$GITHUB_WORKSPACE/diagnostic-source/tools/pcmanfm-diagnostic" \\
            --recovery-bundle "$GITHUB_WORKSPACE/recovery-source/tools/same-iso-recovery" \\
            --inputs "$DIAGNOSTIC_ROOT/inputs" --evidence "$DIAGNOSTIC_ROOT/evidence"
      - name: Download fixed original ISO artifact only
        uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093
        with:
          repository: yuvalkolodkingal/Arctic-Linux
          run-id: 37507582946
          artifact-ids: 11434226349
          github-token: ${{ github.token }}
          merge-multiple: true
          path: ${{ env.DIAGNOSTIC_ROOT }}/inputs
      - name: Verify exact actual ISO bytes before any VM
        run: |
          python3 diagnostic-source/tools/pcmanfm-diagnostic/diagnostic-runner.py verify \\
            --source "$GITHUB_WORKSPACE/candidate-source" --bundle "$GITHUB_WORKSPACE/diagnostic-source/tools/pcmanfm-diagnostic" \\
            --recovery-bundle "$GITHUB_WORKSPACE/recovery-source/tools/same-iso-recovery" \\
            --inputs "$DIAGNOSTIC_ROOT/inputs" --evidence "$DIAGNOSTIC_ROOT/evidence"
      - name: One fresh live-only bounded PCManFM diagnostic VM
        run: |
          python3 diagnostic-source/tools/pcmanfm-diagnostic/diagnostic-runner.py run \\
            --source "$GITHUB_WORKSPACE/candidate-source" --bundle "$GITHUB_WORKSPACE/diagnostic-source/tools/pcmanfm-diagnostic" \\
            --recovery-bundle "$GITHUB_WORKSPACE/recovery-source/tools/same-iso-recovery" \\
            --inputs "$DIAGNOSTIC_ROOT/inputs" --evidence "$DIAGNOSTIC_ROOT/evidence"
      - name: Preserve new diagnostic evidence including failures
        if: ${{ always() && env.DIAGNOSTIC_ROOT != '' }}
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          name: pcmanfm-diagnostic-37507582946-${{ github.run_id }}-${{ github.run_attempt }}
          path: ${{ env.DIAGNOSTIC_ROOT }}/evidence/
          if-no-files-found: warn
          retention-days: 14
'''
    return value+job


def harness(base):
    value=replace(base,'security-collector.py runtime-pins.json','security-collector.py bulk-channel.py gtk-physical.py runtime-pins.json')
    value=replace(value,"    controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)\n    try:\n        controller.run(vm, out, menu_seen, os.environ['PCMANFM_CHECKER_SHA'])\n    finally:\n        vm.quit()", """    bulk_owns_cleanup = False
    try:
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        bspec = importlib.util.spec_from_file_location('diagnostic_bulk_channel', '/pcmanfm-diagnostic/bulk-channel.py')
        bulk_module = importlib.util.module_from_spec(bspec); bspec.loader.exec_module(bulk_module)
        bulk_owns_cleanup = True # Only a successful import transfers cleanup ownership.
        bulk_module.run_owned(vm, out,
            lambda bulk: controller.run_v3(vm, out, menu_seen, os.environ['PCMANFM_CHECKER_SHA'], bulk),
            max(0, min(900, vmtest.T0+timeout-time.time())))
    finally:
        if not bulk_owns_cleanup: vm.quit()""")
    value=replace(value,'-serial "file:$OUT/serial.log" -monitor none -no-reboot\n        -drive file=/tmp/target.qcow2',
        '-serial "file:$OUT/serial.log" -monitor none -no-reboot\n'
        '        -chardev "socket,id=arctic_bulk,path=$OUT/bulk.sock,server=on,wait=off"\n'
        '        -device virtio-serial-pci,id=arctic_bulk_bus\n'
        '        -device virtserialport,bus=arctic_bulk_bus.0,chardev=arctic_bulk,name=org.arctic.diagnostic.bulk\n'
        '        -drive file=/tmp/target.qcow2')
    return value


def workflow(base):
    value=replace(base,'One bounded native PCManFM successor diagnostic only (same image; no build/install/release)',
        'One finite GTK/keymap and separate virtio-data diagnostic only (same image; no build/install/release)')
    value=replace(value,'One fresh live-only reviewed PCManFM successor diagnostic VM',
        'One fresh live-only reviewed GTK keymap and bounded virtio-data diagnostic VM')
    value=replace(value,'name: pcmanfm-diagnostic-v2-37507582946-${{ github.run_id }}',
        'name: pcmanfm-diagnostic-v3-37507582946-${{ github.run_id }}')
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repository',type=Path,required=True)
    args=parser.parse_args()
    def gitfile(path):return subprocess.check_output(['git','-C',str(args.repository),'show',BASE+':'+path])
    base_iso=gitfile('tools/test-iso.sh').decode();base_workflow=gitfile('.github/workflows/iso.yml').decode()
    if (HERE/'base-test-iso.sh').read_text()!=base_iso or (HERE/'base-iso.yml').read_text()!=base_workflow:
        raise RuntimeError('base snapshots differ from immutable Git objects')
    guest=HERE/'guest-pcmanfm-diagnostic.py'
    guest.write_text(re.sub(r"SECURITY_SHA = '[^']+'", "SECURITY_SHA = '"+hashlib.sha256((HERE/'security-collector.py').read_bytes()).hexdigest()+"'", guest.read_text()))
    for constant,name in [('BULK_SHA','bulk-channel.py'),('GTK_PHYSICAL_SHA','gtk-physical.py')]:
        value=hashlib.sha256((HERE/name).read_bytes()).hexdigest()
        guest.write_text(re.sub(constant+r" = '[^']+'",constant+" = '"+value+"'",guest.read_text()))
    tree=HERE/'execution-tree' 
    if tree.exists():shutil.rmtree(tree) # Only this generator's own directory, never caller paths or a Git checkout.
    (tree/'tools/pcmanfm-diagnostic').mkdir(parents=True)
    for name in ('tools/lib/container.sh','tools/lib/vmtest.py','tools/native-functional-v4/native-runner-v4.py',
                 'tools/same-iso-recovery/vm-only-recovery-v2.py'):
        target=tree/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(gitfile(name))
    old=json.loads(gitfile('tools/native-functional-v4/execution-pins-v4.json'))
    frozen={path:digest for path,digest in old['files'].items() if path not in ('.github/workflows/iso.yml','tools/test-iso.sh')}
    for path,digest in frozen.items():
        data=gitfile(path)
        if hashlib.sha256(data).hexdigest()!=digest:raise RuntimeError('old source pin mismatch: '+path)
        target=tree/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    (HERE/'frozen-base-pins.json').write_text(json.dumps(dict(base=BASE,allowed_changed_existing=['.github/workflows/iso.yml','tools/test-iso.sh'],files=frozen),indent=2)+'\n')
    runtime={name:hashlib.sha256((HERE/source).read_bytes()).hexdigest() for name,source in
             [('guest-check.py','guest-pcmanfm-diagnostic.py'),('native_smoke.py','native_smoke.py'),('native-launcher.py','native-launcher.py'),
              ('atspi-snapshot.py','atspi-snapshot.py'),('gtk-entry-control.py','gtk-entry-control.py'),('bounded-launch.py','bounded-launch.py'),
              ('bootstrap-diagnostic.sh','bootstrap-diagnostic.sh'),('original-h264-aac-1s.mp4','original-h264-aac-1s.mp4'),
              ('codec-fixture-manifest.json','codec-fixture-manifest.json'),('security-collector.py','security-collector.py'),
              ('bulk-channel.py','bulk-channel.py'),('gtk-physical.py','gtk-physical.py')]}
    runsh=b'#!/bin/bash\nset -euo pipefail\nexec python3 /run/t/guest-check.py\n'
    runtime['run.sh']=hashlib.sha256(runsh).hexdigest()
    (HERE/'runtime-pins.json').write_text(json.dumps(runtime,indent=2,sort_keys=True)+'\n')
    iso=harness(base_iso);registered=workflow(base_workflow)
    (HERE/'registered-iso-diagnostic.yml').write_text(registered)
    for path,value in [('tools/test-iso.sh',iso),('.github/workflows/iso.yml',registered)]:
        target=tree/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value)
        if path=='tools/test-iso.sh':target.chmod(0o755)
        (HERE/(Path(path).name+'.patch')).write_text(''.join(difflib.unified_diff(
            (base_iso if path=='tools/test-iso.sh' else base_workflow).splitlines(True),value.splitlines(True),
            fromfile='a/'+path,tofile='b/'+path)))
    spec=importlib.util.spec_from_file_location('diagnostic_source_manifest',HERE/'diagnostic-runner.py')
    R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
    for name in R.BUNDLE_FILES:shutil.copyfile(HERE/name,tree/'tools/pcmanfm-diagnostic'/name)
    files={path:hashlib.sha256((tree/path).read_bytes()).hexdigest() for path in sorted(R.EXECUTION_FILES)}
    manifest=dict(schema='arctic-pcmanfm-execution-v1',execution_base=BASE,recovery_base=R.RECOVERY_BASE,
                  candidate_source='fe4742c8b9414c45f0bcbb0a4191f116383c60d1',files=files,
                  modes={path:('100755' if path=='tools/test-iso.sh' else '100644') for path in files},
                  self_excluded='tools/pcmanfm-diagnostic/execution-pins.json')
    (HERE/'execution-pins.json').write_text(json.dumps(manifest,indent=2)+'\n')
    shutil.copyfile(HERE/'execution-pins.json',tree/'tools/pcmanfm-diagnostic/execution-pins.json')
    print(json.dumps(dict(status='prepared-source-only',files=len(files),runtime_files=len(runtime),runtime=False,
                         manifest_sha256=hashlib.sha256((HERE/'execution-pins.json').read_bytes()).hexdigest())))


if __name__=='__main__':main()
