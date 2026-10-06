#!/usr/bin/env python3
"""Reproduce an audit-only ae55-based harness patch. No Git/CI/VM mutations."""
import argparse
import difflib
import hashlib
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BASE = 'ae55fbc9d48cec5ecc786cf61994ed986296d1bb'
BASE_SHA = '9beb039d69dad07176e00a8e890c7e099631ff68175235a83be8b6394f63434f'
WORKFLOW_SHA = '5b0c1493333288acb43d7baaecb19ae40c662189d9ff0a591ce183a04871d2dd'
SAFE_JOB = r'''
  safe-visual-diagnostic:
    if: ${{ github.event_name == 'workflow_dispatch' && inputs.safe_visual_diagnostic }}
    runs-on: ubuntu-latest
    timeout-minutes: 55
    permissions:
      contents: read
      actions: read
    env:
      SAFE_DIAGNOSTIC_MODE: ${{ inputs.safe_visual_diagnostic && 'true' || 'false' }}
      RECOVERY_MODE: ${{ inputs.same_iso_recovery && 'true' || 'false' }}
      RELEASE_REQUESTED: ${{ inputs.release && 'true' || 'false' }}
      NATIVE_SMOKE_MODE: 'false'
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
      - name: Checkout unchanged frozen v2 verification source
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          ref: ae55fbc9d48cec5ecc786cf61994ed986296d1bb
          path: frozen-recovery-source
          persist-credentials: false
          sparse-checkout: |
            tools
            .github/workflows
      - name: Checkout separately reviewed Safe execution source
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          ref: ${{ github.sha }}
          path: safe-execution-source
          persist-credentials: false
          # The fail-closed source guard verifies ae55 ancestry locally.
          fetch-depth: 0
          sparse-checkout: |
            tools
            .github/workflows
      - name: Declare unused isolated diagnostic paths
        shell: bash
        run: |
          set -euo pipefail
          safe_root="$RUNNER_TEMP/arctic-safe-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
          test ! -e "$safe_root"
          mkdir "$safe_root"
          echo "SAFE_ROOT=$safe_root" >> "$GITHUB_ENV"
      - name: Fail closed on mode, original result, frozen source and artifact metadata
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          python3 safe-execution-source/tools/safe-visual-diagnostic/safe-runner-v1.py preflight \
            --source "$GITHUB_WORKSPACE/candidate-source" \
            --recovery-bundle "$GITHUB_WORKSPACE/frozen-recovery-source/tools/same-iso-recovery" \
            --bundle "$GITHUB_WORKSPACE/safe-execution-source/tools/safe-visual-diagnostic" \
            --inputs "$SAFE_ROOT/inputs" --evidence "$SAFE_ROOT/evidence"
      - name: Download exact existing candidate artifact
        uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093
        with:
          repository: yuvalkolodkingal/Arctic-Linux
          run-id: 37507582946
          artifact-ids: 11434226349
          github-token: ${{ github.token }}
          merge-multiple: true
          path: ${{ env.SAFE_ROOT }}/inputs
      - name: Verify actual immutable ISO bytes before any VM
        run: |
          python3 safe-execution-source/tools/safe-visual-diagnostic/safe-runner-v1.py verify \
            --source "$GITHUB_WORKSPACE/candidate-source" \
            --recovery-bundle "$GITHUB_WORKSPACE/frozen-recovery-source/tools/same-iso-recovery" \
            --bundle "$GITHUB_WORKSPACE/safe-execution-source/tools/safe-visual-diagnostic" \
            --inputs "$SAFE_ROOT/inputs" --evidence "$SAFE_ROOT/evidence"
      - name: One fresh passive and separated-input Safe diagnosis
        run: |
          python3 safe-execution-source/tools/safe-visual-diagnostic/safe-runner-v1.py run \
            --source "$GITHUB_WORKSPACE/candidate-source" \
            --recovery-bundle "$GITHUB_WORKSPACE/frozen-recovery-source/tools/same-iso-recovery" \
            --bundle "$GITHUB_WORKSPACE/safe-execution-source/tools/safe-visual-diagnostic" \
            --inputs "$SAFE_ROOT/inputs" --evidence "$SAFE_ROOT/evidence"
      - name: Preserve new diagnostic evidence including failure
        if: ${{ always() && env.SAFE_ROOT != '' }}
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          name: safe-diagnostic-37507582946-${{ github.run_id }}-${{ github.run_attempt }}
          path: ${{ env.SAFE_ROOT }}/evidence/
          if-no-files-found: warn
          retention-days: 14
'''



def replace(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after, 1)


def harness(base):
    text = replace(base, 'COLLECT=0\n', 'COLLECT=0\nSAFE_DIAGNOSTIC=""  # default-off, no product setting change\n')
    text = replace(text, '    --collect) COLLECT=1; shift ;;',
                   '    --collect) COLLECT=1; shift ;;\n    --safe-diagnostic) SAFE_DIAGNOSTIC="$2"; shift 2 ;;')
    text = replace(text, '[[ -f "$ISO" ]] || arctic_die', '''if [[ -n "$SAFE_DIAGNOSTIC" ]]; then
  [[ "$FIRMWARE" == uefi && "$MODE" == safe && "$KVM" == 1 && "$SECUREBOOT" == 0 && "$COLLECT" == 0
     && "$TIMEOUT" == 600 && "$INTERVAL" == 60 && "$MEMORY" == 4096 && "$SMP" == 2 && "$VGA" == virtio ]] \\
    || arctic_die "Safe diagnostic requires the fixed isolated Safe/KVM/600s/2CPU/4GiB settings"
  [[ -c /dev/kvm && -f "$SAFE_DIAGNOSTIC/guest-safe-collector-v1.py" && -f "$SAFE_DIAGNOSTIC/safe-driver-v1.py"
     && -f "$SAFE_DIAGNOSTIC/bootstrap-safe-v1.sh" ]] || arctic_die "Safe diagnostic prerequisites absent"
  [[ "$APPEND" == " console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1" ]] \\
    || arctic_die "Safe diagnostic requires the exact debug arguments"
fi
[[ -f "$ISO" ]] || arctic_die''')
    text = replace(text, 'rm -rf "$OUT"; mkdir -p "$OUT"', '''if [[ -n "$SAFE_DIAGNOSTIC" ]]; then
  [[ ! -e "$OUT" ]] || arctic_die "Safe diagnostic output must be unused"
  mkdir -p "$OUT"
else
  rm -rf "$OUT"; mkdir -p "$OUT"
fi''')
    text = replace(text, 'collect = os.environ.get("COLLECT") == "1"',
                   'collect = os.environ.get("COLLECT") == "1"\nsafe_diagnostic = os.environ.get("SAFE_DIAGNOSTIC") == "1"')
    text = replace(text, '        keys("ctrl-x")',
                   '        if safe_diagnostic: safe_entry_origin = time.monotonic()\n        keys("ctrl-x")')
    text = replace(text, '        keys("ret")\n        log(f"selected',
                   '        if safe_diagnostic: safe_entry_origin = time.monotonic()\n        keys("ret")\n        log(f"selected')
    text = replace(text, '# 2. Splash and boot:', '''if safe_diagnostic:
    sys.path.insert(0, "/safe-diagnostic")
    import importlib.util
    spec = importlib.util.spec_from_file_location('safe_driver_v1', '/safe-diagnostic/safe-driver-v1.py')
    safe_driver_v1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(safe_driver_v1)
    try:
        safe_driver_v1.run(vm, out, safe_driver_v1.qemu_process_origin(vm.proc.pid),
                           safe_entry_origin if menu_seen else None, menu_seen)
    finally:
        vm.quit()
    sys.exit(0)

# 2. Splash and boot:''')
    text = replace(text, 'dnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"',
                   'if [ "$SAFE_DIAGNOSTIC" = 1 ]; then pkgs+=(xorriso); fi\ndnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"')
    text = replace(text, 'python3 -c "$DRIVER" "${args[@]}"', '''if [ "$SAFE_DIAGNOSTIC" = 1 ]; then
  mkdir /tmp/safe-data
  cp /safe-diagnostic/guest-safe-collector-v1.py /tmp/safe-data/
  xorriso -as mkisofs -quiet -V ARCTICSAFE -J -R -G /safe-diagnostic/bootstrap-safe-v1.sh \\
    -o /tmp/safe-data.iso /tmp/safe-data
  args+=(-drive file=/tmp/safe-data.iso,media=cdrom,readonly=on,if=none,id=safedata -device ide-cd,drive=safedata)
  {
    qemu-system-x86_64 --version
    rpm -q "${pkgs[@]}"
    sha256sum "$(command -v qemu-system-x86_64)" "$code" "$vars" /tmp/safe-data.iso \\
      /safe-diagnostic/guest-safe-collector-v1.py /safe-diagnostic/safe-driver-v1.py
    printf '%s\\n' 'Additional read-only diagnostic data CD; actual new tool hashes, not baseline parity proof.'
  } > "$OUT/safe-toolchain.txt"
fi
python3 -c "$DRIVER" "${args[@]}"''')
    text = replace(text, '"$engine" run --rm "${name_args[@]}"', '''safe_args=()
safe_enabled=0
if [[ -n "$SAFE_DIAGNOSTIC" ]]; then
  safe_enabled=1
  safe_args=(-v "$SAFE_DIAGNOSTIC:/safe-diagnostic:ro")
fi
"$engine" run --rm "${safe_args[@]}" "${name_args[@]}"''')
    text = replace(text, '  -e OUT=/out -e MODE=', '  -e SAFE_DIAGNOSTIC="$safe_enabled" -e OUT=/out -e MODE=')
    return text


def workflow(base):
    text = replace(base, '    inputs:\n      same_iso_recovery:', '    inputs:\n      safe_visual_diagnostic:\n        description: Diagnose fixed candidate Safe graphics only; no build, install, release or acceptance pass\n        type: boolean\n        default: false\n      same_iso_recovery:')
    text = replace(text, "if: ${{ github.event_name != 'workflow_dispatch' || !inputs.same_iso_recovery }}", "if: ${{ github.event_name != 'workflow_dispatch' || (!inputs.same_iso_recovery && !inputs.safe_visual_diagnostic) }}")
    old = "if: ${{ github.event_name == 'workflow_dispatch' && inputs.same_iso_recovery }}"
    assert text.count(old) == 2
    text = text.replace(old, "if: ${{ github.event_name == 'workflow_dispatch' && inputs.same_iso_recovery && !inputs.safe_visual_diagnostic }}")
    return text + SAFE_JOB


def base_sources():
    result = []
    for fixture, relative, expected in (('base-test-iso.sh', 'tools/test-iso.sh', BASE_SHA),
                                       ('base-iso.yml', '.github/workflows/iso.yml', WORKFLOW_SHA)):
        path = HERE / fixture
        value = path.read_bytes() if path.exists() else subprocess.check_output(
            ['git', '-C', str(HERE.parents[1]), 'show', BASE + ':' + relative], timeout=30)
        assert hashlib.sha256(value).hexdigest() == expected, 'Pinned base source differs: ' + relative
        result.append(value.decode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base_test, base_workflow = base_sources()
    for base, output, filename, target, patchname in (
        (base_test, harness(base_test), 'prepared-test-iso.sh', 'tools/test-iso.sh', 'test-iso-safe-diagnostic-v1.patch'),
        (base_workflow, workflow(base_workflow), 'registered-iso-safe-v1.yml', '.github/workflows/iso.yml', 'iso-safe-diagnostic-v1.patch')):
        (args.out / filename).write_text(output)
        value = ''.join(difflib.unified_diff(base.splitlines(True), output.splitlines(True),
                        fromfile='a/' + target, tofile='b/' + target))
        (args.out / patchname).write_text(value)


if __name__ == '__main__':
    main()
